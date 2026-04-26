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
RUN_TS="$(date '+%Y-%m-%d %H:%M:%S')"
RUN_ID="$(date '+%Y%m%d-%H%M%S')"
WORKTREE_DIR="${PAPERTOOLS_DAILY_WORKTREE:-/tmp/papertools-daily-${RUN_ID}}"
PROXY_HOST="${PAPERTOOLS_PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${PAPERTOOLS_PROXY_PORT:-7897}"
PROXY_URL="${PAPERTOOLS_PROXY_URL:-http://${PROXY_HOST}:${PROXY_PORT}}"

log() {
    echo "[$RUN_TS] $*" | tee -a "$LOG_FILE"
}

run_logged() {
    log "▶ $*"
    "$@" >>"$LOG_FILE" 2>&1
}

exec 9>"$LOCK_FILE"
if command -v flock >/dev/null 2>&1; then
    if ! flock -n 9; then
        log "⏭️ Previous daily run is still active; exiting"
        exit 0
    fi
fi

cleanup() {
    if git worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $WORKTREE_DIR"; then
        git worktree remove --force "$WORKTREE_DIR" >>"$LOG_FILE" 2>&1 || true
    fi
}
trap cleanup EXIT

if command -v nc >/dev/null 2>&1 && nc -z "$PROXY_HOST" "$PROXY_PORT" >/dev/null 2>&1; then
    export http_proxy="$PROXY_URL"
    export https_proxy="$PROXY_URL"
    export HTTP_PROXY="$PROXY_URL"
    export HTTPS_PROXY="$PROXY_URL"
    export NO_PROXY="localhost,127.0.0.1"
else
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
    export NO_PROXY="localhost,127.0.0.1"
fi

log "🚀 Starting daily full pipeline"
if [ -n "${http_proxy:-}" ]; then
    log "🌐 Proxy enabled: $http_proxy"
else
    log "🌐 Proxy unavailable; running without proxy"
fi

pkill -f "papertools.py run" 2>/dev/null || true
pkill -f "src/core/pipeline.py" 2>/dev/null || true
pkill -f "src/core/serve_webpages.py" 2>/dev/null || true
sleep 2

run_logged git fetch origin master
run_logged git worktree add --detach "$WORKTREE_DIR" origin/master

if [ -f "$ROOT_DIR/.env" ]; then
    cp "$ROOT_DIR/.env" "$WORKTREE_DIR/.env"
fi

cd "$WORKTREE_DIR"
BASE_SHA="$(git rev-parse --short HEAD)"
log "📌 Running from clean origin/master worktree at $BASE_SHA"

PIPELINE_EXIT=0
if "$PYTHON_BIN" papertools.py run --mode full --skip-serve >>"$LOG_FILE" 2>&1; then
    PIPELINE_EXIT=0
else
    PIPELINE_EXIT=$?
fi

if [ "$PIPELINE_EXIT" -ne 0 ]; then
    log "⚠️ Pipeline exited with code $PIPELINE_EXIT (committing generated partial output if present)"
else
    log "✅ Pipeline completed"
fi

# arxiv_paper/domain_paper/summary are local cache/state directories and are
# intentionally gitignored. The published artifact is webpages/.
git add webpages/
if git diff --cached --quiet; then
    log "ℹ️ No generated changes detected; nothing to commit"
    exit "$PIPELINE_EXIT"
fi

COMMIT_MSG="chore: arxiv daily update $(date '+%Y-%m-%d')"
git commit -m "$COMMIT_MSG" >>"$LOG_FILE" 2>&1
COMMIT_SHA="$(git rev-parse --short HEAD)"
log "📝 Created daily commit $COMMIT_SHA"

set +e
git push origin HEAD:master >>"$LOG_FILE" 2>&1
PUSH_EXIT=$?
set -e

if [ "$PUSH_EXIT" -ne 0 ]; then
    log "⚠️ Initial push failed; rebasing on latest origin/master and retrying"
    run_logged git fetch origin master
    if git rebase origin/master >>"$LOG_FILE" 2>&1; then
        set +e
        git push origin HEAD:master >>"$LOG_FILE" 2>&1
        PUSH_EXIT=$?
        set -e
    else
        log "❌ Rebase failed; daily changes remain in $WORKTREE_DIR for inspection"
        trap - EXIT
        exit 1
    fi
fi

if [ "$PUSH_EXIT" -ne 0 ]; then
    log "❌ Push failed after retry; daily changes remain in $WORKTREE_DIR for inspection"
    trap - EXIT
    exit 1
fi

log "📦 Changes committed and pushed"
exit "$PIPELINE_EXIT"
