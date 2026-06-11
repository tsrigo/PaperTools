import pytest

from src.core import generate_summary


def _paper(**overrides):
    paper = {
        "title": "Repairable Paper",
        "arxiv_id": "2605.00001",
        "link": "https://arxiv.org/abs/2605.00001",
        "authors": "Ada Lovelace, Alan Turing",
        "category": "cs.AI",
        "date": "2026-05-19",
        "summary": "Original abstract.",
        "summary_translation": "中文摘要。",
        "intro_logic": "引入逻辑。",
        "core_insight": "核心洞察。",
        "methodology": "",
        "additional_insights": "",
        "research_value": "研究价值。",
    }
    paper.update(overrides)
    return paper


def test_save_html_page_uses_atomic_text_writer(monkeypatch):
    calls = []

    def fake_save_text(path, content):
        calls.append((path, content))
        return True

    monkeypatch.setattr(generate_summary, "save_text", fake_save_text)

    assert (
        generate_summary.save_html_page("out/index.html", "<html></html>")
        == "out/index.html"
    )
    assert calls == [("out/index.html", "<html></html>")]


def test_save_html_page_failure_blocks_publication(monkeypatch):
    monkeypatch.setattr(generate_summary, "save_text", lambda *_args, **_kwargs: False)

    with pytest.raises(OSError, match="failed to save HTML page"):
        generate_summary.save_html_page("out/index.html", "<html></html>")


def test_generate_papers_list_html_escapes_untrusted_paper_fields(tmp_path):
    html_file = generate_summary.generate_papers_list_html(
        [
            {
                "arxiv_id": '2605.00001" onclick="evil()',
                "title": '<script>alert("x")</script>',
                "authors": "<img src=x onerror=alert(1)>",
                "category": 'cs.AI"><svg/onload=alert(2)>',
                "filter_reason": "<b onclick=evil>reason</b>",
                "summary2": "<script>bad()</script>",
                "summary": "<i>abstract</i>",
                "inspiration_trace": "<iframe src=evil></iframe>",
                "research_insights": "<math><mtext></math>",
                "critical_evaluation": "<details open>bad</details>",
            }
        ],
        str(tmp_path / "2026-05-31"),
    )

    html = (tmp_path / "2026-05-31" / "index.html").read_text(encoding="utf-8")

    assert html_file == str(tmp_path / "2026-05-31" / "index.html")
    assert '<script>alert("x")</script>' not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "<img src=x" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<b onclick=evil>reason</b>" not in html
    assert "&lt;b onclick=evil&gt;reason&lt;/b&gt;" in html
    assert "https://arxiv.org/abs/2605.00001%22%20onclick%3D%22evil%28%29" in html
    assert "deletePaper(&quot;2026-05-31&quot;," in html
    assert 'rel="noopener noreferrer"' in html


def test_repair_missing_summary_fields_backfills_methodology_and_insights(monkeypatch):
    paper = _paper()

    monkeypatch.setattr(
        generate_summary,
        "generate_methodology",
        lambda *_args, **_kwargs: "修复后的方法论。",
    )
    monkeypatch.setattr(
        generate_summary,
        "generate_additional_insights",
        lambda *_args, **_kwargs: "修复后的额外洞察。",
    )

    generate_summary.repair_missing_summary_fields(
        paper,
        ["methodology", "additional_insights"],
        "paper content",
        providers=[],
        temperature=0.1,
        paper_title="Repairable Paper",
        cache_manager=None,
    )

    assert paper["methodology"] == "修复后的方法论。"
    assert paper["additional_insights"] == "修复后的额外洞察。"
    assert generate_summary.missing_publish_fields(paper) == []


