"""Unified document extraction exports."""

from src.document_extraction.core import (
    DEFAULT_PROVIDER_CHAIN,
    DOCUMENT_CACHE_SCHEMA_VERSION,
    DocumentExtractionError,
    ExtractionManager,
    ExtractionResult,
    ProviderStatus,
    build_document_cache_key,
    detect_source_type,
    ensure_valid_extraction_content,
    get_document_content,
    get_paper_content_issue,
    get_provider_statuses,
    normalize_arxiv_pdf_url,
    normalize_document_source,
    normalize_whitespace,
    resolve_provider_chain,
)

__all__ = [
    "DEFAULT_PROVIDER_CHAIN",
    "DOCUMENT_CACHE_SCHEMA_VERSION",
    "DocumentExtractionError",
    "ExtractionManager",
    "ExtractionResult",
    "ProviderStatus",
    "build_document_cache_key",
    "detect_source_type",
    "ensure_valid_extraction_content",
    "get_document_content",
    "get_paper_content_issue",
    "get_provider_statuses",
    "normalize_arxiv_pdf_url",
    "normalize_document_source",
    "normalize_whitespace",
    "resolve_provider_chain",
]
