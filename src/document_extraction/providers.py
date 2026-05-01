"""Provider implementations for document extraction."""

from __future__ import annotations

import threading
import time
import warnings
from importlib import util as importlib_util
from typing import Any, Dict, Iterable, Optional

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .*doesn't match a supported version!",
    category=Warning,
)

import requests

from src.document_extraction.core import (
    ExtractionContext,
    ExtractionResult,
    ProviderStatus,
    ensure_valid_extraction_content,
)
from src.utils.config import (
    JINA_API_TOKEN,
    JINA_BACKOFF_FACTOR,
    JINA_MAX_REQUESTS_PER_MINUTE,
    JINA_MAX_RETRIES,
    JINA_REQUEST_TIMEOUT,
)


def _module_available(module_name: str) -> bool:
    """Safely check whether a module can be imported."""
    try:
        return importlib_util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


class BaseDocumentExtractor:
    """Shared provider behavior."""

    name = ""
    cache_version = "impl-v1"
    supported_source_types: Iterable[str] = ()
    requires_local_path = False

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            available=True,
            detail="ready",
            cache_version=self.cache_version,
        )

    def extract(self, context: ExtractionContext, ocr_mode: str = "auto") -> ExtractionResult:
        raise NotImplementedError


class DoclingExtractor(BaseDocumentExtractor):
    name = "docling"
    cache_version = "impl-v1"
    supported_source_types = {"pdf", "html", "docx", "pptx", "xlsx", "image"}
    requires_local_path = True

    def get_status(self) -> ProviderStatus:
        available = _module_available("docling.document_converter")
        detail = "ready" if available else "install extra: papertools[extract-docling]"
        return ProviderStatus(
            name=self.name,
            available=available,
            detail=detail,
            cache_version=self.cache_version,
        )

    def extract(self, context: ExtractionContext, ocr_mode: str = "auto") -> ExtractionResult:
        from docling.document_converter import DocumentConverter

        if not context.local_path:
            raise FileNotFoundError("Docling requires a local file path")

        warnings = []
        if ocr_mode == "force":
            warnings.append("Docling OCR mode currently uses library defaults.")

        converter = DocumentConverter()
        conversion_result = converter.convert(context.local_path)
        document = getattr(conversion_result, "document", conversion_result)

        if not hasattr(document, "export_to_markdown"):
            raise RuntimeError("Docling result does not expose export_to_markdown()")

        markdown = ensure_valid_extraction_content(
            document.export_to_markdown(),
            f"{self.name} {context.original_source}",
        )
        return ExtractionResult(
            markdown=markdown,
            plain_text=markdown,
            provider=self.name,
            source_type=context.source_type,
            ocr_used=ocr_mode != "disable",
            warnings=warnings,
            metadata={"local_path": context.local_path},
        )


class PyMuPDF4LLMExtractor(BaseDocumentExtractor):
    name = "pymupdf4llm"
    cache_version = "impl-v1"
    supported_source_types = {"pdf"}
    requires_local_path = True

    def get_status(self) -> ProviderStatus:
        available = _module_available("pymupdf4llm")
        detail = "ready" if available else "install extra: papertools[extract-pymupdf]"
        return ProviderStatus(
            name=self.name,
            available=available,
            detail=detail,
            cache_version=self.cache_version,
        )

    def extract(self, context: ExtractionContext, ocr_mode: str = "auto") -> ExtractionResult:
        import pymupdf4llm

        if not context.local_path:
            raise FileNotFoundError("PyMuPDF4LLM requires a local PDF path")

        warnings = []
        kwargs: Dict[str, Any] = {}
        if ocr_mode != "disable":
            kwargs["use_ocr"] = True
        try:
            markdown = pymupdf4llm.to_markdown(context.local_path, **kwargs)
        except TypeError:
            markdown = pymupdf4llm.to_markdown(context.local_path)
            if kwargs:
                warnings.append("Installed pymupdf4llm does not expose OCR flags; used defaults.")

        markdown = ensure_valid_extraction_content(
            markdown,
            f"{self.name} {context.original_source}",
        )
        return ExtractionResult(
            markdown=markdown,
            plain_text=markdown,
            provider=self.name,
            source_type=context.source_type,
            ocr_used=ocr_mode != "disable",
            warnings=warnings,
            metadata={"local_path": context.local_path},
        )


class JinaRateLimiter:
    """Simple cross-thread pacing for remote Jina requests."""

    def __init__(self, max_requests_per_minute: int = JINA_MAX_REQUESTS_PER_MINUTE):
        self.max_requests_per_minute = max(1, int(max_requests_per_minute))
        self.min_interval = 60.0 / self.max_requests_per_minute
        self.last_request_time = 0.0
        self.lock = threading.Lock()

    def wait_if_needed(self) -> None:
        with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.min_interval:
                time.sleep(self.min_interval - time_since_last)
            self.last_request_time = time.time()


jina_rate_limiter = JinaRateLimiter()


class JinaExtractor(BaseDocumentExtractor):
    name = "jina"
    cache_version = "impl-v1"
    supported_source_types = {"pdf", "html", "docx", "pptx", "xlsx", "image"}
    requires_local_path = False

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            available=True,
            detail="remote fallback",
            cache_version=self.cache_version,
        )

    def extract(self, context: ExtractionContext, ocr_mode: str = "auto") -> ExtractionResult:
        if context.local_path and not context.normalized_source.startswith(("http://", "https://")):
            raise RuntimeError("Jina fallback only supports remote URLs")
        if not context.normalized_source.startswith(("http://", "https://")):
            raise RuntimeError("Jina fallback requires a remote URL")

        jina_url = f"https://r.jina.ai/{context.normalized_source}"
        headers = {"Authorization": f"Bearer {JINA_API_TOKEN}"} if JINA_API_TOKEN else None

        last_exception: Optional[Exception] = None
        for attempt in range(JINA_MAX_RETRIES):
            try:
                jina_rate_limiter.wait_if_needed()
                response = requests.get(jina_url, headers=headers, timeout=JINA_REQUEST_TIMEOUT)
                response.raise_for_status()
                content = ensure_valid_extraction_content(
                    response.content.decode("utf-8", errors="replace"),
                    f"{self.name} {context.original_source}",
                )
                return ExtractionResult(
                    markdown=content,
                    plain_text=content,
                    provider=self.name,
                    source_type=context.source_type,
                    ocr_used=False,
                    warnings=[],
                    metadata={"reader_url": jina_url},
                )
            except (requests.exceptions.RequestException, ValueError) as exc:
                last_exception = exc
                if attempt < JINA_MAX_RETRIES - 1:
                    time.sleep(JINA_BACKOFF_FACTOR ** attempt)
                else:
                    raise

        if last_exception:
            raise last_exception
        raise RuntimeError("Jina extraction failed without an exception")


PROVIDER_REGISTRY = {
    "docling": DoclingExtractor,
    "pymupdf4llm": PyMuPDF4LLMExtractor,
    "jina": JinaExtractor,
}


def create_provider(name: str) -> BaseDocumentExtractor:
    """Instantiate a provider by registry name."""
    try:
        provider_cls = PROVIDER_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported document extractor provider: {name}") from exc
    return provider_cls()
