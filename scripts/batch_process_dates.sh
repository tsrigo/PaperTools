#!/bin/bash
# 批量处理指定日期范围的论文
# 用法: bash scripts/batch_process_dates.sh 2026-03-01 2026-03-25
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

START_DATE="${1:?用法: $0 START_DATE END_DATE (格式: YYYY-MM-DD)}"
END_DATE="${2:?用法: $0 START_DATE END_DATE (格式: YYYY-MM-DD)}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
RUN_ID="$(date '+%Y%m%d_%H%M%S')_$$"
LOG_FILE="$LOG_DIR/batch_${RUN_ID}.log"
STATUS_DIR="$LOG_DIR/batch_status_${RUN_ID}"
mkdir -p "$STATUS_DIR"
LOCK_FILE="${PAPERTOOLS_PUBLISH_LOCK_FILE:-${PAPERTOOLS_DAILY_LOCK_FILE:-$LOG_DIR/papertools_publish.lock}}"

echo "🚀 批量处理论文: $START_DATE 到 $END_DATE" | tee "$LOG_FILE"
echo "日志文件: $LOG_FILE"
echo "状态文件目录: $STATUS_DIR" | tee -a "$LOG_FILE"

processed_dates=()
skipped_dates=()
failed_dates=()

canonical_date() {
    local value="$1"
    date -d "$value" +%Y-%m-%d 2>/dev/null || date -j -f "%Y-%m-%d" "$value" +%Y-%m-%d 2>/dev/null
}

validate_date_arg() {
    local label="$1"
    local value="$2"
    local canonical

    if [[ ! "$value" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        echo "❌ $label 必须使用 YYYY-MM-DD 格式: $value" | tee -a "$LOG_FILE"
        exit 2
    fi

    if ! canonical="$(canonical_date "$value")" || [[ "$canonical" != "$value" ]]; then
        echo "❌ $label 不是有效日历日期: $value" | tee -a "$LOG_FILE"
        exit 2
    fi
}

validate_date_arg "START_DATE" "$START_DATE"
validate_date_arg "END_DATE" "$END_DATE"
if [[ "$START_DATE" > "$END_DATE" ]]; then
    echo "❌ START_DATE 不能晚于 END_DATE: $START_DATE > $END_DATE" | tee -a "$LOG_FILE"
    exit 2
fi

mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
if command -v flock >/dev/null 2>&1; then
    if ! flock -n 9; then
        echo "⏭️ 已有 PaperTools 发布或回填任务在运行，跳过本次批处理: $LOCK_FILE" | tee -a "$LOG_FILE"
        exit 0
    fi
fi

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

# 生成日期列表（跳过周末 - arXiv 周末不更新）
current="$START_DATE"
while [[ "$current" < "$END_DATE" ]] || [[ "$current" == "$END_DATE" ]]; do
    dow=$(date -d "$current" +%u 2>/dev/null || date -j -f "%Y-%m-%d" "$current" +%u 2>/dev/null)
    # 周六=6 周日=7，跳过
    if [[ "$dow" -le 5 ]]; then
        echo "" | tee -a "$LOG_FILE"
        echo "========================================" | tee -a "$LOG_FILE"
        echo "📅 处理日期: $current" | tee -a "$LOG_FILE"
        echo "========================================" | tee -a "$LOG_FILE"

        status_file="$STATUS_DIR/pipeline_status_${current}.json"
        had_date_payload=0
        if [[ -f "webpages/data/${current}.json" ]]; then
            had_date_payload=1
        fi
        if "$PYTHON_BIN" papertools.py run --mode full --date "$current" --skip-serve --status-file "$status_file" 2>&1 | tee -a "$LOG_FILE"; then
            pipeline_status="$(read_pipeline_status "$status_file")"
            case "$pipeline_status" in
                ok)
                    echo "✅ $current 处理完成" | tee -a "$LOG_FILE"
                    processed_dates+=("$current")
                    ;;
                skipped_no_source_papers|skipped_no_selected_papers)
                    if [[ "$had_date_payload" -eq 0 && -f "webpages/data/${current}.json" ]]; then
                        echo "❌ $current 被标记为跳过但生成了发布 payload: webpages/data/${current}.json" | tee -a "$LOG_FILE"
                        failed_dates+=("$current")
                    else
                        echo "⏭️ $current 无可发布内容，已记录为跳过: $pipeline_status" | tee -a "$LOG_FILE"
                        skipped_dates+=("$current")
                    fi
                    ;;
                *)
                    echo "❌ $current 返回成功但状态文件不健康: $pipeline_status" | tee -a "$LOG_FILE"
                    failed_dates+=("$current")
                    ;;
            esac
        else
            echo "⚠️ $current 处理失败，继续下一天" | tee -a "$LOG_FILE"
            failed_dates+=("$current")
        fi
    else
        echo "⏭️ 跳过周末: $current" | tee -a "$LOG_FILE"
    fi

    # 日期加一天
    current=$(date -d "$current + 1 day" +%Y-%m-%d 2>/dev/null || date -j -v+1d -f "%Y-%m-%d" "$current" +%Y-%m-%d 2>/dev/null)
done

echo "" | tee -a "$LOG_FILE"
if [[ "${#processed_dates[@]}" -gt 0 || "${#skipped_dates[@]}" -gt 0 ]]; then
    echo "🔎 校验批量处理后的发布 payload..." | tee -a "$LOG_FILE"
    if ! "$PYTHON_BIN" scripts/validate_published_payloads.py --webpages-dir webpages 2>&1 | tee -a "$LOG_FILE"; then
        echo "❌ 发布 payload 校验失败" | tee -a "$LOG_FILE"
        exit 1
    fi
fi

if [[ "${#failed_dates[@]}" -gt 0 ]]; then
    printf '❌ 批量处理完成但存在失败日期: %s\n' "${failed_dates[*]}" | tee -a "$LOG_FILE"
    exit 1
fi

if [[ "${#processed_dates[@]}" -eq 0 ]]; then
    if [[ "${#skipped_dates[@]}" -eq 0 ]]; then
        echo "⏭️ 没有工作日需要处理" | tee -a "$LOG_FILE"
    else
        printf '⏭️ 没有发布新内容，跳过日期: %s\n' "${skipped_dates[*]}" | tee -a "$LOG_FILE"
    fi
else
    printf '🎉 批量处理完成: %s\n' "${processed_dates[*]}" | tee -a "$LOG_FILE"
    if [[ "${#skipped_dates[@]}" -gt 0 ]]; then
        printf '⏭️ 跳过日期: %s\n' "${skipped_dates[*]}" | tee -a "$LOG_FILE"
    fi
fi
