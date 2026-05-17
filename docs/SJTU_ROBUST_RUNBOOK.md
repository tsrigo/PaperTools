# PaperTools 日跑鲁棒性热修说明

## 发现的问题

1. `src/utils/config.py` 里的模型别名会把 `MiniMax-M2.7` 映射成 `qwen`，把 `deepseek-reasoner` 映射成 `deepseek-chat`。在 SJTU 端点已经提供 `minimax` 和 `deepseek-reasoner` 这两个 model_id 时，这会让你以为选了某个模型，实际请求却打到另一个模型。
2. 默认 summary base URL 仍指向 ModelScope，而你给的是 SJTU OpenAI-compatible API。没有额外 summary key 时，日跑容易在总结阶段跑到错误 provider。
3. `daily_update.sh` 只有单次 `python papertools.py run --mode full --skip-serve`，失败后直接跳过提交，没有状态文件、重试、窗口补抓、并发降载和永久错误识别。
4. OpenAI-compatible 客户端没有统一 timeout / SDK retry 默认值；共享网关上偶发 429、502、503、524 时容易把整次流水线打断。

## 安装

在 PaperTools 仓库根目录执行：

```bash
python /path/to/install_hardening.py
```

安装器会备份改动文件到 `.papertools_hotfix_backup/<timestamp>/`。

然后把模板复制成 `.env`，填入真实 key：

```bash
cp .env.sjtu.example .env
chmod 600 .env
# 编辑 OPENAI_API_KEY
```

## 推荐 crontab

```cron
0 8 * * * cd /path/to/PaperTools && bash scripts/robust_daily_update.sh >> logs/cron.log 2>&1
```

默认使用最近 4 天的滚动窗口，适合 arXiv/镜像站晚更新、前一天失败后自动补抓的场景。

## 回滚

改动前文件都在：

```bash
.papertools_hotfix_backup/<timestamp>/
```

可直接复制回去，或用 git checkout 回滚源码文件。
