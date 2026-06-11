import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def parse_key_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def run_runtime_dump(
    tmp_path: Path,
    env_file: Path,
    script: str = "scripts/robust_daily_update.sh",
    **overrides: str,
) -> dict[str, str]:
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "OPENAI_BASE_URL": "https://openrouter.ai/api/v1/",
        "PAPERTOOLS_DAILY_ENV_FILE": str(env_file),
        "PAPERTOOLS_DAILY_LOCK_FILE": str(tmp_path / "daily.lock"),
        "PAPERTOOLS_DAILY_PRINT_RUNTIME_CONFIG": "1",
        **overrides,
    }
    result = subprocess.run(
        ["bash", script],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return parse_key_values(result.stdout)


def clear_preflight_model_chains(monkeypatch):
    for name in (
        "SUMMARY_MODEL_CHAIN",
        "PAPERTOOLS_DEFAULT_SUMMARY_MODEL_CHAIN",
        "PAPERTOOLS_FILTER_MODEL_CHAIN",
        "FILTER_MODEL_CHAIN",
        "PAPERTOOLS_CLUSTER_MODEL_CHAIN",
        "CLUSTER_MODEL_CHAIN",
        "CLUSTER_OPENAI_API_KEY",
        "CLUSTER_OPENAI_BASE_URL",
        "SUMMARY_OPENAI_API_KEY",
        "SUMMARY_OPENAI_BASE_URL",
        "SUMMARY_SJTU_OPENAI_API_KEY",
        "SUMMARY_SJTU_OPENAI_BASE_URL",
        "SJTU_OPENAI_API_KEY",
        "SJTU_OPENAI_BASE_URL",
        "SUMMARY_PRISM_OPENAI_API_KEY",
        "SUMMARY_PRISM_OPENAI_BASE_URL",
        "PRISM_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def prepare_preflight_test_env(monkeypatch, preflight_check):
    clear_preflight_model_chains(monkeypatch)
    monkeypatch.setattr(preflight_check, "load_dotenv", None)


def test_robust_daily_defaults_override_stale_dotenv_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_BASE_URL=https://models.sjtu.edu.cn/api/v1/",
                "OPENAI_API_KEY=sk-test",
                "MODEL=minimax-m2.5",
                "FILTER_MODEL=minimax-m2.5",
                "CLUSTER_MODEL=minimax-m2.5",
                "SUMMARY_MODEL=minimax-m2.5",
                "SUMMARY_MODEL_CHAIN=sjtu:minimax-m2.5",
                "PAPERTOOLS_FILTER_RPM=1",
                "PAPERTOOLS_FILTER_LLM_TIMEOUT=999",
                "PAPERTOOLS_FILTER_LLM_MAX_RETRIES=9",
                "PAPERTOOLS_FILTER_EARLY_STOP_AFTER_CAP=0",
                "PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE=false",
            ]
        ),
        encoding="utf-8",
    )

    values = run_runtime_dump(tmp_path, env_file)

    assert values["MODEL"] == "deepseek-reasoner"
    assert values["OPENAI_BASE_URL"] == "https://models.sjtu.edu.cn/api/v1/"
    assert values["FILTER_MODEL"] == "qwen"
    assert values["PAPERTOOLS_FILTER_MODEL_CHAIN"] == "qwen,deepseek-chat,minimax"
    assert values["CLUSTER_MODEL"] == "glm"
    assert values["PAPERTOOLS_CLUSTER_MODEL_CHAIN"] == "qwen,deepseek-chat,minimax"
    assert values["SUMMARY_MODEL"] == "qwen"
    assert values["SUMMARY_MODEL_CHAIN"].startswith("sjtu:qwen")
    assert values["PAPERTOOLS_FILTER_RPM"] == "4"
    assert values["PAPERTOOLS_FILTER_LLM_TIMEOUT"] == "60"
    assert values["PAPERTOOLS_FILTER_LLM_MAX_RETRIES"] == "1"
    assert values["PAPERTOOLS_FILTER_EARLY_STOP_AFTER_CAP"] == "1"
    assert values["PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE"] == "0"
    assert values["PAPERTOOLS_FILTER_MAX_OUTPUT_PAPERS"] == "0"
    assert values["PAPERTOOLS_FILTER_RULE_VERSION"] == "2026-05-31-topic-post-v2-daily"
    assert values["PAPERTOOLS_SUMMARY_OPENAI_TIMEOUT"] == "60"
    assert values["DOCUMENT_EXTRACTOR_CHAIN"] == "jina,pymupdf4llm"
    assert values["JINA_MAX_RETRIES"] == "2"
    assert values["PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS"] == "21600"
    assert values["PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK"] == "0"


