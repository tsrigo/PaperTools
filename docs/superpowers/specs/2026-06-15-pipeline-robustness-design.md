# PaperTools Pipeline Robustness — Design

Date: 2026-06-15
Status: Approved (surgical scope)
Author: Claude (with tsrigo)

## Goal

Make the daily arXiv pipeline reliable under an unstable / rate-limited LLM API,
**without changing what it produces** (same crawl → filter → cluster → summary →
webpages output, same publish quality gates). Scope is surgical: change *where the
code runs*, *what persists between runs*, and *how the summary stage behaves when
the API throttles* — not the content pipeline itself.

## Background: why it keeps failing

Investigation on 2026-06-15 found three compounding root causes. They explain why
the pipeline has failed every night (06-12, 06-13, 06-14 all timed out at exactly
6h on date 2026-06-08) despite repeated fixes.

### RC1 — Fixes never reach production
- crontab runs `scripts/daily_full_run.sh` daily at 17:00 (Asia/Shanghai).
- That script *self-refreshes*: it `git fetch origin/master`, creates a throwaway
  `/tmp/papertools-daily-*` worktree from `origin/master`, and runs the pipeline
  there (`daily_full_run.sh:257-291, 402-411`).
- The last 3 fix commits (`660475d`, `33b5781`, `3eaf620`) are local-only, never
  pushed. `git log origin/master..HEAD` shows all three.
- The memory-recorded fixes were applied to `robust_daily_update.sh`, which cron
  does **not** run. Evidence: cron logs show `FILTER_MODEL=deepseek-chat FILTER_RPM=1`
  (daily_full_run defaults), not `robust_daily_update`'s `qwen`/`6`.
- Net effect: every fix the user made had zero effect on production.

### RC2 — Zero forward progress
- `cache/`, `arxiv_paper/`, `domain_paper/`, `summary/` are all gitignored
  (`.gitignore:29-73`) and `CACHE_DIR` defaults to relative `"cache"`.
- Because production runs inside a fresh `/tmp` worktree, none of these persist.
  Every night re-crawls, re-filters, and re-summarizes from empty; the per-field
  summary cache (`cache/summaries/`) provides zero cross-run benefit.
- The per-date loop `exit`s on the first failed date (`daily_full_run.sh:525-529`),
  so one stuck date (2026-06-08) permanently blocks the entire backlog behind it.

### RC3 — The summary stage spins 6h, then is SIGKILLed (losing work)
- `SUMMARY_MODEL_CHAIN` includes `sjtu:deepseek-reasoner` (`daily_full_run.sh:65`).
  All `sjtu:*` providers share one 100k-token / 5-min bucket (same key+base_url →
  same `_rate_state`, `generate_summary.py:298-307`).
- A `deepseek-reasoner` full-paper request exceeds the whole bucket, so it returns
  HTTP 429 "Limit type: tokens" *every* time — it can never succeed.
- `collect_streaming_completion` cycles all providers; the chain's last provider has
  no fallback, so it waits the fixed `SUMMARY_SJTU_429_COOLDOWN_SECONDS` (300s),
  retries, 429s again. Wrapped in `retry_on_openai_error(max_retries=6)` and the
  per-field repair loops, this spins indefinitely across every field of every paper.
- The cooldown ignores the exact `Limit resets at: <UTC>` timestamp the API returns.
- There is no wall-clock budget; the only thing that stops it is the external
  `timeout 21600` (6h) which SIGKILLs the process, discarding all in-memory state.

## Design

Four changes, each mapped to a root cause. Output and publish gates unchanged.

### Change 1 — Run from the persistent checkout (fixes RC1; foundation for RC2)

- Retire the self-refresh + `/tmp` worktree path in the production wrapper. The
  pipeline runs directly in `/data/users/weikaihuang/projects/PaperTools`.
- Consolidate onto a single in-place wrapper: rework `daily_full_run.sh` to run in
  place (no `run_latest_wrapper`, no `git worktree add`), keeping its per-date
  validate / commit / push logic. `robust_daily_update.sh` is removed or reduced to
  a thin alias to avoid future "fixed the wrong script" confusion.
- In-place publishing safety: before committing, refresh the publish branch
  (`git fetch` + `git merge --ff-only origin/<branch>`); commit only `webpages/`
  (as today); push behind the existing flags.
- Local code is now the source of truth — fixes take effect immediately, and
  `cache/` + intermediate artifacts persist on disk between runs.

### Change 2 — Automatic resume + backlog progress (fixes RC2)

- With Change 1, `cache/summaries/` persists. Each field is cached the moment it is
  produced (`_llm_generate`: cache lookup → call → cache save), so even a hard kill
  loses only the final file assembly, not the expensive per-field LLM work. Re-runs
  reuse cached fields and complete quickly.
