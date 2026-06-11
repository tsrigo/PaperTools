import sys

import pytest

from src.core import crawl_arxiv


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


def test_scrape_papers_raises_category_error_on_fetch_failure(monkeypatch):
    def failing_fetch(_url):
        raise RuntimeError("network timeout")

    monkeypatch.setattr(crawl_arxiv, "_fetch_url", failing_fetch)
    monkeypatch.setattr(crawl_arxiv.time, "sleep", lambda _seconds: None)

    with pytest.raises(crawl_arxiv.CrawlCategoryError) as exc_info:
        crawl_arxiv.scrape_papers(
            "cs.AI",
            target_date="2026-05-29",
            use_cache=False,
        )

    assert "cs.AI" in str(exc_info.value)
    assert "network timeout" in str(exc_info.value)


def test_scrape_papers_keeps_true_empty_page_as_empty_result(monkeypatch):
    monkeypatch.setattr(
        crawl_arxiv,
        "_fetch_url",
        lambda _url: FakeResponse("<html><body></body></html>"),
    )
    monkeypatch.setattr(crawl_arxiv.time, "sleep", lambda _seconds: None)

    papers, paper_ids = crawl_arxiv.scrape_papers(
        "cs.AI",
        target_date="2026-05-29",
        use_cache=False,
    )

    assert papers == []
    assert paper_ids == set()


def test_main_fails_closed_when_any_selected_category_fails(
    tmp_path, monkeypatch, capsys
):
    def fake_scrape_papers(category, *_args):
        if category == "cs.AI":
            return (
                [
                    {
                        "arxiv_id": "1234.5678",
                        "link": "https://arxiv.org/abs/1234.5678",
                    }
                ],
                {"1234.5678"},
            )
        raise crawl_arxiv.CrawlCategoryError("fetch failed")

    def fail_save_papers(*_args, **_kwargs):
        raise AssertionError("save_papers must not be called for partial crawls")

    monkeypatch.setattr(crawl_arxiv, "CRAWL_CATEGORIES", ["cs.AI", "cs.CL"])
    monkeypatch.setattr(crawl_arxiv, "scrape_papers", fake_scrape_papers)
    monkeypatch.setattr(crawl_arxiv, "save_papers", fail_save_papers)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "crawl_arxiv.py",
            "--categories",
            "cs.AI",
            "cs.CL",
            "--date",
            "2026-05-29",
            "--max-workers",
            "1",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert crawl_arxiv.main() == 1

    output = capsys.readouterr().out
    assert "拒绝保存部分爬取结果" in output
    assert "cs.CL" in output


def test_main_rejects_invalid_categories_without_crawling(
    tmp_path, monkeypatch, capsys
):
    def fail_scrape_papers(*_args, **_kwargs):
        raise AssertionError("scrape_papers must not run with invalid categories")

    monkeypatch.setattr(crawl_arxiv, "CRAWL_CATEGORIES", ["cs.AI"])
    monkeypatch.setattr(crawl_arxiv, "scrape_papers", fail_scrape_papers)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "crawl_arxiv.py",
            "--categories",
            "cs.AI",
            "bad.CAT",
            "--date",
            "2026-05-29",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert crawl_arxiv.main() == 2

    output = capsys.readouterr().out
    assert "包含无效类别" in output
    assert "bad.CAT" in output


def test_main_rejects_all_category_mixed_with_specific_categories(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(crawl_arxiv, "CRAWL_CATEGORIES", ["cs.AI"])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "crawl_arxiv.py",
            "--categories",
            "all",
            "cs.AI",
            "--date",
            "2026-05-29",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert crawl_arxiv.main() == 2

    output = capsys.readouterr().out
    assert "all 不能和具体类别混用" in output


def test_main_allows_true_empty_result_only_with_explicit_allow_empty(
    tmp_path, monkeypatch
):
    saved_payload = {}

    def fake_save_papers(all_papers, selected_categories, *_args):
        saved_payload["all_papers"] = all_papers
        saved_payload["selected_categories"] = selected_categories
        return str(tmp_path / "papers.json")

    monkeypatch.setattr(crawl_arxiv, "CRAWL_CATEGORIES", ["cs.AI"])
    monkeypatch.setattr(crawl_arxiv, "scrape_papers", lambda *_args: ([], set()))
    monkeypatch.setattr(crawl_arxiv, "save_papers", fake_save_papers)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "crawl_arxiv.py",
            "--categories",
            "cs.AI",
            "--date",
            "2026-05-29",
            "--allow-empty",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert crawl_arxiv.main() == 0
    assert saved_payload == {
        "all_papers": {},
        "selected_categories": ["cs.AI"],
    }
