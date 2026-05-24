import os
import subprocess
import sys
from pathlib import Path


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
    assert values["CLUSTER_MODEL"] == "glm"
    assert values["SUMMARY_MODEL"] == "qwen"
    assert values["SUMMARY_MODEL_CHAIN"].startswith("sjtu:qwen")
    assert values["PAPERTOOLS_FILTER_RPM"] == "8"
    assert values["PAPERTOOLS_FILTER_LLM_TIMEOUT"] == "60"
    assert values["PAPERTOOLS_FILTER_LLM_MAX_RETRIES"] == "1"
    assert values["PAPERTOOLS_FILTER_EARLY_STOP_AFTER_CAP"] == "1"
    assert values["PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE"] == "1"
    assert values["PAPERTOOLS_FILTER_MAX_OUTPUT_PAPERS"] == "0"
    assert values["PAPERTOOLS_FILTER_RULE_VERSION"] == "2026-05-24-daily"
    assert values["PAPERTOOLS_SUMMARY_OPENAI_TIMEOUT"] == "60"
    assert values["DOCUMENT_EXTRACTOR_CHAIN"] == "jina,pymupdf4llm"
    assert values["JINA_MAX_RETRIES"] == "2"


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
    assert values["OPENAI_BASE_URL"] == "https://models.sjtu.edu.cn/api/v1/"
    assert values["PAPERTOOLS_FILTER_RPM"] == "8"
    assert values["PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE"] == "1"
    assert values["PAPERTOOLS_FILTER_MAX_OUTPUT_PAPERS"] == "0"
    assert values["PAPERTOOLS_FILTER_RULE_VERSION"] == "2026-05-24-daily"
    assert values["PAPERTOOLS_SUMMARY_OPENAI_TIMEOUT"] == "60"
    assert values["DOCUMENT_EXTRACTOR_CHAIN"] == "jina,pymupdf4llm"


def test_robust_daily_allows_explicit_daily_overrides(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test\nFILTER_MODEL=minimax-m2.5\n", encoding="utf-8")

    values = run_runtime_dump(
        tmp_path,
        env_file,
        PAPERTOOLS_DAILY_FILTER_MODEL="minimax",
        PAPERTOOLS_DAILY_FILTER_RPM="12",
        PAPERTOOLS_DAILY_TOPIC_HEURISTIC_BYPASS_PRESTIGE="0",
        PAPERTOOLS_DAILY_FILTER_MAX_OUTPUT_PAPERS="2",
        PAPERTOOLS_DAILY_FILTER_RULE_VERSION="test-rule",
    )

    assert values["FILTER_MODEL"] == "minimax"
    assert values["PAPERTOOLS_FILTER_RPM"] == "12"
    assert values["PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE"] == "0"
    assert values["PAPERTOOLS_FILTER_MAX_OUTPUT_PAPERS"] == "2"
    assert values["PAPERTOOLS_FILTER_RULE_VERSION"] == "test-rule"


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
