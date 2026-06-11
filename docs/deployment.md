# 部署指南

## GitHub Pages

将生成的论文网站免费发布到 GitHub Pages，推荐使用 Fork + GitHub Actions 方式实现自动部署。

### 步骤 1：Fork 本仓库

点击页面右上角的 **Fork** 按钮，将项目复制到自己的 GitHub 账户。

### 步骤 2：配置 Pages 和 Actions 权限

**配置 Pages 源：**

1. 进入 Fork 后仓库的 `Settings` > `Pages`
2. 在 `Build and deployment` > `Source` 中选择 `GitHub Actions`

**检查 Actions 权限：**

1. 进入 `Settings` > `Actions` > `General`
2. 滚动到 `Workflow permissions`
3. 确认 GitHub Actions 已启用
4. 不需要勾选 `Allow GitHub Actions to create and approve pull requests`

部署工作流在 `.github/workflows/deploy.yml` 中声明最小权限：
`contents: read`、`pages: write`、`id-token: write`。

### 步骤 3：触发部署

首次配置完成后，在 `Actions` 标签页手动触发 `Deploy PaperTools Website` 工作流，或推送一次提交触发自动运行。

部署成功后，网站地址为：`https://<用户名>.github.io/<仓库名>/`

### GitHub Actions 工作流说明

`.github/workflows/deploy.yml` 的执行流程：

1. Checkout 代码（包含已提交的 `webpages/` 发布内容）
2. 安装依赖
3. 运行 `scripts/validate_published_payloads.py --webpages-dir webpages`
4. 将已验证的 `webpages/` 目录作为 Pages artifact 上传并部署

**更新网站内容**：优先使用 `./daily_update.sh`。脚本会从最新 `origin/master` 或 `origin/main` 开始，要求干净工作区，加锁防止并发发布，运行完整流水线，执行 `scripts/validate_published_payloads.py`，然后只提交 `webpages/` 发布内容。Actions 会在推送后自动重新部署。

**自定义筛选规则**：修改 `src/utils/config.py` 中的 `PAPER_FILTER_PROMPT` 并推送后，需要用 `./daily_update.sh` 重新生成并验证 `webpages/` 发布内容。部署工作流不会从中间文件重新生成网页。

### 备选方案：手动部署

在本地生成网站后，将 `webpages/` 目录的内容上传到任意静态托管服务（Netlify、Vercel、Cloudflare Pages 等）。

---

## crontab 定时运行

在服务器上设置 cron 任务，每天自动运行、校验并发布：

```bash
crontab -e
```

常用示例：

```bash
# 每天早上 8 点运行 hardened daily publisher
0 8 * * * cd /path/to/PaperTools && ./daily_update.sh >> logs/cron.log 2>&1

# 仅工作日运行（周一至周五）
0 8 * * 1-5 cd /path/to/PaperTools && ./daily_update.sh >> logs/cron.log 2>&1

# SJTU/慢网关重试窗口模式
0 8 * * * cd /path/to/PaperTools && bash scripts/robust_daily_update.sh >> logs/cron.log 2>&1
```

不要在生产 cron 中直接运行 `papertools run --skip-serve`。该命令适合本地诊断，但不会独立保证发布前 worktree 干净、已 fast-forward 到最新 `origin`、持有发布锁、只暂存 `webpages/`、失败时不提交等发布不变量。

本地排查流水线时可以手动运行：

```bash
papertools run --mode full --skip-serve --date YYYY-MM-DD
python scripts/validate_published_payloads.py --webpages-dir webpages
git diff -- webpages/
```

只有验证后的 `webpages/` 变更才是可发布内容。

---

## 日志管理

### 输出重定向

`>> logs/cron.log 2>&1` 将标准输出和错误输出均追加到日志文件。确保 `logs/` 目录存在：

```bash
mkdir -p /path/to/PaperTools/logs
```

### 防止日志无限增长（logrotate）

创建 `/etc/logrotate.d/papertools`：

```
/path/to/PaperTools/logs/cron.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
}
```

或使用简单的手动轮转（在 cron 中）：

```bash
0 8 * * * cd /path/to/PaperTools && ./daily_update.sh >> logs/cron.log 2>&1 && find logs/ -name "*.log" -mtime +30 -delete
```

---

## 常见问题

### cron 中找不到 `papertools` 命令

cron 的 `PATH` 不包含 Python 虚拟环境。有两种解决方式：

**方式一**：在 crontab 中指定完整路径：

```bash
0 8 * * * cd /path/to/PaperTools && PATH="/path/to/venv/bin:$PATH" ./daily_update.sh >> logs/cron.log 2>&1
```

**方式二**：用脚本包装并激活虚拟环境：

```bash
# run.sh
#!/bin/bash
source /path/to/venv/bin/activate
cd /path/to/PaperTools
./daily_update.sh
```

```bash
0 8 * * * /path/to/run.sh >> /path/to/PaperTools/logs/cron.log 2>&1
```

### cron 中缺少环境变量

cron 不读取 `.env` 文件以外，也不继承 shell 的环境变量。确保 `.env` 文件存在且内容正确：

```bash
# 验证 .env 被正确读取
cd /path/to/PaperTools && papertools check
```

如果使用系统环境变量而非 `.env`，需要在 crontab 顶部显式声明：

```bash
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.example.com/v1
MODEL=your-model
```

### 时区问题

cron 使用系统时区。arXiv 每天约 UTC 00:00 更新前一天的论文。若要确保爬取到最新数据，建议将 cron 时间设置在 UTC 01:00 之后（即北京时间 09:00 之后）。
