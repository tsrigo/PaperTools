"""Tests for helper functions defined in src.core.pipeline."""

from __future__ import annotations

import os
import subprocess
import time

import pytest

from src.core import cluster_papers as cluster_module
from src.core import pipeline as pipeline_module
from src.core.generate_summary import has_non_empty_text
from src.core.generate_unified_index import backfill_paper_metadata
from src.core.paper_filter import repair_paper_metadata_from_source
from src.core.pipeline import (
    find_file_by_date,
    find_latest_file,
    select_cluster_output_file,
    validate_webpages_for_publication,
)


def _write_json(path) -> None:
    path.write_text("{}", encoding="utf-8")


def test_find_latest_file_prefers_filtered_results(tmp_path) -> None:
    domain_dir = tmp_path / "domain_paper"
    domain_dir.mkdir()

    other = domain_dir / "excluded_papers_2025-01-01.json"
    filtered = domain_dir / "filtered_papers_2025-01-01.json"
    _write_json(other)
    _write_json(filtered)

    now = time.time()
    os.utime(filtered, (now + 10, now + 10))

    assert find_latest_file(str(domain_dir)) == str(filtered)


def test_find_latest_file_prefers_combined_arxiv_files(tmp_path) -> None:
    arxiv_dir = tmp_path / "arxiv_paper"
    arxiv_dir.mkdir()

    single = arxiv_dir / "cs.AI_paper_2025-01-01.json"
    combined = arxiv_dir / "cs.AI_cs.CL_paper_2025-01-01.json"
    _write_json(single)
    _write_json(combined)

    assert find_latest_file(str(arxiv_dir)) == str(combined)


def test_find_file_by_date_matches_specific_day(tmp_path) -> None:
    domain_dir = tmp_path / "domain_paper"
    domain_dir.mkdir()

    jan = domain_dir / "filtered_papers_2025-01-01.json"
    feb = domain_dir / "filtered_papers_2025-02-01.json"
    _write_json(jan)
    _write_json(feb)

    assert find_file_by_date(str(domain_dir), "2025-02-01") == str(feb)


def test_find_file_by_date_requires_specific_day_by_default(tmp_path) -> None:
    domain_dir = tmp_path / "domain_paper"
    domain_dir.mkdir()

    jan = domain_dir / "filtered_papers_2025-01-01.json"
    feb = domain_dir / "filtered_papers_2025-02-01.json"
    _write_json(jan)
    _write_json(feb)

    now = time.time()
    os.utime(feb, (now + 5, now + 5))

    assert find_file_by_date(str(domain_dir), "2024-12-31") is None


def test_find_file_by_date_can_explicitly_fallback_to_latest(tmp_path) -> None:
    domain_dir = tmp_path / "domain_paper"
    domain_dir.mkdir()

    jan = domain_dir / "filtered_papers_2025-01-01.json"
    feb = domain_dir / "filtered_papers_2025-02-01.json"
    _write_json(jan)
    _write_json(feb)

    now = time.time()
    os.utime(feb, (now + 5, now + 5))

    assert find_file_by_date(
        str(domain_dir), "2024-12-31", allow_latest_fallback=True
    ) == str(feb)


def test_select_cluster_output_file_requires_specific_day_for_dated_run(
    tmp_path,
) -> None:
    old_cluster = tmp_path / "clustered_filtered_papers_2025-01-01.json"
    _write_json(old_cluster)

    assert select_cluster_output_file([str(old_cluster)], "2025-01-02") is None


def test_select_cluster_output_file_picks_matching_date(tmp_path) -> None:
    old_cluster = tmp_path / "clustered_filtered_papers_2025-01-01.json"
    target_cluster = tmp_path / "clustered_filtered_papers_2025-01-02.json"
    _write_json(old_cluster)
    _write_json(target_cluster)

    now = time.time()
    os.utime(old_cluster, (now + 10, now + 10))

    assert select_cluster_output_file(
        [str(old_cluster), str(target_cluster)], "2025-01-02"
    ) == str(target_cluster)


def test_filter_repair_backfills_missing_summary_from_source() -> None:
    old_filtered = {
        "arxiv_id": "2604.00001",
        "title": "Kept Paper",
        "filter_reason": "ok",
    }
    source = {
        "arxiv_id": "2604.00001",
        "summary": "Original abstract from crawl.",
        "link": "/arxiv/2604.00001",
        "category": "cs.CL",
    }

    repaired, changed = repair_paper_metadata_from_source(old_filtered, source)

    assert changed is True
    assert repaired["summary"] == "Original abstract from crawl."
    assert repaired["link"] == "/arxiv/2604.00001"
    assert repaired["category"] == "cs.CL"


