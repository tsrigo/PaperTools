"""Helpers for constructing OpenAI-compatible clients used by pipeline stages."""

from __future__ import annotations

import os
from typing import Any

from openai import DefaultHttpxClient, OpenAI


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed


def openai_trust_env() -> bool:
    """Whether OpenAI-compatible API clients should inherit proxy env vars."""
    return _env_bool("PAPERTOOLS_OPENAI_TRUST_ENV", False)


def create_openai_client(**kwargs: Any) -> OpenAI:
    """Create an OpenAI client with deterministic timeout/retry defaults.

    The SDK defaults are not always enough for long daily PaperTools runs.  We
    set process-wide defaults that can still be overridden by callers:

      PAPERTOOLS_OPENAI_TIMEOUT             default 120 seconds
      PAPERTOOLS_OPENAI_SDK_MAX_RETRIES     default 2 SDK-level retries
      PAPERTOOLS_OPENAI_TRUST_ENV           default false; avoids broken proxy env
    """
    kwargs.setdefault("timeout", _env_float("PAPERTOOLS_OPENAI_TIMEOUT", 120.0, minimum=5.0))
    kwargs.setdefault("max_retries", _env_int("PAPERTOOLS_OPENAI_SDK_MAX_RETRIES", 2, minimum=0))
    kwargs.setdefault("http_client", DefaultHttpxClient(trust_env=openai_trust_env()))
    return OpenAI(**kwargs)
