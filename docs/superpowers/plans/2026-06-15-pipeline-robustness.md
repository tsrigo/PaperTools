# Pipeline Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the daily arXiv pipeline reliable under an unstable/rate-limited LLM API without changing its output: run in place (so fixes deploy and cache persists), make the summary stage degrade gracefully instead of spinning 6h, and let the backlog advance past stuck dates.

**Architecture:** Surgical changes to four areas — summary model chain/config (drop the bucket-busting reasoner, add a real cross-bucket Prism fallback), the summary stage's rate-limit handling (respect `Limit resets at`, bounded cooldown, wall-clock budget with clean "partial/resume" exit), the pipeline's status plumbing (surface `partial`), and the cron wrapper (run in the persistent checkout, per-date `continue`).

**Tech Stack:** Python 3 (stdlib + openai SDK), pytest, bash.

---

## File Structure

- `src/utils/config.py` — default summary chain without reasoner; sane rate defaults. (modify)
- `src/core/generate_summary.py` — reset-aware bounded cooldown; time budget + `SummaryBudgetExceeded` + `deferred` status + exit code 3. (modify)
- `src/core/pipeline.py` — pass summary time budget; map summary rc 3 → pipeline status `partial`. (modify)
- `scripts/daily_full_run.sh` — run in place (no self-refresh/worktree); per-date `continue`; handle `partial`; sane defaults. (modify)
- `scripts/robust_daily_update.sh` — reduce to a thin alias to avoid divergence. (modify)
- `.env` / `.env.example` — working SJTU key + Prism backup (real key only in gitignored `.env`). (modify)
- Tests: `tests/test_summary_provider_fallback.py` (extend), `tests/test_summary_rate_limit.py` (new), `tests/test_daily_runtime_defaults.py` (extend).

---

## Task 1: Drop reasoner from default summary chain, add Prism fallback

**Files:**
- Modify: `src/utils/config.py` (DEFAULT_SUMMARY_MODEL_CHAIN, around line 134-141)
- Test: `tests/test_summary_provider_fallback.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_summary_provider_fallback.py`:

```python
def test_default_daily_chain_excludes_reasoner_and_includes_prism():
    from src.core.generate_summary import build_summary_providers

    chain = "sjtu:qwen,sjtu:deepseek-chat,sjtu:minimax,sjtu:glm,prism:gpt-5.5"
    providers = build_summary_providers(
        chain,
        modelscope_api_key="", modelscope_base_url="",
        sjtu_api_key="sk-sjtu", sjtu_base_url="https://models.sjtu.edu.cn/api/v1/",
        prism_api_key="sk-prism", prism_base_url="https://ai.prism.uno/v1",
        prism_rpm=5, prism_reasoning_effort="",
    )
    models = [p.model for p in providers]
    assert "deepseek-reasoner" not in models
    assert any(p.name == "prism" and p.model == "gpt-5.5" for p in providers)
```

- [ ] **Step 2: Run test to verify it passes already (chain builder is generic)** — Run: `python -m pytest tests/test_summary_provider_fallback.py::test_default_daily_chain_excludes_reasoner_and_includes_prism -v`. If it passes, the builder is fine and the real change is the *default*; proceed to Step 3 to fix the default constant.

- [ ] **Step 3: Update the default chain** in `src/utils/config.py`. Set `DEFAULT_SUMMARY_MODEL_CHAIN` default value to `"sjtu:qwen,sjtu:deepseek-chat,sjtu:minimax,sjtu:glm,prism:gpt-5.5"` (no `sjtu:deepseek-reasoner`). Keep it env-overridable via `PAPERTOOLS_DEFAULT_SUMMARY_MODEL_CHAIN` / `SUMMARY_MODEL_CHAIN`.

- [ ] **Step 4: Run the related suite** — Run: `python -m pytest tests/test_summary_provider_fallback.py -v`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils/config.py tests/test_summary_provider_fallback.py
git commit -m "fix(summary): default chain drops bucket-busting reasoner, adds prism fallback"
```

---

## Task 2: Reset-aware, bounded 429 cooldown

**Files:**
- Modify: `src/core/generate_summary.py` (add parser near `is_rate_limit_error` ~line 544; use it in `note_rate_limit_error` ~line 405)
- Test: `tests/test_summary_rate_limit.py` (new)

- [ ] **Step 1: Write the failing test** — create `tests/test_summary_rate_limit.py`:

```python
import time
from src.core.generate_summary import parse_rate_limit_reset_seconds


