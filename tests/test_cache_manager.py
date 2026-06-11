"""Tests for the cache management utilities."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from src.utils.cache_manager import CacheManager


def _summary_cache_path(
    manager: CacheManager, cache_dir: Path, title: str, content: str
) -> Path:
    content_hash = hashlib.sha256((content or "").encode("utf-8")).hexdigest()
    key = hashlib.sha256(
        f"{manager.summary_namespace}:{title}:{len(content or '')}:{content_hash}".encode(
            "utf-8"
        )
    ).hexdigest()
    return cache_dir / "summaries" / f"{key}.json"


def _document_cache_path(manager: CacheManager, cache_key: str) -> Path:
    return Path(manager._get_cache_file("documents", manager._generate_key(cache_key)))


def test_summary_cache_roundtrip(tmp_path) -> None:
    """Setting and fetching a summary cache returns the stored payload."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))

    manager.set_summary_cache("Agent", "content", "cached-summary")

    assert manager.get_summary_cache("Agent", "content") == "cached-summary"


def test_summary_cache_respects_expiry(tmp_path) -> None:
    """Expired summary cache entries are ignored."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))

    title = "A Title"
    content = "Long content that will be hashed"
    manager.set_summary_cache(title, content, "stale")

    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    key = hashlib.sha256(
        f":{title}:{len(content)}:{content_hash}".encode("utf-8")
    ).hexdigest()
    cache_file = cache_dir / "summaries" / f"{key}.json"

    old_timestamp = time.time() - 60 * 60 * 24 * 40
    os.utime(cache_file, (old_timestamp, old_timestamp))

    assert manager.get_summary_cache(title, content) is None


def test_summary_cache_rejects_failure_placeholders(tmp_path) -> None:
    """Failure sentinel text must not be reused as a successful summary cache hit."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))

    manager.set_summary_cache("Agent", "content", "生成失败")

    assert manager.get_summary_cache("Agent", "content") is None
    assert manager.get_cache_stats()["summaries"] == 0


