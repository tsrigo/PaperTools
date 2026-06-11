#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/miniconda3/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

mkdir -p logs
RUN_ID="$(TZ=Asia/Tokyo date +'%Y%m%d-%H%M%S')"
LOG_FILE="logs/robust_daily_${RUN_ID}.log"
STATUS_FILE="logs/robust_daily_status_${RUN_ID}.json"
LOCK_FILE="${PAPERTOOLS_PUBLISH_LOCK_FILE:-${PAPERTOOLS_DAILY_LOCK_FILE:-logs/papertools_publish.lock}}"

mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another PaperTools daily run is already active; exiting." | tee -a "$LOG_FILE"
  exit 0
fi

log() {
  printf '[%s] %s\n' "$(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S %Z')" "$*" | tee -a "$LOG_FILE"
}

# Load .env without printing secrets. PaperTools itself also loads .env.
ENV_FILE="${PAPERTOOLS_DAILY_ENV_FILE:-.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ENV_FILE"
  set +a
fi

# SJTU-safe daily defaults. Keep the actual API key only in .env / secret manager.
#
# The daily wrapper intentionally overwrites risky .env values for operational
# controls. Use PAPERTOOLS_DAILY_* variables for explicit cron-time overrides.
export OPENAI_BASE_URL="${PAPERTOOLS_DAILY_OPENAI_BASE_URL:-https://models.sjtu.edu.cn/api/v1/}"
# Force SJTU key for filter/cluster when using SJTU base URL. Shell environment
# may carry an OpenRouter OPENAI_API_KEY that silently overrides the .env value.
# Read the SJTU key directly from .env as a reliable fallback.
if [ -z "${PAPERTOOLS_DAILY_OPENAI_API_KEY:-}" ]; then
  _SJTU_KEY="${SUMMARY_SJTU_OPENAI_API_KEY:-}"
  if [ -z "$_SJTU_KEY" ] && [ -f "$ENV_FILE" ]; then
    _SJTU_KEY="$(grep -m1 '^SUMMARY_SJTU_OPENAI_API_KEY=' "$ENV_FILE" | cut -d= -f2-)"
  fi
  if [ -z "$_SJTU_KEY" ] && [ -f "$ENV_FILE" ]; then
    _SJTU_KEY="$(grep -m1 '^OPENAI_API_KEY=' "$ENV_FILE" | cut -d= -f2-)"
  fi
  export OPENAI_API_KEY="${_SJTU_KEY:-$OPENAI_API_KEY}"
  unset _SJTU_KEY
fi
export MODEL="${PAPERTOOLS_DAILY_MODEL:-deepseek-reasoner}"
export FILTER_MODEL="${PAPERTOOLS_DAILY_FILTER_MODEL:-qwen}"
export PAPERTOOLS_FILTER_MODEL_CHAIN="${PAPERTOOLS_DAILY_FILTER_MODEL_CHAIN:-qwen,deepseek-chat,minimax}"
export CLUSTER_MODEL="${PAPERTOOLS_DAILY_CLUSTER_MODEL:-glm}"
export PAPERTOOLS_CLUSTER_MODEL_CHAIN="${PAPERTOOLS_DAILY_CLUSTER_MODEL_CHAIN:-qwen,deepseek-chat,minimax}"
export SUMMARY_MODEL_CHAIN="${PAPERTOOLS_DAILY_SUMMARY_MODEL_CHAIN:-sjtu:qwen,sjtu:deepseek-chat,sjtu:minimax,sjtu:glm}"
export SUMMARY_SJTU_OPENAI_API_KEY="${SUMMARY_SJTU_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
export SUMMARY_SJTU_OPENAI_BASE_URL="${SUMMARY_SJTU_OPENAI_BASE_URL:-$OPENAI_BASE_URL}"
export SUMMARY_OPENAI_API_KEY="${SUMMARY_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
export SUMMARY_OPENAI_BASE_URL="${SUMMARY_OPENAI_BASE_URL:-$OPENAI_BASE_URL}"
export SUMMARY_MODEL="${PAPERTOOLS_DAILY_SUMMARY_MODEL:-qwen}"

