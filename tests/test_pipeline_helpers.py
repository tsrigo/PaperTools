"""Tests for helper functions defined in src.core.pipeline."""

from __future__ import annotations

import os
import time

import pytest

from src.core import cluster_papers as cluster_module
from src.core.generate_summary import has_non_empty_text
from src.core.generate_unified_index import backfill_paper_metadata
from src.core.paper_filter import repair_paper_metadata_from_source
from src.core.pipeline import find_file_by_date, find_latest_file


def _write_json(path) -> None:
    path.write_text("{}", encoding="utf-8")


def test_find_latest_file_prefers_filtered_results(tmp_path) -> None:
    domain_dir = tmp_path / "domain_paper"
    domain_dir.mkdir()

    other = domain_dir / "excluded_papers_2025-01-01.json"
    filtered = domain_dir / "filtered_papers_2025-01-01.json"
    _write_json(other)
    _write_json(filtered)

    now = time.time()
    os.utime(filtered, (now + 10, now + 10))

    assert find_latest_file(str(domain_dir)) == str(filtered)


def test_find_latest_file_prefers_combined_arxiv_files(tmp_path) -> None:
    arxiv_dir = tmp_path / "arxiv_paper"
    arxiv_dir.mkdir()

    single = arxiv_dir / "cs.AI_paper_2025-01-01.json"
    combined = arxiv_dir / "cs.AI_cs.CL_paper_2025-01-01.json"
    _write_json(single)
    _write_json(combined)

    assert find_latest_file(str(arxiv_dir)) == str(combined)


def test_find_file_by_date_matches_specific_day(tmp_path) -> None:
    domain_dir = tmp_path / "domain_paper"
    domain_dir.mkdir()

    jan = domain_dir / "filtered_papers_2025-01-01.json"
    feb = domain_dir / "filtered_papers_2025-02-01.json"
    _write_json(jan)
    _write_json(feb)

    assert find_file_by_date(str(domain_dir), "2025-02-01") == str(feb)


def test_find_file_by_date_falls_back_to_latest(tmp_path) -> None:
    domain_dir = tmp_path / "domain_paper"
    domain_dir.mkdir()

    jan = domain_dir / "filtered_papers_2025-01-01.json"
    feb = domain_dir / "filtered_papers_2025-02-01.json"
    _write_json(jan)
    _write_json(feb)

    now = time.time()
    os.utime(feb, (now + 5, now + 5))

    assert find_file_by_date(str(domain_dir), "2024-12-31") == str(feb)


def test_filter_repair_backfills_missing_summary_from_source() -> None:
    old_filtered = {
        "arxiv_id": "2604.00001",
        "title": "Kept Paper",
        "filter_reason": "ok",
    }
    source = {
        "arxiv_id": "2604.00001",
        "summary": "Original abstract from crawl.",
        "link": "/arxiv/2604.00001",
        "category": "cs.CL",
    }

    repaired, changed = repair_paper_metadata_from_source(old_filtered, source)

    assert changed is True
    assert repaired["summary"] == "Original abstract from crawl."
    assert repaired["link"] == "/arxiv/2604.00001"
    assert repaired["category"] == "cs.CL"


def test_unified_index_backfills_clustered_papers_before_display() -> None:
    clustered = [
        {
            "arxiv_id": "2604.00002",
            "title": "Clustered Paper",
            "cluster": "Agents",
        }
    ]
    source_by_id = {
        "2604.00002": {
            "arxiv_id": "2604.00002",
            "summary": "Recovered original abstract.",
            "authors": "A. Researcher",
        }
    }

    backfilled = backfill_paper_metadata(clustered, source_by_id)

    assert backfilled[0]["summary"] == "Recovered original abstract."
    assert backfilled[0]["authors"] == "A. Researcher"
    assert backfilled[0]["cluster"] == "Agents"


def test_summary_skip_helper_rejects_blank_text() -> None:
    assert has_non_empty_text(" abstract ") is True
    assert has_non_empty_text("   ") is False
    assert has_non_empty_text(None) is False


def test_cluster_batch_failure_is_publish_blocking(monkeypatch) -> None:
    def fail_clustering(*_args, **_kwargs):
        raise RuntimeError("invalid model")

    monkeypatch.setattr(cluster_module, "call_llm_for_clustering", fail_clustering)

    with pytest.raises(RuntimeError, match="clustering batch failed"):
        cluster_module.cluster_batch(
            client=None,
            model="bad-model",
            papers=[{"title": "Paper", "summary": "Abstract"}],
            temperature=0.1,
        )
