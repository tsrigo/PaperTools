"""Publication quality gates for user-facing daily paper pages."""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Tuple


FAILED_GENERATION_MARKERS = (
    "翻译失败",
    "生成失败",
    "提取失败",
    "extraction failed",
    "generation failed",
    "translation failed",
)

FAILED_REVIEW_MARKERS = (
    "reviewgrounder 审稿生成失败",
    "reviewgrounder review generation failed",
)

REQUIRED_PUBLISH_FIELDS = (
    "summary",
    "summary_translation",
    "intro_logic",
    "core_insight",
    "methodology",
    "additional_insights",
    "research_value",
)


def has_non_empty_text(value: Any) -> bool:
    """Return True when a field contains visible text."""
    return isinstance(value, str) and bool(value.strip())


def is_failed_generated_text(value: Any) -> bool:
    """Return True for generated failure sentinels that must not be published."""
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    return any(marker in lowered for marker in FAILED_GENERATION_MARKERS)


def has_valid_generated_text(value: Any) -> bool:
    """Return True for non-empty generated text that is not a failure marker."""
    return has_non_empty_text(value) and not is_failed_generated_text(value)


def _reviewgrounder_failed(paper: Dict[str, Any]) -> bool:
    review = paper.get("reviewgrounder_review")
    if isinstance(review, dict) and review.get("error"):
        return True

    research_value = paper.get("research_value")
    if isinstance(research_value, str):
        lowered = research_value.strip().lower()
        if any(marker in lowered for marker in FAILED_REVIEW_MARKERS):
            return True

    return False


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _prestige_bypass_disallowed(paper: Dict[str, Any]) -> bool:
    """Reject legacy topic-only prestige bypasses when the hard gate is active."""
    prestige_enabled = _env_bool("PRESTIGE_ENABLED", True)
    bypass_enabled = _env_bool("PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE", False)
    return (
        prestige_enabled
        and not bypass_enabled
        and paper.get("prestige_source") == "topic_heuristic_bypass"
    )


def missing_publish_fields(paper: Dict[str, Any]) -> List[str]:
    """List missing or invalid fields for a paper that is about to be published."""
    missing = [
        field
        for field in REQUIRED_PUBLISH_FIELDS
        if not has_valid_generated_text(paper.get(field))
    ]

    if _reviewgrounder_failed(paper):
        missing.append("reviewgrounder_review")

    if _prestige_bypass_disallowed(paper):
        missing.append("prestige_verification")

    seen = set()
    return [field for field in missing if not (field in seen or seen.add(field))]


def is_publishable_paper(paper: Dict[str, Any]) -> bool:
    """Return whether a paper has all user-facing generated content."""
    return not missing_publish_fields(paper)


def validate_publishable_papers(
    papers: Iterable[Dict[str, Any]],
    *,
    context: str = "papers",
) -> Tuple[bool, List[str]]:
    """Validate every paper and return compact human-readable errors."""
    errors: List[str] = []
    for index, paper in enumerate(papers, 1):
        missing = missing_publish_fields(paper)
        if missing:
            identity = (
                paper.get("arxiv_id")
                or paper.get("title")
                or f"paper#{index}"
            )
            errors.append(f"{context}: {identity} missing {', '.join(missing)}")
    return not errors, errors


def flatten_date_data_papers(date_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten a generated per-date webpage payload into paper records."""
    papers: List[Dict[str, Any]] = []
    for cluster in date_data.get("clusters", []) or []:
        if not isinstance(cluster, dict):
            continue
        cluster_name = cluster.get("name") or "Other"
        for paper in cluster.get("papers", []) or []:
            if not isinstance(paper, dict):
                continue
            paper_copy = dict(paper)
            paper_copy["cluster"] = paper_copy.get("cluster") or cluster_name
            papers.append(paper_copy)
    return papers


def validate_date_data_payload(
    date_data: Dict[str, Any],
    *,
    expected_date: str = "",
) -> Tuple[bool, List[str]]:
    """Validate a generated daily JSON file before it is committed."""
    errors: List[str] = []

    if expected_date and date_data.get("date") != expected_date:
        errors.append(f"date mismatch: expected {expected_date}, got {date_data.get('date')!r}")

    clusters = date_data.get("clusters")
    if not isinstance(clusters, list):
        errors.append("clusters must be a list")
        return False, errors

    if not has_valid_generated_text(date_data.get("overview")):
        errors.append("missing daily overview")

    papers = flatten_date_data_papers(date_data)
    if not papers:
        errors.append("no publishable papers")
        return False, errors

    ok, paper_errors = validate_publishable_papers(
        papers,
        context=expected_date or str(date_data.get("date") or "date_data"),
    )
    errors.extend(paper_errors)
    return ok and not errors, errors
