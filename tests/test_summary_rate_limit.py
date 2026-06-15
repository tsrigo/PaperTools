import calendar
import datetime

from src.core.generate_summary import parse_rate_limit_reset_seconds


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
    secs = parse_rate_limit_reset_seconds(msg, now_utc_epoch=_epoch("2026-06-14 21:46:50"))
    assert 55 <= secs <= 65  # ~60s until reset


def test_parse_reset_absent_returns_none():
    assert parse_rate_limit_reset_seconds("some other 429 error") is None


def test_parse_reset_in_past_returns_zero():
    msg = "Limit resets at: 2026-06-14 21:47:50 UTC"
    secs = parse_rate_limit_reset_seconds(msg, now_utc_epoch=_epoch("2026-06-14 21:50:00"))
    assert secs == 0.0
