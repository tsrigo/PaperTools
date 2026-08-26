from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_skill_frontmatter_is_discoverable_and_focused() -> None:
    content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(?P<frontmatter>.*?)\n---\n", content, re.DOTALL)

    assert match, "SKILL.md must start with YAML frontmatter"
    frontmatter = match.group("frontmatter")
    assert re.search(r"(?m)^name: papertools$", frontmatter)
    assert re.search(r"(?m)^description: .+", frontmatter)
    assert "PaperTools arXiv reading pipeline" in frontmatter
    assert "Do not use for generic paper summarization" in frontmatter


def test_skill_ui_metadata_matches_skill_name() -> None:
    content = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert 'display_name: "PaperTools"' in content
    assert 'short_description: "' in content
    assert 'default_prompt: "使用 $papertools ' in content


def test_readme_documents_skill_installation() -> None:
    content = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "## 作为 SKILL 安装" in content
    assert "$skill-installer" in content
    assert "$papertools" in content
    assert "$HOME/.agents/skills/papertools" in content


def test_readme_documents_custom_paper_interest_prompt() -> None:
    content = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "PAPER_FILTER_PROMPT" in content
    assert "{title}" in content
    assert "{summary}" in content
    assert "结果: [True/False]" in content
    assert "domain_paper/filtered_papers_YYYY-MM-DD.json" in content
    assert "domain_paper/excluded_papers_YYYY-MM-DD.json" in content
