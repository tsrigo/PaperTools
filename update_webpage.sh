#!/bin/bash

# 1. 运行流水线生成新数据
/home/xuanli/miniconda3/bin/python3 papertools.py run --mode full --skip-serve

eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519_wk

# 2. 生成智能 commit 消息
generate_commit_msg() {
    local msg=""
    local new_papers=0
    local modified_files=0

    # 检查新增的数据文件
    new_data=$(git status --porcelain webpages/data/*.json 2>/dev/null | grep "^?" | wc -l)
    modified_data=$(git status --porcelain webpages/data/*.json 2>/dev/null | grep "^.M" | wc -l)

    # 检查 summary 目录的变化
    new_summary=$(git status --porcelain summary/ 2>/dev/null | grep "^?" | wc -l)

    # 检查是否有代码变更
    code_changes=$(git status --porcelain src/ 2>/dev/null | wc -l)

    # 构建消息
    if [ "$new_data" -gt 0 ] || [ "$new_summary" -gt 0 ]; then
        msg="Add papers: $(date +%Y-%m-%d)"
    elif [ "$modified_data" -gt 0 ]; then
        msg="Update papers: $(date +%Y-%m-%d)"
    elif [ "$code_changes" -gt 0 ]; then
        msg="Update code: $(date +%Y-%m-%d)"
    else
        msg="Chore: $(date +%Y-%m-%d)"
    fi

    echo "$msg"
}

# 3. 推送更新
git add .

# 检查是否有变更
if git diff --cached --quiet; then
    echo "没有需要提交的变更"
    exit 0
fi

COMMIT_MSG=$(generate_commit_msg)
git commit -m "$COMMIT_MSG"
git push origin master