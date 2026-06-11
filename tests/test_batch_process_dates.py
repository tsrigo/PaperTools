from __future__ import annotations

import fcntl
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_fake_python(tmp_path: Path) -> Path:
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$BATCH_CALL_LOG"
if [ "${1:-}" = "-" ]; then
  status_file="${2:-}"
  if [ -f "$status_file" ]; then
    sed -n 's/.*"status": "\\([^"]*\\)".*/\\1/p' "$status_file"
  else
    printf 'missing\\n'
  fi
  exit 0
fi
if [ "${1:-}" = "papertools.py" ]; then
  status_file=""
  run_date=""
  previous=""
  for arg in "$@"; do
    if [ "$previous" = "--status-file" ]; then
      status_file="$arg"
    elif [ "$previous" = "--date" ]; then
      run_date="$arg"
    fi
    previous="$arg"
  done
  if [[ " $* " == *" --date ${BATCH_FAIL_DATE:-__none__} "* ]]; then
    exit 3
  fi
  if [ -n "$status_file" ]; then
    mkdir -p "$(dirname "$status_file")"
    status="${BATCH_STATUS_VALUE:-ok}"
    if [ "$run_date" = "${BATCH_SKIP_DATE:-__none__}" ]; then
      status="${BATCH_SKIP_STATUS:-skipped_no_source_papers}"
      if [ "${BATCH_CREATE_SKIPPED_PAYLOAD:-0}" = "1" ]; then
        mkdir -p webpages/data
        printf '{"date": "%s"}\\n' "$run_date" > "webpages/data/${run_date}.json"
      fi
    fi
    printf '{"status": "%s", "exit_code": 0}\\n' "$status" > "$status_file"
  fi
  exit 0
fi
if [ "${1:-}" = "scripts/validate_published_payloads.py" ]; then
  exit "${BATCH_VALIDATE_EXIT:-0}"
fi
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    return fake_python


def _run_batch(tmp_path: Path, **env_overrides: str) -> subprocess.CompletedProcess:
    return _run_batch_range(tmp_path, "2026-06-01", "2026-06-02", **env_overrides)


def _run_batch_range(
    tmp_path: Path,
    start_date: str,
    end_date: str,
    **env_overrides: str,
) -> subprocess.CompletedProcess:
    call_log = tmp_path / "calls.log"
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "PYTHON_BIN": str(_write_fake_python(tmp_path)),
        "BATCH_CALL_LOG": str(call_log),
        **env_overrides,
    }
    touched_payloads = [
        ROOT / "webpages" / "data" / "2026-06-01.json",
        ROOT / "webpages" / "data" / "2026-06-02.json",
    ]
    preexisting_payloads = {path: path.exists() for path in touched_payloads}
    try:
        return subprocess.run(
            [
                "bash",
                str(ROOT / "scripts" / "batch_process_dates.sh"),
                start_date,
                end_date,
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    finally:
        for path in touched_payloads:
            if not preexisting_payloads[path] and path.exists():
                path.unlink()


def test_batch_process_dates_validates_after_successful_backfill(tmp_path):
    result = _run_batch(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    calls = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "papertools.py run --mode full --date 2026-06-01 --skip-serve" in calls
    assert "papertools.py run --mode full --date 2026-06-02 --skip-serve" in calls
    assert "--status-file" in calls
    assert "scripts/validate_published_payloads.py --webpages-dir webpages" in calls


def test_batch_process_dates_rejects_invalid_date_format(tmp_path):
    result = _run_batch_range(tmp_path, "2026-6-01", "2026-06-02")

    assert result.returncode == 2
    assert "START_DATE 必须使用 YYYY-MM-DD 格式" in result.stdout
    assert not (tmp_path / "calls.log").exists()


def test_batch_process_dates_rejects_invalid_calendar_date(tmp_path):
    result = _run_batch_range(tmp_path, "2026-02-31", "2026-03-01")

    assert result.returncode == 2
    assert "START_DATE 不是有效日历日期" in result.stdout
    assert not (tmp_path / "calls.log").exists()


def test_batch_process_dates_rejects_reversed_range(tmp_path):
    result = _run_batch_range(tmp_path, "2026-06-02", "2026-06-01")

    assert result.returncode == 2
    assert "START_DATE 不能晚于 END_DATE" in result.stdout
    assert not (tmp_path / "calls.log").exists()


def test_batch_process_dates_skips_when_publish_lock_is_held(tmp_path):
    lock_file = tmp_path / "publish.lock"
    with lock_file.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

        result = _run_batch(tmp_path, PAPERTOOLS_PUBLISH_LOCK_FILE=str(lock_file))

    assert result.returncode == 0, result.stderr + result.stdout
    assert "已有 PaperTools 发布或回填任务在运行" in result.stdout
    assert not (tmp_path / "calls.log").exists()


def test_batch_process_dates_creates_custom_lock_parent_directory(tmp_path):
    lock_file = tmp_path / "locks" / "nested" / "publish.lock"

    result = _run_batch(tmp_path, PAPERTOOLS_PUBLISH_LOCK_FILE=str(lock_file))

    assert result.returncode == 0, result.stderr + result.stdout
    assert lock_file.exists()


def test_batch_process_dates_tracks_skipped_dates_separately(tmp_path):
    result = _run_batch(tmp_path, BATCH_SKIP_DATE="2026-06-01")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "2026-06-01 无可发布内容，已记录为跳过" in result.stdout
    assert "批量处理完成: 2026-06-02" in result.stdout
    assert "跳过日期: 2026-06-01" in result.stdout
    calls = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "scripts/validate_published_payloads.py --webpages-dir webpages" in calls


def test_batch_process_dates_fails_if_skipped_date_generates_payload(tmp_path):
    result = _run_batch(
        tmp_path,
        BATCH_SKIP_DATE="2026-06-01",
        BATCH_CREATE_SKIPPED_PAYLOAD="1",
    )

    assert result.returncode == 1
    assert "被标记为跳过但生成了发布 payload" in result.stdout
    assert "存在失败日期: 2026-06-01" in result.stdout


def test_batch_process_dates_fails_on_unhealthy_success_status(tmp_path):
    result = _run_batch(tmp_path, BATCH_STATUS_VALUE="failed")

    assert result.returncode == 1
    assert "返回成功但状态文件不健康: failed" in result.stdout
    assert "存在失败日期: 2026-06-01 2026-06-02" in result.stdout


def test_batch_process_dates_exits_nonzero_when_any_date_fails(tmp_path):
    result = _run_batch(tmp_path, BATCH_FAIL_DATE="2026-06-01")

    assert result.returncode == 1
    assert "存在失败日期: 2026-06-01" in result.stdout
    calls = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "papertools.py run --mode full --date 2026-06-02 --skip-serve" in calls
    assert "scripts/validate_published_payloads.py --webpages-dir webpages" in calls


def test_batch_process_dates_exits_nonzero_when_final_validation_fails(tmp_path):
    result = _run_batch(tmp_path, BATCH_VALIDATE_EXIT="9")

    assert result.returncode == 1
    assert "发布 payload 校验失败" in result.stdout
