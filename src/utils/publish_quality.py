"""Publication quality gates for user-facing daily paper pages."""

from __future__ import annotations

import os
import re
from datetime import date
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse


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

PLACEHOLDER_TEXT_VALUES = {
    "n/a",
    "na",
    "n.a.",
    "none",
    "null",
    "not applicable",
    "not available",
    "not provided",
    "tbd",
    "todo",
    "unknown",
    "unknown author",
    "unknown authors",
    "暂无",
    "无",
    "未知",
    "未提供",
}

PLACEHOLDER_TEXT_CANONICAL_VALUES = {
    re.sub(r"[\s._/\-]+", "", value)
    for value in PLACEHOLDER_TEXT_VALUES
    if value.isascii()
}

REQUIRED_PUBLISH_FIELDS = (
    "summary",
    "summary_translation",
    "intro_logic",
    "core_insight",
    "methodology",
    "additional_insights",
    "research_value",
)

REQUIRED_METADATA_FIELDS = (
    "arxiv_id",
    "title",
    "link",
    "authors",
    "category",
)

ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")
ARXIV_CATEGORY_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[A-Za-z0-9-]+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def has_non_empty_text(value: Any) -> bool:
    """Return True when a field contains visible text."""
    return isinstance(value, str) and bool(value.strip())


def is_placeholder_text(value: Any) -> bool:
    """Return True for common metadata placeholders that should not be published."""
    if not isinstance(value, str):
        return False
    text = re.sub(r"\s+", " ", value).strip().casefold()
    if not text:
        return False
    if not re.search(r"[\w\u4e00-\u9fff]", text):
        return True
    if text in PLACEHOLDER_TEXT_VALUES:
        return True
    canonical = re.sub(r"[\s._/\-]+", "", text)
    return canonical in PLACEHOLDER_TEXT_CANONICAL_VALUES


def has_publishable_metadata_text(value: Any) -> bool:
    """Return True for non-empty metadata that is not a placeholder."""
    return has_non_empty_text(value) and not is_placeholder_text(value)


def has_canonical_text(value: Any) -> bool:
    """Return True when a string has no leading or trailing whitespace."""
    return isinstance(value, str) and value == value.strip()


def is_failed_generated_text(value: Any) -> bool:
    """Return True for generated failure sentinels that must not be published."""
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    return any(marker in lowered for marker in FAILED_GENERATION_MARKERS)


def has_valid_generated_text(value: Any) -> bool:
    """Return True for non-empty generated text that is not a failure marker."""
    return (
        has_non_empty_text(value)
        and not is_failed_generated_text(value)
        and not is_placeholder_text(value)
    )


def has_cjk_text(value: Any) -> bool:
    """Return True when text contains at least one CJK ideograph."""
    return isinstance(value, str) and bool(CJK_RE.search(value))


def has_valid_arxiv_id(value: Any) -> bool:
    """Return True for modern arXiv identifiers used by daily paper pages."""
    return isinstance(value, str) and bool(ARXIV_ID_RE.fullmatch(value.strip()))


def has_valid_arxiv_category(value: Any) -> bool:
    """Return True for arXiv primary category syntax such as cs.AI or q-bio.BM."""
    return isinstance(value, str) and bool(ARXIV_CATEGORY_RE.fullmatch(value.strip()))


