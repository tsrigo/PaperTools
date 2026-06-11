#!/usr/bin/env python3
"""Validate user-facing PaperTools webpage JSON before publication."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.publish_quality import (  # noqa: E402
    has_canonical_text,
    has_non_empty_text,
    has_publishable_metadata_text,
    has_valid_arxiv_id,
    link_matches_arxiv_id,
    validate_date_data_payload,
)
from src.utils.published_data_version import build_published_data_version  # noqa: E402
from src.utils.published_webpage_data import project_embedded_clusters  # noqa: E402

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PRESTIGE_EXCLUDED_FILENAME = "prestige_excluded_papers.json"
AVAILABLE_DATES_RE = re.compile(r"\bconst\s+availableDates\s*=\s*(\[[^;]*\])\s*;")
LOADED_DATES_RE = re.compile(
    r"\bconst\s+loadedDates\s*=\s*new\s+Set\((\[[^;]*\])\)\s*;"
)
LOAD_MORE_DAYS_RE = re.compile(r"\bconst\s+LOAD_MORE_DAYS\s*=\s*(\d+)\s*;")
DATA_VERSION_RE = re.compile(r'\bconst\s+DATA_VERSION\s*=\s*"([^"]+)"\s*;')


def read_json(path: Path) -> tuple[Any | None, str | None]:
    """Return parsed JSON or a compact error string."""
    if path.is_symlink() or not path.is_file():
        return None, f"{path}: JSON payload must be an ordinary file"

    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle), None
    except Exception as exc:
        return None, f"{path}: failed to read JSON: {exc}"


def exists_or_symlink(path: Path) -> bool:
    """Return True for existing paths and broken symlink entries."""
    return path.is_symlink() or path.exists()


def read_html(path: Path) -> tuple[str | None, str | None]:
    """Return HTML text or a compact error string."""
    if path.is_symlink() or not path.is_file():
        return None, f"{path}: site entrypoint must be an ordinary HTML file"

    try:
        return path.read_text(encoding="utf-8", errors="replace"), None
    except Exception as exc:
        return None, f"{path}: failed to read site entrypoint: {exc}"


def validate_html_page(path: Path, *, required_reference: str = "") -> list[str]:
    """Validate a user-facing HTML page and optional asset/data reference."""
    errors: list[str] = []
    html, read_error = read_html(path)
    if read_error is not None:
        if not exists_or_symlink(path):
            return [f"{path}: missing site entrypoint"]
        return [read_error]
    if html is None:
        return [f"{path}: failed to read site entrypoint"]

    if not html.strip():
        errors.append(f"{path}: site entrypoint is empty")
    lowered = html.lower()
    if "<html" not in lowered or "</html>" not in lowered:
        errors.append(f"{path}: site entrypoint must be an HTML page")
    if required_reference and required_reference not in html:
        errors.append(
            f"{path}: site entrypoint does not reference {required_reference}"
        )
    return errors


def _extract_js_string_array(
    html: str,
    path: Path,
    label: str,
    pattern: re.Pattern[str],
) -> tuple[list[str] | None, list[str]]:
    match = pattern.search(html)
    if not match:
        return None, [f"{path}: missing {label} manifest"]

    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return None, [f"{path}: {label} manifest is not valid JSON: {exc}"]

    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None, [f"{path}: {label} manifest must be a list of strings"]
    return value, []


def _extract_js_data_block(
    html: str,
    path: Path,
    label: str,
    start_marker: str,
    end_marker: str,
) -> tuple[Any | None, list[str]]:
    start = html.find(start_marker)
    if start == -1:
        return None, [f"{path}: missing {label} embedded data"]
    value_start = start + len(start_marker)
    end = html.find(end_marker, value_start)
    if end == -1:
        return None, [f"{path}: unterminated {label} embedded data"]

    value_text = html[value_start:end].strip()
    if value_text.endswith(";"):
        value_text = value_text[:-1].strip()
    value_text = re.sub(r",(\s*[}\]])", r"\1", value_text)
    value_text = re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f]",
        lambda match: f"\\u{ord(match.group(0)):04x}",
        value_text,
    )

    try:
        return json.loads(value_text), []
    except json.JSONDecodeError as exc:
        return None, [f"{path}: {label} embedded data is not valid JSON: {exc}"]


def validate_initial_embedded_data(
    html: str,
    path: Path,
    *,
    loaded_dates: list[str],
    date_payloads_by_date: dict[str, Any],
) -> list[str]:
    """Validate first-screen embedded data against the JSON users can lazy-load."""
    errors: list[str] = []
    all_papers, parse_errors = _extract_js_data_block(
        html,
        path,
        "allPapers",
        "const allPapers =",
        "\n\nconst allPaperTags =",
    )
    errors.extend(parse_errors)
    all_tags, parse_errors = _extract_js_data_block(
        html,
        path,
        "allPaperTags",
        "const allPaperTags =",
        "\n\nconst availableDates =",
    )
    errors.extend(parse_errors)
    overviews, parse_errors = _extract_js_data_block(
        html,
        path,
        "dailyOverviewsRaw",
        "const dailyOverviewsRaw =",
        "\nconst dailyOverviews =",
    )
    errors.extend(parse_errors)

    if not isinstance(all_papers, dict):
        errors.append(f"{path}: allPapers embedded data must be an object")
        all_papers = {}
    if not isinstance(all_tags, dict):
        errors.append(f"{path}: allPaperTags embedded data must be an object")
        all_tags = {}
    if not isinstance(overviews, dict):
        errors.append(f"{path}: dailyOverviewsRaw embedded data must be an object")
        overviews = {}

    loaded_set = set(loaded_dates)
    for label, value in (
        ("allPapers", all_papers),
        ("allPaperTags", all_tags),
        ("dailyOverviewsRaw", overviews),
    ):
        if set(value) != loaded_set:
            errors.append(f"{path}: {label} embedded dates must match loadedDates")

    for date in loaded_dates:
        date_payload = date_payloads_by_date.get(date)
        if not isinstance(date_payload, dict):
            continue
        expected_clusters = project_embedded_clusters(date_payload)
        if all_papers.get(date) != expected_clusters:
            errors.append(f"{path}: allPapers embedded data mismatch for {date}")
        if all_tags.get(date) != date_payload.get("tags"):
            errors.append(f"{path}: allPaperTags embedded data mismatch for {date}")
        if overviews.get(date) != date_payload.get("overview"):
            errors.append(
                f"{path}: dailyOverviewsRaw embedded data mismatch for {date}"
            )

    return errors


def validate_site_data_manifest(
    path: Path,
    *,
    index_data: dict[str, Any],
    normalized_dates: list[str],
    date_payloads_by_date: dict[str, Any] | None = None,
) -> list[str]:
    """Validate that the entrypoint's embedded data manifest matches index.json."""
    if not exists_or_symlink(path) or path.is_symlink() or not path.is_file():
        return []

    errors: list[str] = []
    html, read_error = read_html(path)
    if read_error is not None:
        return [read_error]
    if html is None:
        return [f"{path}: failed to read site entrypoint"]

    available_dates, parse_errors = _extract_js_string_array(
        html,
        path,
        "availableDates",
        AVAILABLE_DATES_RE,
    )
    errors.extend(parse_errors)
    if available_dates is not None and available_dates != normalized_dates:
        errors.append(f"{path}: availableDates manifest must match data/index.json")

    loaded_dates, parse_errors = _extract_js_string_array(
        html,
        path,
        "loadedDates",
        LOADED_DATES_RE,
    )
    errors.extend(parse_errors)
    initial_days = index_data.get("initial_days")
    if (
        loaded_dates is not None
        and isinstance(initial_days, int)
        and not isinstance(initial_days, bool)
        and initial_days > 0
    ):
        expected_loaded_dates = normalized_dates[:initial_days]
        if loaded_dates != expected_loaded_dates:
            errors.append(
                f"{path}: loadedDates manifest must match the first {initial_days} indexed dates"
            )

    load_more_match = LOAD_MORE_DAYS_RE.search(html)
    if not load_more_match:
        errors.append(f"{path}: missing LOAD_MORE_DAYS manifest")
    else:
        load_more_days = index_data.get("load_more_days")
        if (
            isinstance(load_more_days, int)
            and not isinstance(load_more_days, bool)
            and load_more_days > 0
        ):
            html_load_more_days = int(load_more_match.group(1))
            if html_load_more_days != load_more_days:
                errors.append(
                    f"{path}: LOAD_MORE_DAYS mismatch: expected {load_more_days}, got {html_load_more_days}"
                )

    version_match = DATA_VERSION_RE.search(html)
    if not version_match:
        errors.append(f"{path}: missing DATA_VERSION cache-busting token")
    else:
        html_data_version = version_match.group(1)
        if not re.fullmatch(r"[0-9a-f]{12}", html_data_version):
            errors.append(f"{path}: DATA_VERSION must be a 12-character hex string")
        elif date_payloads_by_date is not None and all(
            date in date_payloads_by_date for date in normalized_dates
        ):
            expected_data_version = build_published_data_version(
                index_data,
                {date: date_payloads_by_date[date] for date in normalized_dates},
            )
            if html_data_version != expected_data_version:
                errors.append(
                    f"{path}: DATA_VERSION mismatch: expected {expected_data_version}, got {html_data_version}"
                )

    if (
        isinstance(loaded_dates, list)
        and date_payloads_by_date is not None
        and all(date in date_payloads_by_date for date in loaded_dates)
    ):
        errors.extend(
            validate_initial_embedded_data(
                html,
                path,
                loaded_dates=loaded_dates,
                date_payloads_by_date=date_payloads_by_date,
            )
        )

    return errors


