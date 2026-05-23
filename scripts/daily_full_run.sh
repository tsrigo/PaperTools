#!/usr/bin/env bash
# Daily full run + conditional commit/push.
#
# The cron entry lives in a development checkout that can be dirty or behind
# origin/master. Run the pipeline from a fresh temporary worktree instead, so
# publishing is not blocked by local commits or manual debugging edits.
set -euo pipefail

export HOME="${HOME:-/home/weikaihuang}"
export PATH="/opt/miniconda3/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="${PAPERTOOLS_DAILY_LOG_DIR:-$ROOT_DIR/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_pipeline.log"
LOCK_DIR="${PAPERTOOLS_DAILY_LOCK_DIR:-$LOG_DIR}"
mkdir -p "$LOCK_DIR"
LOCK_FILE="$LOCK_DIR/daily_full_run.lock"

PYTHON_BIN="${PYTHON_BIN:-/opt/miniconda3/bin/python3}"
RUN_ID="$(date '+%Y%m%d-%H%M%S')"
WORKTREE_DIR="${PAPERTOOLS_DAILY_WORKTREE:-/tmp/papertools-daily-${RUN_ID}}"
BOOTSTRAP_WORKTREE_DIR="${PAPERTOOLS_DAILY_BOOTSTRAP_WORKTREE:-/tmp/papertools-daily-bootstrap-${RUN_ID}}"
DAILY_WINDOW_DAYS="${PAPERTOOLS_DAILY_WINDOW_DAYS:-4}"
DAILY_MAX_CATCHUP_DAYS="${PAPERTOOLS_DAILY_MAX_CATCHUP_DAYS:-7}"
export PAPERTOOLS_DAILY_WINDOW_DAYS="$DAILY_WINDOW_DAYS"
export PAPERTOOLS_DAILY_MAX_CATCHUP_DAYS="$DAILY_MAX_CATCHUP_DAYS"
REPROCESS_EXISTING_DATES="${PAPERTOOLS_DAILY_REPROCESS_EXISTING:-0}"
SELF_REFRESH="${PAPERTOOLS_DAILY_SELF_REFRESH:-1}"
SELF_REFRESHED="${PAPERTOOLS_DAILY_SELF_REFRESHED:-0}"
PROXY_HOST="${PAPERTOOLS_PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${PAPERTOOLS_PROXY_PORT:-7897}"
PROXY_URL="${PAPERTOOLS_PROXY_URL:-http://${PROXY_HOST}:${PROXY_PORT}}"
NO_PROXY_VALUE="localhost,127.0.0.1,::1"
CURRENT_STAGE="initializing"
FAILURE_NOTIFIED=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

configure_daily_runtime_defaults() {
    # Daily automation owns operational safety defaults. The repository .env
    # still supplies secrets, but should not disable cron recovery behavior.
    export OPENAI_BASE_URL="${PAPERTOOLS_DAILY_OPENAI_BASE_URL:-https://models.sjtu.edu.cn/api/v1/}"
    export MODEL="${PAPERTOOLS_DAILY_MODEL:-deepseek-reasoner}"
    export FILTER_MODEL="${PAPERTOOLS_DAILY_FILTER_MODEL:-qwen}"
    export CLUSTER_MODEL="${PAPERTOOLS_DAILY_CLUSTER_MODEL:-glm}"
    export SUMMARY_MODEL="${PAPERTOOLS_DAILY_SUMMARY_MODEL:-minimax}"
    export SUMMARY_MODEL_CHAIN="${PAPERTOOLS_DAILY_SUMMARY_MODEL_CHAIN:-sjtu:minimax,sjtu:glm,sjtu:qwen,sjtu:deepseek-chat,sjtu:deepseek-reasoner}"
    export FILTER_MAX_WORKERS="${PAPERTOOLS_DAILY_FILTER_MAX_WORKERS:-1}"
    export SUMMARY_MAX_WORKERS="${PAPERTOOLS_DAILY_SUMMARY_MAX_WORKERS:-1}"
    export PAPERTOOLS_FILTER_RPM="${PAPERTOOLS_DAILY_FILTER_RPM:-8}"
    export PAPERTOOLS_FILTER_LLM_TIMEOUT="${PAPERTOOLS_DAILY_FILTER_LLM_TIMEOUT:-60}"
    export PAPERTOOLS_FILTER_LLM_MAX_RETRIES="${PAPERTOOLS_DAILY_FILTER_LLM_MAX_RETRIES:-1}"
    export PAPERTOOLS_FILTER_EARLY_STOP_AFTER_CAP="${PAPERTOOLS_DAILY_FILTER_EARLY_STOP_AFTER_CAP:-1}"
    export PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE="${PAPERTOOLS_DAILY_TOPIC_HEURISTIC_BYPASS_PRESTIGE:-1}"
    export PAPERTOOLS_FILTER_RULE_VERSION="${PAPERTOOLS_DAILY_FILTER_RULE_VERSION:-2026-05-24-daily}"
    export PAPERTOOLS_OPENAI_TIMEOUT="${PAPERTOOLS_DAILY_OPENAI_TIMEOUT:-120}"
    export PAPERTOOLS_OPENAI_SDK_MAX_RETRIES="${PAPERTOOLS_DAILY_OPENAI_SDK_MAX_RETRIES:-2}"
    export PAPERTOOLS_RETRY_MAX_DELAY_SECONDS="${PAPERTOOLS_DAILY_RETRY_MAX_DELAY_SECONDS:-60}"
    export PAPERTOOLS_OPENAI_TRUST_ENV="${PAPERTOOLS_DAILY_OPENAI_TRUST_ENV:-false}"
}

print_runtime_config() {
    for key in \
        OPENAI_BASE_URL MODEL FILTER_MODEL CLUSTER_MODEL SUMMARY_MODEL SUMMARY_MODEL_CHAIN \
        FILTER_MAX_WORKERS SUMMARY_MAX_WORKERS PAPERTOOLS_FILTER_RPM \
        PAPERTOOLS_FILTER_LLM_TIMEOUT PAPERTOOLS_FILTER_LLM_MAX_RETRIES \
        PAPERTOOLS_FILTER_EARLY_STOP_AFTER_CAP PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE \
        PAPERTOOLS_FILTER_RULE_VERSION PAPERTOOLS_OPENAI_TIMEOUT \
        PAPERTOOLS_OPENAI_SDK_MAX_RETRIES PAPERTOOLS_RETRY_MAX_DELAY_SECONDS \
        PAPERTOOLS_OPENAI_TRUST_ENV PAPERTOOLS_DAILY_WINDOW_DAYS \
        PAPERTOOLS_DAILY_MAX_CATCHUP_DAYS; do
        printf '%s=%s\n' "$key" "${!key:-}"
    done
}

configure_daily_runtime_defaults

if [ "${PAPERTOOLS_DAILY_PRINT_RUNTIME_CONFIG:-0}" = "1" ]; then
    print_runtime_config
    exit 0
fi

run_logged() {
    log "▶ $*"
    "$@" >>"$LOG_FILE" 2>&1
}

fetch_origin_master() {
    run_logged git fetch origin +refs/heads/master:refs/remotes/origin/master
}

set_proxy_env() {
    export http_proxy="$PROXY_URL"
    export https_proxy="$PROXY_URL"
    export HTTP_PROXY="$PROXY_URL"
    export HTTPS_PROXY="$PROXY_URL"
    export all_proxy="$PROXY_URL"
    export ALL_PROXY="$PROXY_URL"
    export no_proxy="$NO_PROXY_VALUE"
    export NO_PROXY="$NO_PROXY_VALUE"
}

clear_proxy_env() {
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
    export no_proxy="$NO_PROXY_VALUE"
    export NO_PROXY="$NO_PROXY_VALUE"
}

notify_wrapper() {
    local message="$1"
    "$PYTHON_BIN" - "$ROOT_DIR/.env" "$message" <<'PY' >>"$LOG_FILE" 2>&1 || true
import os
import sys

try:
    import warnings
    warnings.filterwarnings(
        "ignore",
        message=r"urllib3 .*doesn't match a supported version!",
        category=Warning,
    )
    import requests
except Exception as exc:
    print(f"Webhook notification skipped; requests unavailable: {exc}")
    sys.exit(0)

env_path = sys.argv[1]
message = sys.argv[2]


def clean_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


url = os.environ.get("WEBHOOK_URL", "").strip()
if not url and os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "WEBHOOK_URL":
                url = clean_env_value(value)
                break

if not url:
    sys.exit(0)

retry_exceptions = (
    requests.exceptions.ProxyError,
    requests.exceptions.ConnectionError,
    requests.exceptions.ConnectTimeout,
)

for trust_env in (True, False):
    session = requests.Session()
    session.trust_env = trust_env
    try:
        response = session.post(url, json={"text": message}, timeout=10)
        response.raise_for_status()
        suffix = "" if trust_env else " without proxy/env"
        print(f"Webhook notification sent successfully{suffix}")
        break
    except retry_exceptions as exc:
        route = "proxy/env" if trust_env else "direct"
        print(f"Webhook notification failed via {route}: {exc}")
        if trust_env:
            continue
        break
    except Exception as exc:
        print(f"Webhook notification failed: {exc}")
        break
    finally:
        session.close()
PY
}

notify_failure() {
    FAILURE_NOTIFIED=1
    notify_wrapper "$1"
}

cleanup_bootstrap_worktree() {
    if git worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $BOOTSTRAP_WORKTREE_DIR"; then
        git worktree remove --force "$BOOTSTRAP_WORKTREE_DIR" >>"$LOG_FILE" 2>&1 || true
    fi
}

run_latest_wrapper() {
    CURRENT_STAGE="self_refresh_fetch_origin_master"
    log "🔄 Refreshing daily wrapper from origin/master"
    if ! fetch_origin_master; then
        notify_failure "$(printf '❌ PaperTools daily wrapper failed\n  • stage: %s\n  • exit_code: %s\n  • run_id: %s' "$CURRENT_STAGE" "1" "$RUN_ID")"
        exit 1
    fi

    CURRENT_STAGE="self_refresh_create_worktree"
    cleanup_bootstrap_worktree
    if ! run_logged git worktree add --detach "$BOOTSTRAP_WORKTREE_DIR" origin/master; then
        notify_failure "$(printf '❌ PaperTools daily wrapper failed\n  • stage: %s\n  • exit_code: %s\n  • run_id: %s' "$CURRENT_STAGE" "1" "$RUN_ID")"
        exit 1
    fi

    if [ -f "$ROOT_DIR/.env" ]; then
        cp "$ROOT_DIR/.env" "$BOOTSTRAP_WORKTREE_DIR/.env"
    fi

    log "🔁 Delegating to latest origin/master daily wrapper"
    set +e
    PAPERTOOLS_DAILY_SELF_REFRESHED=1 \
        PAPERTOOLS_DAILY_LOG_DIR="$LOG_DIR" \
        PAPERTOOLS_DAILY_LOCK_DIR="$LOCK_DIR" \
        "$BOOTSTRAP_WORKTREE_DIR/scripts/daily_full_run.sh"
    local status=$?
    set -e
    cleanup_bootstrap_worktree
    exit "$status"
}

if [ "$SELF_REFRESH" = "1" ] && [ "$SELF_REFRESHED" != "1" ]; then
    run_latest_wrapper
fi

cleanup() {
    if git worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WORKTREE_DIR"; then
        git worktree remove --force "$WORKTREE_DIR" >>"$LOG_FILE" 2>&1 || true
    fi
}

finish() {
    local status="$1"
    cleanup
    if [ "$status" -ne 0 ] && [ "$FAILURE_NOTIFIED" -eq 0 ]; then
        notify_failure "$(printf '❌ PaperTools daily wrapper failed\n  • stage: %s\n  • exit_code: %s\n  • run_id: %s' "$CURRENT_STAGE" "$status" "$RUN_ID")"
    fi
}
trap 'finish $?' EXIT

exec 9>"$LOCK_FILE"
if command -v flock >/dev/null 2>&1; then
    if ! flock -n 9; then
        log "⏭️ Previous daily run is still active; exiting"
        notify_wrapper "$(printf '⏭️ PaperTools daily skipped\n  • reason: previous run still active\n  • run_id: %s' "$RUN_ID")"
        exit 0
    fi
fi

if command -v nc >/dev/null 2>&1 && nc -z "$PROXY_HOST" "$PROXY_PORT" >/dev/null 2>&1; then
    set_proxy_env
else
    clear_proxy_env
fi

log "🚀 Starting daily full pipeline"
if ! [[ "$DAILY_WINDOW_DAYS" =~ ^[0-9]+$ ]] || [ "$DAILY_WINDOW_DAYS" -lt 1 ]; then
    log "⚠️ Invalid PAPERTOOLS_DAILY_WINDOW_DAYS=$DAILY_WINDOW_DAYS; falling back to 4"
    DAILY_WINDOW_DAYS=4
fi
if ! [[ "$DAILY_MAX_CATCHUP_DAYS" =~ ^[0-9]+$ ]] || [ "$DAILY_MAX_CATCHUP_DAYS" -lt 1 ]; then
    log "⚠️ Invalid PAPERTOOLS_DAILY_MAX_CATCHUP_DAYS=$DAILY_MAX_CATCHUP_DAYS; falling back to 7"
    DAILY_MAX_CATCHUP_DAYS=7
fi
DATE_RANGE="$(
    "$PYTHON_BIN" - "$DAILY_WINDOW_DAYS" "$DAILY_MAX_CATCHUP_DAYS" <<'PY'
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

window = int(sys.argv[1])
max_catchup = int(sys.argv[2])
end_date = datetime.strptime(
    os.getenv("PAPERTOOLS_DAILY_END_DATE") or date.today().isoformat(),
    "%Y-%m-%d",
).date()

default_start = end_date - timedelta(days=max(0, window - 1))
start_date = default_start

if not os.getenv("PAPERTOOLS_DAILY_START_DATE"):
    published_dates = []
    for path in (Path.cwd() / "webpages" / "data").glob("????-??-??.json"):
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
print(start + " " + end_date.isoformat())
PY
)"
DAILY_START_DATE="${DATE_RANGE% *}"
DAILY_END_DATE="${DATE_RANGE#* }"
log "📅 Daily crawl window: $DAILY_START_DATE to $DAILY_END_DATE"
log "⚙️ Runtime defaults: FILTER_MODEL=$FILTER_MODEL CLUSTER_MODEL=$CLUSTER_MODEL SUMMARY_MODEL=$SUMMARY_MODEL FILTER_RPM=$PAPERTOOLS_FILTER_RPM HEURISTIC_BYPASS_PRESTIGE=$PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE"
if [ "$REPROCESS_EXISTING_DATES" = "1" ]; then
    log "♻️ Existing published dates will be reprocessed"
