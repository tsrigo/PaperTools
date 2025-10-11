# 1. 运行流水线生成新数据
/home/xuanli/miniconda3/bin/python3 papertools.py run --mode full --skip-serve

eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519_wk
# 2. 推送更新
git add .
git commit -m "Update papers: $(date -d "yesterday" +%Y-%m-%d)"
git push origin master