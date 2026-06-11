import json

import pytest

from scripts.validate_published_payloads import validate_webpages_data
from src.core import generate_unified_index


def _publishable_paper(arxiv_id: str, title: str) -> dict:
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "link": f"https://arxiv.org/abs/{arxiv_id}",
        "authors": "Ada Lovelace, Alan Turing",
        "category": "cs.AI",
        "tags": ["cs.AI"],
        "summary": "Original abstract.",
        "summary_translation": "中文摘要。",
        "intro_logic": "Intro logic.",
        "core_insight": "Core insight.",
        "methodology": "Methodology.",
        "additional_insights": "Additional insights.",
        "research_value": "Research value.",
        "cluster": "Agents",
    }


def test_required_date_regeneration_does_not_merge_stale_published_papers(
    tmp_path, monkeypatch
):
    summary_dir = tmp_path / "summary"
    domain_dir = tmp_path / "domain_paper"
    webpages_dir = tmp_path / "webpages"
    data_dir = webpages_dir / "data"
    arxiv_dir = tmp_path / "arxiv_paper"
    for path in (summary_dir, domain_dir, data_dir, arxiv_dir):
        path.mkdir(parents=True)

    current = [_publishable_paper("2605.00001", "Current Paper")]
    published = {
        "date": "2026-05-11",
        "overview": "已有速览 2026-05-11。",
        "clusters": [
            {
                "name": "Agents",
                "papers": [
                    _publishable_paper("2605.00001", "Current Paper"),
                    _publishable_paper("2605.00002", "Stale Paper"),
                ],
            }
        ],
    }

    (summary_dir / "clustered_papers_2026-05-11_with_summary2.json").write_text(
        json.dumps(current),
        encoding="utf-8",
    )
    (data_dir / "2026-05-11.json").write_text(
        json.dumps(published),
        encoding="utf-8",
    )

    monkeypatch.setattr(generate_unified_index, "SUMMARY_DIR", str(summary_dir))
    monkeypatch.setattr(generate_unified_index, "DOMAIN_PAPER_DIR", str(domain_dir))
    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))
    monkeypatch.setattr(generate_unified_index, "ARXIV_PAPER_DIR", str(arxiv_dir))

    merged = generate_unified_index.load_paper_data()
    replaced = generate_unified_index.load_paper_data(replace_dates={"2026-05-11"})

    assert [paper["arxiv_id"] for paper in merged["2026-05-11"]] == [
        "2605.00001",
        "2605.00002",
    ]
    assert [paper["arxiv_id"] for paper in replaced["2026-05-11"]] == ["2605.00001"]


def test_unified_index_script_data_escapes_script_breakout():
    escaped = generate_unified_index.escape_js_string(
        '</script><script>alert("x")</script>'
    )

    assert "</script>" not in escaped
    assert "<script>" not in escaped
    assert "\\u003C/script\\u003E\\u003Cscript\\u003E" in escaped


def test_unified_index_html_uses_safe_render_helpers(tmp_path, monkeypatch):
    webpages_dir = tmp_path / "webpages"
    paper = _publishable_paper(
        "2605.00003",
        '</script><script>alert("title")</script>',
    )
    paper.update(
        {
            "authors": "<img src=x onerror=alert(1)>",
            "summary": "Original abstract <script>alert(2)</script>",
            "summary_translation": "中文摘要 <iframe src=evil></iframe>",
            "filter_reason": "[bad](javascript:alert(3))",
            "tags": ["cs.AI", '</script><script>alert("tag")</script>'],
        }
    )

    monkeypatch.setattr(
        generate_unified_index,
        "load_paper_data",
        lambda replace_dates=None: {"2026-05-31": [paper]},
    )
    monkeypatch.setattr(
        generate_unified_index,
        "load_daily_overviews",
        lambda: {"2026-05-31": "今日速览 2026-05-31 <script>alert(4)</script>"},
    )
    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))

    html = generate_unified_index.generate_complete_html()

    assert '</script><script>alert("title")</script>' not in html
    assert '</script><script>alert("tag")</script>' not in html
    assert "今日速览 2026-05-31 <script>alert(4)</script>" not in html
    assert "\\u003C/script\\u003E\\u003Cscript\\u003Ealert" in html
    assert "marked.parse(escapeMarkdownHtml(raw))" in html
    assert "sanitizeRenderedMarkdown(el)" in html
    assert "const titleHtml = escapeHtml(paper.title)" in html
    assert "formatAuthorsWithAffiliations(paper.authors, paper.affiliations)" in html


