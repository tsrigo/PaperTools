"""Shared validation for extracted or cached document text."""

from __future__ import annotations

import re
from typing import Any


MIN_VALID_PAPER_CONTENT_CHARS = 2000
MIN_VALID_PAPER_CONTENT_ALPHA_CHARS = 800

INVALID_DOCUMENT_CONTENT_ERROR_MARKERS = (
    "401 unauthorized",
    "403 forbidden",
    "404 not found",
    "502 bad gateway",
    "503 service unavailable",
    "upstream connect error",
    "error code:",
    "bad gateway",
    "gateway timeout",
    "too many requests",
    "rate limit exceeded",
    "access denied",
    "request blocked",
    "request failed",
    "server error",
    "failed to fetch",
    "could not fetch",
)

INVALID_DOCUMENT_CONTENT_GATE_MARKERS = (
    "captcha",
    "verify you are human",
    "enable cookies",
    "automated access",
)

HIGH_CONFIDENCE_GATE_MARKERS = (
    "just a moment",
    "checking your browser",
    "please enable javascript",
    "attention required",
    "cloudflare ray id",
    "cf-browser-verification",
    "ddos protection",
)


def normalize_whitespace(text: Any) -> str:
    """Collapse repeated whitespace for lightweight content validation."""
    return re.sub(r"\s+", " ", "" if text is None else str(text)).strip()


def get_document_content_issue(
    content: Any,
    *,
    enforce_paper_length: bool,
    empty_issue: str = "内容为空",
    min_chars: int = MIN_VALID_PAPER_CONTENT_CHARS,
    min_alpha_chars: int = MIN_VALID_PAPER_CONTENT_ALPHA_CHARS,
) -> str | None:
    """Return a human-readable issue when document text looks invalid."""
    normalized = normalize_whitespace(content)
    if not normalized:
        return empty_issue

    lowered = normalized.lower()
    error_page_window = lowered[:2000]
    for marker in INVALID_DOCUMENT_CONTENT_ERROR_MARKERS:
        if marker in error_page_window and len(normalized) < 10000:
            return f"命中错误页特征: {marker}"

    for marker in HIGH_CONFIDENCE_GATE_MARKERS:
        if marker in lowered:
            return f"命中访问拦截页特征: {marker}"

    if len(normalized) < 10000:
        for marker in INVALID_DOCUMENT_CONTENT_GATE_MARKERS:
            if marker in lowered:
                return f"命中访问拦截页特征: {marker}"

    if not enforce_paper_length:
        return None

    if len(normalized) < min_chars:
        return f"内容过短 ({len(normalized)} chars)"

    alpha_chars = sum(ch.isalpha() for ch in normalized)
    if alpha_chars < min_alpha_chars:
        return f"有效字母过少 ({alpha_chars})"

    return None