else
    log "⏭️ Existing published dates will be skipped by default"
fi
if [ -n "${http_proxy:-}" ]; then
    log "🌐 Proxy enabled: $http_proxy"
else
    log "🌐 Proxy unavailable; running without proxy"
fi

if [ "${PAPERTOOLS_KILL_STALE:-0}" = "1" ]; then
    log "🧹 Killing stale PaperTools processes because PAPERTOOLS_KILL_STALE=1"
    pkill -f "papertools.py run" 2>/dev/null || true
    pkill -f "src/core/pipeline.py" 2>/dev/null || true
    pkill -f "src/core/serve_webpages.py" 2>/dev/null || true
    sleep 2
else
    log "ℹ️ Skipping global process cleanup; lock file protects scheduled runs"
fi

CURRENT_STAGE="fetch_origin_master"
fetch_origin_master
CURRENT_STAGE="create_worktree"
run_logged git worktree add --detach "$WORKTREE_DIR" origin/master

if [ -f "$ROOT_DIR/.env" ]; then
    cp "$ROOT_DIR/.env" "$WORKTREE_DIR/.env"
fi

cd "$WORKTREE_DIR"
BASE_SHA="$(git rev-parse --short HEAD)"
log "📌 Running from clean origin/master worktree at $BASE_SHA"
CURRENT_STAGE="init_submodules"
if ! run_logged git submodule update --init --recursive; then
    log "⚠️ Submodule init failed; continuing because summary generation has a non-ReviewGrounder fallback"