def test_generated_unified_index_embedded_data_passes_publish_validator(
    tmp_path, monkeypatch
):
    webpages_dir = tmp_path / "webpages"
    paper = _publishable_paper("2605.00005", "Generated Paper")
    paper.update(
        {
            "authors": "Ada Lovelace",
            "category": "cs.AI",
            "tags": ["cs.AI"],
            "filter_reason": "Relevant agent paper.",
            "affiliations": "",
        }
    )

    monkeypatch.setattr(
        generate_unified_index,
        "load_paper_data",
        lambda replace_dates=None: {"2026-05-31": [paper]},
    )
    monkeypatch.setattr(
        generate_unified_index,
        "load_daily_overviews",
        lambda: {"2026-05-31": "今日速览 2026-05-31。"},
    )
    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))

    html = generate_unified_index.generate_complete_html()
    (webpages_dir / "index.html").write_text(html, encoding="utf-8")

    assert validate_webpages_data(webpages_dir) == []


def test_unified_index_candidate_fails_closed_when_quality_gate_unavailable(
    monkeypatch, capsys
):
    paper = _publishable_paper("2605.00004", "Candidate Paper")

    monkeypatch.setattr(
        generate_unified_index,
        "validate_publishable_papers",
        lambda papers, *, context="papers": (
            False,
            [f"{context}: publication quality gate unavailable"],
        ),
    )

    assert generate_unified_index.publishable_papers_or_none([paper], "summary") is None
    assert "publication quality gate unavailable" in capsys.readouterr().out


def test_unified_index_save_date_data_fails_when_quality_gate_unavailable(
    tmp_path, monkeypatch
):
    webpages_dir = tmp_path / "webpages"
    paper = _publishable_paper("2605.00005", "Daily Paper")

    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))
    monkeypatch.setattr(
        generate_unified_index,
        "validate_date_data_payload",
        lambda date_data, *, expected_date="": (
            False,
            ["publication quality gate unavailable"],
        ),
    )

    with pytest.raises(ValueError, match="publication quality gate unavailable"):
        generate_unified_index.save_date_data_files(
            {"2026-05-12": [paper]},
            {"2026-05-12": "今日速览。"},
        )

    assert not (webpages_dir / "data" / "2026-05-12.json").exists()


def test_unified_index_save_date_data_does_not_prune_before_validation(
    tmp_path, monkeypatch
):
    webpages_dir = tmp_path / "webpages"
    data_dir = webpages_dir / "data"
    data_dir.mkdir(parents=True)
    stale_file = data_dir / "2026-05-11.json"
    stale_file.write_text('{"date": "2026-05-11"}', encoding="utf-8")
    paper = _publishable_paper("2605.00005", "Daily Paper")

    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))
    monkeypatch.setattr(
        generate_unified_index,
        "validate_date_data_payload",
        lambda date_data, *, expected_date="": (
            False,
            ["publication quality gate unavailable"],
        ),
    )

    with pytest.raises(ValueError, match="publication quality gate unavailable"):
        generate_unified_index.save_date_data_files(
            {"2026-05-12": [paper]},
            {"2026-05-12": "今日速览 2026-05-12。"},
        )

    assert stale_file.exists()
    assert not (data_dir / "2026-05-12.json").exists()