# Conservative concurrency is usually more stable on shared OpenAI-compatible gateways.
export FILTER_MAX_WORKERS="${PAPERTOOLS_DAILY_FILTER_MAX_WORKERS:-3}"
export SUMMARY_MAX_WORKERS="${PAPERTOOLS_DAILY_SUMMARY_MAX_WORKERS:-1}"
export PAPERTOOLS_FILTER_RPM="${PAPERTOOLS_DAILY_FILTER_RPM:-6}"
export PAPERTOOLS_FILTER_LLM_TIMEOUT="${PAPERTOOLS_DAILY_FILTER_LLM_TIMEOUT:-90}"
export PAPERTOOLS_FILTER_LLM_MAX_RETRIES="${PAPERTOOLS_DAILY_FILTER_LLM_MAX_RETRIES:-3}"
export PAPERTOOLS_FILTER_EARLY_STOP_AFTER_CAP="${PAPERTOOLS_DAILY_FILTER_EARLY_STOP_AFTER_CAP:-1}"
export PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE="${PAPERTOOLS_DAILY_TOPIC_HEURISTIC_BYPASS_PRESTIGE:-0}"
export PAPERTOOLS_FILTER_MAX_OUTPUT_PAPERS="${PAPERTOOLS_DAILY_FILTER_MAX_OUTPUT_PAPERS:-0}"
export PAPERTOOLS_FILTER_RULE_VERSION="${PAPERTOOLS_DAILY_FILTER_RULE_VERSION:-2026-05-31-topic-post-v2-daily}"
export PAPERTOOLS_OPENAI_TIMEOUT="${PAPERTOOLS_DAILY_OPENAI_TIMEOUT:-120}"
export PAPERTOOLS_SUMMARY_OPENAI_TIMEOUT="${PAPERTOOLS_DAILY_SUMMARY_OPENAI_TIMEOUT:-90}"
export PAPERTOOLS_OPENAI_SDK_MAX_RETRIES="${PAPERTOOLS_DAILY_OPENAI_SDK_MAX_RETRIES:-2}"
export PAPERTOOLS_RETRY_MAX_DELAY_SECONDS="${PAPERTOOLS_DAILY_RETRY_MAX_DELAY_SECONDS:-120}"
export PAPERTOOLS_OPENAI_TRUST_ENV="${PAPERTOOLS_DAILY_OPENAI_TRUST_ENV:-false}"
export DOCUMENT_EXTRACTOR_CHAIN="${PAPERTOOLS_DAILY_DOCUMENT_EXTRACTOR_CHAIN:-jina,pymupdf4llm}"
export DOCUMENT_EXTRACT_TIMEOUT="${PAPERTOOLS_DAILY_DOCUMENT_EXTRACT_TIMEOUT:-60}"
export JINA_REQUEST_TIMEOUT="${PAPERTOOLS_DAILY_JINA_REQUEST_TIMEOUT:-45}"
export JINA_MAX_RETRIES="${PAPERTOOLS_DAILY_JINA_MAX_RETRIES:-2}"
export PAPERTOOLS_DAILY_WINDOW_DAYS="${PAPERTOOLS_DAILY_WINDOW_DAYS:-4}"
export PAPERTOOLS_DAILY_MAX_CATCHUP_DAYS="${PAPERTOOLS_DAILY_MAX_CATCHUP_DAYS:-7}"
export PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS="${PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS:-28800}"
export PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK="${PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK:-0}"

print_runtime_config() {
  for key in \
    OPENAI_BASE_URL MODEL FILTER_MODEL CLUSTER_MODEL SUMMARY_MODEL SUMMARY_MODEL_CHAIN \
    PAPERTOOLS_FILTER_MODEL_CHAIN PAPERTOOLS_CLUSTER_MODEL_CHAIN \
    FILTER_MAX_WORKERS SUMMARY_MAX_WORKERS PAPERTOOLS_FILTER_RPM \
    PAPERTOOLS_FILTER_LLM_TIMEOUT PAPERTOOLS_FILTER_LLM_MAX_RETRIES \
    PAPERTOOLS_FILTER_EARLY_STOP_AFTER_CAP PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE \
    PAPERTOOLS_FILTER_MAX_OUTPUT_PAPERS PAPERTOOLS_FILTER_RULE_VERSION PAPERTOOLS_OPENAI_TIMEOUT \
    PAPERTOOLS_SUMMARY_OPENAI_TIMEOUT PAPERTOOLS_OPENAI_SDK_MAX_RETRIES PAPERTOOLS_RETRY_MAX_DELAY_SECONDS \
    PAPERTOOLS_OPENAI_TRUST_ENV DOCUMENT_EXTRACTOR_CHAIN DOCUMENT_EXTRACT_TIMEOUT \
    JINA_REQUEST_TIMEOUT JINA_MAX_RETRIES PAPERTOOLS_DAILY_WINDOW_DAYS \
    PAPERTOOLS_DAILY_MAX_CATCHUP_DAYS PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS \
    PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK; do
    printf '%s=%s\n' "$key" "${!key:-}"
  done
}

