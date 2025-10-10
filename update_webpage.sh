python3 papertools.py run --mode full --skip-serve

git add .
git commit -m "Update papers: $(date -d "yesterday" +%Y-%m-%d)"
git push origin master