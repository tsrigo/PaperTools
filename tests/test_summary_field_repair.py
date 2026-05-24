from src.core import generate_summary


def _paper(**overrides):
    paper = {
        "title": "Repairable Paper",
        "arxiv_id": "2605.00001",
        "date": "2026-05-19",
        "summary": "Original abstract.",
        "summary_translation": "中文摘要。",
        "intro_logic": "引入逻辑。",
        "core_insight": "核心洞察。",
        "methodology": "",
        "additional_insights": "",
        "research_value": "研究价值。",
    }
    paper.update(overrides)
    return paper


def test_repair_missing_summary_fields_backfills_methodology_and_insights(monkeypatch):
    paper = _paper()

    monkeypatch.setattr(
        generate_summary,
        "generate_methodology",
        lambda *_args, **_kwargs: "修复后的方法论。",
    )
    monkeypatch.setattr(
        generate_summary,
        "generate_additional_insights",
        lambda *_args, **_kwargs: "修复后的额外洞察。",
    )

    generate_summary.repair_missing_summary_fields(
        paper,
        ["methodology", "additional_insights"],
        "paper content",
        providers=[],
        temperature=0.1,
        paper_title="Repairable Paper",
        cache_manager=None,
    )

    assert paper["methodology"] == "修复后的方法论。"
    assert paper["additional_insights"] == "修复后的额外洞察。"
    assert generate_summary.missing_publish_fields(paper) == []


def test_repair_missing_additional_insights_uses_focused_prompt_after_invalid_default(monkeypatch):
    paper = _paper(methodology="方法论。", additional_insights="")
    calls = []

    def invalid_default(*_args, **_kwargs):
        calls.append("default")
        return "生成失败"

    def focused_repair(*_args, **_kwargs):
        calls.append("focused")
        return "聚焦修复后的额外洞察。"

    monkeypatch.setattr(generate_summary, "generate_additional_insights", invalid_default)
    monkeypatch.setattr(
        generate_summary,
        "repair_additional_insights_with_focused_prompt",
        focused_repair,
    )

    generate_summary.repair_missing_summary_fields(
        paper,
        ["additional_insights"],
        "paper content",
        providers=[],
        temperature=0.1,
        paper_title="Repairable Paper",
        cache_manager=None,
    )

    assert calls == ["default", "focused"]
    assert paper["additional_insights"] == "聚焦修复后的额外洞察。"
    assert generate_summary.missing_publish_fields(paper) == []


def test_repair_missing_summary_fields_replaces_failed_research_value(monkeypatch):
    paper = _paper(
        methodology="方法论。",
        additional_insights="额外洞察。",
        research_value="ReviewGrounder 审稿生成失败：timeout",
        reviewgrounder_review={"error": "timeout"},
    )

    monkeypatch.setattr(
        generate_summary,
        "generate_research_value",
        lambda *_args, **_kwargs: "修复后的研究价值评估。",
    )

    generate_summary.repair_missing_summary_fields(
        paper,
        ["research_value", "reviewgrounder_review"],
        "paper content",
        providers=[],
        temperature=0.1,
        paper_title="Repairable Paper",
        cache_manager=None,
    )

    assert paper["research_value"] == "修复后的研究价值评估。"
    assert paper["reviewgrounder_review"]["source"] == "summary_field_repair_fallback"
    assert generate_summary.missing_publish_fields(paper) == []
