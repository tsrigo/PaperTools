#!/bin/bash
# 批量修复所有缺失日期的数据

# 激活环境
source /home/xuanli/miniconda3/etc/profile.d/conda.sh
conda activate alphaapollo
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087

# 需要处理的日期
DATES=(
    "2025-12-19"
    "2025-12-22"
    "2025-12-23"
    "2025-12-24"
    "2025-12-26"
    "2025-12-29"
    "2025-12-31"
    "2026-01-02"
    "2026-01-05"
    "2026-01-06"
    "2026-01-07"
)

echo "=========================================="
echo "开始批量修复缺失数据"
echo "总共需要处理 ${#DATES[@]} 个日期"
echo "=========================================="
echo ""

for date in "${DATES[@]}"; do
    echo "----------------------------------------"
    echo "[$date] 开始处理..."
    echo "----------------------------------------"

    # 删除旧缓存
    rm -f domain_paper/filtered_papers_${date}.json
    rm -f domain_paper/excluded_papers_${date}.json
    echo "✓ 已删除旧缓存"

    # 重新筛选
    echo "正在筛选论文..."
    python3 src/core/select_.py \
        --input-file arxiv_paper/cs.AI_cs.CL_cs.LG_cs.MA_paper_${date}.json \
        --output-dir domain_paper \
        --max-workers 10

    if [ $? -eq 0 ]; then
        # 检查筛选结果
        if [ -f "domain_paper/filtered_papers_${date}.json" ]; then
            count=$(grep -o '"arxiv_id"' domain_paper/filtered_papers_${date}.json 2>/dev/null | wc -l)
            if [ "$count" -gt 0 ]; then
                echo "✓ 筛选完成，发现 $count 篇论文"

                # 生成总结
                echo "正在生成总结..."
                python3 src/core/generate_summary.py \
                    --input-file domain_paper/filtered_papers_${date}.json \
                    --output-dir summary

                if [ $? -eq 0 ]; then
                    echo "✓ 总结生成完成"
                else
                    echo "✗ 总结生成失败"
                fi
            else
                echo "✓ 筛选完成，但没有论文通过筛选"
            fi
        fi
    else
        echo "✗ 筛选失败"
    fi

    echo ""
    sleep 2
done

echo "=========================================="
echo "所有日期处理完成！"
echo "=========================================="
echo ""
echo "下一步操作："
echo "1. 运行: python3 src/core/generate_unified_index.py"
echo "2. 检查生成的网页"
echo "3. 提交更新到 git"
