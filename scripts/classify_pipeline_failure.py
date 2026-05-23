#!/usr/bin/env python3
"""Classify daily pipeline failures without matching noisy progress text."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


PERMANENT_TEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\binvalid[_\s-]*api[_\s-]*key\b",
        r"\bunauthorized\b",
        r"\bforbidden\b",
        r"\bnot a valid model(?: id)?\b",
        r"\binvalid model(?: id| name)?\b",
        r"\bmodel[_\s-]*not[_\s-]*found\b",
        r"\binsufficient balance\b",
        r"\binsufficient quota\b",
        r"\bquota exceeded\b",
    )
]

PERMANENT_STATUS_CODE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:http\s*)?(?:error\s*)?code\s*[:=\-]?\s*(?:401|403)\b",
        r"\b(?:http\s*)?status\s*[:=\-]?\s*(?:401|403)\b",
        r"\bHTTP\s+(?:401|403)\b",
    )
]


def _flatten_status_strings(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"failure_reason", "message", "error", "code", "status"}:
                yield str(item)
            yield from _flatten_status_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_status_strings(item)


def is_permanent_failure_text(text: str) -> bool:
    """Return True for configuration/auth/model failures that retries cannot fix."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in PERMANENT_TEXT_PATTERNS) or any(
        pattern.search(text) for pattern in PERMANENT_STATUS_CODE_PATTERNS
    )


def is_permanent_failure(status_file: str | None, log_file: str | None) -> bool:
    texts: list[str] = []

    if status_file:
        path = Path(status_file)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                texts.extend(_flatten_status_strings(payload))
            except Exception:
                pass

    if log_file:
        path = Path(log_file)
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            # Keep only explicit error-ish lines so progress timestamps like 4:03
            # cannot be mistaken for HTTP 403.
            for line in text.splitlines():
                lowered = line.lower()
                if any(
                    token in lowered
                    for token in (
                        "error",
                        "exception",
                        "unauthorized",
                        "forbidden",
                        "invalid",
                        "quota",
                        "model",
                        "http",
                    )
                ):
                    texts.append(line)

    return any(is_permanent_failure_text(text) for text in texts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify PaperTools daily pipeline failures.")
    parser.add_argument("--status-file")
    parser.add_argument("--log-file")
    parser.add_argument(
        "--permanent",
        action="store_true",
        help="Exit 0 when the failure is permanent, 1 otherwise.",
    )
    args = parser.parse_args()

    permanent = is_permanent_failure(args.status_file, args.log_file)
    if args.permanent:
        return 0 if permanent else 1
    print("permanent" if permanent else "transient")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
