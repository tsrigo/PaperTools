"""Generic retry utility with exponential backoff."""

import time
import logging
import warnings
from functools import wraps
from typing import Tuple, Type

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 .*doesn't match a supported version!",
    category=Warning,
)

import requests
from openai import OpenAIError

logger = logging.getLogger(__name__)

RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError,
    ConnectionError,
    TimeoutError,
)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 524}

RETRYABLE_ERROR_STRINGS = (
    'Connection error', 'timeout', 'Too Many Requests',
    'Rate limit', 'Service Unavailable', '503', '502', '500', '524',
)


def is_retryable(exc: Exception) -> bool:
    """Determine if an exception is retryable."""
    if isinstance(exc, requests.exceptions.HTTPError):
        if hasattr(exc, 'response') and exc.response is not None:
            return exc.response.status_code in RETRYABLE_STATUS_CODES
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True
    if isinstance(exc, OpenAIError):
        return any(s in str(exc) for s in RETRYABLE_ERROR_STRINGS)
    return False


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 2.0,
    multiplier: float = 2.0,
    max_delay: float = 60.0,
):
    """Decorator that retries a function with exponential backoff.

    Only retries on network/server errors. Auth errors (4xx except 429)
    are raised immediately.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc

                    if attempt == max_retries or not is_retryable(exc):
                        raise

                    logger.warning(
                        "Retry %d/%d for %s after error: %s — waiting %.1fs",
                        attempt + 1, max_retries, func.__name__, exc, delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * multiplier, max_delay)

            raise last_exception

        return wrapper
    return decorator
