import calendar
import datetime

import pytest

from src.core import generate_summary as gs
from src.core.generate_summary import (
    SummaryBudgetExceeded,
    collect_streaming_completion,
    parse_rate_limit_reset_seconds,
    retry_on_openai_error,
)


def _epoch(s):
    dt = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return calendar.timegm(dt.timetuple())


def test_parse_reset_from_limit_resets_at():
    # API message form seen in production logs.
    msg = (
        "Error code: 429 - {'error': {'message': "
        "'Rate limit exceeded for api_key: x. Limit type: tokens. "
        "Current limit: 100000, Remaining: 0. "
        "Limit resets at: 2026-06-14 21:47:50 UTC'}}"
    )
    secs = parse_rate_limit_reset_seconds(
        msg, now_utc_epoch=_epoch("2026-06-14 21:46:50")
    )
    assert 55 <= secs <= 65  # ~60s until reset


def test_parse_reset_absent_returns_none():
    assert parse_rate_limit_reset_seconds("some other 429 error") is None


def test_parse_reset_in_past_returns_zero():
    msg = "Limit resets at: 2026-06-14 21:47:50 UTC"
    secs = parse_rate_limit_reset_seconds(
        msg, now_utc_epoch=_epoch("2026-06-14 21:50:00")
    )
    assert secs == 0.0


def test_budget_helpers():
    import time as _t

    gs.set_summary_deadline(0.0)  # 0 disables the budget
    assert gs.summary_budget_exceeded() is False

    gs.set_summary_deadline(_t.monotonic() - 1)  # already past
    assert gs.summary_budget_exceeded() is True

    gs.set_summary_deadline(_t.monotonic() + 1000)  # far future
    assert gs.summary_budget_exceeded() is False

    gs.set_summary_deadline(0.0)  # reset for other tests


def test_retry_decorator_does_not_retry_summary_budget_exceeded():
    calls = 0

    @retry_on_openai_error(max_retries=6)
    def budgeted_call():
        nonlocal calls
        calls += 1
        raise SummaryBudgetExceeded("rate-limit wait exceeds summary budget")

    with pytest.raises(SummaryBudgetExceeded):
        budgeted_call()

    assert calls == 1


def test_collect_streaming_completion_propagates_summary_budget_exceeded():
    class BudgetedProvider:
        disabled = False
        label = "sjtu:qwen"

        def cooldown_remaining(self):
            return 0.0

        def wait_for_rate_limit(self):
            raise SummaryBudgetExceeded("rate-limit wait exceeds summary budget")

    with pytest.raises(SummaryBudgetExceeded):
        collect_streaming_completion(
            [BudgetedProvider()],
            [{"role": "user", "content": "hello"}],
            temperature=0.1,
            cache_key="budget-test",
        )