def has_valid_calendar_date(value: Any) -> bool:
    """Return True for real calendar dates formatted as YYYY-MM-DD."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not DATE_RE.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def link_matches_arxiv_id(link: Any, arxiv_id: Any) -> bool:
    """Return True when a source link points at the listed arXiv identifier."""
    if not has_non_empty_text(link) or not has_valid_arxiv_id(arxiv_id):
        return False
    canonical_id = str(arxiv_id).strip().split("v", 1)[0]
    parsed = urlparse(str(link).strip())
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    if host:
        if parsed.scheme not in {"http", "https"}:
            return False
        if host not in {"arxiv.org", "www.arxiv.org"}:
            return False
        allowed_prefixes = ("/abs/", "/pdf/")
    else:
        allowed_prefixes = ("/arxiv/", "/abs/", "/pdf/")

    if not any(path.startswith(prefix) for prefix in allowed_prefixes):
        return False

    path_identifier = path.rsplit("/", 1)[-1]
    if path_identifier.endswith(".pdf"):
        path_identifier = path_identifier[:-4]
    path_identifier = path_identifier.split("v", 1)[0]
    return path_identifier == canonical_id


def validate_tag_metadata(tags: Any) -> List[str]:
    """Validate top-level tag metadata used by the webpage filters."""
    errors: List[str] = []
    if not isinstance(tags, list):
        return ["tags must be a list"]
    if not tags:
        return ["tags must contain at least one tag"]

    seen: set[str] = set()
    for index, tag in enumerate(tags, 1):
        label = f"tag#{index}"
        if not isinstance(tag, dict):
            errors.append(f"{label} must be an object")
            continue

        name = tag.get("name")
        if not has_non_empty_text(name):
            errors.append(f"{label} missing tag name")
        elif not has_publishable_metadata_text(name):
            errors.append(f"{label} tag name must be publishable text")
        elif not has_canonical_text(name):
            errors.append(f"{label} tag name must be canonical text")
        elif name in seen:
            errors.append(f"duplicate tag {name}")
        else:
            seen.add(name)

        count = tag.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            errors.append(f"{label} count must be a positive integer")

    return errors


def validate_tag_count_consistency(
    tags: Any,
    observed_counts: Counter[str],
) -> List[str]:
    """Validate top-level tag counts against paper and cluster metadata."""
    errors: List[str] = []
    if not isinstance(tags, list):
        return errors

    declared_counts: Dict[str, int] = {}
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        name = tag.get("name")
        count = tag.get("count")
        if (
            has_publishable_metadata_text(name)
            and has_canonical_text(name)
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
        ):
            declared_counts[name] = count

    for name, expected_count in sorted(observed_counts.items()):
        declared_count = declared_counts.get(name)
        if declared_count is None:
            errors.append(f"missing tag metadata for {name}")
        elif declared_count != expected_count:
            errors.append(
                f"tag {name} count mismatch: expected {expected_count}, got {declared_count!r}"
            )

    for name in sorted(set(declared_counts) - set(observed_counts)):
        errors.append(f"tag {name} has no matching paper")

    return errors


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
        for field in REQUIRED_METADATA_FIELDS
        if not has_publishable_metadata_text(paper.get(field))
    ]
    for field in REQUIRED_METADATA_FIELDS:
        if field not in missing and not has_canonical_text(paper.get(field)):
            missing.append(field)
    if "arxiv_id" not in missing and not has_valid_arxiv_id(paper.get("arxiv_id")):
        missing.append("arxiv_id")
    if "category" not in missing and not has_valid_arxiv_category(
        paper.get("category")
    ):
        missing.append("category")
    if "link" not in missing and not link_matches_arxiv_id(
        paper.get("link"),
        paper.get("arxiv_id"),
    ):
        missing.append("link")
    missing.extend(
        field
        for field in REQUIRED_PUBLISH_FIELDS
        if not has_valid_generated_text(paper.get(field))
    )
    for field in REQUIRED_PUBLISH_FIELDS:
        if field not in missing and not has_canonical_text(paper.get(field)):
            missing.append(field)
    if "summary_translation" not in missing and not has_cjk_text(
        paper.get("summary_translation")
    ):
        missing.append("summary_translation")

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
        if not isinstance(paper, dict):
            errors.append(f"{context}: paper#{index} must be an object")
            continue

        missing = missing_publish_fields(paper)
        if missing:
            identity = paper.get("arxiv_id") or paper.get("title") or f"paper#{index}"
            errors.append(f"{context}: {identity} missing {', '.join(missing)}")
    return not errors, errors


def flatten_date_data_papers(date_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten a generated per-date webpage payload into paper records."""
    papers: List[Dict[str, Any]] = []
    if not isinstance(date_data, dict):
        return papers

    clusters = date_data.get("clusters")
    if not isinstance(clusters, list):
        return papers

    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        cluster_name = cluster.get("name")
        cluster_papers = cluster.get("papers")
        if not isinstance(cluster_papers, list):
            continue
        for paper in cluster_papers:
            if not isinstance(paper, dict):
                continue
            paper_copy = dict(paper)
            if has_non_empty_text(cluster_name):
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

    if not isinstance(date_data, dict):
        return False, ["payload must be an object"]

    date_value = date_data.get("date")
    date_text = ""
    if not has_non_empty_text(date_value):
        errors.append("date must be non-empty")
    else:
        date_text = str(date_value).strip()
    if date_text and str(date_value) != date_text:
        errors.append("date must be canonical YYYY-MM-DD")
    elif date_text and not DATE_RE.fullmatch(date_text):
        errors.append("date must be YYYY-MM-DD")
    elif date_text and not has_valid_calendar_date(date_text):
        errors.append("date must be a valid calendar date")

    if expected_date and date_text != expected_date:
        errors.append(f"date mismatch: expected {expected_date}, got {date_value!r}")

    clusters = date_data.get("clusters")
    if not isinstance(clusters, list):
        errors.append("clusters must be a list")
        return False, errors

    errors.extend(validate_tag_metadata(date_data.get("tags")))

    flattened_papers: List[Dict[str, Any]] = []
    observed_tag_counts: Counter[str] = Counter()
    seen_cluster_names: set[str] = set()
    for cluster_index, cluster in enumerate(clusters, 1):
        cluster_label = f"cluster#{cluster_index}"
        if not isinstance(cluster, dict):
            errors.append(f"{cluster_label} must be an object")
            continue

        cluster_name = cluster.get("name")
        has_cluster_name = has_publishable_metadata_text(cluster_name)
        if not has_non_empty_text(cluster_name):
            errors.append(f"{cluster_label} missing cluster name")
        elif not has_cluster_name:
            errors.append(f"{cluster_label} cluster name must be publishable text")
        elif not has_canonical_text(cluster_name):
            errors.append(f"{cluster_label} cluster name must be canonical text")
        elif str(cluster_name) in seen_cluster_names:
            errors.append(f"duplicate cluster {cluster_name}")
        else:
            seen_cluster_names.add(str(cluster_name))

        cluster_papers = cluster.get("papers")
        if not isinstance(cluster_papers, list):
            errors.append(f"{cluster_label} papers must be a list")
            continue

        if not cluster_papers:
            errors.append(f"{cluster_label} has no papers")

        if "count" not in cluster:
            errors.append(f"{cluster_label} missing cluster count")
        else:
            declared_count = cluster.get("count")
            if (
                isinstance(declared_count, bool)
                or not isinstance(declared_count, int)
                or declared_count <= 0
            ):
                errors.append(f"{cluster_label} count must be a positive integer")
            elif declared_count != len(cluster_papers):
                errors.append(
                    f"{cluster_label} count mismatch: expected {len(cluster_papers)}, got {declared_count!r}"
                )

        for paper_index, paper in enumerate(cluster_papers, 1):
            paper_label = f"{cluster_label} paper#{paper_index}"
            if not isinstance(paper, dict):
                errors.append(f"{paper_label} must be an object")
                continue

            paper_copy = dict(paper)
            paper_cluster = paper_copy.get("cluster")
            if has_non_empty_text(paper_cluster) and not has_publishable_metadata_text(
                paper_cluster
            ):
                errors.append(
                    f"{paper_label} cluster metadata must be publishable text"
                )
            elif has_non_empty_text(paper_cluster) and not has_canonical_text(
                paper_cluster
            ):
                errors.append(f"{paper_label} cluster metadata must be canonical text")
            elif not has_non_empty_text(paper_cluster):
                if has_cluster_name:
                    paper_copy["cluster"] = cluster_name
                else:
                    errors.append(f"{paper_label} missing cluster metadata")

            if expected_date and "source_date" in paper:
                source_date = paper.get("source_date")
                source_date_text = ""
                if not has_non_empty_text(source_date):
                    errors.append(f"{paper_label} source_date must be non-empty")
                else:
                    source_date_text = str(source_date).strip()
                if source_date_text and str(source_date) != source_date_text:
                    errors.append(
                        f"{paper_label} source_date must be canonical YYYY-MM-DD"
                    )
                elif source_date_text and not DATE_RE.fullmatch(source_date_text):
                    errors.append(f"{paper_label} source_date must be YYYY-MM-DD")
                elif source_date_text and not has_valid_calendar_date(source_date_text):
                    errors.append(
                        f"{paper_label} source_date must be a valid calendar date"
                    )
                elif source_date_text and source_date_text != expected_date:
                    errors.append(
                        f"{paper_label} source_date mismatch: expected {expected_date}, got {source_date!r}"
                    )

            paper_tags: set[str] = set()
            raw_tag_values: set[str] = set()
            if has_cluster_name:
                paper_tags.add(str(cluster_name))
            raw_paper_tags = paper.get("tags")
            if raw_paper_tags is not None:
                if not isinstance(raw_paper_tags, list):
                    errors.append(f"{paper_label} tags must be a list")
                else:
                    for tag_index, tag_name in enumerate(raw_paper_tags, 1):
                        if not has_non_empty_text(tag_name):
                            errors.append(
                                f"{paper_label} tag#{tag_index} must be non-empty text"
                            )
                            continue
                        if not has_publishable_metadata_text(tag_name):
                            errors.append(
                                f"{paper_label} tag#{tag_index} must be publishable text"
                            )
                            continue
                        if not has_canonical_text(tag_name):
                            errors.append(
                                f"{paper_label} tag#{tag_index} must be canonical text"
                            )
                            continue
                        if tag_name in paper_tags:
                            errors.append(f"{paper_label} duplicate tag {tag_name}")
                            continue
                        raw_tag_values.add(str(tag_name))
                        paper_tags.add(str(tag_name))
            category = paper.get("category")
            if has_valid_arxiv_category(category):
                category_tag = str(category).strip()
                if category_tag not in raw_tag_values:
                    errors.append(f"{paper_label} missing category tag {category_tag}")
            observed_tag_counts.update(paper_tags)
            flattened_papers.append(paper_copy)

    errors.extend(
        validate_tag_count_consistency(date_data.get("tags"), observed_tag_counts)
    )

    overview = date_data.get("overview")
    if not has_valid_generated_text(overview):
        errors.append("missing daily overview")
    elif not has_canonical_text(overview):
        errors.append("daily overview must be canonical text")
    elif not has_cjk_text(overview):
        errors.append("daily overview must contain Chinese text")
    else:
        overview_expected_date = ""
        if has_valid_calendar_date(expected_date):
            overview_expected_date = expected_date
        elif has_valid_calendar_date(date_value):
            overview_expected_date = str(date_value).strip()
        if overview_expected_date and overview_expected_date not in str(overview):
            errors.append(
                f"daily overview date mismatch: expected {overview_expected_date}"
            )

    if not flattened_papers:
        errors.append("no publishable papers")
        return False, errors

    ok, paper_errors = validate_publishable_papers(
        flattened_papers,
        context=expected_date or str(date_data.get("date") or "date_data"),
    )
    errors.extend(paper_errors)

    seen_arxiv_ids: set[str] = set()
    for paper in flattened_papers:
        arxiv_id = str(paper.get("arxiv_id") or "").strip()
        if not arxiv_id or not has_valid_arxiv_id(arxiv_id):
            continue
        if arxiv_id in seen_arxiv_ids:
            errors.append(f"duplicate arxiv_id {arxiv_id}")
            continue
        seen_arxiv_ids.add(arxiv_id)

    return ok and not errors, errors
