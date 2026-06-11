from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPERATOR_DOCS = (
    "README.md",
    ".github/copilot-instructions.md",
    "docs/QUALITY_GATES.md",
    "docs/SJTU_ROBUST_RUNBOOK.md",
    "docs/deployment.md",
    "docs/pipeline.md",
)


def _read_doc(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_operator_docs_do_not_schedule_raw_pipeline_publishing():
    cron_raw_pipeline = re.compile(
        r"(?m)^\s*[\d*/,-]+\s+[\d*/,-]+\s+[\d*/,-]+\s+[\d*/,-]+\s+"
        r"[\d*/,-]+.*(?:papertools(?:\.py)?\s+run|python\s+papertools\.py\s+run)"
    )

    offenders = [
        relative_path
        for relative_path in OPERATOR_DOCS
        if cron_raw_pipeline.search(_read_doc(relative_path))
    ]

    assert offenders == []


def test_pipeline_docs_mark_skip_serve_as_diagnostic_not_publish_cron():
    pipeline_docs = _read_doc("docs/pipeline.md")

    assert "papertools run --skip-serve" in pipeline_docs
    assert "适合本地诊断" in pipeline_docs
    assert "适合 cron" not in pipeline_docs


def test_deployment_docs_match_hardened_pages_workflow():
    deployment_docs = _read_doc("docs/deployment.md")

    assert "Deploy PaperTools Website" in deployment_docs
    assert "Deploy MyArxiv Website" not in deployment_docs
    assert "Allow GitHub Actions to create and approve pull requests" in deployment_docs
    assert "不需要勾选" in deployment_docs
    assert "./daily_update.sh" in deployment_docs
    assert "scripts/robust_daily_update.sh" in deployment_docs


def test_ai_coding_guide_keeps_publish_and_cache_invariants_current():
    guide = _read_doc(".github/copilot-instructions.md")

    assert "scripts/validate_published_payloads.py --webpages-dir webpages" in guide
    assert "papertools run --skip-serve" in guide
    assert "只适合本地诊断" in guide
    assert "SHA-256" in guide
    assert "MD5" not in guide


def test_public_docs_match_filter_timeout_default():
    source = _read_doc("src/core/paper_filter.py")
    match = re.search(
        r'FILTER_LLM_TIMEOUT = env_float\("PAPERTOOLS_FILTER_LLM_TIMEOUT", (?P<default>\d+),',
        source,
    )
    assert match, "missing PAPERTOOLS_FILTER_LLM_TIMEOUT default in source"
    default = match.group("default")

    assert f"默认 {default}" in _read_doc("README.md")
    assert f"默认 `{default}`" in _read_doc("docs/configuration.md")


def test_public_docs_match_pipeline_stage_timeout_default():
    source = _read_doc("src/core/pipeline.py")
    match = re.search(
        r'os\.getenv\("PAPERTOOLS_PIPELINE_STAGE_TIMEOUT_SECONDS", "(?P<default>\d+)"\)',
        source,
    )
    assert match, "missing PAPERTOOLS_PIPELINE_STAGE_TIMEOUT_SECONDS default in source"
    default = match.group("default")

    assert f"默认 {default}" in _read_doc("README.md")
    assert f"默认 `{default}`" in _read_doc("docs/configuration.md")
