# 1. 运行流水线生成新数据
python3 papertools.py run --mode full --skip-serve

# 2. 推送更新
git add .
git commit -m "Update papers: $(date -d "yesterday" +%Y-%m-%d)"
git push origin master