#!/bin/bash
# 修复缺失数据的脚本
# 用于重新处理 API 失效期间的论文数据

# 激活 conda 环境
source /home/xuanli/miniconda3/etc/profile.d/conda.sh
conda activate alphaapollo

# 设置代理
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087

# 需要重新处理的日期列表（API 失效期间）
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
echo "开始修复缺失的论文数据"
echo "=========================================="
echo ""

for date in "${DATES[@]}"; do
    echo "----------------------------------------"
    echo "处理日期: $date"
    echo "----------------------------------------"

    # 检查 arxiv_paper 文件是否存在
    arxiv_file="arxiv_paper/cs.AI_cs.CL_cs.LG_cs.MA_paper_${date}.json"

    if [ ! -f "$arxiv_file" ]; then
        echo "⚠️  警告: $arxiv_file 不存在，跳过"
        continue
    fi

    # 检查文件大小
    file_size=$(stat -f%z "$arxiv_file" 2>/dev/null || stat -c%s "$arxiv_file" 2>/dev/null)
    if [ "$file_size" -lt 100 ]; then
        echo "⚠️  警告: $arxiv_file 文件太小，可能无效，跳过"
        continue
    fi

    echo "📄 找到论文文件: $arxiv_file (大小: $file_size 字节)"
    echo "🔄 开始重新筛选..."

    # 重新运行筛选步骤
    /home/xuanli/miniconda3/bin/python3 src/core/select_.py \
        --input-file "$arxiv_file" \
        --output-dir domain_paper \
        --max-workers 10

    if [ $? -eq 0 ]; then
        echo "✅ 筛选完成"

        # 检查筛选结果
        filtered_file="domain_paper/filtered_papers_${date}.json"
        if [ -f "$filtered_file" ]; then
            filtered_size=$(stat -f%z "$filtered_file" 2>/dev/null || stat -c%s "$filtered_file" 2>/dev/null)
            echo "📊 筛选结果文件大小: $filtered_size 字节"

            # 如果筛选出了论文，继续生成总结
            if [ "$filtered_size" -gt 10 ]; then
                echo "🔄 开始生成总结..."
                /home/xuanli/miniconda3/bin/python3 src/core/generate_summary.py \
                    --input-file "$filtered_file" \
                    --output-dir summary

                if [ $? -eq 0 ]; then
                    echo "✅ 总结生成完成"
                else
                    echo "❌ 总结生成失败"
                fi
            else
                echo "ℹ️  该日期没有筛选出论文"
            fi
        fi
    else
        echo "❌ 筛选失败"
    fi

    echo ""
    sleep 2  # 避免 API 限流
done

echo "=========================================="
echo "数据修复完成！"
echo "=========================================="
echo ""
echo "接下来的步骤："
echo "1. 运行: python src/core/generate_unified_index.py  # 重新生成统一网页"
echo "2. 检查生成的网页是否正常"
echo "3. 提交更新: git add . && git commit -m 'Fix missing data' && git push"
