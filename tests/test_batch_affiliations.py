import pytest

from scripts import batch_affiliations


def test_save_summary_papers_uses_atomic_json_writer(monkeypatch):
    calls = []

    def fake_save_json(path, payload, *, ensure_ascii, indent):
        calls.append(
            {
                "path": path,
                "payload": payload,
                "ensure_ascii": ensure_ascii,
                "indent": indent,
            }
        )
        return True

    monkeypatch.setattr(batch_affiliations, "save_json", fake_save_json)

    batch_affiliations.save_summary_papers("summary/file.json", [{"title": "A"}])

    assert calls == [
        {
            "path": "summary/file.json",
            "payload": [{"title": "A"}],
            "ensure_ascii": False,
            "indent": 2,
        }
    ]


def test_save_summary_papers_failure_is_blocking(monkeypatch):
    monkeypatch.setattr(
        batch_affiliations, "save_json", lambda *_args, **_kwargs: False
    )

    with pytest.raises(OSError, match="failed to save summary payload"):
        batch_affiliations.save_summary_papers("summary/file.json", [])


def test_load_summary_papers_rejects_malformed_payload(monkeypatch):
    monkeypatch.setattr(
        batch_affiliations, "load_json", lambda *_args, **_kwargs: {"bad": "shape"}
    )

    with pytest.raises(ValueError, match="invalid summary payload"):
        batch_affiliations.load_summary_papers("summary/file.json")


def test_write_affiliation_results_groups_updates_by_file(monkeypatch):
    payloads = {
        "summary/clustered_papers_2026-05-29_with_summary2.json": [
            {"title": "A"},
            {"title": "B"},
        ],
        "summary/clustered_papers_2026-05-30_with_summary2.json": [
            {"title": "C"},
        ],
    }
    saved = {}

    def fake_load_summary_papers(path):
        return [paper.copy() for paper in payloads[path]]

    def fake_save_summary_papers(path, papers):
        saved[path] = papers

    monkeypatch.setattr(
        batch_affiliations, "load_summary_papers", fake_load_summary_papers
    )
    monkeypatch.setattr(
        batch_affiliations, "save_summary_papers", fake_save_summary_papers
    )

    updated = batch_affiliations.write_affiliation_results(
        {
            ("summary/clustered_papers_2026-05-29_with_summary2.json", 1): "aff-b",
            ("summary/clustered_papers_2026-05-30_with_summary2.json", 0): "aff-c",
        }
    )

    assert updated == set(payloads)
    assert saved["summary/clustered_papers_2026-05-29_with_summary2.json"] == [
        {"title": "A"},
        {"title": "B", "affiliations": "aff-b"},
    ]
    assert saved["summary/clustered_papers_2026-05-30_with_summary2.json"] == [
        {"title": "C", "affiliations": "aff-c"},
    ]


def test_write_affiliation_results_rejects_stale_index(monkeypatch):
    monkeypatch.setattr(batch_affiliations, "load_summary_papers", lambda _path: [])

    with pytest.raises(IndexError, match="out of range"):
        batch_affiliations.write_affiliation_results(
            {("summary/clustered_papers_2026-05-29_with_summary2.json", 0): "aff"}
        )


def test_process_one_uses_summary_provider_chain(monkeypatch):
    providers = [object()]
    cache_manager = object()
    calls = []

    def fake_extract_affiliations(
        paper_content,
        authors,
        provider_chain,
        temperature,
        *,
        paper_title,
        cache_manager,
    ):
        calls.append(
            {
                "paper_content": paper_content,
                "authors": authors,
                "provider_chain": provider_chain,
                "temperature": temperature,
                "paper_title": paper_title,
                "cache_manager": cache_manager,
            }
        )
        return '{"institutions":[]}'

    monkeypatch.setattr(
        batch_affiliations, "extract_affiliations", fake_extract_affiliations
    )

    title, result = batch_affiliations.process_one(
        {"title": "Paper", "authors": "A. Author"},
        "paper content",
        providers,
        cache_manager,
    )

    assert title == "Paper"
    assert result == '{"institutions":[]}'
    assert calls == [
        {
            "paper_content": "paper content",
            "authors": "A. Author",
            "provider_chain": providers,
            "temperature": batch_affiliations.TEMPERATURE,
            "paper_title": "Paper",
            "cache_manager": cache_manager,
        }
    ]


def test_main_noop_does_not_require_providers(monkeypatch, capsys):
    monkeypatch.setattr(batch_affiliations.glob, "glob", lambda _pattern: [])

    def fail_provider_build():
        raise AssertionError("providers should not be built for a no-op run")

    monkeypatch.setattr(
        batch_affiliations, "build_affiliation_providers", fail_provider_build
    )

    assert batch_affiliations.main() == 0
    assert "无需处理" in capsys.readouterr().out


def test_main_fails_closed_when_tasks_need_missing_providers(monkeypatch, capsys):
    summary_file = "summary/clustered_papers_2026-05-29_with_summary2.json"
    monkeypatch.setattr(
        batch_affiliations.glob, "glob", lambda _pattern: [summary_file]
    )
    monkeypatch.setattr(
        batch_affiliations,
        "load_summary_papers",
        lambda _path: [{"title": "Paper", "link": "https://arxiv.org/pdf/2605.00001"}],
    )
    monkeypatch.setattr(
        batch_affiliations.CacheManager,
        "get_paper_cache",
        lambda _self, _link: {"data": {"content": "paper content"}},
    )
    monkeypatch.setattr(batch_affiliations, "build_affiliation_providers", lambda: [])

    assert batch_affiliations.main() == 1
    assert "无可用总结 provider" in capsys.readouterr().out
