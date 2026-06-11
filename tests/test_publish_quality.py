from src.utils.publish_quality import (
    is_publishable_paper,
    missing_publish_fields,
    validate_date_data_payload,
)


def _complete_paper():
    return {
        "arxiv_id": "2605.00001",
        "title": "Complete Agent Paper",
        "link": "https://arxiv.org/abs/2605.00001",
        "authors": "Ada Lovelace, Alan Turing",
        "category": "cs.AI",
        "summary": "Original abstract.",
        "summary_translation": "中文摘要。",
        "intro_logic": "Intro logic.",
        "core_insight": "Core insight.",
        "methodology": "Methodology.",
        "additional_insights": "Additional insights.",
        "research_value": "Grounded review.",
        "tags": ["cs.AI"],
    }


def _tags():
    return [{"name": "Agents", "count": 1}, {"name": "cs.AI", "count": 1}]


def test_publishable_paper_requires_generated_fields():
    paper = _complete_paper()
    assert is_publishable_paper(paper) is True

    paper["methodology"] = ""
    assert is_publishable_paper(paper) is False


def test_publishable_paper_rejects_placeholder_generated_fields():
    paper = _complete_paper()
    paper["summary_translation"] = "N/A"
    paper["methodology"] = "TBD"
    paper["research_value"] = "未知"

    assert is_publishable_paper(paper) is False
    assert {
        "summary_translation",
        "methodology",
        "research_value",
    }.issubset(missing_publish_fields(paper))


def test_publishable_paper_rejects_noncanonical_generated_fields():
    paper = _complete_paper()
    paper["summary"] = " Original abstract."
    paper["methodology"] = "Methodology.\n"
    paper["research_value"] = " Grounded review. "

    assert is_publishable_paper(paper) is False
    assert {"summary", "methodology", "research_value"}.issubset(
        missing_publish_fields(paper)
    )


def test_publishable_paper_requires_chinese_summary_translation():
    paper = _complete_paper()
    paper["summary_translation"] = "This is still the English abstract."

    assert is_publishable_paper(paper) is False
    assert "summary_translation" in missing_publish_fields(paper)


def test_publishable_paper_requires_identity_and_source_link():
    paper = _complete_paper()
    paper["link"] = ""

    assert is_publishable_paper(paper) is False
    assert "link" in missing_publish_fields(paper)


def test_publishable_paper_requires_author_and_category_metadata():
    paper = _complete_paper()
    paper["authors"] = ""
    paper["category"] = " "

    assert is_publishable_paper(paper) is False
    assert {"authors", "category"}.issubset(missing_publish_fields(paper))


def test_publishable_paper_rejects_placeholder_identity_metadata():
    paper = _complete_paper()
    paper["authors"] = "Unknown"
    paper["category"] = "N/A"

    assert is_publishable_paper(paper) is False
    assert {"authors", "category"}.issubset(missing_publish_fields(paper))


def test_publishable_paper_rejects_noncanonical_identity_metadata():
    paper = _complete_paper()
    paper["title"] = " Complete Agent Paper"
    paper["authors"] = "Ada Lovelace, Alan Turing "

    assert is_publishable_paper(paper) is False
    assert {"title", "authors"}.issubset(missing_publish_fields(paper))


def test_publishable_paper_requires_arxiv_category_syntax():
    paper = _complete_paper()
    paper["category"] = "Artificial Intelligence"

    assert is_publishable_paper(paper) is False
    assert "category" in missing_publish_fields(paper)


def test_publishable_paper_requires_valid_arxiv_id_and_matching_link():
    paper = _complete_paper()
    paper["arxiv_id"] = "not-an-arxiv-id"

    assert is_publishable_paper(paper) is False
    assert "arxiv_id" in missing_publish_fields(paper)

    paper = _complete_paper()
    paper["link"] = "https://arxiv.org/abs/2605.99999"

    assert is_publishable_paper(paper) is False
    assert "link" in missing_publish_fields(paper)


def test_publishable_paper_rejects_noncanonical_arxiv_metadata():
    paper = _complete_paper()
    paper["arxiv_id"] = " 2605.00001"
    paper["category"] = "cs.AI "
    paper["link"] = "https://arxiv.org/abs/2605.00001\n"

    assert is_publishable_paper(paper) is False
    assert {"arxiv_id", "category", "link"}.issubset(missing_publish_fields(paper))