def test_translate_summary_prompt_preserves_terms_without_parenthetical_gloss(
    monkeypatch,
):
    captured = {}

    def fake_collect(_providers, messages, _temperature, _cache_key):
        captured["messages"] = messages
        return "本文提出 GRPO-style RLVR 方法。", object()

    monkeypatch.setattr(generate_summary, "collect_streaming_completion", fake_collect)

    result = generate_summary.translate_summary(
        "We propose a GRPO-style RLVR method.",
        providers=[],
        temperature=0.1,
        paper_title="Prompt Style",
        cache_manager=None,
    )

    prompt = captured["messages"][1]["content"]
    assert result == "本文提出 GRPO-style RLVR 方法。"
    assert "不要用括号为英文专有名词添加中文解释" in prompt
    assert "标注中文解释" not in prompt


def test_generate_daily_overview_rejects_failure_placeholder(monkeypatch):
    def fake_collect(_providers, _messages, _temperature, _cache_key):
        return "生成失败", object()

    monkeypatch.setattr(generate_summary, "collect_streaming_completion", fake_collect)

    with pytest.raises(ValueError, match="每日速览 2026-05-31"):
        generate_summary.generate_daily_overview(
            [_paper()],
            providers=[],
            temperature=0.1,
            date_str="2026-05-31",
            cache_manager=None,
        )


def test_generate_daily_overview_ignores_invalid_cached_overview(monkeypatch):
    class FakeCache:
        def __init__(self):
            self.saved = []
            self.fingerprints = []

        def get_summary_cache(self, _key, fingerprint):
            self.fingerprints.append(fingerprint)
            return "生成失败"

        def set_summary_cache(self, key, fingerprint, overview):
            self.saved.append((key, fingerprint, overview))

    class FakeProvider:
        cache_label = "fake"

    def fake_collect(_providers, _messages, _temperature, _cache_key):
        return "### 今日AI论文速览 (2026-05-31)\n\n有效速览。", FakeProvider()

    cache = FakeCache()
    monkeypatch.setattr(generate_summary, "ENABLE_CACHE", True)
    monkeypatch.setattr(generate_summary, "collect_streaming_completion", fake_collect)

    papers = [_paper(title="Paper A")]
    expected_fingerprint = generate_summary.build_daily_overview_cache_fingerprint(
        papers
    )
    overview = generate_summary.generate_daily_overview(
        papers,
        providers=[FakeProvider()],
        temperature=0.1,
        date_str="2026-05-31",
        cache_manager=cache,
    )

    assert overview.startswith("### 今日AI论文速览")
    assert cache.fingerprints == [expected_fingerprint]
    assert cache.saved == [
        (
            "fake:daily_overview_v2_2026-05-31",
            expected_fingerprint,
            "### 今日AI论文速览 (2026-05-31)\n\n有效速览。",
        )
    ]


def test_daily_overview_cache_fingerprint_covers_all_prompt_inputs():
    papers = [
        _paper(
            title=f"Paper {index}",
            arxiv_id=f"2605.{index:05d}",
            category="cs.AI",
            cluster="Agents",
            summary=f"Abstract {index}",
        )
        for index in range(12)
    ]
    changed_late_paper = [dict(paper) for paper in papers]
    changed_late_paper[11]["summary"] = (
        "Changed abstract outside the old first-ten-title fingerprint."
    )
    changed_cluster = [dict(paper) for paper in papers]
    changed_cluster[0]["cluster"] = "Planning"

    baseline = generate_summary.build_daily_overview_cache_fingerprint(papers)

    assert baseline != generate_summary.build_daily_overview_cache_fingerprint(
        changed_late_paper
    )
    assert baseline != generate_summary.build_daily_overview_cache_fingerprint(
        changed_cluster
    )


