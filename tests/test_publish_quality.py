from src.utils.publish_quality import (
    is_publishable_paper,
    validate_date_data_payload,
)


def _complete_paper():
    return {
        "arxiv_id": "2605.00001",
        "title": "Complete Agent Paper",
        "summary": "Original abstract.",
        "summary_translation": "中文摘要。",
        "intro_logic": "Intro logic.",
        "core_insight": "Core insight.",
        "methodology": "Methodology.",
        "additional_insights": "Additional insights.",
        "research_value": "Grounded review.",
    }


def test_publishable_paper_requires_generated_fields():
    paper = _complete_paper()
    assert is_publishable_paper(paper) is True

    paper["methodology"] = ""
    assert is_publishable_paper(paper) is False


def test_publishable_paper_rejects_reviewgrounder_error_placeholder():
    paper = _complete_paper()
    paper["research_value"] = "ReviewGrounder 审稿生成失败：timeout"
    paper["reviewgrounder_review"] = {"error": "timeout"}

    assert is_publishable_paper(paper) is False


def test_publishable_paper_accepts_research_value_fallback():
    paper = _complete_paper()
    paper["research_value_source"] = "legacy_research_value_fallback"
    paper["reviewgrounder_review"] = {
        "source": "legacy_research_value_fallback",
        "fallback_reason": "ReviewGrounder dependency unavailable",
    }

    assert is_publishable_paper(paper) is True


def test_publishable_paper_rejects_topic_only_prestige_bypass(monkeypatch):
    monkeypatch.setenv("PRESTIGE_ENABLED", "true")
    monkeypatch.setenv("PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE", "false")
    paper = _complete_paper()
    paper["prestige_result"] = True
    paper["prestige_source"] = "topic_heuristic_bypass"
    paper["prestige_status"] = "bypassed"

    assert is_publishable_paper(paper) is False


def test_date_payload_rejects_empty_or_missing_overview():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "papers": [_complete_paper()]}],
        "overview": "",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "missing daily overview" in errors


def test_date_payload_accepts_complete_daily_page():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "papers": [_complete_paper()]}],
        "overview": "今日速览。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is True
    assert errors == []