def test_malformed_summary_cache_is_discarded(tmp_path) -> None:
    """Malformed JSON cache files are removed instead of repeatedly reused."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))
    cache_file = _summary_cache_path(manager, cache_dir, "Agent", "content")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("{bad json", encoding="utf-8")

    assert manager.get_summary_cache("Agent", "content") is None
    assert not cache_file.exists()


def test_document_cache_requires_extracted_content(tmp_path) -> None:
    """Document cache entries need real extracted text before they count."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))
    cache_key = "doc-key"
    cache_file = Path(
        manager._get_cache_file("documents", manager._generate_key(cache_key))
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "cache_key": cache_key,
                "data": {"provider": "jina", "markdown": "   ", "plain_text": ""},
                "cached_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    assert manager.get_document_cache(cache_key) is None
    assert not cache_file.exists()


def test_document_cache_rejects_http_error_pages_on_write(tmp_path) -> None:
    """HTTP error pages must not be persisted as successful document content."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))
    cache_key = "doc-key"
    error_page = "403 Forbidden\nRequest blocked by gateway\n" + ("nginx " * 500)

    manager.set_document_cache(
        cache_key,
        {"provider": "jina", "markdown": error_page, "plain_text": error_page},
    )

    assert manager.get_document_cache(cache_key) is None
    assert not _document_cache_path(manager, cache_key).exists()


def test_document_cache_discards_persisted_antibot_challenge(tmp_path) -> None:
    """Existing challenge-page caches are removed on read instead of reused."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))
    cache_key = "doc-key"
    cache_file = _document_cache_path(manager, cache_key)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    challenge_page = "Just a moment...\nPlease enable JavaScript and cookies" + (
        " challenge" * 400
    )
    cache_file.write_text(
        json.dumps(
            {
                "cache_key": cache_key,
                "data": {
                    "provider": "jina",
                    "markdown": challenge_page,
                    "plain_text": challenge_page,
                },
                "cached_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    assert manager.get_document_cache(cache_key) is None
    assert not cache_file.exists()


def test_paper_cache_rejects_invalid_cached_content_on_write(tmp_path) -> None:
    """Paper cache content should satisfy the same paper-text gate as extraction."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))
    paper_url = "https://arxiv.org/pdf/2605.00001.pdf"
    error_page = "502 Bad Gateway\nUpstream connect error\n" + ("nginx " * 500)

    manager.set_paper_cache(paper_url, {"content": error_page})

    assert manager.get_paper_cache(paper_url) is None
    cache_file = Path(
        manager._get_cache_file("papers", manager._generate_key(paper_url))
    )
    assert not cache_file.exists()


def test_paper_cache_discards_persisted_short_content(tmp_path) -> None:
    """Legacy paper caches with non-paper content must not feed downstream repair jobs."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))
    paper_url = "https://arxiv.org/pdf/2605.00001.pdf"
    cache_file = Path(
        manager._get_cache_file("papers", manager._generate_key(paper_url))
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "url": paper_url,
                "data": {"content": "paper text"},
                "cached_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    assert manager.get_paper_cache(paper_url) is None
    assert not cache_file.exists()


def test_paper_cache_allows_metadata_only_entries(tmp_path) -> None:
    """Paper metadata caches without extracted content remain valid."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))

    manager.set_paper_cache("http://example.com", {"title": "paper"})

    cached = manager.get_paper_cache("http://example.com")

    assert cached is not None
    assert cached["data"]["title"] == "paper"


def test_paper_cache_discards_envelope_url_mismatch(tmp_path) -> None:
    """A paper cache copied under the wrong key must not satisfy another URL."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))
    paper_url = "https://arxiv.org/abs/2605.00001"
    cache_file = Path(
        manager._get_cache_file("papers", manager._generate_key(paper_url))
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "url": "https://arxiv.org/abs/2605.99999",
                "data": {"title": "wrong paper"},
                "cached_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    assert manager.get_paper_cache(paper_url) is None
    assert not cache_file.exists()


def test_crawl_cache_requires_paper_object_list(tmp_path) -> None:
    """Crawl cache papers must be a list of JSON objects, not arbitrary values."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))
    category = "cs.AI"
    date = "2026-01-01"
    cache_file = Path(
        manager._get_cache_file(
            "crawl", manager._generate_key(f"crawl:{category}:{date}")
        )
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "category": category,
                "date": date,
                "papers": [{"title": "valid"}, "not-a-paper"],
                "cached_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    assert manager.get_crawl_cache(category, date) is None
    assert not cache_file.exists()


def test_crawl_cache_discards_date_or_category_mismatch(tmp_path) -> None:
    """Crawl caches are date-sensitive publication inputs and must match exactly."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))
    category = "cs.AI"
    date = "2026-01-01"
    cache_file = Path(
        manager._get_cache_file(
            "crawl", manager._generate_key(f"crawl:{category}:{date}")
        )
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "category": "cs.CL",
                "date": date,
                "papers": [{"title": "wrong category paper"}],
                "paper_count": 1,
                "cached_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    assert manager.get_crawl_cache(category, date) is None
    assert not cache_file.exists()


def test_crawl_cache_discards_paper_count_mismatch(tmp_path) -> None:
    """A crawl cache envelope with inconsistent counts is treated as corrupted."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))
    category = "cs.AI"
    date = "2026-01-01"
    cache_file = Path(
        manager._get_cache_file(
            "crawl", manager._generate_key(f"crawl:{category}:{date}")
        )
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "category": category,
                "date": date,
                "papers": [{"title": "paper"}],
                "paper_count": 2,
                "cached_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    assert manager.get_crawl_cache(category, date) is None
    assert not cache_file.exists()


def test_document_summary_and_webpage_caches_discard_envelope_mismatches(
    tmp_path,
) -> None:
    """All reusable caches should prove the payload belongs to the requested key."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))

    document_key = "doc-key"
    document_file = _document_cache_path(manager, document_key)
    document_file.parent.mkdir(parents=True, exist_ok=True)
    document_file.write_text(
        json.dumps(
            {
                "cache_key": "different-doc-key",
                "data": {"markdown": "paper body " * 20},
                "cached_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    summary_file = _summary_cache_path(manager, cache_dir, "Agent", "content")
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(
        json.dumps(
            {
                "title": "Different title",
                "summary": "cached summary",
                "cached_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    webpage_key = manager._generate_key("Agent:hash")
    webpage_file = Path(manager._get_cache_file("webpages", webpage_key))
    webpage_file.parent.mkdir(parents=True, exist_ok=True)
    webpage_file.write_text(
        json.dumps(
            {
                "title": "Agent",
                "content_hash": "different-hash",
                "webpage_content": "<html></html>",
                "cached_at": "2026-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    assert manager.get_document_cache(document_key) is None
    assert manager.get_summary_cache("Agent", "content") is None
    assert manager.get_webpage_cache("Agent", "hash") is None
    assert not document_file.exists()
    assert not summary_file.exists()
    assert not webpage_file.exists()


def test_blank_webpage_cache_is_not_persisted(tmp_path) -> None:
    """Blank generated pages should not be cached as reusable output."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))

    manager.set_webpage_cache("Agent", "hash", "  ")

    assert manager.get_webpage_cache("Agent", "hash") is None
    assert manager.get_cache_stats()["webpages"] == 0


def test_cache_stats_reports_counts(tmp_path) -> None:
    """Cache statistics include counts for every cache bucket."""

    cache_dir = tmp_path / "cache"
    manager = CacheManager(cache_dir=str(cache_dir))

    manager.set_paper_cache("http://example.com", {"title": "paper"})
    manager.set_document_cache("doc-key", {"markdown": "paper"})
    manager.set_summary_cache("Agent", "content", "summary")
    manager.set_webpage_cache("Agent", "hash", "<html></html>")
    manager.set_crawl_cache("cs.AI", "2025-01-01", [{"title": "p"}])

    stats = manager.get_cache_stats()

    assert stats["papers"] == 1
    assert stats["documents"] == 1
    assert stats["summaries"] == 1
    assert stats["webpages"] == 1
    assert stats["crawl"] == 1
    assert stats["total"] == 5