- Change the per-date loop so a failed date is **logged and skipped (`continue`)**
  instead of aborting the whole run. A single stuck date no longer blocks newer
  dates. The run's overall exit reflects whether any date failed, but every
  processable date still gets published.
- No change to the dated-file reuse already present (`find_file_by_date`,
  `--skip-existing`).

### Change 3 — Summary stage degrades gracefully instead of spinning (core fix)

All sub-changes preserve output (same models actually used for summaries).

- **(a) Drop `sjtu:deepseek-reasoner` from the daily summary chain.** It cannot fit
  the SJTU token bucket and only causes the spin. Default daily chain becomes
  `sjtu:qwen,sjtu:deepseek-chat,sjtu:minimax,sjtu:glm,prism:gpt-5.5`.
- **(b) Respect `Limit resets at`.** Parse the reset timestamp (and/or
  `Remaining` tokens) from 429 errors and set the bucket cooldown until that time
  (bounded by a sane max), instead of a blind fixed 300s. Falls back to the fixed
  cooldown when the timestamp is absent.
- **(c) Prism as a real cross-bucket fallback.** Append `prism:gpt-5.5`
  (separate key + base_url → separate `_rate_state`; 10M tokens / 5h, 25 req / 5min).
  When SJTU is exhausted, the chain now actually makes progress instead of cycling
  cooling SJTU models.
- **(d) Wall-clock budget + clean checkpoint exit.** Give the summary stage a time
  budget (derived from / passed by the pipeline; configurable env). When the budget
  is exhausted, or all buckets are cooling past the budget, **save partial progress
  and exit with a `partial` status** rather than spinning to SIGKILL. The wrapper
  treats `partial` as "resume this date next run" (works because of Change 2).

### Change 4 — Config hygiene (supports all)

- `.env` is the single source of truth for secrets. Set a working SJTU key, correct
  RPM (10), and the Prism backup (`SUMMARY_PRISM_OPENAI_API_KEY` /
  `SUMMARY_PRISM_OPENAI_BASE_URL=https://ai.prism.uno/v1`, model `gpt-5.5`).
- Stop `daily_full_run.sh` from overriding `.env`/config with worse values
  (`FILTER_RPM=1`, reasoner chain). Keep env overrides available, but defaults must
  be sane: `SUMMARY_SJTU_RPM≈8-10`, `SUMMARY_PRISM_RPM≈5`, summary chain without
  the reasoner.
- The 3 SJTU keys the user has are interchangeable; pick the working one. Each key
  is its own token bucket (the 429 is per-`api_key`).

## Components touched

- `scripts/daily_full_run.sh` — remove worktree/self-refresh; run in place;
  per-date `continue`; in-place publish safety; sane defaults. (Change 1, 2, 4)
- `crontab` — point at the in-place wrapper (no functional change if we keep the
  same path but disable self-refresh). (Change 1)
- `src/core/generate_summary.py` — reset-time-aware cooldown; time budget + clean
  `partial` exit; ensure the chain dropping reasoner is purely config-driven.
  (Change 3)
- `src/utils/config.py` — sane rate-limit defaults; daily chain default without
  reasoner. (Change 4)
- `src/core/pipeline.py` — pass/propagate the summary time budget and surface a
  `partial` pipeline status that the wrapper resumes. (Change 3d)
- `.env` / `.env.example` — working SJTU key, Prism backup, documented knobs.
  (Change 4)

## Error handling / behavior contract

- A date that cannot complete within budget produces a `partial` status and **no**
  `webpages/data/<date>.json` (so nothing half-baked is published); it is retried
  next run from cache.
- A date that completes passes the existing publish quality gates unchanged.
- A failed/partial date never blocks other dates in the same run.
- API 429 / instability is handled by: per-bucket reset-aware cooldown → cross-bucket
  fallback (Prism) → time-budget checkpoint. No unbounded spin.

## Testing

- Unit: 429 `Limit resets at` parsing → correct cooldown; summary chain builder
  excludes reasoner from default; budget exhaustion triggers clean `partial` exit;
  resume skips cached fields.
- Integration / dry-run: run the stuck date 2026-06-08 in place locally and confirm
  it either completes or cleanly checkpoints + resumes, with no 6h spin.
- Regression: existing `tests/` stay green.

## Rollout

1. Land changes on a feature branch; review; merge to master (now the real source).
2. Update cron to the in-place wrapper.
3. Manually run the backlog (2026-06-08 onward) in place to unstick publishing.
4. Watch the next 2-3 cron runs via `logs/cron.log` + status JSONs.

## Out of scope (YAGNI)

- Rewriting the crawl/filter/cluster logic or output schema.
- A general checkpoint state machine across all stages (only summary needs the
  budget/partial behavior; other stages are fast and already file-resumable).
- Changing prompts, models' actual outputs, or publish quality rules.