fi

build_date_list() {
    local current="$DAILY_START_DATE"
    while [ "$(date -d "$current" '+%Y%m%d')" -le "$(date -d "$DAILY_END_DATE" '+%Y%m%d')" ]; do
        printf '%s\n' "$current"
        current="$(date -d "$current + 1 day" '+%Y-%m-%d')"
    done
}

validate_date_output() {
    local run_date="$1"
    local status_file="$2"
    "$PYTHON_BIN" - "$run_date" "$status_file" <<'PY' >>"$LOG_FILE" 2>&1
import json
import os
import sys

run_date = sys.argv[1]
status_file = sys.argv[2]

with open(status_file, "r", encoding="utf-8") as handle:
    status = json.load(handle)

if status.get("status") != "ok" or status.get("exit_code") != 0:
    raise SystemExit(f"pipeline status is not healthy for {run_date}: {status}")

date_file = os.path.join("webpages", "data", f"{run_date}.json")
if not os.path.exists(date_file):
    raise SystemExit(f"missing generated date file: {date_file}")

with open(date_file, "r", encoding="utf-8") as handle:
    date_data = json.load(handle)

if date_data.get("date") != run_date:
    raise SystemExit(f"date mismatch in {date_file}: {date_data.get('date')!r}")

from src.utils.publish_quality import validate_date_data_payload

ok, errors = validate_date_data_payload(date_data, expected_date=run_date)
if not ok:
    raise SystemExit(f"date payload is not publishable for {run_date}: {'; '.join(errors[:5])}")

index_file = os.path.join("webpages", "data", "index.json")
with open(index_file, "r", encoding="utf-8") as handle:
    index_data = json.load(handle)

if run_date not in index_data.get("dates", []):
    raise SystemExit(f"{run_date} missing from webpages/data/index.json")

print(f"validated generated output for {run_date}")
PY
}

