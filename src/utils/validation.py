"""Validation helpers for CLI and runtime arguments."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from src.utils.exceptions import ValidationError


DATE_FORMAT = "%Y-%m-%d"


def validate_date_string(value: Optional[str], field_name: str) -> Optional[str]:
    """Validate and normalize a date string in YYYY-MM-DD format."""
    if value in (None, ""):
        return None

    try:
        parsed = datetime.strptime(value, DATE_FORMAT)
    except ValueError as exc:
        raise ValidationError(
            f"{field_name} 格式错误，应为 YYYY-MM-DD: {value}"
        ) from exc

    return parsed.strftime(DATE_FORMAT)


def validate_date_inputs(
    *,
    date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Validate mutually exclusive single-date and date-range inputs."""
    normalized_date = validate_date_string(date, "--date")
    normalized_start = validate_date_string(start_date, "--start-date")
    normalized_end = validate_date_string(end_date, "--end-date")

    if normalized_date and (normalized_start or normalized_end):
        raise ValidationError("不能同时指定单个日期和日期范围")

    if bool(normalized_start) != bool(normalized_end):
        raise ValidationError("--start-date 和 --end-date 必须同时提供")

    if normalized_start and normalized_end and normalized_start > normalized_end:
        raise ValidationError("--start-date 不能晚于 --end-date")

    return normalized_date, normalized_start, normalized_end


def validate_positive_int(value: int, field_name: str, minimum: int = 1) -> int:
    """Ensure an integer is greater than or equal to the minimum."""
    if value < minimum:
        raise ValidationError(f"{field_name} 必须 >= {minimum}，当前值: {value}")
    return value


def validate_non_negative_int(value: int, field_name: str) -> int:
    """Ensure an integer is non-negative."""
    if value < 0:
        raise ValidationError(f"{field_name} 不能为负数，当前值: {value}")
    return value


def validate_positive_float(
    value: float,
    field_name: str,
    *,
    allow_zero: bool = False,
) -> float:
    """Ensure a float is positive, or non-negative when allow_zero is True."""
    if allow_zero:
        if value < 0:
            raise ValidationError(f"{field_name} 不能为负数，当前值: {value}")
    elif value <= 0:
        raise ValidationError(f"{field_name} 必须 > 0，当前值: {value}")
    return value
