# Quality Gates

PaperTools publishes daily reading pages directly from generated JSON payloads.
The default posture is fail closed: a missing daily page is preferable to a
published page that looks complete but contains empty, partial, or placeholder
content.

## Local Setup

PaperTools supports CPython 3.10 through 3.14. Pull request CI runs the test
suite across every CPython minor version advertised in `pyproject.toml`.

```bash
pip install -e ".[dev]"
pre-commit install
```

`papertools run` does not install missing dependencies at runtime. Use
`pip install -e .` for normal setup, or `papertools check --install-missing`
when you explicitly want the CLI to install missing core runtime packages.

Use `make pre-commit` to run the pre-commit hooks across tracked files, and
`make ci` to run the same project-level gates used for pull request review.

## Gate Matrix

| Gate | Command | What it protects |
|------|---------|------------------|
| Lint and format | `make lint` | Python style drift across the CLI, `src/`, `tests/`, and `scripts/` |
| Tests with coverage | `make test-cov` | Runtime behavior and publication-quality guardrails |
| Security scan | `make security` | Medium/high Bandit findings in production code and the root CLI |
| Published data validation | `make validate-data` | User-facing `webpages/` entrypoint plus data completeness and index integrity |
| Dependency metadata | `make validate-metadata` | Drift between `pyproject.toml` and legacy `requirements.txt` |
| Package build | `make build` | Wheel buildability from `pyproject.toml` without installing dependencies |
| Full local gate | `make ci` | Main pre-merge confidence check, including pre-commit hooks |
| Pre-commit hooks | `make pre-commit` | Fast staged-file feedback plus payload validation when published HTML/data changes |

## Publication Payload Validation

`scripts/validate_published_payloads.py` is the release gate for checked-in
published data. It validates that:

- `webpages/` exists as an ordinary non-symlink directory, and
  `webpages/index.html` exists as an ordinary non-symlink HTML file, is
  readable, non-empty, and references published data.
- The entrypoint's embedded date manifest, initially loaded dates,
  load-more batch size, and content-derived cache-busting token match the
  published data index and date JSON payloads.
- The entrypoint's first-screen embedded papers, tag metadata, and daily
  overviews match the same date JSON payloads users can lazy-load.
- `webpages/data/index.json` is well formed, sorted newest-first, and has no
  duplicate dates.
- `index.json` runtime count fields such as `initial_days` and
  `load_more_days` must be positive integers, not JSON booleans.
- `webpages/data/` is an ordinary non-symlink directory and contains only
  expected ordinary JSON payload files: `index.json`, indexed date files, and
  the optional prestige-excluded audit payload. Temporary directories,
  non-JSON files, and symlinks are not publishable; JSON payload reads also
  refuse symlinks and directories instead of following them. Broken symlinks
  are reported as invalid publish artifacts rather than silently treated as
  missing files.
- Every indexed date has a corresponding `webpages/data/YYYY-MM-DD.json` file.
  Date-file matching only counts ordinary JSON files; a symlink or directory
  with the right name is still treated as a missing publishable payload.
- Date fields must use canonical `YYYY-MM-DD` strings with no leading or
  trailing whitespace.
- No stale date JSON files exist outside the index.
- Each listed date contains at least one paper and a non-empty daily overview.
- Every paper passes `src/utils/publish_quality.py`, including title, authors,
  arXiv ID, arXiv category, source link matching the arXiv ID, abstract,
  translation, intro logic, core insight, methodology, additional insights,
  research value review, and cluster metadata.
- Required identity metadata fields (`arxiv_id`, `title`, `link`, `authors`,
  and `category`) must be canonical strings with no leading or trailing
  whitespace.
- Paper `category` values must use arXiv primary category syntax such as
  `cs.AI`, `cs.CL`, `stat.ML`, or `q-bio.BM`.
- Each paper's arXiv category must also be present in its `tags` and in
  top-level tag counts so category filtering cannot silently disappear.
- `summary_translation` must contain Chinese text; an English abstract copied
  into the translation field is not publishable.
