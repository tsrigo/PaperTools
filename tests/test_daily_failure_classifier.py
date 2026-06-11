import json

from scripts.classify_pipeline_failure import (
    is_permanent_failure,
    is_permanent_failure_text,
)


def test_progress_timestamp_does_not_look_like_http_403(tmp_path):
    log_file = tmp_path / "daily.log"
    log_file.write_text(
        "筛选论文: 19%|█████ | 185/981 [2:38:07<4:16:35, 19.34s/篇]\n"
        "[06:28:35] 筛选失败，流水线终止\n",
        encoding="utf-8",
    )

    assert not is_permanent_failure(None, str(log_file))


def test_explicit_403_error_is_permanent(tmp_path):
    log_file = tmp_path / "daily.log"
    log_file.write_text(
        "OpenAIError: Error code: 403 - forbidden\n",
        encoding="utf-8",
    )

    assert is_permanent_failure(None, str(log_file))


def test_status_failure_reason_can_mark_permanent_error(tmp_path):
    status_file = tmp_path / "status.json"
    status_file.write_text(
        json.dumps({"failure_reason": "model not found: stale-model"}),
        encoding="utf-8",
    )

    assert is_permanent_failure(str(status_file), None)


def test_rate_limit_text_is_not_permanent():
    assert not is_permanent_failure_text(
        "Error code: 429 - Crossed TPM / RPM / Max Parallel Request Limit"
    )