def test_repair_missing_additional_insights_uses_focused_prompt_after_invalid_default(
    monkeypatch,
):
    paper = _paper(methodology="方法论。", additional_insights="")
    calls = []

    def invalid_default(*_args, **_kwargs):
        calls.append("default")
        return "生成失败"

    def focused_repair(*_args, **_kwargs):
        calls.append("focused")
        return "聚焦修复后的额外洞察。"

    monkeypatch.setattr(
        generate_summary, "generate_additional_insights", invalid_default
    )
    monkeypatch.setattr(
        generate_summary,
        "repair_additional_insights_with_focused_prompt",
        focused_repair,
    )

    generate_summary.repair_missing_summary_fields(
        paper,
        ["additional_insights"],
        "paper content",
        providers=[],
        temperature=0.1,
        paper_title="Repairable Paper",
        cache_manager=None,
    )

    assert calls == ["default", "focused"]
    assert paper["additional_insights"] == "聚焦修复后的额外洞察。"
    assert generate_summary.missing_publish_fields(paper) == []


def test_repair_missing_methodology_uses_focused_prompt_after_invalid_default(
    monkeypatch,
):
    paper = _paper(methodology="", additional_insights="已有额外洞察。")
    calls = []

    def invalid_default(*_args, **_kwargs):
        calls.append("default")
        return "生成失败"

    def focused_repair(*_args, **_kwargs):
        calls.append("focused")
        return "聚焦修复后的方法论。"

    monkeypatch.setattr(generate_summary, "generate_methodology", invalid_default)
    monkeypatch.setattr(
        generate_summary,
        "repair_methodology_with_focused_prompt",
        focused_repair,
    )

    generate_summary.repair_missing_summary_fields(
        paper,
        ["methodology"],
        "paper content",
        providers=[],
        temperature=0.1,
        paper_title="Repairable Paper",
        cache_manager=None,
    )

    assert calls == ["default", "focused"]
    assert paper["methodology"] == "聚焦修复后的方法论。"
    assert generate_summary.missing_publish_fields(paper) == []


def test_repair_missing_fields_use_grounded_fallback_when_llm_repairs_invalid(
    monkeypatch,
):
    paper = _paper(
        summary="The paper studies persistent memory for long-horizon agents.",
        intro_logic="长程 agent 容易遗忘早期状态并重复犯错。",
        core_insight="作者把经验组织成可复用记忆，而不是只延长上下文。",
        methodology="",
        additional_insights="",
    )

    monkeypatch.setattr(
        generate_summary, "generate_methodology", lambda *_args, **_kwargs: "生成失败"
    )
    monkeypatch.setattr(
        generate_summary,
        "repair_methodology_with_focused_prompt",
        lambda *_args, **_kwargs: "生成失败",
    )
    monkeypatch.setattr(
        generate_summary,
        "generate_additional_insights",
        lambda *_args, **_kwargs: "生成失败",
    )
    monkeypatch.setattr(
        generate_summary,
        "repair_additional_insights_with_focused_prompt",
        lambda *_args, **_kwargs: "生成失败",
    )

    generate_summary.repair_missing_summary_fields(
        paper,
        ["methodology", "additional_insights"],
        "The method stores trajectories as reusable evidence for later decisions.",
        providers=[],
        temperature=0.1,
        paper_title="Repairable Paper",
        cache_manager=None,
    )

    assert "可提取文本" in paper["methodology"]
    assert "额外价值" in paper["additional_insights"]
    assert generate_summary.missing_publish_fields(paper) == []


def test_repair_missing_summary_fields_replaces_failed_research_value(monkeypatch):
    paper = _paper(
        methodology="方法论。",
        additional_insights="额外洞察。",
        research_value="ReviewGrounder 审稿生成失败：timeout",
        reviewgrounder_review={"error": "timeout"},
    )

    monkeypatch.setattr(
        generate_summary,
        "generate_research_value",
        lambda *_args, **_kwargs: "修复后的研究价值评估。",
    )

    generate_summary.repair_missing_summary_fields(
        paper,
        ["research_value", "reviewgrounder_review"],
        "paper content",
        providers=[],
        temperature=0.1,
        paper_title="Repairable Paper",
        cache_manager=None,
    )

    assert paper["research_value"] == "修复后的研究价值评估。"
    assert paper["reviewgrounder_review"]["source"] == "summary_field_repair_fallback"
    assert generate_summary.missing_publish_fields(paper) == []
