import json

from src.core import crawl_arxiv, generate_unified_index


def test_crawl_arxiv_fallback_json_writer_preserves_existing_file_on_replace_failure(
    tmp_path, monkeypatch
):
    target = tmp_path / "papers.json"
    target.write_text('{"old": true}', encoding="utf-8")

    def failing_replace(_temp_path, _filepath):
        raise OSError("replace failed")

    monkeypatch.setattr(crawl_arxiv.os, "replace", failing_replace)

    assert crawl_arxiv._atomic_save_json(str(target), {"new": True}) is False
    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert not list(tmp_path.glob(".*.tmp"))


def test_crawl_arxiv_fallback_json_writer_saves_valid_json(tmp_path):
    target = tmp_path / "papers.json"

    assert crawl_arxiv._atomic_save_json(str(target), [{"title": "论文"}]) is True

    assert json.loads(target.read_text(encoding="utf-8")) == [{"title": "论文"}]


def test_unified_index_fallback_text_writer_preserves_existing_file_on_replace_failure(
    tmp_path, monkeypatch
):
    target = tmp_path / "index.html"
    target.write_text("old", encoding="utf-8")

    def failing_replace(_temp_path, _filepath):
        raise OSError("replace failed")

    monkeypatch.setattr(generate_unified_index.os, "replace", failing_replace)

    assert generate_unified_index._atomic_save_text(str(target), "new") is False
    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".*.tmp"))


def test_unified_index_fallback_json_writer_rejects_unserializable_payload(tmp_path):
    target = tmp_path / "data.json"

    assert generate_unified_index._atomic_save_json(str(target), {object()}) is False
    assert not target.exists()
    assert not list(tmp_path.glob(".*.tmp"))
