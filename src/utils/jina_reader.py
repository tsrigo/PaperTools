"""Backward-compatible Jina Reader helpers built on the unified extraction layer."""

from __future__ import annotations

from typing import Optional

from src.document_extraction import (
    ensure_valid_extraction_content,
    get_paper_content_issue,
    normalize_arxiv_pdf_url,
)
from src.document_extraction.core import ExtractionContext
from src.document_extraction.providers import JinaExtractor
from src.utils.cache_manager import CacheManager

__all__ = [
    "build_jina_reader_url",
    "ensure_valid_paper_content",
    "fetch_paper_content_from_jina",
    "fetch_paper_content_from_jinja",
    "get_paper_content_issue",
    "normalize_arxiv_pdf_url",
]


def ensure_valid_paper_content(content: Optional[str], source: str) -> str:
    """Backward-compatible alias for shared extraction validation."""
    return ensure_valid_extraction_content(content, source)


def build_jina_reader_url(arxiv_url: str) -> str:
    """Build a Jina Reader URL from an arXiv URL or id."""
    pdf_url = normalize_arxiv_pdf_url(arxiv_url)
    return f"https://r.jina.ai/{pdf_url}"


def fetch_paper_content_from_jina(
    arxiv_url: str,
    cache_manager: Optional[CacheManager] = None,
    session=None,
) -> Optional[str]:
    """Fetch paper content through the Jina fallback provider."""
    provider = JinaExtractor()
    context = ExtractionContext(
        original_source=arxiv_url,
        normalized_source=normalize_arxiv_pdf_url(arxiv_url),
        source_type="pdf",
        local_path=None,
    )
    result = provider.extract(context)
    if cache_manager:
        cache_manager.set_paper_cache(arxiv_url, {"content": result.content})
    return result.content


# Backward compatibility for existing typoed call sites.
fetch_paper_content_from_jinja = fetch_paper_content_from_jina