def test_daily_full_runner_uses_same_daily_defaults(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("FILTER_MODEL=minimax-m2.5\n", encoding="utf-8")

    values = run_runtime_dump(
        tmp_path,
        env_file,
        script="scripts/daily_full_run.sh",
        PAPERTOOLS_DAILY_SELF_REFRESH="0",
    )

    assert values["FILTER_MODEL"] == "qwen"
    assert values["PAPERTOOLS_FILTER_MODEL_CHAIN"] == "qwen,deepseek-chat,minimax"
    assert values["PAPERTOOLS_CLUSTER_MODEL_CHAIN"] == "qwen,deepseek-chat,minimax"
    assert values["OPENAI_BASE_URL"] == "https://models.sjtu.edu.cn/api/v1/"
    assert values["PAPERTOOLS_FILTER_RPM"] == "4"
    assert values["PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE"] == "0"
    assert values["PAPERTOOLS_FILTER_MAX_OUTPUT_PAPERS"] == "0"
    assert values["PAPERTOOLS_FILTER_RULE_VERSION"] == "2026-05-31-topic-post-v2-daily"
    assert values["PAPERTOOLS_SUMMARY_OPENAI_TIMEOUT"] == "60"
    assert values["DOCUMENT_EXTRACTOR_CHAIN"] == "jina,pymupdf4llm"
    assert values["PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS"] == "21600"
    assert values["PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK"] == "0"


def test_robust_daily_publish_path_validates_and_only_stages_webpages():
    script = (ROOT / "scripts/robust_daily_update.sh").read_text(encoding="utf-8")

    assert "sync_publish_branch" in script
    assert "require_clean_worktree" in script
    assert 'mkdir -p "$(dirname "$LOCK_FILE")"' in script
    assert 'git merge --ff-only "origin/${PAPERTOOLS_GIT_BRANCH}"' in script
    assert "scripts/validate_published_payloads.py --webpages-dir webpages" in script
    assert "preflight_cmd=(python scripts/preflight_check.py)" in script
    assert "preflight_cmd+=(--offline-ok)" in script
    assert "PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK" in script
    assert "python scripts/preflight_check.py --offline-ok" not in script
    assert "read_pipeline_status" in script
    assert "has_webpage_changes" in script
    assert "handle_successful_pipeline_status" in script
    assert "skipped_no_source_papers|skipped_no_selected_papers" in script
    assert "git status --short -- webpages" in script
    assert "git diff --quiet -- webpages" not in script
    assert "Pipeline exited successfully but status file is not healthy" in script
    assert "Pipeline reported $pipeline_status but changed published webpages" in script
    assert (
        'run_cmd=(timeout "$PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS" python papertools.py run'
        in script
    )
    assert script.index("handle_successful_pipeline_status") < script.index(
        "git add webpages/"
    )
    assert "git add webpages/" in script
    assert 'git push origin "$PAPERTOOLS_GIT_BRANCH"' in script
    assert "${PAPERTOOLS_GIT_BRANCH:-master}" not in script
    assert "git add arxiv_paper/" not in script
    assert "git add arxiv_paper/ domain_paper/ summary/ webpages/ logs/" not in script
    assert (
        'git commit -m "Daily paper update: ${END_DATE}" 2>&1 | tee -a "$LOG_FILE" || true'
        not in script
    )
    assert (
        'git push origin "${PAPERTOOLS_GIT_BRANCH:-master}" 2>&1 | tee -a "$LOG_FILE" || true'
        not in script
    )


def test_default_daily_update_writes_status_and_validates_before_staging():
    script = (ROOT / "daily_update.sh").read_text(encoding="utf-8")

    validator = "python scripts/validate_published_payloads.py --webpages-dir webpages"
    pipeline = 'timeout "$PIPELINE_TIMEOUT_SECONDS" python papertools.py run --mode full --skip-serve --status-file "$STATUS_FILE"'

    assert 'STATUS_DIR="${PAPERTOOLS_DAILY_STATUS_DIR:-$PROJECT_DIR/logs}"' in script
    assert "PAPERTOOLS_PUBLISH_LOCK_FILE" in script
    assert "PAPERTOOLS_DAILY_LOCK_FILE" in script
    assert "logs/papertools_publish.lock" in script
    assert 'exec 9>"$LOCK_FILE"' in script
    assert "flock -n 9" in script
    assert "PAPERTOOLS_DAILY_STATUS_FILE" in script
    assert (
        'PIPELINE_TIMEOUT_SECONDS="${PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS:-21600}"'
        in script
    )
    assert 'mkdir -p "$STATUS_DIR"' in script
    assert "run_preflight_check" in script
    assert "preflight_cmd=(python scripts/preflight_check.py)" in script
    assert "preflight_cmd+=(--offline-ok)" in script
    assert "PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK" in script
    assert "python scripts/preflight_check.py --offline-ok" not in script
    assert "read_pipeline_status" in script
    assert 'PIPELINE_STATUS="$(read_pipeline_status)"' in script
    assert "skipped_no_source_papers|skipped_no_selected_papers" in script
    assert "git status --short -- webpages" in script
    assert "pipeline exited successfully but status file is not healthy" in script
    assert pipeline in script
    assert validator in script
    assert (
        script.index("run_preflight_check")
        < script.index(pipeline)
        < script.index('PIPELINE_STATUS="$(read_pipeline_status)"')
        < script.index(validator)
        < script.index("git add webpages/")
    )
    assert "git add arxiv_paper/" not in script
    assert "git add arxiv_paper/ domain_paper/ summary/ webpages/ logs/" not in script


def test_daily_full_runner_validates_before_staging_and_never_commits_failures():
    script = (ROOT / "scripts/daily_full_run.sh").read_text(encoding="utf-8")

    validator = "scripts/validate_published_payloads.py --webpages-dir webpages"
    assert 'mkdir -p "$(dirname "$LOCK_FILE")"' in script
    assert validator in script
    assert script.index('CURRENT_STAGE="validate_published_webpages"') < script.index(
        "git add webpages/"
    )
    assert 'CURRENT_STAGE="validate_published_webpages_after_rebase"' in script
    assert "PAPERTOOLS_COMMIT_ON_PIPELINE_FAILURE" not in script
    assert "continuing with generated partial output" not in script
    assert "run_preflight_check" in script
    assert 'preflight_cmd=("$PYTHON_BIN" scripts/preflight_check.py)' in script
    assert "preflight_cmd+=(--offline-ok)" in script
    assert "PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK" in script
    assert "python scripts/preflight_check.py --offline-ok" not in script
    assert script.index('CURRENT_STAGE="preflight"') < script.index(
        'CURRENT_STAGE="pipeline_${RUN_DATE}"'
    )
    assert (
        'timeout "$PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS" "$PYTHON_BIN" papertools.py run'
        in script
    )
    assert "origin/master" not in script
    assert "HEAD:master" not in script
    assert 'git push origin "HEAD:$PUBLISH_BRANCH"' in script
    assert "fetch_origin_branch" in script
    assert "git add arxiv_paper/" not in script
    assert "git add arxiv_paper/ domain_paper/ summary/ webpages/ logs/" not in script


def test_robust_daily_allows_explicit_daily_overrides(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=sk-test\nFILTER_MODEL=minimax-m2.5\n", encoding="utf-8"
    )

    values = run_runtime_dump(
        tmp_path,
        env_file,
        PAPERTOOLS_DAILY_FILTER_MODEL="minimax",
        PAPERTOOLS_DAILY_FILTER_MODEL_CHAIN="deepseek-chat,qwen",
        PAPERTOOLS_DAILY_CLUSTER_MODEL_CHAIN="minimax,qwen",
        PAPERTOOLS_DAILY_FILTER_RPM="12",
        PAPERTOOLS_DAILY_TOPIC_HEURISTIC_BYPASS_PRESTIGE="0",
        PAPERTOOLS_DAILY_FILTER_MAX_OUTPUT_PAPERS="2",
        PAPERTOOLS_DAILY_FILTER_RULE_VERSION="test-rule",
        PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS="42",
        PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK="1",
    )

    assert values["FILTER_MODEL"] == "minimax"
    assert values["PAPERTOOLS_FILTER_MODEL_CHAIN"] == "deepseek-chat,qwen"
    assert values["PAPERTOOLS_CLUSTER_MODEL_CHAIN"] == "minimax,qwen"
    assert values["PAPERTOOLS_FILTER_RPM"] == "12"
    assert values["PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE"] == "0"
    assert values["PAPERTOOLS_FILTER_MAX_OUTPUT_PAPERS"] == "2"
    assert values["PAPERTOOLS_FILTER_RULE_VERSION"] == "test-rule"
    assert values["PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS"] == "42"
    assert values["PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK"] == "1"


def test_preflight_respects_runtime_env_over_dotenv(tmp_path):
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_BASE_URL=https://models.sjtu.edu.cn/api/v1/",
                "OPENAI_API_KEY=sk-dotenv",
                "MODEL=stale-model",
                "FILTER_MODEL=stale-model",
            ]
        ),
        encoding="utf-8",
    )
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "OPENAI_BASE_URL": "https://models.sjtu.edu.cn/api/v1/",
        "OPENAI_API_KEY": "sk-runtime",
        "MODEL": "deepseek-reasoner",
        "FILTER_MODEL": "qwen",
        "CLUSTER_MODEL": "glm",
        "SUMMARY_MODEL": "minimax",
    }

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/preflight_check.py"), "--offline-ok"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "MODEL=deepseek-reasoner" in result.stdout
    assert "FILTER_MODEL=qwen" in result.stdout


