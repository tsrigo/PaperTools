"""Generic retry utility with exponential backoff and jitter."""

from __future__ import annotations

import logging
import os
import random
import time
import warnings
from functools import wraps
from typing import Callable, Optional, Tuple, Type, TypeVar

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .*doesn't match a supported version!",
    category=Warning,
)

import requests
from openai import OpenAIError

try:  # openai>=1.x typed exceptions
    from openai import APIConnectionError, APIStatusError, APITimeoutError, InternalServerError, RateLimitError
except Exception:  # pragma: no cover - compatibility with older openai packages
    APIConnectionError = APITimeoutError = RateLimitError = InternalServerError = OpenAIError  # type: ignore
    APIStatusError = OpenAIError  # type: ignore

logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable)

RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    ConnectionError,
    TimeoutError,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)

RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}
RETRYABLE_ERROR_STRINGS = (
    "connection error",
    "timeout",
    "timed out",
    "too many requests",
    "rate limit",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "try again",
    "overloaded",
    "econnreset",
    "connection reset",
    "connection aborted",
    "remote protocol error",
    "请求超时",
    "请求数限制",
)


def _status_code(exc: Exception) -> Optional[int]:
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) is not None:
        return int(response.status_code)
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        try:
            return int(status_code)
        except Exception:
            return None
    return None


def is_retryable(exc: Exception) -> bool:
    """Determine if an exception is retryable."""
    status_code = _status_code(exc)
    if status_code in NON_RETRYABLE_STATUS_CODES:
        return False
    if status_code in RETRYABLE_STATUS_CODES:
        return True

    if isinstance(exc, requests.exceptions.HTTPError):
        return False
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True
    if isinstance(exc, APIStatusError):
        return status_code in RETRYABLE_STATUS_CODES
    if isinstance(exc, OpenAIError):
        message = str(exc).lower()
        if any(code in message for code in ("401", "403", "invalid_api_key", "unauthorized", "forbidden")):
            return False
        return any(marker in message for marker in RETRYABLE_ERROR_STRINGS)
    return False


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


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 2.0,
    multiplier: float = 2.0,
    max_delay: float = 60.0,
    jitter: float = 0.25,
):
    """Retry a function with exponential backoff.

    Only retries network/server/rate-limit errors.  Authentication and most
    client-side 4xx errors are raised immediately.  Jitter is important for cron
    jobs because many daily API calls otherwise retry in lock-step.
    """
    env_max_delay = _env_float("PAPERTOOLS_RETRY_MAX_DELAY_SECONDS", max_delay, minimum=1.0)
    max_delay = min(max_delay, env_max_delay) if max_delay else env_max_delay

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception: Optional[Exception] = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc
                    if attempt >= max_retries or not is_retryable(exc):
                        raise
                    sleep_for = min(delay, max_delay)
                    if jitter:
                        sleep_for = sleep_for * random.uniform(max(0.0, 1.0 - jitter), 1.0 + jitter)
                    logger.warning(
                        "Retry %d/%d for %s after retryable error: %s; waiting %.1fs",
                        attempt + 1,
                        max_retries,
                        getattr(func, "__name__", "call"),
                        exc,
                        sleep_for,
                    )
                    time.sleep(sleep_for)
                    delay = min(delay * multiplier, max_delay)
            if last_exception:
                raise last_exception
            raise RuntimeError("retry wrapper exited unexpectedly")

        return wrapper  # type: ignore[return-value]

    return decorator
