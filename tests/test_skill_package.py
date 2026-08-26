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
    assert "Codex-native agent mode" in frontmatter


def test_skill_ui_metadata_matches_skill_name() -> None:
    content = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert 'display_name: "PaperTools"' in content
    assert 'short_description: "' in content
    assert 'default_prompt: "使用 $papertools ' in content


def test_skill_requires_mode_choice_and_defines_agent_native_pipeline() -> None:
    content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "## Choose a mode first" in content
    assert "## Resolve research interests" in content
    assert "Agent-native mode" in content
    assert "Full pipeline mode" in content
    assert "python src/core/crawl_arxiv.py" in content
    assert "gpt-5.6-luna" in content
    assert "processed exactly once" in content
    assert "agent_output/YYYY-MM-DD.html" in content
    assert "Never copy this simplified output into `webpages/data/`" in content
    assert "do not edit `PAPER_FILTER_PROMPT`" in content
    assert "prestige author or institution rules" in content
    assert "agent_output/" in gitignore


def test_readme_documents_skill_installation() -> None:
    content = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "## 作为 SKILL 安装" in content
    assert "$skill-installer" in content
    assert "$papertools" in content
    assert "$HOME/.agents/skills/papertools" in content
    assert "从 tsrigo/PaperTools 仓库根目录安装" in content
    assert "Agent 原生模式" in content
    assert "完整 Pipeline 模式" in content


def test_readme_documents_custom_paper_interest_prompt() -> None:
    content = (ROOT / "README.md").read_text(encoding="utf-8")

    assert content.index("## 自定义论文兴趣 Prompt") < content.index(
        "## 直接浏览已有内容"
    )
    assert "### 在 Agent 原生模式中" in content
    assert "### 在完整 Pipeline 模式中" in content
    assert "不会自行启用作者和机构优先级筛选" in content
    assert "PAPER_FILTER_PROMPT" in content
    assert "PRESTIGE_ENABLED=false" in content
    assert "{title}" in content
    assert "{summary}" in content
    assert "结果: [True/False]" in content
    assert "domain_paper/filtered_papers_YYYY-MM-DD.json" in content
    assert "domain_paper/excluded_papers_YYYY-MM-DD.json" in content