def test_parse_reset_from_limit_resets_at(monkeypatch):
    # API message form seen in production logs.
    msg = ("Error code: 429 - {'error': {'message': "
           "'Rate limit exceeded for api_key: x. Limit type: tokens. "
           "Current limit: 100000, Remaining: 0. "
           "Limit resets at: 2026-06-14 21:47:50 UTC'}}")
    secs = parse_rate_limit_reset_seconds(msg, now_utc_epoch=_epoch("2026-06-14 21:46:50"))
    assert 55 <= secs <= 65  # ~60s until reset


def test_parse_reset_absent_returns_none():
    assert parse_rate_limit_reset_seconds("some other 429 error") is None


def _epoch(s):
    import calendar, datetime
    dt = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return calendar.timegm(dt.timetuple())
```

- [ ] **Step 2: Run to verify it fails** — Run: `python -m pytest tests/test_summary_rate_limit.py -v`. Expected: FAIL (`parse_rate_limit_reset_seconds` undefined).

- [ ] **Step 3: Implement the parser** in `src/core/generate_summary.py` (place above `note_rate_limit_error` usage, e.g. near line 544):

```python
import calendar
import datetime as _dt
import re as _re

_RESET_AT_RE = _re.compile(
    r"resets? at:?\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\s*UTC", _re.IGNORECASE
)


