import time

from src.core import generate_summary as summary_module
from src.core.generate_summary import SummaryProvider, collect_streaming_completion


class _FakeDelta:
    content = "fallback ok"


class _FakeChoice:
    delta = _FakeDelta()


class _FakeChunk:
    choices = [_FakeChoice()]


class _FakeCompletions:
    def create(self, **_kwargs):
        return [_FakeChunk()]


class _FakeChat:
    completions = _FakeCompletions()


class _FailingCompletions:
    def create(self, **_kwargs):
        raise AssertionError("cooled-down provider should be skipped")


class _FailingChat:
    completions = _FailingCompletions()


class _FakeClient:
    chat = _FakeChat()


class _FailingClient:
    chat = _FailingChat()


def _provider(name: str) -> SummaryProvider:
    provider = SummaryProvider(
        name=name,
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
    )
    return provider


def test_collect_streaming_completion_skips_cooled_down_provider_when_fallback_exists():
    cooled_down = _provider("prism")
    fallback = _provider("sjtu")
    cooled_down.client = _FailingClient()
    fallback.client = _FakeClient()

    with cooled_down._rate_lock:
        cooled_down._cooldown_until = time.monotonic() + 60

    result, provider = collect_streaming_completion(
        [cooled_down, fallback],
        [{"role": "user", "content": "hello"}],
        temperature=0.1,
        cache_key="test",
    )

    assert result == "fallback ok"
    assert provider is fallback


def test_same_summary_provider_quota_bucket_shares_cooldown():
    summary_module._SUMMARY_RATE_STATES.clear()
    first = _provider("sjtu")
    second = SummaryProvider(
        name="sjtu",
        base_url=first.base_url,
        api_key=first.api_key,
        model="fallback-model",
    )
    first.rate_limit_cooldown_seconds = 60

    first.note_rate_limit_error()

    assert first._rate_lock is second._rate_lock
    assert second.cooldown_remaining() > 0


def test_summary_provider_timeout_can_be_lowered_by_environment(monkeypatch):
    captured = {}

    def fake_create_openai_client(**kwargs):
        captured["timeout"] = kwargs["timeout"]
        return _FakeClient()

    monkeypatch.setenv("PAPERTOOLS_SUMMARY_OPENAI_TIMEOUT", "12.5")
    monkeypatch.setattr(
        "src.core.generate_summary.create_openai_client",
        fake_create_openai_client,
    )

    SummaryProvider(
        name="sjtu",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
    )

    assert captured["timeout"] == 12.5


def test_default_daily_chain_excludes_reasoner_and_includes_prism():
    from src.core.generate_summary import build_summary_providers

    chain = "sjtu:qwen,sjtu:deepseek-chat,sjtu:minimax,sjtu:glm,prism:gpt-5.5"
    providers = build_summary_providers(
        chain,
        modelscope_api_key="",
        modelscope_base_url="",
        sjtu_api_key="sk-sjtu",
        sjtu_base_url="https://models.sjtu.edu.cn/api/v1/",
        prism_api_key="sk-prism",
        prism_base_url="https://ai.prism.uno/v1",
        prism_rpm=5,
        prism_reasoning_effort="",
    )
    models = [p.model for p in providers]
    assert "deepseek-reasoner" not in models
    assert any(p.name == "prism" and p.model == "gpt-5.5" for p in providers)
