"""Deterministic cache-busting tokens for published webpage JSON."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def build_published_data_version(
    index_data: dict[str, Any],
    date_payloads_by_date: dict[str, Any],
) -> str:
    """Return a stable token for the exact JSON payloads the entrypoint can load."""
    dates = index_data.get("dates")
    ordered_dates = dates if isinstance(dates, list) else sorted(date_payloads_by_date)
    payload = {
        "index": index_data,
        "dates": {
            date: date_payloads_by_date.get(date)
            for date in ordered_dates
            if isinstance(date, str)
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]