def parse_rate_limit_reset_seconds(message: str, now_utc_epoch: float | None = None):
    """Seconds to wait until the API's stated reset time; None if not present."""
    if not message:
        return None
    m = _RESET_AT_RE.search(message)
    if not m:
        return None
    try:
        dt = _dt.datetime.strptime(m.group(1).replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    reset_epoch = calendar.timegm(dt.timetuple())
    now = now_utc_epoch if now_utc_epoch is not None else calendar.timegm(_dt.datetime.utcnow().timetuple())
    return max(0.0, reset_epoch - now)
```

- [ ] **Step 4: Use it in `note_rate_limit_error`** — change the signature to `note_rate_limit_error(self, exc=None)` and compute the cooldown from the parsed reset time when available, bounded by `PAPERTOOLS_SUMMARY_429_MAX_COOLDOWN_SECONDS` (default 330):

```python
def note_rate_limit_error(self, exc=None) -> None:
    base = max(0, int(self.rate_limit_cooldown_seconds or 0))
    cooldown = base
    if exc is not None:
        reset = parse_rate_limit_reset_seconds(str(exc))
        if reset is not None:
            cooldown = reset + 2.0  # small safety margin
    max_cd = env_int("PAPERTOOLS_SUMMARY_429_MAX_COOLDOWN_SECONDS", 330, minimum=1)
    cooldown = min(cooldown, float(max_cd))
    if cooldown <= 0:
        return
    with self._rate_lock:
        self._cooldown_until = max(self._cooldown_until, time.monotonic() + cooldown)
    print(f"⏳ {self.label} 触发 429，冷却 {cooldown:.0f}s 后再使用该 provider")
```

Update the single caller in `collect_streaming_completion` (~line 607): `provider.note_rate_limit_error(exc)`.

- [ ] **Step 5: Run tests** — Run: `python -m pytest tests/test_summary_rate_limit.py tests/test_summary_provider_fallback.py -v`. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/core/generate_summary.py tests/test_summary_rate_limit.py
git commit -m "fix(summary): honor API reset time for 429 cooldown, bounded"
```

---

## Task 3: Summary wall-clock budget + clean "partial" exit

**Files:**
- Modify: `src/core/generate_summary.py` (exception + deadline globals near top of module; arg in `main`; checks in `wait_for_rate_limit` and `process_paper_wrapper`; result handling; return code)
- Test: `tests/test_summary_rate_limit.py` (extend)

- [ ] **Step 1: Write failing test** — append to `tests/test_summary_rate_limit.py`:

```python
def test_budget_helpers(monkeypatch):
    from src.core import generate_summary as gs
    gs.set_summary_deadline(0.0)  # no budget
    assert gs.summary_budget_exceeded() is False
    import time as _t
    gs.set_summary_deadline(_t.monotonic() - 1)  # already past
    assert gs.summary_budget_exceeded() is True
    gs.set_summary_deadline(0.0)  # reset
```

- [ ] **Step 2: Run to verify it fails** — Run: `python -m pytest tests/test_summary_rate_limit.py::test_budget_helpers -v`. Expected: FAIL (helpers undefined).

- [ ] **Step 3: Add the budget primitives** near the top of `generate_summary.py` (after imports / globals):

```python
class SummaryBudgetExceeded(Exception):
    """Raised when the summary stage's wall-clock budget is exhausted."""


_SUMMARY_DEADLINE = 0.0  # monotonic seconds; 0 disables


def set_summary_deadline(deadline_monotonic: float) -> None:
    global _SUMMARY_DEADLINE
    _SUMMARY_DEADLINE = float(deadline_monotonic or 0.0)


def summary_budget_exceeded() -> bool:
    return _SUMMARY_DEADLINE > 0.0 and time.monotonic() >= _SUMMARY_DEADLINE
```

- [ ] **Step 4: Enforce the budget in `wait_for_rate_limit`** — before `time.sleep(wait_time)` (~line 403), bail out instead of sleeping past the deadline:

```python
            if _SUMMARY_DEADLINE > 0.0 and time.monotonic() + wait_time > _SUMMARY_DEADLINE:
                raise SummaryBudgetExceeded(
                    f"rate-limit wait {wait_time:.0f}s exceeds summary budget"
                )
            time.sleep(wait_time)
```

- [ ] **Step 5: Check budget + catch in `process_paper_wrapper`** — at the very top of `process_paper_wrapper` (after unpacking, before skip-existing), add:

```python
        if summary_budget_exceeded():
            return ("deferred", index, paper,
                    f"⏳ 预算用尽，推迟到下次运行: {paper_title[:50]}...")
```

and wrap the existing body so `SummaryBudgetExceeded` maps to `deferred` (add an except before the generic `except Exception`):

```python
        except SummaryBudgetExceeded:
            return ("deferred", index, paper,
                    f"⏳ 预算用尽，推迟到下次运行: {paper_title[:50]}...")
```

- [ ] **Step 6: Handle `deferred` in the results loop** (~line 2511-2532). Add a counter `deferred = 0` next to `partial_failed = 0`, and a branch:

```python
                elif status == "deferred":
                    deferred += 1
```

(Leave `updated_papers[index]` as the original paper — its cached fields persist for next run.)

- [ ] **Step 7: Distinguish partial exit code.** Replace the final return logic (~line 2611-2620) so that a budget-deferred run returns code 3 (resume), while genuine failures still return 1:

```python
    if deferred > 0 and failed == 0 and partial_failed == 0:
        print(f"⏳ 本轮预算用尽，{deferred} 篇推迟；已保存 {processed} 篇，下次续跑")
        return 3  # partial / resume
    if failed > 0 or partial_failed > 0:
        print("❌ 存在未完整生成的论文，拒绝将半成品交给发布阶段")
        return 1
    if overview_failed > 0:
        print("❌ 每日速览生成失败，拒绝发布不完整日期")
        return 1
    if processed + skipped != len(papers):
        print("❌ 处理数量与输入数量不一致，拒绝发布")
        return 1
    return 0 if (processed > 0 or skipped > 0) else 1
```

- [ ] **Step 8: Add the `--time-budget-seconds` arg + wire the deadline** in `main` (near other args ~line 1917, and after `args = parser.parse_args()`):

```python
    parser.add_argument(
        "--time-budget-seconds", type=float, default=0.0,
        help="本阶段墙钟预算秒数，0=不限；超出后保存已完成部分并以码3退出以便续跑",
    )
```

```python
    budget = args.time_budget_seconds or env_int("PAPERTOOLS_SUMMARY_TIME_BUDGET_SECONDS", 0, minimum=0)
    if budget and budget > 0:
        set_summary_deadline(time.monotonic() + float(budget))
        print(f"⏱️ 总结阶段预算: {budget:.0f}s")
```

- [ ] **Step 9: Run tests** — Run: `python -m pytest tests/test_summary_rate_limit.py -v`. Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add src/core/generate_summary.py tests/test_summary_rate_limit.py
git commit -m "feat(summary): wall-clock budget with clean partial/resume exit (code 3)"
```

---

## Task 4: Pipeline propagates budget and surfaces `partial` status

**Files:**
- Modify: `src/core/pipeline.py` (summary stage ~line 1012-1075)
- Test: `tests/test_pipeline_helpers.py` (extend if a helper is extracted; otherwise covered by dry-run)

- [ ] **Step 1: Pass a time budget to the summary subprocess.** In the summary `cmd` list (~line 1015-1035) append:

```python
            "--time-budget-seconds",
            str(int(os.getenv("PAPERTOOLS_SUMMARY_TIME_BUDGET_SECONDS", "0") or "0")),
```

(0 = unlimited unless the wrapper sets the env. The wrapper sets it; see Task 5.)

- [ ] **Step 2: Map summary rc 3 to a `partial` pipeline status.** `run_command` returns only bool, so add a budget-aware variant for the summary stage. Replace the summary `run_command(...)` call (~line 1047) with a direct check of the return code. Add this helper near `run_command`:

```python
def run_command_rc(cmd, description, progress_tracker=None, env=None):
    """Like run_command but returns the subprocess return code (or 124 on timeout)."""
    secret_args = find_secret_cli_args(cmd)
    if secret_args:
        msg = "❌ 拒绝运行包含密钥命令行参数的子进程: " + ", ".join(secret_args)
        (progress_tracker.log_with_timestamp if progress_tracker else print)(msg)
        return 1
    (progress_tracker.log_with_timestamp if progress_tracker else print)(f"🔄 开始: {description}")
    timeout = pipeline_stage_timeout_seconds()
    try:
        run_kwargs = {"text": True, "timeout": timeout}
        if env is not None:
            run_kwargs["env"] = env
        completed = subprocess.run(cmd, **run_kwargs)
        return completed.returncode
    except subprocess.TimeoutExpired:
        return 124
    except Exception:
        return 1
```

- [ ] **Step 3: Use it for the summary stage.** Replace `if run_command(cmd, "生成论文总结", progress, env=summary_env):` block so:

```python
        summary_rc = run_command_rc(cmd, "生成论文总结", progress, env=summary_env)
        if summary_rc == 3:
            progress.complete_step("生成论文总结", False)
            reason = "总结阶段预算用尽，已保存部分进度，下次运行续跑"
            progress.log_with_timestamp(f"⏳ {reason}")
            return finish_pipeline(0, "partial", reason)
        if summary_rc == 0:
            # ... existing success path (find file, validate) ...
        else:
            progress.complete_step("生成论文总结", False)
            progress.log_with_timestamp("❌ 总结生成失败，流水线终止")
            notify_failures("summary", ["Summary stage failed"])
            return finish_pipeline(1, "failed", "总结生成失败")
```

(Keep the existing success-path body — finding `_with_summary2.json`, `validate_summary_file`, `complete_step` — under the `if summary_rc == 0:` branch unchanged.)

- [ ] **Step 4: Run the suite** — Run: `python -m pytest tests/ -q`. Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/core/pipeline.py
git commit -m "feat(pipeline): propagate summary budget; surface partial/resume status"
```

---

## Task 5: Run the daily wrapper in place (no self-refresh/worktree); per-date continue; handle partial

**Files:**
- Modify: `scripts/daily_full_run.sh`

- [ ] **Step 1: Disable self-refresh by default.** Change line 32 `SELF_REFRESH="${PAPERTOOLS_DAILY_SELF_REFRESH:-1}"` → default `0`. This skips `run_latest_wrapper` so the script runs the local checkout's code.

- [ ] **Step 2: Run in the persistent checkout instead of a temp worktree.** Replace the worktree block (lines ~402-413: `fetch_origin_branch` / `git worktree add ... "$WORKTREE_DIR"` / `cp .env` / `cd "$WORKTREE_DIR"` / `BASE_SHA=...`) with running in `$ROOT_DIR`:

```bash
CURRENT_STAGE="prepare_checkout"
cd "$ROOT_DIR"
# Keep publishing on the configured branch; pull latest published webpages fast-forward only.
if [ -z "${PUBLISH_BRANCH:-}" ]; then PUBLISH_BRANCH="$(git symbolic-ref --quiet --short HEAD || echo master)"; fi
export PAPERTOOLS_GIT_BRANCH="$PUBLISH_BRANCH"
run_logged git fetch origin "$PUBLISH_BRANCH" || log "⚠️ fetch failed; continuing with local state"
git merge --ff-only "origin/$PUBLISH_BRANCH" >>"$LOG_FILE" 2>&1 || log "ℹ️ ff-merge skipped (local ahead or diverged)"
BASE_SHA="$(git rev-parse --short HEAD)"
log "📌 Running in place at $ROOT_DIR ($BASE_SHA)"
```

Remove the `cleanup()` worktree-removal body (or make it a no-op) and the `WORKTREE_DIR`/`BOOTSTRAP_WORKTREE_DIR` worktree creation; leave variable definitions harmless.

- [ ] **Step 3: Set a summary time budget from the per-date pipeline timeout.** Near `configure_daily_runtime_defaults` add:

```bash
    export PAPERTOOLS_SUMMARY_TIME_BUDGET_SECONDS="${PAPERTOOLS_DAILY_SUMMARY_TIME_BUDGET_SECONDS:-3000}"  # ~50 min/date
```

and lower the per-date hard timeout to a sane ceiling above the budget:

```bash
    export PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS="${PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS:-5400}"  # 90 min hard ceiling
```

- [ ] **Step 4: Sane summary/filter defaults (no reasoner; usable RPM).** In `configure_daily_runtime_defaults`:
  - line 65 `SUMMARY_MODEL_CHAIN` default → `sjtu:qwen,sjtu:deepseek-chat,sjtu:minimax,sjtu:glm,prism:gpt-5.5`
  - `PAPERTOOLS_FILTER_RPM` default 1 → `6`
  - add `export SUMMARY_SJTU_RPM="${PAPERTOOLS_DAILY_SUMMARY_SJTU_RPM:-8}"`

- [ ] **Step 5: Per-date `continue` + handle `partial`.** In the date loop (~line 525-548), replace the failure `exit "$PIPELINE_EXIT"` with non-fatal handling, and add a `partial` case:

```bash
    if [ "$PIPELINE_EXIT" -ne 0 ]; then
        log "⚠️ Pipeline for $RUN_DATE exited with code $PIPELINE_EXIT; skipping this date, continuing backlog"
        notify_failure "$(printf '⚠️ PaperTools pipeline date failed\n  • date: %s\n  • exit_code: %s\n  • run_id: %s' "$RUN_DATE" "$PIPELINE_EXIT" "$RUN_ID")"
        FAILED_DATE_LIST="$(append_date "${FAILED_DATE_LIST:-}" "$RUN_DATE")"
        continue
    fi
    PIPELINE_STATUS_VALUE="$(read_pipeline_status "$STATUS_FILE")"
    case "$PIPELINE_STATUS_VALUE" in
        partial)
            log "⏳ $RUN_DATE partial (budget); will resume next run"
            SKIPPED_DATE_LIST="$(append_date "$SKIPPED_DATE_LIST" "$RUN_DATE")"
            continue
            ;;
        skipped_no_source_papers|skipped_no_selected_papers)
            # ... existing skip handling ...
            ;;
    esac
    validate_date_output "$RUN_DATE" "$STATUS_FILE"
    log "✅ Pipeline completed for $RUN_DATE"
```

Keep the rest of the existing skip handling intact inside the `case`.

- [ ] **Step 6: Commit on the local branch + push (in place).** The existing commit/push block (lines ~558-603) already `git add webpages/` and pushes `HEAD:$PUBLISH_BRANCH`; in-place this commits onto the real checkout. Keep it; ensure it does NOT depend on `$WORKTREE_DIR`. Replace `$WORKTREE_DIR` references in failure logs with `$ROOT_DIR`.

- [ ] **Step 7: Syntax-check the script** — Run: `bash -n scripts/daily_full_run.sh`. Expected: no output (valid).

- [ ] **Step 8: Print-config smoke test** — Run: `PAPERTOOLS_DAILY_PRINT_RUNTIME_CONFIG=1 bash scripts/daily_full_run.sh`. Expected: prints config with `SUMMARY_MODEL_CHAIN` lacking `deepseek-reasoner`, `PAPERTOOLS_FILTER_RPM=6`, budget set.

- [ ] **Step 9: Commit**

```bash
git add scripts/daily_full_run.sh
git commit -m "fix(daily): run in place (no self-refresh/worktree); per-date continue; handle partial; sane defaults"
```

---

## Task 6: Collapse robust_daily_update.sh to a thin alias

**Files:**
- Modify: `scripts/robust_daily_update.sh`

- [ ] **Step 1: Replace its body with a delegating shim** so there is one wrapper of record:

```bash
#!/usr/bin/env bash
# Deprecated: superseded by daily_full_run.sh (in-place). Kept as an alias so
# existing cron entries / muscle memory keep working.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec /bin/bash "$DIR/daily_full_run.sh" "$@"
```

- [ ] **Step 2: Syntax-check** — Run: `bash -n scripts/robust_daily_update.sh`. Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add scripts/robust_daily_update.sh
git commit -m "chore(daily): make robust_daily_update.sh a thin alias to daily_full_run.sh"
```

---

## Task 7: Wire credentials in .env (secrets stay out of git)

**Files:**
- Modify: `.env` (gitignored — real keys), `.env.example` (placeholders only)

- [ ] **Step 1: Set the SJTU primary + Prism backup in `.env`** (do NOT commit). Ensure these lines exist with the working values:

(Use the real keys provided out-of-band; never commit them. `.env` is gitignored.)

```
SUMMARY_SJTU_OPENAI_API_KEY=<SJTU_KEY>
SUMMARY_SJTU_OPENAI_BASE_URL=https://models.sjtu.edu.cn/api/v1/
SUMMARY_PRISM_OPENAI_API_KEY=<PRISM_KEY>
SUMMARY_PRISM_OPENAI_BASE_URL=https://ai.prism.uno/v1
SUMMARY_SJTU_RPM=8
SUMMARY_PRISM_RPM=5
SUMMARY_MODEL_CHAIN=sjtu:qwen,sjtu:deepseek-chat,sjtu:minimax,sjtu:glm,prism:gpt-5.5
```

- [ ] **Step 2: Mirror as placeholders in `.env.example`** (commit this one) — same keys with `sk-...` / URLs but no real secrets; document the budget/cooldown knobs `PAPERTOOLS_SUMMARY_TIME_BUDGET_SECONDS`, `PAPERTOOLS_SUMMARY_429_MAX_COOLDOWN_SECONDS`.

- [ ] **Step 3: Verify `.env` is gitignored** — Run: `git check-ignore .env`. Expected: prints `.env`. Confirm `git status` does NOT show `.env`.

- [ ] **Step 4: Commit only the example**

```bash
git add .env.example
git commit -m "docs(env): document prism backup + summary budget/cooldown knobs"
```

---

## Task 8: Full validation + backlog dry-run

- [ ] **Step 1: Run the whole test suite** — Run: `python -m pytest tests/ -q`. Expected: all pass.

- [ ] **Step 2: Dry-run the stuck date in place with a small budget** to prove no 6h spin:

Run:
```bash
PAPERTOOLS_SUMMARY_TIME_BUDGET_SECONDS=600 \
PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS=900 \
timeout 1000 python papertools.py run --mode full --skip-serve \
  --date 2026-06-08 --status-file logs/dryrun_2026-06-08.json 2>&1 | tail -40
```

Expected: completes OR exits cleanly with pipeline status `partial` (code 0 at wrapper level / summary code 3) within ~10-15 min — NOT a hard 6h kill. Inspect `logs/dryrun_2026-06-08.json`.

- [ ] **Step 3: Resume run (no budget) to confirm cache reuse**:

Run:
```bash
timeout 3600 python papertools.py run --mode full --skip-serve \
  --date 2026-06-08 --status-file logs/dryrun2_2026-06-08.json 2>&1 | tail -40
```

Expected: most papers skipped/served from `cache/summaries/`, date completes (`status: ok`) and `webpages/data/2026-06-08.json` appears.

- [ ] **Step 4: Update cron** to run the in-place wrapper (path unchanged; self-refresh now off by default). Confirm with `crontab -l`. No edit needed if path is the same; otherwise update the entry.

- [ ] **Step 5: Final commit / branch wrap** — ensure the branch is clean; summarize for merge.

---

## Self-Review

- **Spec coverage:** Change1→Tasks 5,6; Change2→Tasks 3,5 (+ persistent cache from Task 5 in-place); Change3a→Task 1; Change3b→Task 2; Change3c→Tasks 1,7; Change3d→Tasks 3,4,5; Change4→Tasks 1,5,7. All covered.
- **Placeholders:** code shown for each code step; the only "existing path unchanged" reference (Task 4 Step 3) points to clearly-located current code.
- **Type/name consistency:** `parse_rate_limit_reset_seconds`, `set_summary_deadline`, `summary_budget_exceeded`, `SummaryBudgetExceeded`, `run_command_rc`, status `partial`, exit code `3` used consistently across tasks.
