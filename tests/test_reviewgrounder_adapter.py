import json

from src.core.reviewgrounder_adapter import (
    OpenAlexSearchAPI,
    _promote_initial_review_on_refiner_failure,
    build_reviewgrounder_cache_payload,
    reviewgrounder_markdown_from_result,
)


def test_reviewgrounder_markdown_prefers_refined_review():
    review = {
        "review_markdown": "## Summary\n\nGrounded review.",
        "search_keywords": ["agent memory", "review grounding"],
        "reviewgrounder_metadata": {
            "model": "gpt-5.5",
            "reasoning_effort": "xhigh",
            "related_work_search": "openalex",
        },
    }

    markdown = reviewgrounder_markdown_from_result(review)

    assert "ReviewGrounder" in markdown
    assert "model=gpt-5.5" in markdown
    assert "reasoning_effort=xhigh" in markdown
    assert "## Summary" in markdown
    assert "agent memory, review grounding" in markdown


def test_reviewgrounder_cache_payload_changes_with_content():
    first = build_reviewgrounder_cache_payload(
        "T", "2601.00001", "2026-01-01", "A", "body one"
    )
    second = build_reviewgrounder_cache_payload(
        "T", "2601.00001", "2026-01-01", "A", "body two"
    )

    assert first != second
    payload = json.loads(first)
    assert payload["model"] == "gpt-5.5"
    assert payload["reasoning_effort"] == "xhigh"
    assert payload["rpm"] == 5
    assert payload["max_parallel_summaries"] == 1
    assert payload["version"].startswith("reviewgrounder_")


def test_refiner_failure_uses_initial_review_fallback():
    review = {
        "error": "refiner failed",
        "initial_review": {
            "review": "## Summary\n\nInitial review body.",
            "rating": 5.0,
        },
    }

    promoted = _promote_initial_review_on_refiner_failure(review)
    markdown = reviewgrounder_markdown_from_result(promoted)

    assert "error" not in promoted
    assert promoted["refiner_error"] == "refiner failed"
    assert promoted["used_initial_review_fallback"] is True
    assert "Initial review body" in markdown
    assert "Refiner fallback used" in markdown


def test_refiner_failure_formats_json_initial_review():
    review = {
        "error": "refiner failed",
        "initial_review": {
            "review": json.dumps(
                {
                    "summary": "Structured initial review.",
                    "strengths": ["Clear motivation"],
                    "rating": 5,
                }
            ),
        },
    }

    promoted = _promote_initial_review_on_refiner_failure(review)

    assert promoted["review_markdown"].startswith("## Summary")
    assert "Structured initial review." in promoted["review_markdown"]
    assert "- Clear motivation" in promoted["review_markdown"]


def test_openalex_normalization_reconstructs_abstract():
    api = OpenAlexSearchAPI()
    work = {
        "id": "https://openalex.org/W1",
        "display_name": "A Grounded Reviewer",
        "abstract_inverted_index": {"Grounded": [0], "reviews": [1], "help": [2]},
        "publication_year": 2026,
        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "cited_by_count": 7,
        "primary_location": {
            "landing_page_url": "https://example.test/paper",
            "source": {"display_name": "TestConf"},
        },
    }

    normalized = api._normalize_work(work)

    assert normalized["title"] == "A Grounded Reviewer"
    assert normalized["abstract"] == "Grounded reviews help"
    assert normalized["authors"] == ["Ada Lovelace"]
    assert normalized["venue"] == "TestConf"
    assert normalized["search_source"] == "openalex"
