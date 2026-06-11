from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from scripts.validate_published_payloads import (
    validate_html_page,
    validate_webpages_data,
)
from src.utils.published_data_version import build_published_data_version
from src.utils.published_webpage_data import project_embedded_clusters


def _complete_paper() -> dict:
    return {
        "arxiv_id": "2605.00001",
        "title": "Complete Agent Paper",
        "link": "https://arxiv.org/abs/2605.00001",
        "authors": "Ada Lovelace, Alan Turing",
        "category": "cs.AI",
        "tags": ["cs.AI"],
        "filter_reason": "",
        "summary": "Original abstract.",
        "summary_translation": "中文摘要。",
        "intro_logic": "Intro logic.",
        "core_insight": "Core insight.",
        "methodology": "Methodology.",
        "additional_insights": "Additional insights.",
        "research_value": "Grounded review.",
        "research_value_source": "",
        "research_value_model": "",
        "research_value_reasoning_effort": "",
        "affiliations": "",
        "cluster": "Agents",
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_index_html(
    webpages: Path,
    *,
    available_dates: list[str] | None = None,
    loaded_dates: list[str] | None = None,
    load_more_days: int = 7,
    data_version: str = "abcdef123456",
    date_payloads_by_date: dict[str, dict] | None = None,
) -> None:
    available_dates = available_dates or ["2026-05-12"]
    loaded_dates = loaded_dates or ["2026-05-12"]
    date_payloads_by_date = date_payloads_by_date or {"2026-05-12": _date_payload()}
    all_papers = {
        date: project_embedded_clusters(date_payloads_by_date[date])
        for date in loaded_dates
        if date in date_payloads_by_date
    }
    all_tags = {
        date: date_payloads_by_date[date]["tags"]
        for date in loaded_dates
        if date in date_payloads_by_date
    }
    overviews = {
        date: date_payloads_by_date[date]["overview"]
        for date in loaded_dates
        if date in date_payloads_by_date
    }
    (webpages / "index.html").parent.mkdir(parents=True, exist_ok=True)
    (webpages / "index.html").write_text(
        f"""<!doctype html>
<html>
<body>
<script>
const allPapers = {json.dumps(all_papers, ensure_ascii=False)};

const allPaperTags = {json.dumps(all_tags, ensure_ascii=False)};

const availableDates = {json.dumps(available_dates)};
const loadedDates = new Set({json.dumps(loaded_dates)});
const LOAD_MORE_DAYS = {load_more_days};
const DATA_VERSION = "{data_version}";
fetch(`data/${{availableDates[0]}}.json?v=${{DATA_VERSION}}`);
const dailyOverviewsRaw = {json.dumps(overviews, ensure_ascii=False)};
const dailyOverviews = {{}};
</script>
</body>
</html>""",
        encoding="utf-8",
    )


def _date_payload() -> dict:
    return {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": [{"name": "Agents", "count": 1}, {"name": "cs.AI", "count": 1}],
        "overview": "今日速览 2026-05-12。",
    }


def _write_valid_webpages(tmp_path: Path) -> Path:
    webpages = tmp_path / "webpages"
    data_dir = webpages / "data"
    index_payload = {"dates": ["2026-05-12"], "initial_days": 3, "load_more_days": 7}
    date_payload = _date_payload()
    _write_index_html(
        webpages,
        data_version=build_published_data_version(
            index_payload,
            {"2026-05-12": date_payload},
        ),
        date_payloads_by_date={"2026-05-12": date_payload},
    )
    _write_json(
        data_dir / "index.json",
        index_payload,
    )
    _write_json(data_dir / "2026-05-12.json", date_payload)
    return webpages


def _prestige_excluded_payload() -> dict:
    return {
        "count": 1,
        "by_date": {"2026-05-12": 1},
        "top_institutions": [{"name": "Example Lab", "count": 1}],
        "papers": [
            {
                "date": "2026-05-12",
                "title": "Excluded Agent Paper",
                "arxiv_id": "2605.00002",
                "paper_link": "https://arxiv.org/abs/2605.00002",
                "authors": "Ada Lovelace",
                "institution_names": ["Example Lab"],
                "prestige_source": "llm",
                "prestige_reason": "No strong institution signal.",
                "filter_reason": "Topic matched before prestige gate.",
            }
        ],
    }


def test_validate_webpages_data_accepts_complete_payload(tmp_path):
    webpages = _write_valid_webpages(tmp_path)

    assert validate_webpages_data(webpages) == []


def test_validate_webpages_data_rejects_symlinked_webpages_dir(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    linked_webpages = tmp_path / "linked-webpages"
    linked_webpages.symlink_to(webpages, target_is_directory=True)

    errors = validate_webpages_data(linked_webpages)

    assert any(
        "webpages directory must be an ordinary directory" in error for error in errors
    )


def test_validate_webpages_data_rejects_missing_site_entrypoint(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "index.html").unlink()

    errors = validate_webpages_data(webpages)

    assert any("missing site entrypoint" in error for error in errors)


def test_validate_html_page_reports_read_errors(tmp_path, monkeypatch):
    site_index = tmp_path / "index.html"
    site_index.write_text("<!doctype html><html></html>", encoding="utf-8")
    original_read_text = Path.read_text

    def fail_for_site_index(self, *args, **kwargs):
        if self == site_index:
            raise OSError("boom")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_for_site_index)

    errors = validate_html_page(site_index)

    assert any("failed to read site entrypoint: boom" in error for error in errors)


def test_validate_webpages_data_rejects_non_file_site_entrypoint(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    site_index = webpages / "index.html"
    real_index = webpages / "real-index.html"
    real_index.write_text(site_index.read_text(encoding="utf-8"), encoding="utf-8")
    site_index.unlink()
    site_index.symlink_to(real_index.name)

    errors = validate_webpages_data(webpages)

    assert any(
        "site entrypoint must be an ordinary HTML file" in error for error in errors
    )

    site_index.unlink()
    site_index.mkdir()
    errors = validate_webpages_data(webpages)

    assert any(
        "site entrypoint must be an ordinary HTML file" in error for error in errors
    )

    site_index.rmdir()
    site_index.symlink_to(tmp_path / "missing-index.html")
    errors = validate_webpages_data(webpages)

    assert any(
        "site entrypoint must be an ordinary HTML file" in error for error in errors
    )


def test_validate_webpages_data_rejects_site_without_data_reference(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "index.html").write_text(
        "<!doctype html><html><body>No data here</body></html>",
        encoding="utf-8",
    )

    errors = validate_webpages_data(webpages)

    assert any("does not reference data/" in error for error in errors)


def test_validate_webpages_data_rejects_stale_site_date_manifest(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    _write_index_html(
        webpages,
        available_dates=["2026-05-11"],
        loaded_dates=["2026-05-11"],
    )

    errors = validate_webpages_data(webpages)

    assert any(
        "availableDates manifest must match data/index.json" in error
        for error in errors
    )
    assert any(
        "loadedDates manifest must match the first 3 indexed dates" in error
        for error in errors
    )


def test_validate_webpages_data_rejects_invalid_site_runtime_manifest(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    _write_index_html(webpages, load_more_days=99, data_version="not-a-version")

    errors = validate_webpages_data(webpages)

    assert any(
        "LOAD_MORE_DAYS mismatch: expected 7, got 99" in error for error in errors
    )
    assert any(
        "DATA_VERSION must be a 12-character hex string" in error for error in errors
    )


def test_validate_webpages_data_rejects_boolean_index_counts(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    data_dir = webpages / "data"
    index_payload = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    index_payload["initial_days"] = True
    index_payload["load_more_days"] = True
    _write_json(data_dir / "index.json", index_payload)

    errors = validate_webpages_data(webpages)

    assert any("initial_days must be a positive integer" in error for error in errors)
    assert any("load_more_days must be a positive integer" in error for error in errors)


def test_validate_webpages_data_rejects_stale_site_data_version(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    _write_index_html(webpages, data_version="000000000000")

    errors = validate_webpages_data(webpages)

    assert any("DATA_VERSION mismatch" in error for error in errors)


def test_validate_webpages_data_rejects_stale_initial_embedded_data(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    index_payload = json.loads(
        (webpages / "data" / "index.json").read_text(encoding="utf-8")
    )
    date_payload = json.loads(
        (webpages / "data" / "2026-05-12.json").read_text(encoding="utf-8")
    )
    stale_payload = json.loads(json.dumps(date_payload))
    stale_payload["clusters"][0]["papers"][0]["title"] = "Stale title"
    stale_payload["tags"] = [{"name": "Stale", "count": 1}]
    stale_payload["overview"] = "陈旧速览 2026-05-12。"
    _write_index_html(
        webpages,
        data_version=build_published_data_version(
            index_payload,
            {"2026-05-12": date_payload},
        ),
        date_payloads_by_date={"2026-05-12": stale_payload},
    )

    errors = validate_webpages_data(webpages)

    assert any(
        "allPapers embedded data mismatch for 2026-05-12" in error for error in errors
    )
    assert any(
        "allPaperTags embedded data mismatch for 2026-05-12" in error
        for error in errors
    )
    assert any(
        "dailyOverviewsRaw embedded data mismatch for 2026-05-12" in error
        for error in errors
    )


def test_validate_webpages_data_rejects_missing_index_date_file(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "data" / "2026-05-12.json").unlink()

    errors = validate_webpages_data(webpages)

    assert any("listed in index but missing" in error for error in errors)


def test_validate_webpages_data_rejects_symlinked_indexed_date_payload(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    data_dir = webpages / "data"
    date_file = data_dir / "2026-05-12.json"
    real_date_file = tmp_path / "outside-date.json"
    real_date_file.write_text(date_file.read_text(encoding="utf-8"), encoding="utf-8")
    date_file.unlink()
    date_file.symlink_to(real_date_file)

    errors = validate_webpages_data(webpages)

    assert any(
        "symlinks are not allowed in published data directory" in error
        for error in errors
    )
    assert any("JSON payload must be an ordinary file" in error for error in errors)
    assert any("listed in index but missing" in error for error in errors)


def test_validate_webpages_data_rejects_directory_instead_of_indexed_date_payload(
    tmp_path,
):
    webpages = _write_valid_webpages(tmp_path)
    date_file = webpages / "data" / "2026-05-12.json"
    date_file.unlink()
    date_file.mkdir()

    errors = validate_webpages_data(webpages)

    assert any(
        "unexpected directory in published data directory" in error for error in errors
    )
    assert any("JSON payload must be an ordinary file" in error for error in errors)
    assert any("listed in index but missing" in error for error in errors)


def test_validate_webpages_data_rejects_non_directory_data_dir(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    data_dir = webpages / "data"
    real_data_dir = webpages / "real-data"
    data_dir.rename(real_data_dir)
    data_dir.symlink_to(real_data_dir, target_is_directory=True)

    errors = validate_webpages_data(webpages)

    assert any(
        "data directory must be an ordinary directory" in error for error in errors
    )


def test_validate_webpages_data_rejects_non_file_index_json(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    index_file = webpages / "data" / "index.json"
    index_file.unlink()
    index_file.mkdir()

    errors = validate_webpages_data(webpages)

    assert any("index file must be an ordinary JSON file" in error for error in errors)

    index_file.rmdir()
    index_file.symlink_to(tmp_path / "missing-index.json")
    errors = validate_webpages_data(webpages)

    assert any("index file must be an ordinary JSON file" in error for error in errors)


def test_validate_webpages_data_rejects_stale_date_file(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    _write_json(webpages / "data" / "2026-05-11.json", {"date": "2026-05-11"})

    errors = validate_webpages_data(webpages)

    assert any("stale date file not in index" in error for error in errors)


def test_validate_webpages_data_rejects_unexpected_json_payload(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    _write_json(webpages / "data" / "debug.json", {"ok": True})

    errors = validate_webpages_data(webpages)

    assert any("unexpected JSON file" in error for error in errors)


def test_validate_webpages_data_rejects_unexpected_data_directory_entries(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    data_dir = webpages / "data"
    (data_dir / ".publish-stage-leftover").mkdir()
    (data_dir / "partial.tmp").write_text("{}", encoding="utf-8")
    (data_dir / "linked.json").symlink_to(data_dir / "index.json")

    errors = validate_webpages_data(webpages)

    assert any(
        "unexpected directory in published data directory" in error for error in errors
    )
    assert any(
        "unexpected file in published data directory" in error for error in errors
    )
    assert any(
        "symlinks are not allowed in published data directory" in error
        for error in errors
    )


def test_validate_webpages_data_validates_prestige_excluded_payload(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body><script>fetch('data/prestige_excluded_papers.json')</script></body></html>",
        encoding="utf-8",
    )
    _write_json(
        webpages / "data" / "prestige_excluded_papers.json",
        _prestige_excluded_payload(),
    )

    assert validate_webpages_data(webpages) == []


def test_validate_webpages_data_rejects_invalid_prestige_excluded_payload(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body><script>fetch('data/prestige_excluded_papers.json')</script></body></html>",
        encoding="utf-8",
    )
    payload = _prestige_excluded_payload()
    payload["count"] = 2
    payload["by_date"] = {"2026-05-12": 2}
    payload["papers"][0]["paper_link"] = "https://arxiv.org/abs/2605.99999"
    payload["top_institutions"] = [
        {"name": "Small Lab", "count": 1},
        {"name": "Large Lab", "count": 2},
    ]
    _write_json(webpages / "data" / "prestige_excluded_papers.json", payload)

    errors = validate_webpages_data(webpages)

    assert any("count mismatch" in error for error in errors)
    assert any("paper_link does not match arxiv_id" in error for error in errors)
    assert any("by_date[2026-05-12] mismatch" in error for error in errors)
    assert any("counts must be sorted descending" in error for error in errors)


def test_validate_webpages_data_rejects_stale_prestige_institution_summary(
    tmp_path,
):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body><script>fetch('data/prestige_excluded_papers.json')</script></body></html>",
        encoding="utf-8",
    )
    payload = _prestige_excluded_payload()
    second_paper = json.loads(json.dumps(payload["papers"][0]))
    second_paper["arxiv_id"] = "2605.00003"
    second_paper["paper_link"] = "https://arxiv.org/abs/2605.00003"
    second_paper["institution_names"] = ["Better Lab"]
    third_paper = json.loads(json.dumps(payload["papers"][0]))
    third_paper["arxiv_id"] = "2605.00004"
    third_paper["paper_link"] = "https://arxiv.org/abs/2605.00004"
    third_paper["institution_names"] = ["Better Lab"]
    payload["papers"].extend([second_paper, third_paper])
    payload["count"] = 3
    payload["by_date"] = {"2026-05-12": 3}
    payload["top_institutions"] = [
        {"name": "Example Lab", "count": 2},
        {"name": "Stale Lab", "count": 1},
    ]
    _write_json(webpages / "data" / "prestige_excluded_papers.json", payload)

    errors = validate_webpages_data(webpages)

    assert any(
        "top_institutions[Example Lab] count mismatch: expected 1, got 2" in error
        for error in errors
    )
    assert any(
        "top_institutions[Stale Lab] has no matching paper" in error for error in errors
    )
    assert any(
        "top_institutions missing Better Lab with 2 matching papers" in error
        for error in errors
    )


def test_validate_webpages_data_rejects_duplicate_prestige_paper_for_same_date(
    tmp_path,
):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body><script>fetch('data/prestige_excluded_papers.json')</script></body></html>",
        encoding="utf-8",
    )
    payload = _prestige_excluded_payload()
    payload["papers"].append(dict(payload["papers"][0]))
    payload["count"] = 2
    payload["by_date"] = {"2026-05-12": 2}
    _write_json(webpages / "data" / "prestige_excluded_papers.json", payload)

    errors = validate_webpages_data(webpages)

    assert any(
        "duplicate arxiv_id 2605.00002 for 2026-05-12" in error for error in errors
    )


def test_validate_webpages_data_rejects_boolean_prestige_counts(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body><script>fetch('data/prestige_excluded_papers.json')</script></body></html>",
        encoding="utf-8",
    )
    payload = _prestige_excluded_payload()
    payload["count"] = True
    payload["by_date"] = {"2026-05-12": True}
    payload["top_institutions"][0]["count"] = True
    _write_json(webpages / "data" / "prestige_excluded_papers.json", payload)

    errors = validate_webpages_data(webpages)

    assert any("count mismatch: expected 1, got True" in error for error in errors)
    assert any(
        "by_date[2026-05-12] must be a positive integer" in error for error in errors
    )
    assert any(
        "top_institutions[1] count must be a positive integer" in error
        for error in errors
    )


def test_validate_webpages_data_rejects_placeholder_prestige_excluded_metadata(
    tmp_path,
):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body><script>fetch('data/prestige_excluded_papers.json')</script></body></html>",
        encoding="utf-8",
    )
    payload = _prestige_excluded_payload()
    payload["papers"][0]["authors"] = "Unknown"
    payload["papers"][0]["prestige_reason"] = "N/A"
    payload["papers"][0]["institution_names"] = ["TBD"]
    payload["top_institutions"][0]["name"] = "Unknown"
    _write_json(webpages / "data" / "prestige_excluded_papers.json", payload)

    errors = validate_webpages_data(webpages)

    assert any("missing authors" in error for error in errors)
    assert any("missing prestige_reason" in error for error in errors)
    assert any(
        "institution_names must be a list of publishable text" in error
        for error in errors
    )
    assert any("name must be publishable text" in error for error in errors)


def test_validate_webpages_data_rejects_noncanonical_prestige_metadata(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body><script>fetch('data/prestige_excluded_papers.json')</script></body></html>",
        encoding="utf-8",
    )
    payload = _prestige_excluded_payload()
    payload["papers"][0]["title"] = " Excluded Agent Paper"
    payload["papers"][0]["paper_link"] = "https://arxiv.org/abs/2605.00002 "
    payload["papers"][0]["institution_names"] = ["Example Lab "]
    payload["top_institutions"][0]["name"] = "Example Lab "
    _write_json(webpages / "data" / "prestige_excluded_papers.json", payload)

    errors = validate_webpages_data(webpages)

    assert any("title must be canonical text" in error for error in errors)
    assert any("paper_link must be canonical text" in error for error in errors)
    assert any(
        "institution_names must be a list of canonical publishable text" in error
        for error in errors
    )
    assert any(
        "top_institutions[1] name must be canonical text" in error for error in errors
    )


def test_validate_webpages_data_rejects_missing_prestige_excluded_page(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    _write_json(
        webpages / "data" / "prestige_excluded_papers.json",
        _prestige_excluded_payload(),
    )

    errors = validate_webpages_data(webpages)

    assert any("missing prestige excluded page" in error for error in errors)


def test_validate_webpages_data_rejects_prestige_page_without_payload_reference(
    tmp_path,
):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body>No payload here</body></html>",
        encoding="utf-8",
    )
    _write_json(
        webpages / "data" / "prestige_excluded_papers.json",
        _prestige_excluded_payload(),
    )

    errors = validate_webpages_data(webpages)

    assert any(
        "does not reference data/prestige_excluded_papers.json" in error
        for error in errors
    )


def test_validate_webpages_data_rejects_broken_symlink_prestige_payload(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body><script>fetch('data/prestige_excluded_papers.json')</script></body></html>",
        encoding="utf-8",
    )
    prestige_payload = webpages / "data" / "prestige_excluded_papers.json"
    prestige_payload.symlink_to(tmp_path / "missing-prestige.json")

    errors = validate_webpages_data(webpages)

    assert any(
        "symlinks are not allowed in published data directory" in error
        for error in errors
    )
    assert any("JSON payload must be an ordinary file" in error for error in errors)
    assert not any("missing prestige excluded payload" in error for error in errors)


def test_validate_webpages_data_rejects_partial_payload(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    date_file = webpages / "data" / "2026-05-12.json"
    payload = json.loads(date_file.read_text(encoding="utf-8"))
    payload["clusters"][0]["papers"][0]["methodology"] = ""
    _write_json(date_file, payload)

    errors = validate_webpages_data(webpages)

    assert any("missing methodology" in error for error in errors)


def test_validate_webpages_data_rejects_placeholder_generated_content(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    date_file = webpages / "data" / "2026-05-12.json"
    payload = json.loads(date_file.read_text(encoding="utf-8"))
    payload["clusters"][0]["papers"][0]["summary_translation"] = "N/A"
    payload["overview"] = "TBD"
    _write_json(date_file, payload)

    errors = validate_webpages_data(webpages)

    assert any("missing summary_translation" in error for error in errors)
    assert any("missing daily overview" in error for error in errors)


def test_validate_webpages_data_rejects_english_only_summary_translation(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    date_file = webpages / "data" / "2026-05-12.json"
    payload = json.loads(date_file.read_text(encoding="utf-8"))
    payload["clusters"][0]["papers"][0]["summary_translation"] = (
        "This is still the English abstract."
    )
    _write_json(date_file, payload)

    errors = validate_webpages_data(webpages)

    assert any("missing summary_translation" in error for error in errors)


def test_validate_webpages_data_rejects_english_only_daily_overview(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    date_file = webpages / "data" / "2026-05-12.json"
    payload = json.loads(date_file.read_text(encoding="utf-8"))
    payload["overview"] = "Daily overview 2026-05-12."
    _write_json(date_file, payload)

    errors = validate_webpages_data(webpages)

    assert any("daily overview must contain Chinese text" in error for error in errors)


def test_validate_webpages_data_rejects_missing_paper_identity_metadata(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    date_file = webpages / "data" / "2026-05-12.json"
    payload = json.loads(date_file.read_text(encoding="utf-8"))
    payload["clusters"][0]["papers"][0]["authors"] = ""
    payload["clusters"][0]["papers"][0]["category"] = ""
    _write_json(date_file, payload)

    errors = validate_webpages_data(webpages)

    assert any("missing authors, category" in error for error in errors)


def test_validate_webpages_data_rejects_placeholder_paper_identity_metadata(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    date_file = webpages / "data" / "2026-05-12.json"
    payload = json.loads(date_file.read_text(encoding="utf-8"))
    payload["clusters"][0]["papers"][0]["authors"] = "Unknown"
    payload["clusters"][0]["papers"][0]["category"] = "TBD"
    _write_json(date_file, payload)

    errors = validate_webpages_data(webpages)

    assert any("missing authors, category" in error for error in errors)


def test_validate_webpages_data_rejects_invalid_arxiv_category(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    date_file = webpages / "data" / "2026-05-12.json"
    payload = json.loads(date_file.read_text(encoding="utf-8"))
    payload["clusters"][0]["papers"][0]["category"] = "Artificial Intelligence"
    _write_json(date_file, payload)

    errors = validate_webpages_data(webpages)

    assert any("missing category" in error for error in errors)


def test_validate_webpages_data_rejects_missing_category_filter_tag(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    date_file = webpages / "data" / "2026-05-12.json"
    payload = json.loads(date_file.read_text(encoding="utf-8"))
    payload["clusters"][0]["papers"][0]["tags"] = []
    payload["tags"] = [{"name": "Agents", "count": 1}]
    _write_json(date_file, payload)

    errors = validate_webpages_data(webpages)

    assert any("missing category tag cs.AI" in error for error in errors)


def test_validate_webpages_data_rejects_unsorted_index_dates(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    data_dir = webpages / "data"
    _write_json(
        data_dir / "index.json",
        {
            "dates": ["2026-05-11", "2026-05-12"],
            "initial_days": 3,
            "load_more_days": 7,
        },
    )
    _write_json(
        data_dir / "2026-05-11.json",
        {
            "date": "2026-05-11",
            "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
            "tags": [{"name": "Agents", "count": 1}],
            "overview": "昨日速览 2026-05-11。",
        },
    )

    errors = validate_webpages_data(webpages)

    assert any("reverse chronological" in error for error in errors)


def test_validate_webpages_data_rejects_future_index_and_date_files(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    data_dir = webpages / "data"
    future_paper = _complete_paper()
    future_paper["arxiv_id"] = "2606.00001"
    future_paper["link"] = "https://arxiv.org/abs/2606.00001"

    _write_json(
        data_dir / "index.json",
        {
            "dates": ["2026-06-01", "2026-05-12"],
            "initial_days": 3,
            "load_more_days": 7,
        },
    )
    _write_json(
        data_dir / "2026-06-01.json",
        {
            "date": "2026-06-01",
            "clusters": [{"name": "Agents", "count": 1, "papers": [future_paper]}],
            "tags": [{"name": "Agents", "count": 1}],
            "overview": "未来速览 2026-06-01。",
        },
    )

    errors = validate_webpages_data(webpages, today=dt.date(2026, 5, 31))

    assert any("dates[1] must not be in the future" in error for error in errors)
    assert any("date file must not be in the future" in error for error in errors)


def test_validate_webpages_data_rejects_invalid_calendar_dates_without_crashing(
    tmp_path,
):
    webpages = _write_valid_webpages(tmp_path)
    data_dir = webpages / "data"
    invalid_date = "2026-02-31"

    _write_json(
        data_dir / "index.json",
        {
            "dates": [invalid_date],
            "initial_days": 3,
            "load_more_days": 7,
        },
    )
    _write_json(
        data_dir / f"{invalid_date}.json",
        {
            "date": invalid_date,
            "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
            "tags": [{"name": "Agents", "count": 1}],
            "overview": "无效日期速览。",
        },
    )

    errors = validate_webpages_data(webpages, today=dt.date(2026, 5, 31))

    assert any("dates[1] must be a valid calendar date" in error for error in errors)
    assert any("date file must be a valid calendar date" in error for error in errors)


def test_validate_webpages_data_rejects_future_prestige_dates(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body><script>fetch('data/prestige_excluded_papers.json')</script></body></html>",
        encoding="utf-8",
    )
    payload = _prestige_excluded_payload()
    payload["by_date"] = {"2026-06-01": 1}
    payload["papers"][0]["date"] = "2026-06-01"
    _write_json(webpages / "data" / "prestige_excluded_papers.json", payload)

    errors = validate_webpages_data(webpages, today=dt.date(2026, 5, 31))

    assert any("paper#1 date must not be in the future" in error for error in errors)
    assert any(
        "by_date[2026-06-01] must not be in the future" in error for error in errors
    )


def test_validate_webpages_data_rejects_invalid_prestige_calendar_dates(tmp_path):
    webpages = _write_valid_webpages(tmp_path)
    (webpages / "prestige-excluded.html").write_text(
        "<!doctype html><html><body><script>fetch('data/prestige_excluded_papers.json')</script></body></html>",
        encoding="utf-8",
    )
    payload = _prestige_excluded_payload()
    payload["by_date"] = {"2026-02-31": 1}
    payload["papers"][0]["date"] = "2026-02-31"
    _write_json(webpages / "data" / "prestige_excluded_papers.json", payload)

    errors = validate_webpages_data(webpages, today=dt.date(2026, 5, 31))

    assert any(
        "paper#1 date must be a valid calendar date" in error for error in errors
    )
    assert any(
        "by_date[2026-02-31] must be a valid calendar date" in error for error in errors
    )