def test_unified_index_backfills_clustered_papers_before_display() -> None:
    clustered = [
        {
            "arxiv_id": "2604.00002",
            "title": "Clustered Paper",
            "cluster": "Agents",
        }
    ]
    source_by_id = {
        "2604.00002": {
            "arxiv_id": "2604.00002",
            "summary": "Recovered original abstract.",
            "authors": "A. Researcher",
        }
    }

    backfilled = backfill_paper_metadata(clustered, source_by_id)

    assert backfilled[0]["summary"] == "Recovered original abstract."
    assert backfilled[0]["authors"] == "A. Researcher"
    assert backfilled[0]["cluster"] == "Agents"


def test_summary_skip_helper_rejects_blank_text() -> None:
    assert has_non_empty_text(" abstract ") is True
    assert has_non_empty_text("   ") is False
    assert has_non_empty_text(None) is False


def test_cluster_batch_failure_is_publish_blocking(monkeypatch) -> None:
    def fail_clustering(*_args, **_kwargs):
        raise RuntimeError("invalid model")

    monkeypatch.setattr(cluster_module, "call_llm_for_clustering", fail_clustering)

    with pytest.raises(RuntimeError, match="clustering batch failed"):
        cluster_module.cluster_batch(
            client=None,
            model="bad-model",
            papers=[{"title": "Paper", "summary": "Abstract"}],
            temperature=0.1,
        )


def test_cluster_batch_rejects_missing_assignments(monkeypatch) -> None:
    monkeypatch.setattr(
        cluster_module,
        "call_llm_for_clustering",
        lambda *_args, **_kwargs: (
            '{"clusters": [{"name": "Agents", "paper_indices": [0]}]}'
        ),
    )

    with pytest.raises(RuntimeError, match="missing cluster assignments"):
        cluster_module.cluster_batch(
            client=None,
            model="test-model",
            papers=[
                {"title": "Paper 1", "summary": "Abstract 1"},
                {"title": "Paper 2", "summary": "Abstract 2"},
            ],
            temperature=0.1,
        )


def test_cluster_batch_rejects_duplicate_assignments(monkeypatch) -> None:
    monkeypatch.setattr(
        cluster_module,
        "call_llm_for_clustering",
        lambda *_args, **_kwargs: (
            '{"clusters": ['
            '{"name": "Agents", "paper_indices": [0, 1]},'
            '{"name": "Planning", "paper_indices": [0]}'
            "]}"
        ),
    )

    with pytest.raises(RuntimeError, match="assigned to both"):
        cluster_module.cluster_batch(
            client=None,
            model="test-model",
            papers=[
                {"title": "Paper 1", "summary": "Abstract 1"},
                {"title": "Paper 2", "summary": "Abstract 2"},
            ],
            temperature=0.1,
        )


def test_cluster_batch_rejects_out_of_range_assignments(monkeypatch) -> None:
    monkeypatch.setattr(
        cluster_module,
        "call_llm_for_clustering",
        lambda *_args, **_kwargs: (
            '{"clusters": [{"name": "Agents", "paper_indices": [0, 1, 2]}]}'
        ),
    )

    with pytest.raises(RuntimeError, match="out-of-range paper index 2"):
        cluster_module.cluster_batch(
            client=None,
            model="test-model",
            papers=[
                {"title": "Paper 1", "summary": "Abstract 1"},
                {"title": "Paper 2", "summary": "Abstract 2"},
            ],
            temperature=0.1,
        )


def test_cluster_batch_rejects_malformed_cluster_schema(monkeypatch) -> None:
    monkeypatch.setattr(
        cluster_module,
        "call_llm_for_clustering",
        lambda *_args, **_kwargs: (
            '{"clusters": [{"name": "Agents", "paper_indices": "0"}]}'
        ),
    )

    with pytest.raises(RuntimeError, match="paper_indices must be a list"):
        cluster_module.cluster_batch(
            client=None,
            model="test-model",
            papers=[{"title": "Paper", "summary": "Abstract"}],
            temperature=0.1,
        )


def test_cluster_output_save_failure_is_publish_blocking(tmp_path, monkeypatch) -> None:
    output_file = tmp_path / "clustered_papers_2026-05-12.json"
    monkeypatch.setattr(cluster_module, "save_json", lambda *_args, **_kwargs: False)

    with pytest.raises(OSError, match="failed to save clustered papers"):
        cluster_module.save_clustered_papers_output(
            str(output_file),
            [{"arxiv_id": "2605.00001", "cluster": "Agents"}],
        )

    assert not output_file.exists()


