from src.utils.openai_client import create_openai_client, openai_trust_env


def test_openai_clients_ignore_proxy_env_by_default(monkeypatch):
    monkeypatch.delenv("PAPERTOOLS_OPENAI_TRUST_ENV", raising=False)
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:9")

    client = create_openai_client(api_key="test-key", base_url="https://example.test/v1")
    try:
        assert openai_trust_env() is False
        assert getattr(client._client, "_trust_env") is False
    finally:
        client.close()


def test_openai_clients_can_opt_into_proxy_env(monkeypatch):
    monkeypatch.setenv("PAPERTOOLS_OPENAI_TRUST_ENV", "true")

    client = create_openai_client(api_key="test-key", base_url="https://example.test/v1")
    try:
        assert openai_trust_env() is True
        assert getattr(client._client, "_trust_env") is True
    finally:
        client.close()
