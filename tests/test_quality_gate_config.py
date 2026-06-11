import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _local_hook_files_pattern(hook_id: str) -> str:
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    match = re.search(
        rf"(?ms)^      - id: {re.escape(hook_id)}\n(?P<body>.*?)(?=^      - id: |\Z)",
        config,
    )
    assert match, f"missing pre-commit hook {hook_id}"

    files_match = re.search(
        r"^        files: (?P<files>.+)$", match.group("body"), re.M
    )
    assert files_match, f"missing files pattern for pre-commit hook {hook_id}"
    return files_match.group("files")


def test_published_payload_hook_runs_for_html_and_data_changes():
    files_pattern = _local_hook_files_pattern("validate-published-payloads")
    matcher = re.compile(files_pattern)

    assert matcher.search("webpages/index.html")
    assert matcher.search("webpages/prestige-excluded.html")
    assert matcher.search("webpages/data/2026-05-12.json")
    assert matcher.search("webpages/data/prestige_excluded_papers.json")
    assert matcher.search("src/core/generate_unified_index.py")
    assert matcher.search("src/utils/publish_quality.py")
    assert matcher.search("scripts/validate_published_payloads.py")
    assert not matcher.search("README.md")
