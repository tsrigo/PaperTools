#!/bin/bash
# 修复单个日期的数据

if [ -z "$1" ]; then
    echo "用法: $0 <日期> (例如: 2025-12-19)"
    exit 1
fi

DATE=$1

# 激活环境
source /home/xuanli/miniconda3/etc/profile.d/conda.sh
conda activate alphaapollo
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087

echo "=========================================="
echo "处理日期: $DATE"
echo "=========================================="

# 删除旧的缓存文件
echo "🗑️  删除旧缓存..."
rm -f domain_paper/filtered_papers_${DATE}.json
rm -f domain_paper/excluded_papers_${DATE}.json

# 重新筛选
echo "🔄 开始筛选..."
/home/xuanli/miniconda3/bin/python3 src/core/paper_filter.py \
    --input-file arxiv_paper/cs.AI_cs.CL_cs.LG_cs.MA_paper_${DATE}.json \
    --output-dir domain_paper \
    --max-workers 10

if [ $? -eq 0 ]; then
    echo "✅ 筛选完成"

    # 检查是否有筛选结果
    if [ -f "domain_paper/filtered_papers_${DATE}.json" ]; then
        file_size=$(stat -c%s "domain_paper/filtered_papers_${DATE}.json" 2>/dev/null)
        if [ "$file_size" -gt 10 ]; then
            echo "📊 发现 $(grep -o '"arxiv_id"' domain_paper/filtered_papers_${DATE}.json | wc -l) 篇论文"
            echo "🔄 生成总结..."
            /home/xuanli/miniconda3/bin/python3 src/core/generate_summary.py \
                --input-file domain_paper/filtered_papers_${DATE}.json \
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

echo "=========================================="
echo "完成！"
echo "=========================================="