def test_cluster_model_chain_normalizes_openrouter_aliases(monkeypatch) -> None:
    monkeypatch.setattr(cluster_module, "CLUSTER_MODEL_CHAIN_ENV", "")

    chain = cluster_module.build_cluster_model_chain(
        "minimax",
        "https://openrouter.ai/api/v1/",
    )

    assert chain == [
        "qwen/qwen3-30b-a3b",
        "deepseek/deepseek-chat-v3-0324",
    ]


def test_cluster_model_fallback_skips_invalid_model(monkeypatch) -> None:
    calls = []

    def fake_call(_client, model, _prompt, _temperature):
        calls.append(model)
        if model == "bad-model":
            raise RuntimeError("bad-model is not a valid model ID")
        return '{"clusters": [{"name": "Agents", "paper_indices": [0]}]}'

    monkeypatch.setattr(cluster_module, "call_llm_for_clustering", fake_call)
    cluster_module._DISABLED_CLUSTER_MODELS.clear()

    clustered = cluster_module.cluster_batch(
        client=None,
        model=["bad-model", "good-model"],
        papers=[{"title": "Paper", "summary": "Abstract"}],
        temperature=0.1,
    )

    assert clustered == {"Agents": [0]}
    assert calls == ["bad-model", "good-model"]
    assert "bad-model" in cluster_module._DISABLED_CLUSTER_MODELS


def test_validate_webpages_for_publication_blocks_missing_validator(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert validate_webpages_for_publication("webpages") is False


def test_pipeline_status_file_uses_atomic_json_writer(tmp_path, monkeypatch) -> None:
    calls = []
    status_file = tmp_path / "logs" / "status.json"

    def fake_save_json(filepath, payload, indent=2, ensure_ascii=False):
        calls.append((filepath, payload, indent, ensure_ascii))
        return True

    monkeypatch.setattr(pipeline_module, "save_json", fake_save_json)

    assert pipeline_module.write_status_file(str(status_file), {"status": "ok"})

    assert calls == [(str(status_file), {"status": "ok"}, 2, False)]


def test_pipeline_status_write_failure_is_visible(
    tmp_path, monkeypatch, capsys
) -> None:
    status_file = tmp_path / "logs" / "status.json"
    monkeypatch.setattr(pipeline_module, "save_json", lambda *_args, **_kwargs: False)

    assert not pipeline_module.write_status_file(str(status_file), {"status": "failed"})

    assert "写入状态文件失败" in capsys.readouterr().out
    assert not status_file.exists()


def test_pipeline_status_write_failure_blocks_successful_final_status(
    tmp_path, monkeypatch, capsys
) -> None:
    status_file = tmp_path / "logs" / "status.json"
    monkeypatch.setattr(pipeline_module, "save_json", lambda *_args, **_kwargs: False)

    status = {"status": "running"}
    exit_code = pipeline_module.finalize_pipeline_status(
        str(status_file),
        status,
        0,
        "skipped_no_source_papers",
        "no source papers",
    )

    assert exit_code == 1
    assert status["status"] == "skipped_no_source_papers"
    assert status["exit_code"] == 0
    assert status["failure_reason"] == "no source papers"
    captured = capsys.readouterr().out
    assert "状态文件写入失败" in captured
    assert "拒绝把本次运行视为成功或可跳过" in captured


def test_pipeline_status_write_failure_preserves_nonzero_exit(
    tmp_path, monkeypatch
) -> None:
    status_file = tmp_path / "logs" / "status.json"
    monkeypatch.setattr(pipeline_module, "save_json", lambda *_args, **_kwargs: False)

    exit_code = pipeline_module.finalize_pipeline_status(
        str(status_file),
        {"status": "running"},
        2,
        "failed",
        "bad args",
    )

    assert exit_code == 2


def test_pipeline_stage_timeout_default_and_disable(monkeypatch) -> None:
    monkeypatch.delenv("PAPERTOOLS_PIPELINE_STAGE_TIMEOUT_SECONDS", raising=False)
    assert pipeline_module.pipeline_stage_timeout_seconds() == 21600.0

    monkeypatch.setenv("PAPERTOOLS_PIPELINE_STAGE_TIMEOUT_SECONDS", "0")
    assert pipeline_module.pipeline_stage_timeout_seconds() is None


def test_run_command_applies_stage_timeout(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("PAPERTOOLS_PIPELINE_STAGE_TIMEOUT_SECONDS", "7.5")

    def fake_run(cmd, *, text, check, timeout):
        calls.append((cmd, text, check, timeout))

    monkeypatch.setattr(pipeline_module.subprocess, "run", fake_run)

    assert pipeline_module.run_command(["python", "--version"], "version check")
    assert calls == [(["python", "--version"], True, True, 7.5)]


def test_run_command_passes_subprocess_env(monkeypatch) -> None:
    calls = []
    child_env = {
        "OPENAI_API_KEY": "sk-test",
        "OPENAI_BASE_URL": "https://example.test/v1",
    }

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))

    monkeypatch.setattr(pipeline_module.subprocess, "run", fake_run)

    assert pipeline_module.run_command(
        ["python", "--version"], "version", env=child_env
    )
    assert calls == [
        (
            ["python", "--version"],
            {"text": True, "check": True, "timeout": 21600.0, "env": child_env},
        )
    ]