def test_publishable_paper_rejects_external_source_link_with_matching_id():
    paper = _complete_paper()
    paper["link"] = "https://example.com/archive/2605.00001"

    assert is_publishable_paper(paper) is False
    assert "link" in missing_publish_fields(paper)


def test_publishable_paper_accepts_arxiv_and_internal_source_links():
    for link in (
        "https://arxiv.org/abs/2605.00001",
        "https://www.arxiv.org/pdf/2605.00001.pdf",
        "/arxiv/2605.00001",
    ):
        paper = _complete_paper()
        paper["link"] = link

        assert is_publishable_paper(paper) is True
        assert "link" not in missing_publish_fields(paper)


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
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": _tags(),
        "overview": "",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "missing daily overview" in errors


def test_date_payload_rejects_placeholder_overview():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": _tags(),
        "overview": "N/A",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "missing daily overview" in errors


def test_date_payload_rejects_noncanonical_overview():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。\n",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "daily overview must be canonical text" in errors


def test_date_payload_rejects_english_only_overview():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": _tags(),
        "overview": "Daily overview 2026-05-12.",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "daily overview must contain Chinese text" in errors


def test_date_payload_rejects_stale_overview_date():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": _tags(),
        "overview": "### 今日AI论文速览 (2026-05-11)\n\n旧日期速览。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "daily overview date mismatch: expected 2026-05-12" in errors


def test_date_payload_accepts_complete_daily_page():
    paper = _complete_paper()
    paper["tags"] = ["cs.AI"]
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [paper]}],
        "tags": [{"name": "Agents", "count": 1}, {"name": "cs.AI", "count": 1}],
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is True
    assert errors == []


def test_date_payload_rejects_missing_cluster_count():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "papers": [_complete_paper()]}],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "cluster#1 missing cluster count" in errors


def test_date_payload_rejects_invalid_cluster_count_type():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": "1", "papers": [_complete_paper()]}],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "cluster#1 count must be a positive integer" in errors


def test_date_payload_rejects_malformed_cluster_entries():
    payload = {
        "date": "2026-05-12",
        "clusters": [
            {"name": "Agents", "count": 1, "papers": [_complete_paper()]},
            "not-a-cluster",
        ],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "cluster#2 must be an object" in errors


def test_date_payload_rejects_invalid_cluster_papers_shape():
    payload = {
        "date": "2026-05-12",
        "clusters": [
            {"name": "Agents", "count": 1, "papers": [_complete_paper()]},
            {"name": "Broken", "papers": {"title": "not a list"}},
        ],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "cluster#2 papers must be a list" in errors


def test_date_payload_rejects_duplicate_cluster_names():
    duplicate = _complete_paper()
    duplicate["arxiv_id"] = "2605.00002"
    duplicate["link"] = "https://arxiv.org/abs/2605.00002"
    payload = {
        "date": "2026-05-12",
        "clusters": [
            {"name": "Agents", "count": 1, "papers": [_complete_paper()]},
            {"name": "Agents", "count": 1, "papers": [duplicate]},
        ],
        "tags": [{"name": "Agents", "count": 2}, {"name": "cs.AI", "count": 2}],
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "duplicate cluster Agents" in errors


def test_date_payload_rejects_non_object_papers_and_count_mismatch():
    payload = {
        "date": "2026-05-12",
        "clusters": [
            {"name": "Agents", "count": 2, "papers": [_complete_paper()]},
            {"name": "Broken", "count": 1, "papers": ["not-a-paper"]},
        ],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "cluster#1 count mismatch: expected 1, got 2" in errors
    assert "cluster#2 paper#1 must be an object" in errors


def test_date_payload_rejects_duplicate_arxiv_ids():
    duplicate = _complete_paper()
    payload = {
        "date": "2026-05-12",
        "clusters": [
            {"name": "Agents", "count": 1, "papers": [_complete_paper()]},
            {"name": "Retrieval", "count": 1, "papers": [duplicate]},
        ],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "duplicate arxiv_id 2605.00001" in errors


def test_date_payload_rejects_mismatched_source_date():
    paper = _complete_paper()
    paper["source_date"] = "2026-05-11"
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [paper]}],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert any("source_date mismatch" in error for error in errors)


def test_date_payload_rejects_noncanonical_source_date():
    paper = _complete_paper()
    paper["source_date"] = "2026-05-12 "
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [paper]}],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert any("source_date must be canonical YYYY-MM-DD" in error for error in errors)


def test_date_payload_rejects_invalid_calendar_source_date():
    paper = _complete_paper()
    paper["source_date"] = "2026-02-31"
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [paper]}],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert any("source_date must be a valid calendar date" in error for error in errors)


