from openai import OpenAIError

from src.core import paper_filter


def test_filter_model_chain_normalizes_stale_minimax_alias_to_stable_chat_model():
    chain = paper_filter.build_filter_model_chain("minimax-m2.5")

    assert chain[0] == "qwen"
    assert "deepseek-chat" in chain


def test_filter_model_chain_uses_openrouter_model_ids_for_openrouter_base_url():
    chain = paper_filter.build_filter_model_chain(
        "qwen",
        "https://openrouter.ai/api/v1/",
    )

    assert chain[0] == "qwen/qwen3-30b-a3b"
    assert "deepseek/deepseek-chat-v3-0324" in chain
    assert "qwen" not in chain


def test_prestige_defaults_do_not_bypass_hard_filter():
    assert paper_filter.TOPIC_HEURISTIC_BYPASS_PRESTIGE is False
    assert paper_filter.PRESTIGE_AFFILIATION_FETCH_ENABLED is True


def test_large_zero_filter_result_is_suspicious():
    assert paper_filter.is_suspicious_zero_result(
        total_input=1280,
        prefiltered_count=550,
        filtered_total=0,
    )


def test_small_or_keyword_empty_zero_filter_result_can_be_normal_skip():
    assert not paper_filter.is_suspicious_zero_result(
        total_input=1280,
        prefiltered_count=0,
        filtered_total=0,
    )
    assert not paper_filter.is_suspicious_zero_result(
        total_input=100,
        prefiltered_count=80,
        filtered_total=0,
    )
    assert not paper_filter.is_suspicious_zero_result(
        total_input=1280,
        prefiltered_count=550,
        filtered_total=1,
    )


def test_parse_llm_response_accepts_markdown_bold_result_label():
    result, reason = paper_filter.parse_llm_response(
        "**结果**: False\n\n**理由**:\n不符合主题。"
    )

    assert result is False
    assert reason == "不符合主题。"


def test_parse_llm_response_accepts_json_boolean_result():
    result, reason = paper_filter.parse_llm_response(
        '{"result": true, "reason": "strong agent paper"}'
    )

    assert result is True
    assert reason == "strong agent paper"


def test_timeout_exclusion_is_not_treated_as_current_schema():
    assert not paper_filter.is_current_excluded_schema(
        {
            "title": "Timed out paper",
            "filter_reason": "单篇筛选 API 超时",
            "exclude_stage": "filter_timeout",
            "filter_rule_version": paper_filter.FILTER_RULE_VERSION,
        }
    )


def test_existing_large_zero_filter_cache_is_still_suspicious():
    existing_filtered = []
    existing_excluded = [
        {"exclude_stage": "keyword"} for _ in range(400)
    ] + [
        {"exclude_stage": "topic"} for _ in range(150)
    ]

    prefiltered = paper_filter.estimate_existing_prefiltered_count(
        existing_filtered,
        existing_excluded,
    )

    assert prefiltered == 150
    assert paper_filter.is_suspicious_zero_result(
        total_input=550,
        prefiltered_count=prefiltered,
        filtered_total=0,
    )


def test_filter_early_stop_after_publish_cap_is_opt_in():
    assert paper_filter.should_stop_filter_after_cap(
        existing_filtered_count=10,
        new_filtered_count=5,
        max_papers=15,
        early_stop_enabled=True,
    )
    assert not paper_filter.should_stop_filter_after_cap(
        existing_filtered_count=10,
        new_filtered_count=5,
        max_papers=15,
        early_stop_enabled=False,
    )
    assert not paper_filter.should_stop_filter_after_cap(
        existing_filtered_count=10,
        new_filtered_count=5,
        max_papers=0,
        early_stop_enabled=True,
    )


def test_filter_errors_are_publish_blocking_even_with_selected_papers():
    assert paper_filter.has_blocking_filter_failures(
        error_count=1,
        timed_out_count=0,
        fatal_zero_result=False,
    )
    assert paper_filter.has_blocking_filter_failures(
        error_count=0,
        timed_out_count=1,
        fatal_zero_result=False,
    )
    assert not paper_filter.has_blocking_filter_failures(
        error_count=0,
        timed_out_count=0,
        fatal_zero_result=False,
    )


