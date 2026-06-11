# Contributing

PaperTools publishes user-facing daily reading pages. Treat generated webpages
and `webpages/data/*.json` as production content.

## Development Setup

```bash
pip install -e ".[dev]"
pre-commit install
cp .env.example .env
make ci
```

Keep real API keys out of commits. Use `.env` or your secret manager for local
credentials.

## Quality Gates

Run the relevant checks before opening a pull request:

```bash
make test
make lint
make security
```

`make ci` runs the main local gate. Tests disable ambient pytest plugin
autoloading so global developer tooling cannot break the project test run.
`make pre-commit` runs fast staged-file hooks and publication payload
validation when published data changes.

See [Quality Gates](docs/QUALITY_GATES.md) for the full gate matrix and the
payload validation contract.

## Publication Safety

Changes that affect crawling, filtering, clustering, summarization, overview
generation, or webpage generation must fail closed:

- Do not publish empty dates.
- Do not publish partial paper content.
- Do not treat pipeline success as publication success; validate the generated
  `webpages/data/YYYY-MM-DD.json` payload.
- Do not silently fall back after extraction, filtering, clustering,
  summarization, overview generation, or webpage generation fails.
- Add tests for new gates or recovery behavior that protect publication quality.

## Pull Request Checklist

- Describe the user-facing behavior and operational risk.
- Include tests for new validation, retry, fallback, or publication behavior.
- Run `make ci` and mention any checks that could not run.
- Confirm that generated webpages are complete if the PR changes published data.
- Keep unrelated formatting or generated-data churn out of focused fixes.
