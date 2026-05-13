import json

from src.core import generate_unified_index


def _publishable_paper(arxiv_id: str, title: str) -> dict:
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "summary": "Original abstract.",
        "summary_translation": "中文摘要。",
        "intro_logic": "Intro logic.",
        "core_insight": "Core insight.",
        "methodology": "Methodology.",
        "additional_insights": "Additional insights.",
        "research_value": "Research value.",
        "cluster": "Agents",
    }


def test_required_date_regeneration_does_not_merge_stale_published_papers(tmp_path, monkeypatch):
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
        "overview": "Existing overview.",
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

    assert [paper["arxiv_id"] for paper in merged["2026-05-11"]] == ["2605.00001", "2605.00002"]
    assert [paper["arxiv_id"] for paper in replaced["2026-05-11"]] == ["2605.00001"]