def test_date_payload_rejects_invalid_calendar_payload_date():
    payload = {
        "date": "2026-02-31",
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-02-31")

    assert ok is False
    assert "date must be a valid calendar date" in errors


def test_date_payload_rejects_noncanonical_payload_date():
    payload = {
        "date": " 2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "date must be canonical YYYY-MM-DD" in errors


def test_date_payload_allows_legacy_payload_without_source_date():
    paper = _complete_paper()
    paper["date"] = "2026-01-30"
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [paper]}],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is True
    assert errors == []


def test_date_payload_rejects_malformed_tag_metadata():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": [{"name": "Agents", "count": 1}, {"name": "Agents", "count": 0}],
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "duplicate tag Agents" in errors
    assert "tag#2 count must be a positive integer" in errors


def test_date_payload_rejects_boolean_tag_count():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": [{"name": "Agents", "count": True}, {"name": "cs.AI", "count": 1}],
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "tag#1 count must be a positive integer" in errors


def test_date_payload_rejects_inconsistent_tag_counts():
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [_complete_paper()]}],
        "tags": [{"name": "Agents", "count": 2}, {"name": "Stale", "count": 1}],
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "tag Agents count mismatch: expected 1, got 2" in errors
    assert "tag Stale has no matching paper" in errors


def test_date_payload_rejects_malformed_paper_tags():
    paper = _complete_paper()
    paper["tags"] = ["cs.AI", "cs.AI", ""]
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [paper]}],
        "tags": [{"name": "Agents", "count": 1}, {"name": "cs.AI", "count": 1}],
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "cluster#1 paper#1 duplicate tag cs.AI" in errors
    assert "cluster#1 paper#1 tag#3 must be non-empty text" in errors


def test_date_payload_rejects_noncanonical_tag_and_cluster_labels():
    paper = _complete_paper()
    paper["cluster"] = "Agents "
    paper["tags"] = ["cs.AI "]
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents ", "count": 1, "papers": [paper]}],
        "tags": [{"name": "Agents ", "count": 1}, {"name": "cs.AI ", "count": 1}],
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "tag#1 tag name must be canonical text" in errors
    assert "tag#2 tag name must be canonical text" in errors
    assert "cluster#1 cluster name must be canonical text" in errors
    assert "cluster#1 paper#1 cluster metadata must be canonical text" in errors
    assert "cluster#1 paper#1 tag#1 must be canonical text" in errors


def test_date_payload_rejects_missing_category_filter_tag():
    paper = _complete_paper()
    paper["tags"] = []
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "Agents", "count": 1, "papers": [paper]}],
        "tags": [{"name": "Agents", "count": 1}],
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "cluster#1 paper#1 missing category tag cs.AI" in errors


def test_date_payload_rejects_placeholder_cluster_and_tag_metadata():
    paper = _complete_paper()
    paper["cluster"] = "Unknown"
    paper["tags"] = ["TBD"]
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "N/A", "count": 1, "papers": [paper]}],
        "tags": [{"name": "TBD", "count": 1}],
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "tag#1 tag name must be publishable text" in errors
    assert "cluster#1 cluster name must be publishable text" in errors
    assert "cluster#1 paper#1 cluster metadata must be publishable text" in errors
    assert "cluster#1 paper#1 tag#1 must be publishable text" in errors


def test_date_payload_rejects_missing_cluster_metadata():
    paper = _complete_paper()
    paper.pop("cluster", None)
    payload = {
        "date": "2026-05-12",
        "clusters": [{"name": "", "count": 1, "papers": [paper]}],
        "tags": _tags(),
        "overview": "今日速览 2026-05-12。",
    }

    ok, errors = validate_date_data_payload(payload, expected_date="2026-05-12")

    assert ok is False
    assert "cluster#1 missing cluster name" in errors
    assert "cluster#1 paper#1 missing cluster metadata" in errors
