"""Core document-extraction types, validation, and orchestration."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from src.utils.cache_manager import CacheManager
from src.utils.config import (
    DOCUMENT_EXTRACTOR_CHAIN,
    DOCUMENT_EXTRACT_OCR_MODE,
    DOCUMENT_EXTRACT_REMOTE_FALLBACK,
    DOCUMENT_EXTRACT_TIMEOUT,
    ENABLE_CACHE,
)


MIN_VALID_PAPER_CONTENT_CHARS = 2000
MIN_VALID_PAPER_CONTENT_ALPHA_CHARS = 800
INVALID_PAPER_CONTENT_PATTERNS = (
    "upstream connect error",
    "error code:",
    "bad gateway",
    "too many requests",
    "rate limit exceeded",
    "access denied",
    "request failed",
    "server error",
    "captcha",
)
KNOWN_PROVIDER_NAMES = ("docling", "pymupdf4llm", "jina")
DEFAULT_PROVIDER_CHAIN = ("docling", "pymupdf4llm", "jina")
SOURCE_TYPE_PDF = "pdf"
SOURCE_TYPE_HTML = "html"
SOURCE_TYPE_DOCX = "docx"
SOURCE_TYPE_PPTX = "pptx"
SOURCE_TYPE_XLSX = "xlsx"
SOURCE_TYPE_IMAGE = "image"
SOURCE_TYPE_UNKNOWN = "unknown"
DOCUMENT_CACHE_SCHEMA_VERSION = "document-extraction-v1"


class DocumentExtractionError(RuntimeError):
    """Raised when no extractor can produce valid document content."""


@dataclass
class ExtractionResult:
    """A normalized representation for extracted document content."""

    markdown: str
    plain_text: str
    provider: str
    source_type: str
    ocr_used: bool = False
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def content(self) -> str:
        return self.markdown or self.plain_text

    def to_cache_payload(self, normalized_source: str, ocr_mode: str, cache_version: str) -> Dict[str, Any]:
        return {
            "normalized_source": normalized_source,
            "markdown": self.markdown,
            "plain_text": self.plain_text,
            "provider": self.provider,
            "source_type": self.source_type,
            "ocr_used": self.ocr_used,
            "ocr_mode": ocr_mode,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "cache_version": cache_version,
            "cache_schema_version": DOCUMENT_CACHE_SCHEMA_VERSION,
        }

    @classmethod
    def from_cache_payload(cls, payload: Dict[str, Any]) -> "ExtractionResult":
        return cls(
            markdown=payload.get("markdown", "") or payload.get("plain_text", ""),
            plain_text=payload.get("plain_text", "") or payload.get("markdown", ""),
            provider=payload.get("provider", ""),
            source_type=payload.get("source_type", SOURCE_TYPE_UNKNOWN),
            ocr_used=bool(payload.get("ocr_used", False)),
            warnings=list(payload.get("warnings") or []),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class ProviderStatus:
    """User-facing provider availability summary."""

    name: str
    available: bool
    detail: str
    cache_version: str


@dataclass
class ExtractionContext:
    """Resolved source information shared across provider attempts."""

    original_source: str
    normalized_source: str
    source_type: str
    local_path: Optional[str] = None

    @property
    def is_remote(self) -> bool:
        return self.normalized_source.startswith(("http://", "https://"))


def normalize_whitespace(text: Optional[str]) -> str:
    """Collapse repeated whitespace for lightweight content validation."""
    return re.sub(r"\s+", " ", text or "").strip()


def get_paper_content_issue(content: Optional[str]) -> Optional[str]:
    """Return a human-readable issue when extracted paper content looks invalid."""
    normalized = normalize_whitespace(content)
    if not normalized:
        return "内容为空"

    lowered = normalized.lower()
    for pattern in INVALID_PAPER_CONTENT_PATTERNS:
        if pattern in lowered:
            return f"命中错误页特征: {pattern}"

    if len(normalized) < MIN_VALID_PAPER_CONTENT_CHARS:
        return f"内容过短 ({len(normalized)} chars)"

    alpha_chars = sum(ch.isalpha() for ch in normalized)
    if alpha_chars < MIN_VALID_PAPER_CONTENT_ALPHA_CHARS:
        return f"有效字母过少 ({alpha_chars})"

    return None


def ensure_valid_extraction_content(content: Optional[str], source: str) -> str:
    """Validate extracted content and raise a retryable error when invalid."""
    issue = get_paper_content_issue(content)
    if issue:
        raise ValueError(f"{source} 返回的论文内容无效: {issue}")
    return content or ""


def normalize_arxiv_pdf_url(arxiv_url: str) -> str:
    """Normalize a mixed arXiv link or id into a canonical PDF URL."""
    normalized = (arxiv_url or "").strip()
    if not normalized:
        raise ValueError("arXiv 链接不能为空")

    if normalized.startswith("/arxiv/"):
        arxiv_id = normalized.replace("/arxiv/", "", 1).strip()
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    if normalized.startswith("http://"):
        normalized = "https://" + normalized[len("http://"):]

    if normalized.startswith("https://arxiv.org/abs/"):
        normalized = normalized.replace("/abs/", "/pdf/", 1)
    elif normalized.startswith("https://arxiv.org/pdf/"):
        pass
    elif re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", normalized):
        normalized = f"https://arxiv.org/pdf/{normalized}.pdf"
    else:
        raise ValueError(f"无法识别的 arXiv 链接格式: {arxiv_url}")

    if not normalized.endswith(".pdf"):
        normalized += ".pdf"
    return normalized


def is_arxiv_reference(source: str) -> bool:
    """Return whether the source is an arXiv id or arXiv URL/path."""
    normalized = (source or "").strip()
    return bool(
        normalized.startswith("/arxiv/")
        or normalized.startswith("http://arxiv.org/")
        or normalized.startswith("https://arxiv.org/")
        or re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", normalized)
    )


def detect_source_type(source: str) -> str:
    """Infer the source type from a URL, arXiv id, or local path."""
    normalized = (source or "").strip().lower()
    if not normalized:
        return SOURCE_TYPE_UNKNOWN
    if is_arxiv_reference(normalized):
        return SOURCE_TYPE_PDF
    if normalized.endswith(".pdf"):
        return SOURCE_TYPE_PDF
    if normalized.endswith((".html", ".htm")):
        return SOURCE_TYPE_HTML
    if normalized.endswith(".docx"):
        return SOURCE_TYPE_DOCX
    if normalized.endswith(".pptx"):
        return SOURCE_TYPE_PPTX
    if normalized.endswith(".xlsx"):
        return SOURCE_TYPE_XLSX
    if normalized.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")):
        return SOURCE_TYPE_IMAGE
    if normalized.startswith(("http://", "https://")):
        return SOURCE_TYPE_HTML
    return SOURCE_TYPE_UNKNOWN


def normalize_document_source(source: str, source_type: Optional[str] = None) -> ExtractionContext:
    """Resolve a source into a normalized URL/path and a stable source type."""
    detected_type = source_type or detect_source_type(source)
    normalized = (source or "").strip()

    if detected_type == SOURCE_TYPE_PDF and is_arxiv_reference(normalized):
        normalized = normalize_arxiv_pdf_url(normalized)
    elif normalized.startswith("http://") and detected_type in {
        SOURCE_TYPE_PDF,
        SOURCE_TYPE_HTML,
        SOURCE_TYPE_DOCX,
        SOURCE_TYPE_PPTX,
        SOURCE_TYPE_XLSX,
        SOURCE_TYPE_IMAGE,
    }:
        normalized = "https://" + normalized[len("http://"):]
    elif not normalized.startswith(("http://", "https://")):
        normalized = os.path.abspath(normalized)

    local_path = normalized if os.path.exists(normalized) else None
    return ExtractionContext(
        original_source=source,
        normalized_source=normalized,
        source_type=detected_type,
        local_path=local_path,
    )


def get_file_suffix_for_source(source_type: str, normalized_source: str) -> str:
    """Pick a stable file suffix for temporary downloads."""
    extension_map = {
        SOURCE_TYPE_PDF: ".pdf",
        SOURCE_TYPE_HTML: ".html",
        SOURCE_TYPE_DOCX: ".docx",
        SOURCE_TYPE_PPTX: ".pptx",
        SOURCE_TYPE_XLSX: ".xlsx",
        SOURCE_TYPE_IMAGE: ".png",
    }
    suffix = extension_map.get(source_type)
    if suffix:
        return suffix

    _, ext = os.path.splitext(normalized_source)
    return ext or ".bin"


def resolve_provider_chain(chain: Optional[str] = None) -> List[str]:
    """Return a clean provider chain using the configured order."""
    configured = chain or DOCUMENT_EXTRACTOR_CHAIN
    names = []
    seen = set()

    for item in configured.split(","):
        name = item.strip().lower()
        if not name or name in seen or name not in KNOWN_PROVIDER_NAMES:
            continue
        seen.add(name)
        names.append(name)

    if not names:
        return list(DEFAULT_PROVIDER_CHAIN)
    return names


def build_document_cache_key(
    normalized_source: str,
    provider_name: str,
    source_type: str,
    ocr_mode: str,
    cache_version: str,
) -> str:
    """Build a stable cache identity for extracted document content."""
    return ":".join(
        [
            DOCUMENT_CACHE_SCHEMA_VERSION,
            normalized_source,
            provider_name,
            source_type,
            ocr_mode,
            cache_version,
        ]
    )


class ExtractionManager:
    """Try multiple extractors in order and cache normalized results."""

    def __init__(
        self,
        cache_manager: Optional[CacheManager] = None,
        chain: Optional[str] = None,
        ocr_mode: Optional[str] = None,
        remote_fallback: Optional[bool] = None,
        request_timeout: Optional[int] = None,
    ):
        self.cache_manager = cache_manager
        self.chain = resolve_provider_chain(chain)
        self.ocr_mode = (ocr_mode or DOCUMENT_EXTRACT_OCR_MODE or "auto").strip().lower()
        if self.ocr_mode not in {"auto", "disable", "force"}:
            self.ocr_mode = "auto"
        self.remote_fallback = (
            DOCUMENT_EXTRACT_REMOTE_FALLBACK if remote_fallback is None else bool(remote_fallback)
        )
        self.request_timeout = request_timeout or DOCUMENT_EXTRACT_TIMEOUT

    def get_cached_result(self, source: str, source_type: Optional[str] = None) -> Optional[ExtractionResult]:
        """Return the first valid cached result in provider-chain order."""
        context = normalize_document_source(source, source_type)
        for provider_name in self.chain:
            if provider_name == "jina" and not self.remote_fallback:
                continue
            provider = self._create_provider(provider_name)
            cache_key = build_document_cache_key(
                context.normalized_source,
                provider.name,
                context.source_type,
                self.ocr_mode,
                provider.cache_version,
            )
            cached_entry = self._get_cached_entry(cache_key)
            if not cached_entry:
                continue
            try:
                result = ExtractionResult.from_cache_payload(cached_entry["data"])
                ensure_valid_extraction_content(result.content, f"cached {provider.name} {source}")
                return result
            except Exception:
                continue
        return None

    def extract(self, source: str, source_type: Optional[str] = None) -> ExtractionResult:
        """Extract document content through the configured provider chain."""
        cached_result = self.get_cached_result(source, source_type=source_type)
        if cached_result:
            return cached_result

        context = normalize_document_source(source, source_type)
        attempt_errors: List[str] = []

        with tempfile.TemporaryDirectory(prefix="papertools-doc-") as temp_dir:
            for provider_name in self.chain:
                if provider_name == "jina" and not self.remote_fallback:
                    attempt_errors.append("jina: remote fallback disabled")
                    continue

                provider = self._create_provider(provider_name)
                status = provider.get_status()
                if not status.available:
                    attempt_errors.append(f"{provider.name}: {status.detail}")
                    continue

                if context.source_type not in provider.supported_source_types:
                    attempt_errors.append(
                        f"{provider.name}: unsupported source type {context.source_type}"
                    )
                    continue

                cache_key = build_document_cache_key(
                    context.normalized_source,
                    provider.name,
                    context.source_type,
                    self.ocr_mode,
                    provider.cache_version,
                )
                cached_entry = self._get_cached_entry(cache_key)
                if cached_entry:
                    try:
                        result = ExtractionResult.from_cache_payload(cached_entry["data"])
                        ensure_valid_extraction_content(result.content, f"cached {provider.name} {source}")
                        return result
                    except Exception:
                        pass

                try:
                    context_for_provider = self._prepare_context_for_provider(provider, context, temp_dir)
                    result = provider.extract(context_for_provider, ocr_mode=self.ocr_mode)
                    validated_content = ensure_valid_extraction_content(
                        result.content,
                        f"{provider.name} {source}",
                    )
                    if not result.markdown:
                        result.markdown = validated_content
                    if not result.plain_text:
                        result.plain_text = validated_content
                    self._set_cached_entry(
                        cache_key,
                        result.to_cache_payload(
                            normalized_source=context.normalized_source,
                            ocr_mode=self.ocr_mode,
                            cache_version=provider.cache_version,
                        ),
                    )
                    return result
                except Exception as exc:
                    attempt_errors.append(f"{provider.name}: {exc}")

        raise DocumentExtractionError(
            "所有文档提取 provider 均失败: " + " | ".join(attempt_errors or ["unknown error"])
        )

    def _prepare_context_for_provider(
        self,
        provider: Any,
        context: ExtractionContext,
        temp_dir: str,
    ) -> ExtractionContext:
        if context.local_path or not getattr(provider, "requires_local_path", False):
            return context
        if not context.is_remote:
            raise FileNotFoundError(f"本地文件不存在: {context.normalized_source}")

        suffix = get_file_suffix_for_source(context.source_type, context.normalized_source)
        local_path = os.path.join(temp_dir, f"{provider.name}{suffix}")

        response = requests.get(context.normalized_source, timeout=self.request_timeout)
        response.raise_for_status()
        with open(local_path, "wb") as handle:
            handle.write(response.content)

        return ExtractionContext(
            original_source=context.original_source,
            normalized_source=context.normalized_source,
            source_type=context.source_type,
            local_path=local_path,
        )

    def _get_cached_entry(self, cache_key: str) -> Optional[Dict[str, Any]]:
        if not self.cache_manager or not ENABLE_CACHE:
            return None
        return self.cache_manager.get_document_cache(cache_key)

    def _set_cached_entry(self, cache_key: str, payload: Dict[str, Any]) -> None:
        if not self.cache_manager or not ENABLE_CACHE:
            return
        self.cache_manager.set_document_cache(cache_key, payload)

    @staticmethod
    def _create_provider(provider_name: str):
        from src.document_extraction.providers import create_provider

        return create_provider(provider_name)


def get_document_content(
    source: str,
    *,
    cache_manager: Optional[CacheManager] = None,
    source_type: Optional[str] = None,
    chain: Optional[str] = None,
    ocr_mode: Optional[str] = None,
) -> str:
    """Backward-compatible helper returning the extracted markdown string."""
    manager = ExtractionManager(cache_manager=cache_manager, chain=chain, ocr_mode=ocr_mode)
    result = manager.extract(source, source_type=source_type)
    return result.content


def get_provider_statuses(provider_names: Optional[List[str]] = None) -> List[ProviderStatus]:
    """Return availability information for all known extraction providers."""
    from src.document_extraction.providers import create_provider

    names = provider_names or list(DEFAULT_PROVIDER_CHAIN)
    statuses = []
    for name in names:
        provider = create_provider(name)
        statuses.append(provider.get_status())
    return statuses