def test_unified_index_save_date_data_stages_before_visible_write(
    tmp_path, monkeypatch
):
    webpages_dir = tmp_path / "webpages"
    data_dir = webpages_dir / "data"
    data_dir.mkdir(parents=True)
    stale_file = data_dir / "2026-05-11.json"
    stale_file.write_text('{"date": "2026-05-11"}', encoding="utf-8")
    index_file = data_dir / "index.json"
    index_file.write_text('{"dates": ["2026-05-11"]}', encoding="utf-8")
    paper = _publishable_paper("2605.00005", "Daily Paper")

    def fail_staged_date_write(filepath, data, indent=2, ensure_ascii=False):
        if filepath.endswith("2026-05-12.json"):
            return False
        return generate_unified_index._atomic_save_json(
            filepath,
            data,
            indent=indent,
            ensure_ascii=ensure_ascii,
        )

    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))
    monkeypatch.setattr(generate_unified_index, "save_json", fail_staged_date_write)

    with pytest.raises(OSError, match="暂存数据文件失败"):
        generate_unified_index.save_date_data_files(
            {"2026-05-12": [paper]},
            {"2026-05-12": "今日速览 2026-05-12。"},
        )

    assert stale_file.read_text(encoding="utf-8") == '{"date": "2026-05-11"}'
    assert index_file.read_text(encoding="utf-8") == '{"dates": ["2026-05-11"]}'
    assert not (data_dir / "2026-05-12.json").exists()
    assert list(data_dir.glob(".publish-stage-*")) == []


def test_unified_index_save_date_data_rolls_back_commit_failure(tmp_path, monkeypatch):
    webpages_dir = tmp_path / "webpages"
    data_dir = webpages_dir / "data"
    data_dir.mkdir(parents=True)
    old_date_file = data_dir / "2026-05-12.json"
    old_date_file.write_text('{"date": "2026-05-12", "old": true}', encoding="utf-8")
    stale_file = data_dir / "2026-05-11.json"
    stale_file.write_text('{"date": "2026-05-11"}', encoding="utf-8")
    index_file = data_dir / "index.json"
    index_file.write_text('{"dates": ["2026-05-12", "2026-05-11"]}', encoding="utf-8")
    paper = _publishable_paper("2605.00005", "Daily Paper")
    original_replace = generate_unified_index.os.replace

    def fail_index_commit(src, dst):
        src_path = str(src)
        dst_path = generate_unified_index.Path(dst)
        if (
            ".publish-stage-" in src_path
            and dst_path.parent == data_dir
            and dst_path.name == "index.json"
        ):
            raise OSError("index replace failed")
        return original_replace(src, dst)

    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))
    monkeypatch.setattr(generate_unified_index.os, "replace", fail_index_commit)

    with pytest.raises(OSError, match="index replace failed"):
        generate_unified_index.save_date_data_files(
            {"2026-05-12": [paper]},
            {"2026-05-12": "今日速览 2026-05-12。"},
        )

    assert old_date_file.read_text(encoding="utf-8") == (
        '{"date": "2026-05-12", "old": true}'
    )
    assert stale_file.read_text(encoding="utf-8") == '{"date": "2026-05-11"}'
    assert index_file.read_text(encoding="utf-8") == (
        '{"dates": ["2026-05-12", "2026-05-11"]}'
    )
    assert list(data_dir.glob(".publish-stage-*")) == []


def test_unified_index_save_date_data_rejects_empty_publish_set(tmp_path, monkeypatch):
    webpages_dir = tmp_path / "webpages"
    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))

    with pytest.raises(ValueError, match="没有可发布日期"):
        generate_unified_index.save_date_data_files({}, {})

    assert not (webpages_dir / "data" / "index.json").exists()


def test_unified_index_main_fails_when_release_validator_fails(
    tmp_path, monkeypatch, capsys
):
    webpages_dir = tmp_path / "webpages"

    monkeypatch.setattr(
        generate_unified_index.sys, "argv", ["generate_unified_index.py"]
    )
    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))
    monkeypatch.setattr(
        generate_unified_index,
        "generate_complete_html",
        lambda replace_dates=None: "<!doctype html><html></html>",
    )
    monkeypatch.setattr(
        generate_unified_index,
        "validate_generated_webpages_for_publication",
        lambda: (_ for _ in ()).throw(ValueError("bad published payload")),
    )

    assert generate_unified_index.main() == 1
    assert "bad published payload" in capsys.readouterr().out
    assert not (webpages_dir / "index.html").exists()