def test_run_command_refuses_secret_cli_arguments(monkeypatch, capsys) -> None:
    def fake_run(*_args, **_kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(pipeline_module.subprocess, "run", fake_run)

    assert not pipeline_module.run_command(
        ["python", "stage.py", "--api-key", "sk-" + "A" * 32],
        "unsafe stage",
    )

    captured = capsys.readouterr().out
    assert "--api-key" in captured
    assert "sk-" not in captured


def test_run_command_refuses_secret_equals_arguments(monkeypatch, capsys) -> None:
    def fake_run(*_args, **_kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(pipeline_module.subprocess, "run", fake_run)

    assert not pipeline_module.run_command(
        ["python", "stage.py", "--summary-prism-api-key=sk-" + "A" * 32],
        "unsafe stage",
    )

    captured = capsys.readouterr().out
    assert "--summary-prism-api-key" in captured
    assert "sk-" not in captured


def test_build_subprocess_env_applies_overrides_without_mutating_parent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "parent-key")

    child_env = pipeline_module.build_subprocess_env(
        {"OPENAI_API_KEY": "child-key", "EMPTY_ALLOWED": ""}
    )

    assert child_env["OPENAI_API_KEY"] == "child-key"
    assert child_env["EMPTY_ALLOWED"] == ""
    assert os.environ["OPENAI_API_KEY"] == "parent-key"


def test_run_command_timeout_is_stage_failure(monkeypatch, capsys) -> None:
    monkeypatch.setenv("PAPERTOOLS_PIPELINE_STAGE_TIMEOUT_SECONDS", "3")

    def fake_run(cmd, *, text, check, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(pipeline_module.subprocess, "run", fake_run)

    assert not pipeline_module.run_command(["python", "slow.py"], "slow stage")
    assert "超时" in capsys.readouterr().out


def test_run_interactive_command_uses_check_without_stage_timeout(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("PAPERTOOLS_PIPELINE_STAGE_TIMEOUT_SECONDS", "3")

    def fake_run(cmd, *, text, check):
        calls.append((cmd, text, check))

    monkeypatch.setattr(pipeline_module.subprocess, "run", fake_run)

    assert pipeline_module.run_interactive_command(
        ["python", "src/core/serve_webpages.py"],
        "serve",
    )
    assert calls == [(["python", "src/core/serve_webpages.py"], True, True)]


def test_run_interactive_command_treats_nonzero_exit_as_failure(
    monkeypatch, capsys
) -> None:
    def fake_run(cmd, *, text, check):
        raise subprocess.CalledProcessError(3, cmd)

    monkeypatch.setattr(pipeline_module.subprocess, "run", fake_run)

    assert not pipeline_module.run_interactive_command(["python", "server.py"], "serve")
    assert "错误码: 3" in capsys.readouterr().out


def test_run_interactive_command_refuses_secret_cli_arguments(
    monkeypatch, capsys
) -> None:
    def fake_run(*_args, **_kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(pipeline_module.subprocess, "run", fake_run)

    assert not pipeline_module.run_interactive_command(
        ["python", "server.py", "--api-key", "sk-" + "A" * 32],
        "unsafe serve",
    )

    captured = capsys.readouterr().out
    assert "--api-key" in captured
    assert "sk-" not in captured


def test_validate_webpages_for_publication_runs_release_validator(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    validator = tmp_path / "scripts" / "validate_published_payloads.py"
    validator.parent.mkdir()
    validator.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    calls = []

    def fake_run_command(cmd, description, progress_tracker=None):
        calls.append((cmd, description, progress_tracker))
        return True

    monkeypatch.setattr(pipeline_module, "run_command", fake_run_command)

    assert validate_webpages_for_publication("webpages") is True

    assert calls == [
        (
            [
                pipeline_module.sys.executable,
                "scripts/validate_published_payloads.py",
                "--webpages-dir",
                "webpages",
            ],
            "校验发布网页数据",
            None,
        )
    ]
