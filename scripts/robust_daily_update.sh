#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/miniconda3/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

mkdir -p logs
RUN_ID="$(TZ=Asia/Tokyo date +'%Y%m%d-%H%M%S')"
LOG_FILE="logs/robust_daily_${RUN_ID}.log"
STATUS_FILE="logs/robust_daily_status_${RUN_ID}.json"
LOCK_FILE="logs/robust_daily.lock"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another PaperTools daily run is already active; exiting." | tee -a "$LOG_FILE"
  exit 0
fi

log() {
  printf '[%s] %s\n' "$(TZ=Asia/Tokyo date +'%Y-%m-%d %H:%M:%S %Z')" "$*" | tee -a "$LOG_FILE"
}

# Load .env without printing secrets. PaperTools itself also loads .env.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# SJTU-safe defaults. Keep the actual API key only in .env / secret manager.
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://models.sjtu.edu.cn/api/v1/}"
export MODEL="${MODEL:-minimax}"
export FILTER_MODEL="${FILTER_MODEL:-qwen}"
export CLUSTER_MODEL="${CLUSTER_MODEL:-glm}"
export SUMMARY_MODEL_CHAIN="${SUMMARY_MODEL_CHAIN:-sjtu:minimax,sjtu:glm,sjtu:qwen,sjtu:deepseek-chat,sjtu:deepseek-reasoner}"
export SUMMARY_SJTU_OPENAI_API_KEY="${SUMMARY_SJTU_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
export SUMMARY_SJTU_OPENAI_BASE_URL="${SUMMARY_SJTU_OPENAI_BASE_URL:-$OPENAI_BASE_URL}"
export SUMMARY_OPENAI_API_KEY="${SUMMARY_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
export SUMMARY_OPENAI_BASE_URL="${SUMMARY_OPENAI_BASE_URL:-$OPENAI_BASE_URL}"
export SUMMARY_MODEL="${SUMMARY_MODEL:-minimax}"

# Conservative concurrency is usually more stable on shared OpenAI-compatible gateways.
export FILTER_MAX_WORKERS="${FILTER_MAX_WORKERS:-1}"
export SUMMARY_MAX_WORKERS="${SUMMARY_MAX_WORKERS:-1}"
export PAPERTOOLS_FILTER_RPM="${PAPERTOOLS_FILTER_RPM:-3}"
export PAPERTOOLS_FILTER_LLM_TIMEOUT="${PAPERTOOLS_FILTER_LLM_TIMEOUT:-120}"
export PAPERTOOLS_FILTER_LLM_MAX_RETRIES="${PAPERTOOLS_FILTER_LLM_MAX_RETRIES:-3}"
export PAPERTOOLS_FILTER_EARLY_STOP_AFTER_CAP="${PAPERTOOLS_FILTER_EARLY_STOP_AFTER_CAP:-1}"
export PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE="${PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE:-1}"
export PAPERTOOLS_OPENAI_TIMEOUT="${PAPERTOOLS_OPENAI_TIMEOUT:-120}"
export PAPERTOOLS_OPENAI_SDK_MAX_RETRIES="${PAPERTOOLS_OPENAI_SDK_MAX_RETRIES:-2}"
export PAPERTOOLS_RETRY_MAX_DELAY_SECONDS="${PAPERTOOLS_RETRY_MAX_DELAY_SECONDS:-60}"
export PAPERTOOLS_OPENAI_TRUST_ENV="${PAPERTOOLS_OPENAI_TRUST_ENV:-false}"
export PAPERTOOLS_DAILY_WINDOW_DAYS="${PAPERTOOLS_DAILY_WINDOW_DAYS:-4}"
export PAPERTOOLS_DAILY_MAX_CATCHUP_DAYS="${PAPERTOOLS_DAILY_MAX_CATCHUP_DAYS:-7}"

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

run_cmd=(python papertools.py run --start-date "$START_DATE" --end-date "$END_DATE" --skip-serve --status-file "$STATUS_FILE")

log "PaperTools robust daily run: $START_DATE to $END_DATE"
python scripts/preflight_check.py --offline-ok 2>&1 | tee -a "$LOG_FILE" || {
  log "Preflight failed; refusing to run the expensive pipeline."
  exit 2
}

is_permanent_failure() {
  python scripts/classify_pipeline_failure.py \
    --status-file "$STATUS_FILE" \
    --log-file "$LOG_FILE" \
    --permanent >/dev/null 2>&1
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
    if git diff --quiet -- arxiv_paper domain_paper summary webpages 2>/dev/null; then
      log "No generated data changes to commit."
      exit 0
    fi
    if [ "${PAPERTOOLS_AUTO_COMMIT:-1}" = "1" ]; then
      git add arxiv_paper/ domain_paper/ summary/ webpages/ logs/ 2>/dev/null || true
      git commit -m "Daily paper update: ${END_DATE}" 2>&1 | tee -a "$LOG_FILE" || true
      if [ "${PAPERTOOLS_AUTO_PUSH:-0}" = "1" ]; then
        git push origin "${PAPERTOOLS_GIT_BRANCH:-master}" 2>&1 | tee -a "$LOG_FILE" || true
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
