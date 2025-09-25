# 1. 运行流水线生成新数据
python papertools.py run --mode full

# 2. 推送更新
git add .
git commit -m "Update papers: $(date +%Y-%m-%d)"
git push origin master