def test_topic_heuristic_does_not_keep_bare_agentic_cross_domain_paper():
    matched, _reason = paper_filter.evaluate_topic_heuristic(
        "Agentic Pipeline for Self-Synchronized Multiview Joint Angle Monitoring",
        "We propose an agentic pipeline for physical AI monitoring in uncalibrated environments.",
    )

    assert matched is False


def test_topic_heuristic_keeps_explicit_llm_agent_memory_paper():
    matched, reason = paper_filter.evaluate_topic_heuristic(
        "LongMINT: Evaluating Memory under Multi-Target Interference in Long-Horizon Agent Systems",
        "We benchmark memory-augmented LLM agents in long-horizon settings with interference.",
    )

    assert matched is True
    assert "Long-Horizon Agents" in reason or "LLM Agents" in reason


def test_topic_heuristic_keeps_agentic_paper_with_llm_context():
    matched, reason = paper_filter.evaluate_topic_heuristic(
        "Agentic Code Review for Large Language Model Software Agents",
        "This work studies agentic tool use, planning, and evaluation for LLM software agents.",
    )

    assert matched is True
    assert "Agentic" in reason


def test_topic_heuristic_bypass_requires_high_selection_score():
    strong_paper = {
        "title": "LongMINT: Evaluating Memory under Multi-Target Interference in Long-Horizon Agent Systems",
        "summary": "We benchmark memory-augmented LLM agents in long-horizon settings with interference.",
    }
    broad_paper = {
        "title": "Visual Agentic Memory for Online Long Video Understanding",
        "summary": "We study agentic retrieval and memory for multimodal video systems.",
    }

    assert paper_filter.should_bypass_prestige_for_topic_heuristic(strong_paper)
    assert not paper_filter.should_bypass_prestige_for_topic_heuristic(broad_paper)


def test_filter_model_fallback_skips_invalid_model(monkeypatch):
    calls = []

    def fake_run_llm_prompt(_prompt, _system, _client, model, _temperature):
        calls.append(model)
        if model == "bad-model":
            raise OpenAIError("/chat/completions: Invalid model name passed in model=bad-model")
        return "结果: False\n理由: fallback ok"

    monkeypatch.setattr(paper_filter, "run_llm_prompt", fake_run_llm_prompt)
    paper_filter._DISABLED_FILTER_MODELS.clear()

    response = paper_filter.run_llm_prompt_with_fallback(
        "prompt",
        "system",
        client=None,
        models=["bad-model", "qwen"],
        temperature=0.1,
    )

    assert response == "结果: False\n理由: fallback ok"
    assert calls == ["bad-model", "qwen"]
    assert "bad-model" in paper_filter._DISABLED_FILTER_MODELS


def test_filter_model_fallback_skips_not_a_valid_model_id(monkeypatch):
    calls = []

    def fake_run_llm_prompt(_prompt, _system, _client, model, _temperature):
        calls.append(model)
        if model == "qwen":
            raise OpenAIError(
                "Error code: 400 - {'error': {'message': 'qwen is not a valid model ID'}}"
            )
        return "结果: True\n理由: fallback ok"

    monkeypatch.setattr(paper_filter, "run_llm_prompt", fake_run_llm_prompt)
    paper_filter._DISABLED_FILTER_MODELS.clear()

    response = paper_filter.run_llm_prompt_with_fallback(
        "prompt",
        "system",
        client=None,
        models=["qwen", "deepseek-chat"],
        temperature=0.1,
    )

    assert response == "结果: True\n理由: fallback ok"
    assert calls == ["qwen", "deepseek-chat"]
    assert "qwen" in paper_filter._DISABLED_FILTER_MODELS


def test_missing_affiliations_without_author_signal_is_excluded(monkeypatch):
    def fake_query(*_args, **_kwargs):
        return False, "作者和机构都没有明显强信号。"

    monkeypatch.setattr(paper_filter, "PRESTIGE_LLM_ENABLED", True)
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

    monkeypatch.setattr(paper_filter, "PRESTIGE_LLM_ENABLED", True)
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