read_pipeline_status() {
    local status_file="$1"
    "$PYTHON_BIN" - "$status_file" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        status = json.load(handle)
    print(status.get("status", "missing"))
except Exception:
    print("missing")
PY
}

PIPELINE_EXIT=0
PUBLISHED_DATE_LIST=""
SKIPPED_DATE_LIST=""

append_date() {
    local current_list="$1"
    local run_date="$2"
    if [ -z "$current_list" ]; then
        printf '%s' "$run_date"
    else
        printf '%s, %s' "$current_list" "$run_date"
    fi
}

while IFS= read -r RUN_DATE; do
    [ -n "$RUN_DATE" ] || continue
    if [ "$REPROCESS_EXISTING_DATES" != "1" ] && [ -f "webpages/data/${RUN_DATE}.json" ]; then
        log "⏭️ Skipping $RUN_DATE; webpages/data/${RUN_DATE}.json already exists"
        SKIPPED_DATE_LIST="$(append_date "$SKIPPED_DATE_LIST" "$RUN_DATE")"
        continue
    fi

    CURRENT_STAGE="pipeline_${RUN_DATE}"
    STATUS_FILE="logs/pipeline_status_${RUN_DATE}.json"
    log "📅 Running daily pipeline for $RUN_DATE"

    set +e
    "$PYTHON_BIN" papertools.py run --mode full --skip-serve --date "$RUN_DATE" --status-file "$STATUS_FILE" >>"$LOG_FILE" 2>&1
    PIPELINE_EXIT=$?
    set -e

    if [ "$PIPELINE_EXIT" -ne 0 ]; then
        log "⚠️ Pipeline for $RUN_DATE exited with code $PIPELINE_EXIT"
        notify_failure "$(printf '❌ PaperTools pipeline failed\n  • date: %s\n  • exit_code: %s\n  • base: %s\n  • run_id: %s' "$RUN_DATE" "$PIPELINE_EXIT" "$BASE_SHA" "$RUN_ID")"
        if [ "${PAPERTOOLS_COMMIT_ON_PIPELINE_FAILURE:-0}" != "1" ]; then
            log "⏭️ Not committing generated output after pipeline failure"
            exit "$PIPELINE_EXIT"
        fi
        log "⚠️ PAPERTOOLS_COMMIT_ON_PIPELINE_FAILURE=1; continuing with generated partial output"
    else
        PIPELINE_STATUS_VALUE="$(read_pipeline_status "$STATUS_FILE")"
        case "$PIPELINE_STATUS_VALUE" in
            skipped_no_source_papers|skipped_no_selected_papers)
                log "⏭️ Pipeline skipped $RUN_DATE without publishing empty content: $PIPELINE_STATUS_VALUE"
                CURRENT_STAGE="prune_unpublishable_dates_${RUN_DATE}"
                run_logged "$PYTHON_BIN" src/core/generate_unified_index.py
                if [ -f "webpages/data/${RUN_DATE}.json" ]; then
                    log "❌ Skipped date still has generated output: webpages/data/${RUN_DATE}.json"
                    notify_failure "$(printf '❌ PaperTools publish gate failed\n  • date: %s\n  • reason: skipped date still generated a data file\n  • base: %s\n  • run_id: %s' "$RUN_DATE" "$BASE_SHA" "$RUN_ID")"
                    exit 1
                fi
                SKIPPED_DATE_LIST="$(append_date "$SKIPPED_DATE_LIST" "$RUN_DATE")"
                continue
                ;;
        esac
        validate_date_output "$RUN_DATE" "$STATUS_FILE"
        log "✅ Pipeline completed for $RUN_DATE"
    fi

    PUBLISHED_DATE_LIST="$(append_date "$PUBLISHED_DATE_LIST" "$RUN_DATE")"
