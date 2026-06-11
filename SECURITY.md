# Security Policy

## Supported Versions

Security fixes are handled on the default branch. Operators running PaperTools
from a fork should regularly pull the latest default branch before scheduled
publication runs.

## Reporting a Vulnerability

Do not report suspected vulnerabilities in public issues.

Use GitHub's private vulnerability reporting for this repository when available.
If private reporting is unavailable, contact the maintainers through a private
channel and include:

- Affected component and commit.
- Steps to reproduce.
- Impact assessment.
- Any known mitigations.

Avoid sending real API keys, private papers, or production logs containing
secrets. Redact secrets before sharing diagnostic material.

## Security Expectations

- CI runs Bandit and fails on medium/high confidence findings.
- Secrets must stay in `.env`, GitHub Actions secrets, or an equivalent secret
  manager.
- Generated publication data must pass the repository quality gates before it is
  committed or pushed.
- Dependency or provider failures must not create user-visible placeholder
  content.