def _parse_yyyy_mm_dd(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _is_future_date(value: dt.date, today: dt.date) -> bool:
    return value > today


def validate_prestige_excluded_payload(
    path: Path,
    payload: Any,
    *,
    today: dt.date | None = None,
) -> list[str]:
    """Validate the user-facing prestige-excluded audit payload."""
    today = today or dt.date.today()
    errors: list[str] = []
    if not isinstance(payload, dict):
        return [f"{path}: prestige excluded payload must be an object"]

    papers = payload.get("papers")
    if not isinstance(papers, list):
        return [f"{path}: papers must be a list"]

    count = payload.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(papers):
        errors.append(f"{path}: count mismatch: expected {len(papers)}, got {count!r}")

    by_date = payload.get("by_date")
    if not isinstance(by_date, dict):
        errors.append(f"{path}: by_date must be an object")
        by_date = {}

    observed_dates: Counter[str] = Counter()
    observed_institutions: Counter[str] = Counter()
    seen_papers_by_date: set[tuple[str, str]] = set()
    for index, paper in enumerate(papers, 1):
        label = f"{path}: paper#{index}"
        if not isinstance(paper, dict):
            errors.append(f"{label} must be an object")
            continue

        for field in (
            "date",
            "title",
            "arxiv_id",
            "paper_link",
            "authors",
            "prestige_source",
            "prestige_reason",
            "filter_reason",
        ):
            value = paper.get(field)
            if not has_publishable_metadata_text(value):
                errors.append(f"{label} missing {field}")
            elif field != "date" and not has_canonical_text(value):
                errors.append(f"{label} {field} must be canonical text")

        date = paper.get("date")
        if has_non_empty_text(date):
            if DATE_RE.fullmatch(date):
                parsed_date = _parse_yyyy_mm_dd(str(date))
                if parsed_date is None:
                    errors.append(f"{label} date must be a valid calendar date")
                elif _is_future_date(parsed_date, today):
                    errors.append(f"{label} date must not be in the future")
                else:
                    date_text = str(date)
                    observed_dates[date_text] += 1
                    arxiv_id = paper.get("arxiv_id")
                    if has_valid_arxiv_id(arxiv_id):
                        paper_key = (date_text, str(arxiv_id).strip())
                        if paper_key in seen_papers_by_date:
                            errors.append(
                                f"{label} duplicate arxiv_id {paper_key[1]} for {date_text}"
                            )
                        else:
                            seen_papers_by_date.add(paper_key)
            else:
                errors.append(f"{label} date must be YYYY-MM-DD")

        if has_non_empty_text(paper.get("arxiv_id")) and not has_valid_arxiv_id(
            paper.get("arxiv_id")
        ):
            errors.append(f"{label} invalid arxiv_id")
        if has_non_empty_text(paper.get("paper_link")) and not link_matches_arxiv_id(
            paper.get("paper_link"),
            paper.get("arxiv_id"),
        ):
            errors.append(f"{label} paper_link does not match arxiv_id")

        institutions = paper.get("institution_names")
        if institutions is not None and (
            not isinstance(institutions, list)
            or any(not has_publishable_metadata_text(name) for name in institutions)
        ):
            errors.append(
                f"{label} institution_names must be a list of publishable text"
            )
        elif isinstance(institutions, list) and any(
            not has_canonical_text(name) for name in institutions
        ):
            errors.append(
                f"{label} institution_names must be a list of canonical publishable text"
            )
        elif isinstance(institutions, list):
            observed_institutions.update(institutions)

    declared_dates: dict[str, int] = {}
    for date, value in by_date.items():
        if not isinstance(date, str) or not DATE_RE.fullmatch(date):
            errors.append(f"{path}: by_date key must be YYYY-MM-DD: {date!r}")
            continue
        parsed_date = _parse_yyyy_mm_dd(date)
        if parsed_date is None:
            errors.append(f"{path}: by_date[{date}] must be a valid calendar date")
            continue
        if _is_future_date(parsed_date, today):
            errors.append(f"{path}: by_date[{date}] must not be in the future")
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            errors.append(f"{path}: by_date[{date}] must be a positive integer")
            continue
        declared_dates[date] = value

    if sum(declared_dates.values()) != len(papers):
        errors.append(
            f"{path}: by_date total mismatch: expected {len(papers)}, got {sum(declared_dates.values())}"
        )
    for date, observed_count in sorted(observed_dates.items()):
        declared_count = declared_dates.get(date)
        if declared_count != observed_count:
            errors.append(
                f"{path}: by_date[{date}] mismatch: expected {observed_count}, got {declared_count!r}"
            )
    for date in sorted(set(declared_dates) - set(observed_dates)):
        errors.append(f"{path}: by_date[{date}] has no matching paper")

    top_institutions = payload.get("top_institutions")
    if not isinstance(top_institutions, list):
        errors.append(f"{path}: top_institutions must be a list")
        return errors

    seen_institutions: set[str] = set()
    declared_institution_counts: dict[str, int] = {}
    previous_count: int | None = None
    for index, institution in enumerate(top_institutions, 1):
        label = f"{path}: top_institutions[{index}]"
        if not isinstance(institution, dict):
            errors.append(f"{label} must be an object")
            continue
        name = institution.get("name")
        count_value = institution.get("count")
        if not has_non_empty_text(name):
            errors.append(f"{label} missing name")
        elif not has_publishable_metadata_text(name):
            errors.append(f"{label} name must be publishable text")
        elif not has_canonical_text(name):
            errors.append(f"{label} name must be canonical text")
        elif name in seen_institutions:
            errors.append(f"{label} duplicate institution {name}")
        else:
            seen_institutions.add(name)
        if (
            isinstance(count_value, bool)
            or not isinstance(count_value, int)
            or count_value <= 0
        ):
            errors.append(f"{label} count must be a positive integer")
        elif previous_count is not None and count_value > previous_count:
            errors.append(f"{label} counts must be sorted descending")
        if (
            isinstance(count_value, int)
            and not isinstance(count_value, bool)
            and count_value > 0
        ):
            previous_count = count_value
            if (
                has_publishable_metadata_text(name)
                and has_canonical_text(name)
                and name not in declared_institution_counts
            ):
                declared_institution_counts[name] = count_value

    for name, declared_count in declared_institution_counts.items():
        observed_count = observed_institutions.get(name)
        if observed_count is None:
            errors.append(f"{path}: top_institutions[{name}] has no matching paper")
        elif observed_count != declared_count:
            errors.append(
                f"{path}: top_institutions[{name}] count mismatch: expected {observed_count}, got {declared_count!r}"
            )

    if observed_institutions and not declared_institution_counts:
        errors.append(f"{path}: top_institutions must include observed institutions")
    elif declared_institution_counts:
        summary_floor = min(declared_institution_counts.values())
        missing_higher_count_institutions = [
            (name, count)
            for name, count in sorted(
                observed_institutions.items(),
                key=lambda item: (-item[1], item[0]),
            )
            if name not in declared_institution_counts and count > summary_floor
        ]
        for name, count in missing_higher_count_institutions[:5]:
            errors.append(
                f"{path}: top_institutions missing {name} with {count} matching papers"
            )

    return errors


def validate_webpages_data(
    webpages_dir: Path,
    *,
    today: dt.date | None = None,
) -> list[str]:
    """Return publication-blocking errors for a webpages/ directory."""
    today = today or dt.date.today()
    errors: list[str] = []
    data_dir = webpages_dir / "data"
    index_file = data_dir / "index.json"
    site_index_file = webpages_dir / "index.html"

    if webpages_dir.is_symlink() or not webpages_dir.is_dir():
        if not exists_or_symlink(webpages_dir):
            return [f"{webpages_dir}: webpages directory does not exist"]
        return [f"{webpages_dir}: webpages directory must be an ordinary directory"]
    errors.extend(validate_html_page(site_index_file, required_reference="data/"))

    if data_dir.is_symlink() or not data_dir.is_dir():
        if not exists_or_symlink(data_dir):
            errors.append(f"{data_dir}: data directory does not exist")
            return errors
        errors.append(f"{data_dir}: data directory must be an ordinary directory")
        return errors
    if index_file.is_symlink() or not index_file.is_file():
        if not exists_or_symlink(index_file):
            errors.append(f"{index_file}: missing index file")
            return errors
        errors.append(f"{index_file}: index file must be an ordinary JSON file")
        return errors

    index_data, index_error = read_json(index_file)
    if index_error:
        errors.append(index_error)
        return errors
    if not isinstance(index_data, dict):
        errors.append(f"{index_file}: index payload must be an object")
        return errors

    dates = index_data.get("dates")
    if not isinstance(dates, list):
        errors.append(f"{index_file}: dates must be a list")
        dates = []

    normalized_dates: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(dates, 1):
        if not isinstance(value, str) or not DATE_RE.fullmatch(value):
            errors.append(f"{index_file}: dates[{index}] must be YYYY-MM-DD")
            continue
        parsed_date = _parse_yyyy_mm_dd(value)
        if parsed_date is None:
            errors.append(f"{index_file}: dates[{index}] must be a valid calendar date")
            continue
        if _is_future_date(parsed_date, today):
            errors.append(f"{index_file}: dates[{index}] must not be in the future")
        if value in seen:
            errors.append(f"{index_file}: duplicate date {value}")
            continue
        seen.add(value)
        normalized_dates.append(value)

    if not normalized_dates:
        errors.append(f"{index_file}: dates must contain at least one date")

    expected_order = sorted(normalized_dates, reverse=True)
    if normalized_dates != expected_order:
        errors.append(f"{index_file}: dates must be reverse chronological")

    for field in ("initial_days", "load_more_days"):
        value = index_data.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            errors.append(f"{index_file}: {field} must be a positive integer")

    allowed_json_names = {"index.json", PRESTIGE_EXCLUDED_FILENAME}
    for entry in sorted(data_dir.iterdir()):
        if entry.is_symlink():
            errors.append(
                f"{entry}: symlinks are not allowed in published data directory"
            )
            continue
        if entry.is_dir():
            errors.append(f"{entry}: unexpected directory in published data directory")
            continue
        if not entry.is_file():
            errors.append(
                f"{entry}: unexpected filesystem entry in published data directory"
            )
            continue
        if entry.suffix != ".json":
            errors.append(f"{entry}: unexpected file in published data directory")
            continue
        if entry.name in allowed_json_names or DATE_RE.fullmatch(entry.stem):
            continue
        errors.append(f"{entry}: unexpected JSON file in published data directory")

    date_files = sorted(
        path
        for path in data_dir.glob("????-??-??.json")
        if not path.is_symlink() and path.is_file()
    )
    file_dates = {path.stem for path in date_files}
    for date_file in date_files:
        if not DATE_RE.fullmatch(date_file.stem):
            continue
        parsed_date = _parse_yyyy_mm_dd(date_file.stem)
        if parsed_date is None:
            errors.append(f"{date_file}: date file must be a valid calendar date")
            continue
        if _is_future_date(parsed_date, today):
            errors.append(f"{date_file}: date file must not be in the future")
    index_dates = set(normalized_dates)
    for missing in sorted(index_dates - file_dates):
        errors.append(f"{data_dir / (missing + '.json')}: listed in index but missing")
    for stale in sorted(file_dates - index_dates):
        errors.append(f"{data_dir / (stale + '.json')}: stale date file not in index")

    date_payloads_by_date: dict[str, Any] = {}
    for date in normalized_dates:
        date_file = data_dir / f"{date}.json"
        if not exists_or_symlink(date_file):
            continue
        date_data, date_error = read_json(date_file)
        if date_error:
            errors.append(date_error)
            continue
        if not isinstance(date_data, dict):
            errors.append(f"{date_file}: date payload must be an object")
            continue
        date_payloads_by_date[date] = date_data
        ok, payload_errors = validate_date_data_payload(date_data, expected_date=date)
        if not ok:
            for error in payload_errors:
                errors.append(f"{date_file}: {error}")

    errors.extend(
        validate_site_data_manifest(
            site_index_file,
            index_data=index_data,
            normalized_dates=normalized_dates,
            date_payloads_by_date=date_payloads_by_date,
        )
    )

    prestige_page = webpages_dir / "prestige-excluded.html"
    prestige_payload_file = data_dir / PRESTIGE_EXCLUDED_FILENAME
    prestige_page_exists = exists_or_symlink(prestige_page)
    prestige_payload_exists = exists_or_symlink(prestige_payload_file)
    if prestige_payload_exists and not prestige_page_exists:
        errors.append(f"{prestige_page}: missing prestige excluded page")
    if prestige_page_exists:
        errors.extend(
            validate_html_page(
                prestige_page,
                required_reference=f"data/{PRESTIGE_EXCLUDED_FILENAME}",
            )
        )
    if prestige_page_exists and not prestige_payload_exists:
        errors.append(f"{prestige_payload_file}: missing prestige excluded payload")
    if prestige_payload_exists:
        prestige_payload, prestige_error = read_json(prestige_payload_file)
        if prestige_error:
            errors.append(prestige_error)
        else:
            errors.extend(
                validate_prestige_excluded_payload(
                    prestige_payload_file,
                    prestige_payload,
                    today=today,
                )
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate PaperTools user-facing webpage JSON payloads."
    )
    parser.add_argument(
        "--webpages-dir",
        default="webpages",
        type=Path,
        help="Path to the webpages directory.",
    )
    args = parser.parse_args(argv)

    errors = validate_webpages_data(args.webpages_dir)
    if errors:
        print("Published payload validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    index_data, _ = read_json(args.webpages_dir / "data" / "index.json")
    count = len(index_data.get("dates", [])) if isinstance(index_data, dict) else 0
    print(f"Validated {count} published date payloads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