done < <(build_date_list)

# arxiv_paper/domain_paper/summary are local cache/state directories and are
# intentionally gitignored. The published artifact is webpages/.
CURRENT_STAGE="stage_generated_webpages"
git add webpages/
if git diff --cached --quiet; then
    log "ℹ️ No generated changes detected; nothing to commit"
    notify_wrapper "$(printf 'ℹ️ PaperTools daily complete; no generated changes\n  • processed_dates: %s\n  • skipped_dates: %s\n  • pipeline_exit: %s\n  • base: %s\n  • run_id: %s' "${PUBLISHED_DATE_LIST:-none}" "${SKIPPED_DATE_LIST:-none}" "$PIPELINE_EXIT" "$BASE_SHA" "$RUN_ID")"
    exit 0
fi

COMMIT_MSG="chore: arxiv daily update $(date '+%Y-%m-%d')"
CURRENT_STAGE="commit_generated_webpages"
git commit -m "$COMMIT_MSG" >>"$LOG_FILE" 2>&1
COMMIT_SHA="$(git rev-parse --short HEAD)"
log "📝 Created daily commit $COMMIT_SHA"

set +e
CURRENT_STAGE="push_generated_webpages"
git push origin HEAD:master >>"$LOG_FILE" 2>&1
PUSH_EXIT=$?
set -e

