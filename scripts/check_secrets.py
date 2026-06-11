#!/usr/bin/env python3
"""High-signal repository secret scanner for CI and pre-commit."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MAX_FILE_BYTES = 2 * 1024 * 1024
SECRET_CONTEXT_CHARS = 12

ALLOWLIST_VALUES = {
    "sk-REPLACE_WITH_YOUR_KEY",
    "sk-test",
    "sk-dotenv",
    "sk-runtime",
    "your_key_here",
    "your-api-key",
    "your_jina_token_here",
}

SKIP_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "cache",
    "dist",
    "logs",
}

BINARY_EXTENSIONS = {
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".webp",
    ".whl",
    ".zip",
}


@dataclass(frozen=True)
class SecretPattern:
    name: str
    regex: re.Pattern[str]


@dataclass(frozen=True)
class SecretFinding:
    path: str
    line: int
    kind: str
    match: str

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {redact_secret(self.match)}"


SECRET_PATTERNS = (
    SecretPattern(
        "openai_api_key", re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{19,}\b")
    ),
    SecretPattern("github_pat", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    SecretPattern("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    SecretPattern(
        "pumble_webhook",
        re.compile(
            r"https://api\.pumble\.com/[^\s)>'\"]*/incomingWebhooks/postMessage/[A-Za-z0-9_-]{20,}"
        ),
    ),
)


def redact_secret(value: str) -> str:
    """Return a stable redacted form without echoing full credentials."""
    if len(value) <= SECRET_CONTEXT_CHARS * 2:
        return "<redacted>"
    return f"{value[:SECRET_CONTEXT_CHARS]}...{value[-SECRET_CONTEXT_CHARS:]}"


def is_allowlisted(value: str) -> bool:
    if value in ALLOWLIST_VALUES:
        return True
    lowered = value.lower()
    return any(token in lowered for token in ("placeholder", "replace_with", "<"))


def scan_text(path: str, text: str) -> list[SecretFinding]:
    """Scan decoded text and return high-confidence secret findings."""
    findings: list[SecretFinding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in SECRET_PATTERNS:
            for match in pattern.regex.finditer(line):
                value = match.group(0)
                if is_allowlisted(value):
                    continue
                findings.append(
                    SecretFinding(
                        path=path,
                        line=line_no,
                        kind=pattern.name,
                        match=value,
                    )
                )
    return findings


def _git_files(root: Path) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [
        root / entry.decode("utf-8", errors="replace")
        for entry in result.stdout.split(b"\0")
        if entry
    ]


def iter_candidate_files(root: Path) -> Iterable[Path]:
    try:
        files = _git_files(root)
    except (OSError, subprocess.CalledProcessError):
        files = [path for path in root.rglob("*") if path.is_file()]

    for path in files:
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in relative.parts):
            continue
        if path.suffix.lower() in BINARY_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def scan_file(root: Path, path: Path) -> list[SecretFinding]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    except OSError as exc:
        relative = os.fspath(path.relative_to(root))
        return [SecretFinding(relative, 0, "file_read_error", str(exc))]

    relative = os.fspath(path.relative_to(root))
    return scan_text(relative, text)


def scan_repository(root: Path) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for path in iter_candidate_files(root):
        findings.extend(scan_file(root, path))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan repository files for secrets.")
    parser.add_argument("--root", default=".", help="Repository root to scan")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    findings = scan_repository(root)
    if findings:
        print("Secret scan failed:")
        for finding in findings:
            print(f"  - {finding.format()}")
        return 1

    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
