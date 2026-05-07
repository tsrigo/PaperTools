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

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_pipeline.log"
LOCK_FILE="$LOG_DIR/daily_full_run.lock"

PYTHON_BIN="${PYTHON_BIN:-/opt/miniconda3/bin/python3}"
RUN_ID="$(date '+%Y%m%d-%H%M%S')"
WORKTREE_DIR="${PAPERTOOLS_DAILY_WORKTREE:-/tmp/papertools-daily-${RUN_ID}}"
DAILY_WINDOW_DAYS="${PAPERTOOLS_DAILY_WINDOW_DAYS:-4}"
PROXY_HOST="${PAPERTOOLS_PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${PAPERTOOLS_PROXY_PORT:-7897}"
PROXY_URL="${PAPERTOOLS_PROXY_URL:-http://${PROXY_HOST}:${PROXY_PORT}}"
NO_PROXY_VALUE="localhost,127.0.0.1,::1"
CURRENT_STAGE="initializing"
FAILURE_NOTIFIED=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

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
DAILY_END_DATE="${PAPERTOOLS_DAILY_END_DATE:-$(date '+%Y-%m-%d')}"
DAILY_START_DATE="${PAPERTOOLS_DAILY_START_DATE:-$(date -d "$((DAILY_WINDOW_DAYS - 1)) days ago" '+%Y-%m-%d')}"
log "📅 Daily crawl window: $DAILY_START_DATE to $DAILY_END_DATE"
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

if not isinstance(date_data.get("clusters", []), list):
    raise SystemExit(f"invalid clusters payload in {date_file}")

index_file = os.path.join("webpages", "data", "index.json")
with open(index_file, "r", encoding="utf-8") as handle:
    index_data = json.load(handle)

if run_date not in index_data.get("dates", []):
    raise SystemExit(f"{run_date} missing from webpages/data/index.json")

print(f"validated generated output for {run_date}")
PY
}

PIPELINE_EXIT=0
PUBLISHED_DATE_LIST=""
while IFS= read -r RUN_DATE; do
    [ -n "$RUN_DATE" ] || continue
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
        validate_date_output "$RUN_DATE" "$STATUS_FILE"
        log "✅ Pipeline completed for $RUN_DATE"
    fi

    if [ -z "$PUBLISHED_DATE_LIST" ]; then
        PUBLISHED_DATE_LIST="$RUN_DATE"
    else
        PUBLISHED_DATE_LIST="$PUBLISHED_DATE_LIST, $RUN_DATE"
    fi
done < <(build_date_list)

# arxiv_paper/domain_paper/summary are local cache/state directories and are
# intentionally gitignored. The published artifact is webpages/.
CURRENT_STAGE="stage_generated_webpages"
git add webpages/
if git diff --cached --quiet; then
    log "ℹ️ No generated changes detected; nothing to commit"
    notify_wrapper "$(printf 'ℹ️ PaperTools daily complete; no generated changes\n  • dates: %s\n  • pipeline_exit: %s\n  • base: %s\n  • run_id: %s' "$PUBLISHED_DATE_LIST" "$PIPELINE_EXIT" "$BASE_SHA" "$RUN_ID")"
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
notify_wrapper "$(printf '✅ PaperTools publish complete\n  • commit: %s\n  • dates: %s\n  • pipeline_exit: %s\n  • run_id: %s' "$COMMIT_SHA" "${PUBLISHED_DATES:-none}" "$PIPELINE_EXIT" "$RUN_ID")"
exit "$PIPELINE_EXIT"
