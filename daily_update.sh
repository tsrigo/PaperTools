#!/bin/bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATUS_DIR="${PAPERTOOLS_DAILY_STATUS_DIR:-$PROJECT_DIR/logs}"
RUN_ID="$(date +'%Y%m%d-%H%M%S')"
STATUS_FILE="${PAPERTOOLS_DAILY_STATUS_FILE:-$STATUS_DIR/daily_update_status_${RUN_ID}.json}"
PIPELINE_TIMEOUT_SECONDS="${PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS:-21600}"
PREFLIGHT_OFFLINE_OK="${PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK:-0}"
LOCK_FILE="${PAPERTOOLS_PUBLISH_LOCK_FILE:-${PAPERTOOLS_DAILY_LOCK_FILE:-$PROJECT_DIR/logs/papertools_publish.lock}}"
LEGACY_LOCK_DIR="${PAPERTOOLS_DAILY_LOCK_DIR:-$PROJECT_DIR/.papertools_daily.lock}"

log() {
    printf '[%s] %s\n' "$(date +'%Y-%m-%d %H:%M:%S')" "$*"
}

fail() {
    log "ERROR: $*" >&2
    exit 1
}

cleanup_lock() {
    rm -rf "$LEGACY_LOCK_DIR"
}

acquire_lock() {
    if command -v flock >/dev/null 2>&1; then
        mkdir -p "$(dirname "$LOCK_FILE")"
        exec 9>"$LOCK_FILE"
        if flock -n 9; then
            return
        fi
        fail "another PaperTools publish is already running: $LOCK_FILE"
    fi

    if mkdir "$LEGACY_LOCK_DIR" 2>/dev/null; then
        printf '%s\n' "$$" > "$LEGACY_LOCK_DIR/pid"
        trap cleanup_lock EXIT
        return
    fi

    if [ -f "$LEGACY_LOCK_DIR/pid" ]; then
        local existing_pid
        existing_pid="$(cat "$LEGACY_LOCK_DIR/pid" 2>/dev/null || true)"
        if [ -n "$existing_pid" ] && ! kill -0 "$existing_pid" 2>/dev/null; then
            log "Removing stale daily update lock for pid $existing_pid"
            rm -rf "$LEGACY_LOCK_DIR"
            mkdir "$LEGACY_LOCK_DIR"
            printf '%s\n' "$$" > "$LEGACY_LOCK_DIR/pid"
            trap cleanup_lock EXIT
            return
        fi
    fi

    fail "another daily update is already running: $LEGACY_LOCK_DIR"
}

require_clean_worktree() {
    git update-index -q --refresh

    if ! git diff --quiet || ! git diff --cached --quiet; then
        git status --short
        fail "worktree has tracked changes; scheduled runs must start clean"
    fi

    if [ -n "$(git ls-files --others --exclude-standard)" ]; then
        git status --short
        fail "worktree has untracked files; scheduled runs must start clean"
    fi
}

current_branch() {
    git symbolic-ref --quiet --short HEAD
}

run_preflight_check() {
    local preflight_cmd=(python scripts/preflight_check.py)
    if [ "$PREFLIGHT_OFFLINE_OK" = "1" ]; then
        preflight_cmd+=(--offline-ok)
        log "Remote /models preflight disabled by PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK=1"
    fi

    log "Running PaperTools preflight checks"
    "${preflight_cmd[@]}"
}

read_pipeline_status() {
    python - "$STATUS_FILE" <<'PY'
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

cd "$PROJECT_DIR"
acquire_lock

BRANCH="$(current_branch)" || fail "not on a branch"
if [ "$BRANCH" != "master" ] && [ "$BRANCH" != "main" ]; then
    fail "scheduled publishing must run from master or main, not $BRANCH"
fi

require_clean_worktree
log "Fetching latest origin/$BRANCH"
git fetch origin "$BRANCH"
git merge --ff-only "origin/$BRANCH"
require_clean_worktree

if [ -f venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

mkdir -p "$STATUS_DIR"
log "Structured pipeline status will be written to $STATUS_FILE"

run_preflight_check

log "Running PaperTools daily pipeline"
timeout "$PIPELINE_TIMEOUT_SECONDS" python papertools.py run --mode full --skip-serve --status-file "$STATUS_FILE"

PIPELINE_STATUS="$(read_pipeline_status)"
case "$PIPELINE_STATUS" in
    ok)
        ;;
    skipped_no_source_papers|skipped_no_selected_papers)
        log "Pipeline skipped without publishable content: $PIPELINE_STATUS"
        log "Validating existing published payloads before exiting"
        python scripts/validate_published_payloads.py --webpages-dir webpages
        if [ -n "$(git status --short -- webpages)" ]; then
            git status --short -- webpages
            fail "pipeline reported $PIPELINE_STATUS but changed published webpages"
        fi
        log "No publishable changes to commit"
        exit 0
        ;;
    *)
        fail "pipeline exited successfully but status file is not healthy: $PIPELINE_STATUS"
        ;;
esac

log "Validating published payloads before staging"
python scripts/validate_published_payloads.py --webpages-dir webpages

log "Staging generated publication artifacts"
git add webpages/

if git diff --cached --quiet; then
    log "No publishable changes to commit"
    exit 0
fi

COMMIT_MSG="Daily paper update: $(date +'%Y-%m-%d')"
git commit -m "$COMMIT_MSG"
git push origin "$BRANCH"

log "Daily update pushed to origin/$BRANCH"