if [ "${PAPERTOOLS_DAILY_PRINT_RUNTIME_CONFIG:-0}" = "1" ]; then
  print_runtime_config
  exit 0
fi

resolve_publish_branch() {
  local branch="${PAPERTOOLS_GIT_BRANCH:-}"
  if [ -z "$branch" ]; then
    branch="$(git symbolic-ref --quiet --short HEAD)" || {
      log "Not on a git branch; scheduled publishing requires master or main."
      return 1
    }
  fi

  if [ "$branch" != "master" ] && [ "$branch" != "main" ]; then
    log "Scheduled publishing must use master or main, not $branch."
    return 1
  fi

  local current_branch
  current_branch="$(git symbolic-ref --quiet --short HEAD)" || {
    log "Not on a git branch; scheduled publishing requires master or main."
    return 1
  }
  if [ "$current_branch" != "$branch" ]; then
    log "Current branch $current_branch does not match publish branch $branch."
    return 1
  fi

  export PAPERTOOLS_GIT_BRANCH="$branch"
}

require_clean_worktree() {
  git update-index -q --refresh

  if ! git diff --quiet || ! git diff --cached --quiet; then
    git status --short
    log "Worktree has tracked changes; refusing scheduled publication."
    return 1
  fi

  if [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git status --short
    log "Worktree has untracked files; refusing scheduled publication."
    return 1
  fi
}

sync_publish_branch() {
  resolve_publish_branch
  require_clean_worktree

  log "Fetching latest origin/${PAPERTOOLS_GIT_BRANCH}"
  git fetch origin "$PAPERTOOLS_GIT_BRANCH" 2>&1 | tee -a "$LOG_FILE"
  git merge --ff-only "origin/${PAPERTOOLS_GIT_BRANCH}" 2>&1 | tee -a "$LOG_FILE"
  require_clean_worktree
}

sync_publish_branch

DATE_RANGE="$(
python - <<'PY_DAILY_DATE'
from datetime import datetime, timedelta
from pathlib import Path
import os
try:
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
except Exception:
    now = datetime.now()
window = int(os.getenv("PAPERTOOLS_DAILY_WINDOW_DAYS", "4") or "4")
max_catchup = int(os.getenv("PAPERTOOLS_DAILY_MAX_CATCHUP_DAYS", "7") or "7")
end_date = now.date()
default_start = end_date - timedelta(days=max(0, window - 1))
start_date = default_start

if not os.getenv("PAPERTOOLS_DAILY_START_DATE"):
    published_dates = []
    data_dir = Path("webpages/data")
    for path in data_dir.glob("????-??-??.json"):
        try:
            published_dates.append(datetime.strptime(path.stem, "%Y-%m-%d").date())
        except ValueError:
            pass
    if published_dates:
        gap_start = max(published_dates) + timedelta(days=1)
        if gap_start < start_date:
            catchup_floor = end_date - timedelta(days=max(0, max_catchup - 1))
            start_date = max(gap_start, catchup_floor)

start = os.getenv("PAPERTOOLS_DAILY_START_DATE") or start_date.isoformat()
end = os.getenv("PAPERTOOLS_DAILY_END_DATE") or end_date.isoformat()
print(start + " " + end)
PY_DAILY_DATE
)"
START_DATE="${DATE_RANGE% *}"
END_DATE="${DATE_RANGE#* }"

run_cmd=(timeout "$PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS" python papertools.py run --start-date "$START_DATE" --end-date "$END_DATE" --skip-serve --status-file "$STATUS_FILE")

log "PaperTools robust daily run: $START_DATE to $END_DATE"

# Disk space pre-check: fail fast if critically low
DISK_FREE_GB="$(df --output=avail -BG "$PROJECT_DIR" 2>/dev/null | tail -1 | tr -dc '0-9')"
if [ -n "$DISK_FREE_GB" ] && [ "$DISK_FREE_GB" -lt 5 ]; then
  log "❌ CRITICAL: only ${DISK_FREE_GB}GB disk free; refusing to run pipeline"
  exit 2
fi
if [ -n "$DISK_FREE_GB" ] && [ "$DISK_FREE_GB" -lt 10 ]; then
  log "⚠️ WARNING: only ${DISK_FREE_GB}GB disk free; pipeline may fail mid-run"
fi

preflight_cmd=(python scripts/preflight_check.py)
if [ "${PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK}" = "1" ]; then
  preflight_cmd+=(--offline-ok)
  log "Remote /models preflight disabled by PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK=1"
