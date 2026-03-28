#!/bin/bash

# 获取脚本所在目录
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

# 激活虚拟环境
source venv/bin/activate

# 运行论文处理流水线
# --mode full: 运行完整处理（已在 config.py 中设为 0 表示不限制）
# --skip-serve: 运行完后不启动服务器
python papertools.py run --mode full --skip-serve

# 检查运行是否成功
if [ $? -eq 0 ]; then
    echo "✅ 流水线运行成功，准备提交到 GitHub..."
    
    # 添加生成的数据和网页文件
    git add arxiv_paper/ domain_paper/ summary/ webpages/
    
    # 提交更改
    COMMIT_MSG="Daily paper update: $(date +'%Y-%m-%d')"
    git commit -m "$COMMIT_MSG"
    
    # 推送到 GitHub
    git push origin master
    
    if [ $? -eq 0 ]; then
        echo "🚀 成功推送到 GitHub！"
    else
        echo "❌ 推送失败，请检查 Git 配置或网络连接。"
    fi
else
    echo "❌ 流水线运行失败，跳过 Git 提交。"
fi