if [ "$PUSH_EXIT" -ne 0 ]; then
    log "⚠️ Initial push failed; rebasing on latest origin/master and retrying"
    CURRENT_STAGE="rebase_generated_webpages"
    fetch_origin_master
    if git rebase origin/master >>"$LOG_FILE" 2>&1; then
        set +e
        CURRENT_STAGE="push_generated_webpages_after_rebase"
        git push origin HEAD:master >>"$LOG_FILE" 2>&1
        PUSH_EXIT=$?
        set -e
    else
        log "❌ Rebase failed; daily changes remain in $WORKTREE_DIR for inspection"
        notify_failure "$(printf '❌ PaperTools publish failed during rebase\n  • worktree: %s\n  • commit: %s\n  • run_id: %s' "$WORKTREE_DIR" "$COMMIT_SHA" "$RUN_ID")"
        trap - EXIT
        exit 1
    fi
fi

if [ "$PUSH_EXIT" -ne 0 ]; then
    log "❌ Push failed after retry; daily changes remain in $WORKTREE_DIR for inspection"
    notify_failure "$(printf '❌ PaperTools publish failed after retry\n  • worktree: %s\n  • commit: %s\n  • run_id: %s' "$WORKTREE_DIR" "$COMMIT_SHA" "$RUN_ID")"
    trap - EXIT
    exit 1
fi

log "📦 Changes committed and pushed"
PUBLISHED_DATES="$(
    git diff-tree --no-commit-id --name-only -r HEAD \
        | sed -n 's#^webpages/data/\([0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]\)\.json$#\1#p' \
        | sort -r \
        | tr '\n' ',' \
        | sed 's/,$//;s/,/, /g'
)"
notify_wrapper "$(printf '✅ PaperTools publish complete\n  • commit: %s\n  • published_dates: %s\n  • skipped_dates: %s\n  • pipeline_exit: %s\n  • run_id: %s' "$COMMIT_SHA" "${PUBLISHED_DATES:-none}" "${SKIPPED_DATE_LIST:-none}" "$PIPELINE_EXIT" "$RUN_ID")"
exit "$PIPELINE_EXIT"