def test_unified_index_main_restores_existing_html_when_validator_fails(
    tmp_path, monkeypatch
):
    webpages_dir = tmp_path / "webpages"
    webpages_dir.mkdir()
    index_file = webpages_dir / "index.html"
    index_file.write_text("previous html", encoding="utf-8")

    monkeypatch.setattr(
        generate_unified_index.sys, "argv", ["generate_unified_index.py"]
    )
    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))
    monkeypatch.setattr(
        generate_unified_index,
        "generate_complete_html",
        lambda replace_dates=None: "<!doctype html><html>invalid</html>",
    )
    monkeypatch.setattr(
        generate_unified_index,
        "validate_generated_webpages_for_publication",
        lambda: (_ for _ in ()).throw(ValueError("bad published payload")),
    )

    assert generate_unified_index.main() == 1
    assert index_file.read_text(encoding="utf-8") == "previous html"


def test_unified_index_main_removes_candidate_data_dir_when_validator_fails(
    tmp_path, monkeypatch
):
    webpages_dir = tmp_path / "webpages"
    data_dir = webpages_dir / "data"

    def generate_candidate(replace_dates=None):
        data_dir.mkdir(parents=True)
        (data_dir / "index.json").write_text(
            '{"dates": ["2026-05-12"]}', encoding="utf-8"
        )
        (data_dir / "2026-05-12.json").write_text(
            '{"date": "2026-05-12"}', encoding="utf-8"
        )
        return "<!doctype html><html>invalid</html>"

    monkeypatch.setattr(
        generate_unified_index.sys, "argv", ["generate_unified_index.py"]
    )
    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))
    monkeypatch.setattr(
        generate_unified_index,
        "generate_complete_html",
        generate_candidate,
    )
    monkeypatch.setattr(
        generate_unified_index,
        "validate_generated_webpages_for_publication",
        lambda: (_ for _ in ()).throw(ValueError("bad published payload")),
    )

    assert generate_unified_index.main() == 1
    assert not data_dir.exists()


def test_unified_index_main_restores_existing_data_dir_when_validator_fails(
    tmp_path, monkeypatch
):
    webpages_dir = tmp_path / "webpages"
    data_dir = webpages_dir / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "index.json").write_text('{"dates": ["2026-05-11"]}', encoding="utf-8")
    (data_dir / "2026-05-11.json").write_text(
        '{"date": "2026-05-11"}', encoding="utf-8"
    )

    def generate_candidate(replace_dates=None):
        (data_dir / "index.json").write_text(
            '{"dates": ["2026-05-12"]}', encoding="utf-8"
        )
        (data_dir / "2026-05-11.json").unlink()
        (data_dir / "2026-05-12.json").write_text(
            '{"date": "2026-05-12"}', encoding="utf-8"
        )
        return "<!doctype html><html>invalid</html>"

    monkeypatch.setattr(
        generate_unified_index.sys, "argv", ["generate_unified_index.py"]
    )
    monkeypatch.setattr(generate_unified_index, "WEBPAGES_DIR", str(webpages_dir))
    monkeypatch.setattr(
        generate_unified_index,
        "generate_complete_html",
        generate_candidate,
    )
    monkeypatch.setattr(
        generate_unified_index,
        "validate_generated_webpages_for_publication",
        lambda: (_ for _ in ()).throw(ValueError("bad published payload")),
    )

    assert generate_unified_index.main() == 1
    assert (data_dir / "index.json").read_text(
        encoding="utf-8"
    ) == '{"dates": ["2026-05-11"]}'
    assert (data_dir / "2026-05-11.json").read_text(
        encoding="utf-8"
    ) == '{"date": "2026-05-11"}'
    assert not (data_dir / "2026-05-12.json").exists()
