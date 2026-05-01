from src.core import paper_filter


def test_missing_affiliations_without_author_signal_is_excluded(monkeypatch):
    def fake_query(*_args, **_kwargs):
        return False, "作者和机构都没有明显强信号。"

    monkeypatch.setattr(paper_filter, "query_prestige_llm", fake_query)

    included, paper, reason = paper_filter.resolve_missing_affiliations_prestige(
        title="Rethinking Agentic Reinforcement Learning In Large Language Models",
        authors="Fangming Cui, Ruixiao Zhu, Cheng Fang, Sunan Li, Jiahong Li",
        fetch_reason="无法获取论文前置内容",
        paper_with_reason={"title": "Rethinking Agentic Reinforcement Learning In Large Language Models"},
        client=None,
        model="test-model",
        temperature=0.1,
    )

    assert included is False
    assert paper["prestige_result"] is False
    assert paper["prestige_source"] == "llm_missing_affiliations"
    assert paper["prestige_status"] == "rejected"
    assert paper["exclude_stage"] == "prestige"
    assert "无法获取论文前置内容" in reason


def test_missing_affiliations_author_whitelist_is_still_included(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("LLM should not be called when author whitelist matches")

    monkeypatch.setattr(paper_filter, "query_prestige_llm", fail_if_called)

    included, paper, reason = paper_filter.resolve_missing_affiliations_prestige(
        title="A Strong Paper",
        authors="Yann LeCun, Example Author",
        fetch_reason="网络不可用",
        paper_with_reason={"title": "A Strong Paper"},
        client=None,
        model="test-model",
        temperature=0.1,
    )

    assert included is True
    assert paper["prestige_result"] is True
    assert paper["prestige_source"] == "whitelist_author"
    assert paper["prestige_status"] == "verified"
    assert paper["prestige_matches"]["authors"] == ["Yann LeCun"]
    assert "机构信息缺失" in reason


def test_missing_affiliations_llm_author_signal_can_include(monkeypatch):
    def fake_query(*_args, **_kwargs):
        return True, "作者是该领域公认高影响力研究者。"

    monkeypatch.setattr(paper_filter, "query_prestige_llm", fake_query)

    included, paper, reason = paper_filter.resolve_missing_affiliations_prestige(
        title="A Strong Paper",
        authors="Known Senior Researcher",
        fetch_reason="PDF 抽取失败",
        paper_with_reason={"title": "A Strong Paper"},
        client=None,
        model="test-model",
        temperature=0.1,
    )

    assert included is True
    assert paper["prestige_result"] is True
    assert paper["prestige_source"] == "llm_missing_affiliations"
    assert paper["prestige_status"] == "verified"
    assert "PDF 抽取失败" in reason
