#!/usr/bin/env bash
# Daily full run + conditional commit/push
set -euo pipefail

# Ensure cron has a sane environment
export HOME="${HOME:-/home/weikaihuang}"
export PATH="/opt/miniconda3/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Proxy required for external API access (jina.ai, etc.)
export http_proxy="http://127.0.0.1:7897"
export https_proxy="http://127.0.0.1:7897"
export HTTP_PROXY="http://127.0.0.1:7897"
export HTTPS_PROXY="http://127.0.0.1:7897"
export NO_PROXY="localhost,127.0.0.1"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_pipeline.log"

PYTHON_BIN="${PYTHON_BIN:-/opt/miniconda3/bin/python3}"
RUN_TS="$(date '+%Y-%m-%d %H:%M:%S')"

echo "[$RUN_TS] 🚀 Starting daily full pipeline" | tee -a "$LOG_FILE"

if ! "$PYTHON_BIN" papertools.py run --mode full >>"$LOG_FILE" 2>&1; then
    echo "[$RUN_TS] ❌ Pipeline run failed, aborting commit" | tee -a "$LOG_FILE"
    exit 1
fi

echo "[$RUN_TS] ✅ Pipeline completed" | tee -a "$LOG_FILE"

if ! git status --porcelain webpages | grep -q .; then
    echo "[$RUN_TS] ℹ️ No new arXiv updates detected; nothing to commit" | tee -a "$LOG_FILE"
    exit 0
fi

git add webpages/
COMMIT_MSG="chore: arxiv daily update $(date '+%Y-%m-%d')"

git commit -m "$COMMIT_MSG" | tee -a "$LOG_FILE"
git push | tee -a "$LOG_FILE"

echo "[$RUN_TS] 📦 Changes committed and pushed" | tee -a "$LOG_FILE"
