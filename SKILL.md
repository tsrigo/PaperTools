---
name: papertools
description: Operate the PaperTools arXiv reading pipeline in either Codex-native agent mode or the full API-backed pipeline. Use when asked to install or configure PaperTools, crawl and select daily arXiv papers, summarize them with Codex or subagents, generate a lightweight reading result, browse published pages, run or recover the full PaperTools pipeline, customize research filters, validate publication payloads, troubleshoot daily generation, or deploy the website. Do not use for generic paper summarization that does not involve PaperTools or its crawl workflow.
---

# PaperTools

Use the repository containing this file as the PaperTools project root. Reuse its crawler, CLI, caches, tests, and documentation instead of recreating them.

## Choose a mode first

For any request that fetches or generates a new daily result, do not start external calls until the mode is known. If the user has not already chosen one, ask:

1. **Agent-native mode** — crawl paper metadata with PaperTools, then use Codex and optional subagents to filter and summarize it. This needs no separate model API configuration.
2. **Full pipeline mode** — run the repository's API-backed filter, cluster, summary, overview, and website stages with publication quality gates.

Also obtain the target date, arXiv categories, research interests, and desired output when they are missing. Do not ask for information already supplied.

## Start safely

1. Read `AGENTS.md` before changing or publishing anything.
2. Inspect `git status --short --branch`. Preserve unrelated and pre-existing changes.
3. Determine whether the request is to browse, configure, generate, customize, diagnose, deploy, or publish.
4. Treat model-backed generation as potentially costly. If the user did not request execution, explain the command without calling external model APIs.
5. Never expose `.env`, API keys, provider tokens, webhook URLs, or masked credentials in output.

## Resolve research interests

Use research interests from the current request when provided. Otherwise ask whether to use the repository's default scope from `PAPER_FILTER_PROMPT` or define a custom scope. For a custom scope, ask for topics to include and exclude; ask about borderline cases only when they materially change selection.

Convert the answer into a concise rubric with `Include`, `Exclude`, and optional `Prefer` rules. Confirm the rubric only when the request is ambiguous. Keep the same rubric for every paper and pass it unchanged to every filtering subagent.

In Agent-native mode, do not edit `PAPER_FILTER_PROMPT`. Do not apply the repository's prestige author or institution rules unless the user explicitly requests them. In full pipeline mode, use the repository default as-is or follow the persistent customization procedure below.

## Agent-native mode

Use this as a simplified reading workflow. It does not call the repository's external model providers and must not publish into `webpages/`.

### Crawl the source papers

Install the repository dependencies if needed, without creating or overwriting `.env`:

```bash
python -m pip install -e .
```

Run only the deterministic crawler for the requested date and categories:

```bash
python src/core/crawl_arxiv.py \
  --categories cs.AI cs.CL cs.LG \
  --output-dir arxiv_paper \
  --date YYYY-MM-DD
```

Change the category list to match the user's request. Do not add `--allow-empty` unless the user explicitly needs an empty diagnostic artifact. If the source has no papers, report a healthy skip and stop. If any category fetch fails, stop instead of processing a partial crawl.

Locate the generated `arxiv_paper/*_paper_YYYY-MM-DD.json`. Validate that it is a non-empty JSON array and that every item has `arxiv_id`, `title`, `summary`, `authors`, and `link` before delegation.

### Filter and summarize with agents

Treat the resolved research-interest rubric as the only semantic selection policy for the run.

For a large paper set, divide the papers into non-overlapping chunks and delegate independent chunks to subagents. Use `gpt-5.6-luna` for clear, high-volume filtering and concise summaries when it is available; otherwise use an available fast model and disclose the fallback. Adapt the number of agents to the available concurrency, keep assignments bounded, and wait for every assigned chunk.

Require each paper result to contain:

- `arxiv_id`, title, authors, link, and original abstract;
- `selected: true|false` and a short reason tied to the user's rubric;
- a concise Chinese summary for selected papers;
- one short topic label for selected papers.

Use only the crawled metadata by default. Fetch full text only when the user requests deeper analysis. Verify that every crawled `arxiv_id` was processed exactly once, merge duplicate papers by `arxiv_id`, and reject malformed subagent output instead of silently dropping it.

Have the main agent consolidate selected papers into topic groups and write a brief daily overview. Default to presenting the result in chat or Markdown. If the user requests files, place simplified artifacts under `agent_output/`, for example `agent_output/YYYY-MM-DD.md` and `agent_output/YYYY-MM-DD.json`.

Generate `agent_output/YYYY-MM-DD.html` only when the user requests a webpage and the current environment can create it. Keep it self-contained and clearly label it as an Agent-native result. Never copy this simplified output into `webpages/data/` or claim that it passed the full publication gate.

## Full pipeline mode

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

Change arXiv categories through CLI flags when possible. Edit `CRAWL_CATEGORIES` or `PAPER_FILTER_PROMPT` in `src/utils/config.py` only when the user wants a persistent scope change. Preserve the `{title}` and `{summary}` placeholders and the `结果:` and `理由:` output labels. Run a quick dated sample and inspect both selection count and paper relevance before a full run.

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

Lead with the chosen mode and whether the requested reading result, page, diagnosis, or publication is complete. Include the processed date, crawled and selected paper counts when available, validation result, files changed, and any external calls, subagent work, model fallback, or Git operations performed. If the date was skipped, identify the healthy skip status. If blocked, identify the exact failed stage and leave the date unpublished.
