"""Helpers for constructing OpenAI-compatible clients used by pipeline stages."""

import os
from typing import Any

from openai import DefaultHttpxClient, OpenAI


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def openai_trust_env() -> bool:
    """Whether OpenAI-compatible API clients should inherit proxy env vars."""
    return _env_bool("PAPERTOOLS_OPENAI_TRUST_ENV", False)


def create_openai_client(**kwargs: Any) -> OpenAI:
    """Create an OpenAI client isolated from flaky process-wide proxy settings by default."""
    kwargs.setdefault("http_client", DefaultHttpxClient(trust_env=openai_trust_env()))
    return OpenAI(**kwargs)
