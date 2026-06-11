"""Tests for the unified document extraction layer."""

from __future__ import annotations

from dataclasses import dataclass

from src.document_extraction import (
    ExtractionManager,
    ExtractionResult,
    build_document_cache_key,
    get_paper_content_issue,
)
from src.utils.cache_manager import CacheManager


@dataclass
class FakeProviderStatus:
    name: str
    available: bool
    detail: str
    cache_version: str


class FakeProvider:
    """Simple provider double for ExtractionManager tests."""

    def __init__(
        self,
        name,
        *,
        available=True,
        should_fail=False,
        requires_local_path=False,
        content=None,
    ):
        self.name = name
        self.available = available
        self.should_fail = should_fail
        self.requires_local_path = requires_local_path
        self.content = content
        self.cache_version = "impl-test"
        self.supported_source_types = {"pdf"}
        self.call_count = 0

    def get_status(self):
        return FakeProviderStatus(
            name=self.name,
            available=self.available,
            detail="ready" if self.available else "missing",
            cache_version=self.cache_version,
        )

    def extract(self, context, ocr_mode="auto"):
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError(f"{self.name} failed")
        assert context.source_type == "pdf"
        if self.requires_local_path:
            assert context.local_path
        content = self.content or ("Introduction " * 220) + ("Method " * 220)
        return ExtractionResult(
            markdown=content,
            plain_text=content,
            provider=self.name,
            source_type=context.source_type,
            ocr_used=ocr_mode != "disable",
            warnings=[],
            metadata={"provider": self.name},
        )


def test_extraction_manager_falls_back_between_providers(tmp_path, monkeypatch) -> None:
    """If the first provider fails, the next successful provider should win."""

    paper_path = tmp_path / "paper.pdf"
    paper_path.write_bytes(b"%PDF-1.4")

    providers = {
        "docling": FakeProvider("docling", should_fail=True),
        "pymupdf4llm": FakeProvider("pymupdf4llm"),
        "jina": FakeProvider("jina"),
    }

    monkeypatch.setattr(
        "src.document_extraction.providers.create_provider",
        lambda name: providers[name],
    )

    manager = ExtractionManager(chain="docling,pymupdf4llm,jina")
    result = manager.extract(str(paper_path))

    assert result.provider == "pymupdf4llm"
    assert providers["docling"].call_count == 1
    assert providers["pymupdf4llm"].call_count == 1
    assert providers["jina"].call_count == 0


def test_extraction_manager_reads_document_cache_before_provider(
    tmp_path, monkeypatch
) -> None:
    """A valid cached extraction should short-circuit provider execution."""

    paper_path = tmp_path / "paper.pdf"
    paper_path.write_bytes(b"%PDF-1.4")

    cache_manager = CacheManager(cache_dir=str(tmp_path / "cache"))
    provider = FakeProvider("docling", should_fail=True)
    cache_key = build_document_cache_key(
        str(paper_path),
        provider.name,
        "pdf",
        "auto",
        provider.cache_version,
    )
    cached_content = ("Introduction " * 220) + ("Method " * 220)
    cache_manager.set_document_cache(
        cache_key,
        {
            "markdown": cached_content,
            "plain_text": cached_content,
            "provider": provider.name,
            "source_type": "pdf",
            "ocr_used": True,
            "warnings": [],
            "metadata": {},
        },
    )

    monkeypatch.setattr(
        "src.document_extraction.providers.create_provider",
        lambda name: provider,
    )

    manager = ExtractionManager(cache_manager=cache_manager, chain="docling")
    result = manager.extract(str(paper_path))

    assert result.provider == "docling"
    assert provider.call_count == 0


def test_extraction_content_gate_rejects_common_http_error_pages() -> None:
    """Short HTTP and anti-bot pages must not count as extracted paper text."""

    content = "403 Forbidden\nRequest blocked by gateway\n" + ("nginx " * 500)

    assert get_paper_content_issue(content) == "命中错误页特征: 403 forbidden"


def test_extraction_manager_ignores_invalid_cached_extraction(
    tmp_path, monkeypatch
) -> None:
    """Invalid cached content should be treated as stale and regenerated."""

    paper_path = tmp_path / "paper.pdf"
    paper_path.write_bytes(b"%PDF-1.4")

    provider = FakeProvider("docling")
    cache_key = build_document_cache_key(
        str(paper_path),
        provider.name,
        "pdf",
        "auto",
        provider.cache_version,
    )
    cache_manager = CacheManager(cache_dir=str(tmp_path / "cache"))
    error_page = "503 Service Unavailable\nGateway Timeout\n" + ("retry " * 500)
    cache_manager.set_document_cache(
        cache_key,
        {
            "markdown": error_page,
            "plain_text": error_page,
            "provider": provider.name,
            "source_type": "pdf",
            "ocr_used": False,
            "warnings": [],
            "metadata": {},
        },
    )

    monkeypatch.setattr(
        "src.document_extraction.providers.create_provider",
        lambda name: provider,
    )

    manager = ExtractionManager(cache_manager=cache_manager, chain="docling")
    result = manager.extract(str(paper_path))

    assert result.provider == "docling"
    assert provider.call_count == 1
    assert "Introduction" in result.content


def test_extraction_manager_retries_after_provider_returns_error_page(
    tmp_path, monkeypatch
) -> None:
    """A provider returning an error page should fail over to the next provider."""

    paper_path = tmp_path / "paper.pdf"
    paper_path.write_bytes(b"%PDF-1.4")
    error_page = "Just a moment...\nPlease enable JavaScript and cookies" + (
        " challenge" * 400
    )
    providers = {
        "docling": FakeProvider("docling", content=error_page),
        "pymupdf4llm": FakeProvider("pymupdf4llm"),
        "jina": FakeProvider("jina"),
    }

    monkeypatch.setattr(
        "src.document_extraction.providers.create_provider",
        lambda name: providers[name],
    )

    manager = ExtractionManager(chain="docling,pymupdf4llm,jina")
    result = manager.extract(str(paper_path))

    assert result.provider == "pymupdf4llm"
    assert providers["docling"].call_count == 1
    assert providers["pymupdf4llm"].call_count == 1
    assert providers["jina"].call_count == 0