def test_preflight_remote_check_uses_unified_openai_client(monkeypatch, capsys):
    from scripts import preflight_check

    prepare_preflight_test_env(monkeypatch, preflight_check)

    class FakeModel:
        def __init__(self, model_id: str):
            self.id = model_id

    class FakeModels:
        def list(self):
            return type(
                "ModelList",
                (),
                {
                    "data": [
                        FakeModel("minimax"),
                        FakeModel("glm"),
                        FakeModel("qwen"),
                    ]
                },
            )()

    class FakeClient:
        models = FakeModels()

        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    captured = {}
    fake_client = FakeClient()

    def fake_create_openai_client(**kwargs):
        captured.update(kwargs)
        return fake_client

    monkeypatch.setattr(preflight_check, "check_disk_space", lambda: (True, "ok"))
    monkeypatch.setattr(
        preflight_check, "create_openai_client", fake_create_openai_client
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.sjtu.edu.cn/api/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-runtime")
    monkeypatch.setenv("MODEL", "minimax")
    monkeypatch.setenv("FILTER_MODEL", "qwen")
    monkeypatch.setenv("CLUSTER_MODEL", "glm")
    monkeypatch.setenv("SUMMARY_MODEL", "minimax")
    monkeypatch.setenv("SUMMARY_MODEL_CHAIN", "sjtu:minimax,sjtu:glm,sjtu:qwen")
    monkeypatch.setattr(preflight_check.sys, "argv", ["preflight_check.py"])

    assert preflight_check.main() == 0

    assert captured == {
        "api_key": "sk-runtime",
        "base_url": "https://models.sjtu.edu.cn/api/v1/",
        "timeout": 20.0,
        "max_retries": 0,
    }
    assert fake_client.closed is True
    assert "Preflight OK" in capsys.readouterr().out


def test_preflight_checks_stage_specific_model_endpoints(monkeypatch, capsys):
    from scripts import preflight_check

    prepare_preflight_test_env(monkeypatch, preflight_check)

    class FakeModel:
        def __init__(self, model_id: str):
            self.id = model_id

    class FakeModels:
        def __init__(self, model_ids: list[str]):
            self.model_ids = model_ids

        def list(self):
            return type(
                "ModelList",
                (),
                {"data": [FakeModel(model_id) for model_id in self.model_ids]},
            )()

    class FakeClient:
        def __init__(self, model_ids: list[str]):
            self.models = FakeModels(model_ids)
            self.closed = False

        def close(self):
            self.closed = True

    models_by_base_url = {
        "https://models.sjtu.edu.cn/api/v1/": ["minimax", "qwen"],
        "https://cluster.example/v1": ["cluster-model", "cluster-fallback"],
        "https://prism.example/v1": ["gpt-5.5"],
    }
    captured = []
    clients = []

    def fake_create_openai_client(**kwargs):
        captured.append(kwargs)
        client = FakeClient(models_by_base_url[kwargs["base_url"]])
        clients.append(client)
        return client

    monkeypatch.setattr(preflight_check, "check_disk_space", lambda: (True, "ok"))
    monkeypatch.setattr(
        preflight_check, "create_openai_client", fake_create_openai_client
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.sjtu.edu.cn/api/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-runtime")
    monkeypatch.setenv("MODEL", "minimax")
    monkeypatch.setenv("FILTER_MODEL", "qwen")
    monkeypatch.setenv("CLUSTER_MODEL", "cluster-model")
    monkeypatch.setenv("CLUSTER_OPENAI_API_KEY", "sk-cluster")
    monkeypatch.setenv("CLUSTER_OPENAI_BASE_URL", "https://cluster.example/v1")
    monkeypatch.setenv("PAPERTOOLS_CLUSTER_MODEL_CHAIN", "cluster-fallback")
    monkeypatch.setenv("SUMMARY_MODEL_CHAIN", "sjtu:qwen,prism:gpt-5.5")
    monkeypatch.setenv("SUMMARY_PRISM_OPENAI_API_KEY", "sk-prism")
    monkeypatch.setenv("SUMMARY_PRISM_OPENAI_BASE_URL", "https://prism.example/v1")
    monkeypatch.setattr(preflight_check.sys, "argv", ["preflight_check.py"])

    assert preflight_check.main() == 0

    assert {call["base_url"] for call in captured} == set(models_by_base_url)
    assert {(call["base_url"], call["api_key"]) for call in captured} == {
        ("https://models.sjtu.edu.cn/api/v1/", "sk-runtime"),
        ("https://cluster.example/v1", "sk-cluster"),
        ("https://prism.example/v1", "sk-prism"),
    }
    assert all(client.closed for client in clients)
    output = capsys.readouterr().out
    assert "Checking /models for cluster at https://cluster.example/v1" in output
    assert "Checking /models for summary:prism at https://prism.example/v1" in output


def test_preflight_remote_check_fails_for_stage_specific_missing_model(
    monkeypatch, capsys
):
    from scripts import preflight_check

    prepare_preflight_test_env(monkeypatch, preflight_check)

    class FakeModel:
        def __init__(self, model_id: str):
            self.id = model_id

    class FakeModels:
        def __init__(self, model_ids: list[str]):
            self.model_ids = model_ids

        def list(self):
            return type(
                "ModelList",
                (),
                {"data": [FakeModel(model_id) for model_id in self.model_ids]},
            )()

    class FakeClient:
        def __init__(self, model_ids: list[str]):
            self.models = FakeModels(model_ids)
            self.closed = False

        def close(self):
            self.closed = True

    models_by_base_url = {
        "https://models.sjtu.edu.cn/api/v1/": [
            "minimax",
            "qwen",
            "glm",
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "https://cluster.example/v1": ["cluster-fallback"],
    }

    def fake_create_openai_client(**kwargs):
        return FakeClient(models_by_base_url[kwargs["base_url"]])

    monkeypatch.setattr(preflight_check, "check_disk_space", lambda: (True, "ok"))
    monkeypatch.setattr(
        preflight_check, "create_openai_client", fake_create_openai_client
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.sjtu.edu.cn/api/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-runtime")
    monkeypatch.setenv("MODEL", "minimax")
    monkeypatch.setenv("FILTER_MODEL", "qwen")
    monkeypatch.setenv("CLUSTER_MODEL", "cluster-model")
    monkeypatch.setenv("CLUSTER_OPENAI_BASE_URL", "https://cluster.example/v1")
    monkeypatch.setenv("PAPERTOOLS_CLUSTER_MODEL_CHAIN", "cluster-fallback")
    monkeypatch.setattr(preflight_check.sys, "argv", ["preflight_check.py"])

    assert preflight_check.main() == 2

    output = capsys.readouterr().out
    assert "requested models not returned by /models for cluster" in output
    assert "cluster-model" in output


def test_preflight_normalizes_openrouter_stage_aliases_before_remote_check(
    monkeypatch, capsys
):
    from scripts import preflight_check

    prepare_preflight_test_env(monkeypatch, preflight_check)

    class FakeModel:
        def __init__(self, model_id: str):
            self.id = model_id

    class FakeModels:
        def list(self):
            return type(
                "ModelList",
                (),
                {"data": [FakeModel("qwen/qwen3-30b-a3b")]},
            )()

    class FakeClient:
        models = FakeModels()

        def close(self):
            pass

    monkeypatch.setattr(preflight_check, "check_disk_space", lambda: (True, "ok"))
    monkeypatch.setattr(
        preflight_check, "create_openai_client", lambda **_kwargs: FakeClient()
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-runtime")
    monkeypatch.setenv("MODEL", "minimax")
    monkeypatch.setenv("FILTER_MODEL", "qwen")
    monkeypatch.setenv("CLUSTER_MODEL", "qwen")
    monkeypatch.setenv("SUMMARY_MODEL_CHAIN", "modelscope:qwen/qwen3-30b-a3b")
    monkeypatch.setattr(preflight_check.sys, "argv", ["preflight_check.py"])

    assert preflight_check.main() == 0
    assert "Preflight OK" in capsys.readouterr().out


def test_preflight_fails_when_summary_chain_has_no_usable_provider(monkeypatch, capsys):
    from scripts import preflight_check

    prepare_preflight_test_env(monkeypatch, preflight_check)
    monkeypatch.setattr(preflight_check, "check_disk_space", lambda: (True, "ok"))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.sjtu.edu.cn/api/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-runtime")
    monkeypatch.setenv("MODEL", "minimax")
    monkeypatch.setenv("FILTER_MODEL", "qwen")
    monkeypatch.setenv("CLUSTER_MODEL", "glm")
    monkeypatch.setenv("SUMMARY_MODEL_CHAIN", "prism:gpt-5.5")
    monkeypatch.setattr(
        preflight_check.sys, "argv", ["preflight_check.py", "--offline-ok"]
    )

    assert preflight_check.main() == 2

    output = capsys.readouterr().out
    assert "skipping summary provider without credentials" in output
    assert "no usable summary providers" in output


def test_preflight_rejects_invalid_filter_and_cluster_chain_models(monkeypatch, capsys):
    from scripts import preflight_check

    prepare_preflight_test_env(monkeypatch, preflight_check)
    monkeypatch.setattr(preflight_check, "check_disk_space", lambda: (True, "ok"))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.sjtu.edu.cn/api/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-runtime")
    monkeypatch.setenv("MODEL", "minimax")
    monkeypatch.setenv("FILTER_MODEL", "qwen")
    monkeypatch.setenv("CLUSTER_MODEL", "glm")
    monkeypatch.setenv("SUMMARY_MODEL", "minimax")
    monkeypatch.setenv("PAPERTOOLS_FILTER_MODEL_CHAIN", "qwen,not-filter-model")
    monkeypatch.setenv("PAPERTOOLS_CLUSTER_MODEL_CHAIN", "qwen,not-cluster-model")
    monkeypatch.setattr(
        preflight_check.sys, "argv", ["preflight_check.py", "--offline-ok"]
    )

    assert preflight_check.main() == 2

    output = capsys.readouterr().out
    assert "not-filter-model" in output
    assert "not-cluster-model" in output


def test_preflight_prefers_papertools_chain_env_over_legacy(monkeypatch, capsys):
    from scripts import preflight_check

    prepare_preflight_test_env(monkeypatch, preflight_check)
    monkeypatch.setattr(preflight_check, "check_disk_space", lambda: (True, "ok"))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.sjtu.edu.cn/api/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-runtime")
    monkeypatch.setenv("MODEL", "minimax")
    monkeypatch.setenv("FILTER_MODEL", "qwen")
    monkeypatch.setenv("CLUSTER_MODEL", "glm")
    monkeypatch.setenv("SUMMARY_MODEL", "minimax")
    monkeypatch.setenv("PAPERTOOLS_FILTER_MODEL_CHAIN", "deepseek-chat")
    monkeypatch.setenv("FILTER_MODEL_CHAIN", "not-filter-model")
    monkeypatch.setenv("PAPERTOOLS_CLUSTER_MODEL_CHAIN", "minimax")
    monkeypatch.setenv("CLUSTER_MODEL_CHAIN", "not-cluster-model")
    monkeypatch.setattr(
        preflight_check.sys, "argv", ["preflight_check.py", "--offline-ok"]
    )

    assert preflight_check.main() == 0

    output = capsys.readouterr().out
    assert "PAPERTOOLS_FILTER_MODEL_CHAIN=deepseek-chat" in output
    assert "PAPERTOOLS_CLUSTER_MODEL_CHAIN=minimax" in output
    assert "not-filter-model" not in output
    assert "not-cluster-model" not in output


def test_preflight_disk_check_failure_blocks_run(monkeypatch, capsys):
    from scripts import preflight_check

    def failing_disk_usage(_path):
        raise OSError("disk metadata unavailable")

    monkeypatch.setattr(preflight_check.shutil, "disk_usage", failing_disk_usage)

    ok, message = preflight_check.check_disk_space()

    assert ok is False
    assert "CRITICAL: disk check failed" in message
    monkeypatch.setattr(preflight_check.sys, "argv", ["preflight_check.py"])
    assert preflight_check.main() == 2
    assert "disk metadata unavailable" in capsys.readouterr().out


def test_preflight_disk_check_uses_current_working_directory(monkeypatch, tmp_path):
    from scripts import preflight_check

    checked_paths = []

    def fake_disk_usage(path):
        checked_paths.append(Path(path))
        return SimpleNamespace(free=20 * 1024**3)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(preflight_check.shutil, "disk_usage", fake_disk_usage)

    ok, message = preflight_check.check_disk_space()

    assert ok is True
    assert checked_paths == [tmp_path]
    assert f"Disk space OK on {tmp_path}" in message


def test_preflight_remote_check_failure_blocks_run_unless_offline_ok(
    monkeypatch, capsys
):
    from scripts import preflight_check

    prepare_preflight_test_env(monkeypatch, preflight_check)

    def failing_create_openai_client(**_kwargs):
        raise RuntimeError("models endpoint unavailable")

    monkeypatch.setattr(preflight_check, "check_disk_space", lambda: (True, "ok"))
    monkeypatch.setattr(
        preflight_check, "create_openai_client", failing_create_openai_client
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.sjtu.edu.cn/api/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-runtime")
    monkeypatch.setenv("MODEL", "minimax")
    monkeypatch.setenv("FILTER_MODEL", "qwen")
    monkeypatch.setenv("CLUSTER_MODEL", "glm")
    monkeypatch.setenv("SUMMARY_MODEL", "minimax")
    monkeypatch.setattr(preflight_check.sys, "argv", ["preflight_check.py"])

    assert preflight_check.main() == 2
    assert "remote /models check failed" in capsys.readouterr().out

    monkeypatch.setattr(
        preflight_check.sys,
        "argv",
        ["preflight_check.py", "--offline-ok"],
    )

    assert preflight_check.main() == 0


def test_preflight_empty_remote_model_list_blocks_run(monkeypatch, capsys):
    from scripts import preflight_check

    prepare_preflight_test_env(monkeypatch, preflight_check)

    class EmptyModels:
        def list(self):
            return type("ModelList", (), {"data": []})()

    class FakeClient:
        models = EmptyModels()

        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    fake_client = FakeClient()

    monkeypatch.setattr(preflight_check, "check_disk_space", lambda: (True, "ok"))
    monkeypatch.setattr(
        preflight_check, "create_openai_client", lambda **_kwargs: fake_client
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.sjtu.edu.cn/api/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-runtime")
    monkeypatch.setenv("MODEL", "minimax")
    monkeypatch.setenv("FILTER_MODEL", "qwen")
    monkeypatch.setenv("CLUSTER_MODEL", "glm")
    monkeypatch.setenv("SUMMARY_MODEL", "minimax")
    monkeypatch.setattr(preflight_check.sys, "argv", ["preflight_check.py"])

    assert preflight_check.main() == 2

    assert fake_client.closed is True
    assert "remote /models returned no model IDs" in capsys.readouterr().out
