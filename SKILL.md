---
name: papertools
description: Operate the PaperTools arXiv reading pipeline from setup through safe publication. Use when asked to install or configure PaperTools, browse its published reading pages, crawl and select arXiv papers, generate Chinese paper analyses and daily overviews, resume a failed stage, customize research filters, validate publication payloads, troubleshoot the daily pipeline, or deploy the generated website. Do not use for generic paper summarization that does not involve this repository or its workflow.
---

# PaperTools

Use the repository containing this file as the PaperTools project root. Reuse its CLI, scripts, caches, tests, and documentation instead of recreating the pipeline.

## Start safely

1. Read `AGENTS.md` before changing or publishing anything.
2. Inspect `git status --short --branch`. Preserve unrelated and pre-existing changes.
3. Determine whether the request is to browse, configure, generate, customize, diagnose, deploy, or publish.
4. Treat model-backed generation as potentially costly. If the user did not request execution, explain the command without calling external model APIs.
5. Never expose `.env`, API keys, provider tokens, webhook URLs, or masked credentials in output.

## Choose the workflow

### Browse existing pages

Do not require API configuration. From the project root, run:

```bash
python -m http.server 8080 --directory webpages
```

Use `papertools serve` only when Python dependencies are installed; it validates published payloads before serving.

### Set up the pipeline

Require Python 3.10 or newer. Prefer a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
cp .env.example .env
papertools check
```

Do not overwrite an existing `.env`. Ask the user to supply credentials through `.env` or their secret manager. Explain that the current summary provider configuration is not fully provider-neutral; remove unavailable provider and model placeholders before running.

Install `.[extract-all]` only when local PDF extraction is requested. Read `docs/configuration.md` when provider chains, timeouts, concurrency, extraction, or fallback behavior must be changed.

### Generate a reading page

Use a specific arXiv update date. Start with a small run unless the user explicitly requests the full pipeline:

```bash
papertools run --mode quick --date YYYY-MM-DD --skip-serve
```

After it succeeds, validate and serve:

```bash
python scripts/validate_published_payloads.py --webpages-dir webpages
papertools serve
```

Use `--mode full` only when requested or after the quick result has been checked. A weekend, holiday, source date with no papers, or date with no selected papers is a valid skip and must not create an empty page.

### Resume a failed stage

Read `docs/pipeline.md` before resuming. Confirm that the selected stage's input file exists and is complete, then use one of:

```bash
papertools run --start-from cluster --date YYYY-MM-DD --skip-serve
papertools run --start-from summary --date YYYY-MM-DD --skip-serve
papertools run --start-from unified --skip-serve
```

Do not use filtered or clustered intermediate data as a finished webpage. Do not skip a failed publication-blocking stage merely to obtain output.

### Customize the research scope

Change arXiv categories through CLI flags when possible. Edit `CRAWL_CATEGORIES` or `PAPER_FILTER_PROMPT` in `src/utils/config.py` only when the user wants a persistent scope change. Run a quick dated sample and inspect both selection count and paper relevance before a full run.

### Diagnose failures

Inspect the structured status file and the target `webpages/data/YYYY-MM-DD.json`, not only terminal logs or Git history. Classify the failure as crawl, extraction, filtering, clustering, summary, overview, webpage generation, or publication validation.

Fail closed on extraction error pages, model/provider errors, malformed filtering output, suspicious zero results, incomplete clusters, missing summary fields, missing daily overview, or invalid cached content. Preserve successful cache entries and completed stage outputs while repairing the actual blocker.

### Deploy or automate

Read `docs/deployment.md` and `docs/QUALITY_GATES.md`. Use `daily_update.sh` or `scripts/robust_daily_update.sh` for scheduled publication; do not schedule a raw `papertools run` command as the production publisher.

Before publishing, require all of the following:

- the scheduled run started from a clean worktree and the latest `origin/master` or `origin/main`;
- the publish lock was acquired;
- the target date exists in `webpages/data/index.json`;
- the target contains at least one paper and a non-empty daily overview;
- every paper passes the publication quality gate;
- `python scripts/validate_published_payloads.py --webpages-dir webpages` succeeds.

Do not commit or push unless the user explicitly requests publication or Git changes. When authorized, stage only intended files and verify the remote branch before pushing.

## Verify changes

Run checks in proportion to the change. For source, pipeline, or publication behavior, run:

```bash
make ci
```

For a generated website, always run the publication validator even when the pipeline command returned success. Add tests for every new recovery behavior or quality gate.

## Report the result

Lead with whether the requested page, diagnosis, or publication is complete. Include the processed date, paper count when available, validation result, files changed, and any external calls or Git operations performed. If the date was skipped, identify the healthy skip status. If blocked, identify the exact failed stage and leave the date unpublished.