fi

"${preflight_cmd[@]}" 2>&1 | tee -a "$LOG_FILE" || {
  log "Preflight failed; refusing to run the expensive pipeline."
  exit 2
}

is_permanent_failure() {
  python scripts/classify_pipeline_failure.py \
    --status-file "$STATUS_FILE" \
    --log-file "$LOG_FILE" \
    --permanent >/dev/null 2>&1
}

read_pipeline_status() {
  python - "$STATUS_FILE" <<'PY_STATUS'
import json
import sys

try:
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        status = json.load(handle)
    print(status.get("status", "missing"))
except Exception:
    print("missing")
PY_STATUS
}

has_webpage_changes() {
  [ -n "$(git status --short -- webpages)" ]
}

handle_successful_pipeline_status() {
  local pipeline_status
  pipeline_status="$(read_pipeline_status)"
  case "$pipeline_status" in
    ok)
      return 0
      ;;
    skipped_no_source_papers|skipped_no_selected_papers)
      log "Pipeline skipped without publishable content: $pipeline_status"
      if ! python scripts/validate_published_payloads.py --webpages-dir webpages 2>&1 | tee -a "$LOG_FILE"; then
        log "Published payload validation failed after skipped pipeline status."
        exit 1
      fi
      if has_webpage_changes; then
        git status --short -- webpages 2>&1 | tee -a "$LOG_FILE"
        log "Pipeline reported $pipeline_status but changed published webpages; refusing to commit."
        exit 1
      fi
      log "No publishable webpage changes to commit."
      exit 0
      ;;
    *)
      log "Pipeline exited successfully but status file is not healthy: $pipeline_status"
      exit 1
      ;;
  esac
}

next_start_from() {
  python - "$STATUS_FILE" <<'PY_NEXT_STAGE'
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit
reason = str(data.get("failure_reason", ""))
if "爬取" in reason or "crawl" in reason.lower():
    print("crawl")
elif "筛选" in reason or "filter" in reason.lower():
    print("filter")
elif "聚类" in reason or "cluster" in reason.lower():
    print("cluster")
elif "总结" in reason or "summary" in reason.lower():
    print("summary")
elif "统一页面" in reason or "unified" in reason.lower():
    print("unified")
else:
    print("")
PY_NEXT_STAGE
}

max_attempts="${PAPERTOOLS_DAILY_MAX_ATTEMPTS:-3}"
attempt=1
while [ "$attempt" -le "$max_attempts" ]; do
  log "Pipeline attempt $attempt/$max_attempts"
  set +e
  "${run_cmd[@]}" 2>&1 | tee -a "$LOG_FILE"
  rc=${PIPESTATUS[0]}
  set -e

  if [ "$rc" -eq 0 ]; then
    log "Pipeline completed with exit code 0."
    handle_successful_pipeline_status
    if ! python scripts/validate_published_payloads.py --webpages-dir webpages 2>&1 | tee -a "$LOG_FILE"; then
      log "Published payload validation failed; refusing to commit generated output."
      exit 1
    fi
    if ! has_webpage_changes; then
      log "No publishable webpage changes to commit."
      exit 0
    fi
    if [ "${PAPERTOOLS_AUTO_COMMIT:-1}" = "1" ]; then
      # arxiv_paper/domain_paper/summary/logs are local state; only webpages is published.
      git add webpages/
      if git diff --cached --quiet; then
        log "No staged webpage changes after validation."
        exit 0
      fi
      git commit -m "Daily paper update: ${END_DATE}" 2>&1 | tee -a "$LOG_FILE"
      if [ "${PAPERTOOLS_AUTO_PUSH:-0}" = "1" ]; then
        git push origin "$PAPERTOOLS_GIT_BRANCH" 2>&1 | tee -a "$LOG_FILE"
      fi
    fi
    exit 0
  fi

  if is_permanent_failure; then
    log "Permanent configuration/API failure detected; not retrying."
    exit "$rc"
  fi

  start_from="$(next_start_from || true)"
  if [ -n "$start_from" ] && [[ " ${run_cmd[*]} " != *" --start-from "* ]]; then
    run_cmd+=(--start-from "$start_from")
    log "Next retry will resume from stage: $start_from"
  fi

  sleep_seconds=$(( attempt * attempt * 30 ))
  log "Transient failure; retrying after ${sleep_seconds}s."
  sleep "$sleep_seconds"
  attempt=$(( attempt + 1 ))
done

log "Pipeline failed after $max_attempts attempts. Status file: $STATUS_FILE"
exit 1