- Daily overviews must contain Chinese text and be canonical strings with no
  leading or trailing whitespace, so the first-screen reading guide cannot
  silently regress to an English placeholder or raw model output.
- User-facing metadata and generated content fields must contain real content,
  not placeholders such as `Unknown`, `N/A`, `TBD`, or equivalent empty-value
  markers.
- Paper-level generated content fields must also be canonical strings with no
  leading or trailing whitespace.
- User-facing cluster and tag labels must also be real publishable canonical
  text, because these labels drive page navigation and filtering.
- Cluster metadata is structurally consistent with the paper list, and cluster
  names must be unique within a date payload.
- A date cannot contain the same arXiv paper more than once.
- Top-level tag metadata must be present, unique, have positive integer counts
  (JSON booleans are not counts), and match the paper tags plus cluster
  assignments used by the webpage filters.
- If `webpages/prestige-excluded.html` is present, its
  `prestige_excluded_papers.json` payload must have consistent positive integer
  counts, dates, arXiv links, canonical paper fields, per-date paper identity,
  canonical institution summary metadata, and institution summary counts that
  match the paper-level institution names.
- If the prestige-excluded audit payload is present, the corresponding HTML
  page must exist and reference that payload.

If this validator fails, the payload is not publishable even when the pipeline
command itself exits successfully.

The unified page generator and the main pipeline both run this validator after
page generation. When serving existing pages with unified generation skipped,
the pipeline validates the existing `webpages/` artifact before starting the
local server. The top-level `papertools serve` command uses the same validator
before serving an existing site or a site it just regenerated.

If direct unified page generation fails validation, the previous
`webpages/index.html` and `webpages/data/` artifacts are restored; if they did
not previously exist, the failed candidates are removed.
The unified data writer also validates every candidate date payload before it
prunes stale date files or writes `index.json`, stages all JSON files before
making them visible in `webpages/data/`, restores the previous data directory if
the staged commit fails, and refuses to write an empty published-date index.

## Pipeline Changes

Changes in crawling, filtering, extraction, clustering, summarization, overview
generation, or webpage generation must add or update tests for the new failure
mode. Suspicious zero-result filtering, extraction failures, malformed LLM
output, and missing summaries are publication blockers unless an operator has
explicitly opted into debug-only behavior.

Document extraction plus paper/document cache reads treat HTTP error pages,
gateway failures, and common anti-bot challenge pages as invalid content.
Reusable cache envelopes must also match the current request key, URL, date,
category, and declared counts where applicable. Invalid document caches are not
persisted, stale invalid cache files are discarded, and the extraction manager
regenerates through the configured provider chain instead of counting a cached
error page as a successful paper extraction. Legacy paper caches that include
extracted `content` must also pass the paper-content gate before downstream
repair jobs can reuse them.

When debugging production failures, inspect the live JSON payloads under
`webpages/data/`; logs and commit status alone are not enough to prove that a
date is publishable.

## Scheduled Publishing

Use `./daily_update.sh` for cron-based publishing. The script requires a clean
`master` or `main` worktree, fast-forwards from `origin`, acquires the shared
publish lock, runs the full pipeline, validates published payloads, and commits
only `webpages/` artifacts. A failed pipeline or validator exits non-zero and
leaves the date unpublished.

The worktree-based `scripts/daily_full_run.sh` follows the same publish gate:
it resolves `master` or `main` as the publish branch, pipeline failures are not
committed, the full `webpages/` artifact is validated before staging, and any
push retry after rebasing validates the artifact again.

The retry-oriented `scripts/robust_daily_update.sh` also resolves `master` or
`main`, requires a clean scheduled worktree, fast-forwards from origin before
running the pipeline, validates the published artifact, and pushes only to the
resolved publish branch.

GitHub Pages deployment uses the checked-in `webpages/` artifact only. It does
not regenerate pages from intermediate files, and it runs the same validator
before upload.

For manual historical backfills, `scripts/batch_process_dates.sh` processes
weekdays in a date range, validates the final `webpages/` artifact when any
date succeeds, and exits non-zero if any date fails. It uses the same publish
lock as the daily automation so a manual backfill cannot write `webpages/`
while a scheduled publish is running.
