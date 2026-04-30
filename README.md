# PaperTools

自动追踪、筛选、聚类、总结 arXiv 论文。每天帮你从海量论文中找到真正相关的研究。

## 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 配置
cp .env.example .env
# 编辑 .env，填入 API 地址、密钥和模型名

# 3. 运行
papertools run
```

## 配置

| 变量 | 说明 | 必填 |
|------|------|------|
| `OPENAI_BASE_URL` | API 地址 | 是 |
| `OPENAI_API_KEY` | API 密钥 | 是 |
| `MODEL` | 模型名 | 是 |
| `CLUSTER_MODEL` | 聚类阶段模型，默认跟随 `FILTER_MODEL` | 否 |
| `SUMMARY_MODEL_CHAIN` | 总结/翻译模型回退链 | 否 |
| `SUMMARY_PRISM_OPENAI_API_KEY` | Prism 总结/翻译 API，不用于筛选 | 否 |
| `SUMMARY_PRISM_RPM` | Prism 每分钟请求上限，默认 5 | 否 |
| `SUMMARY_PRISM_REASONING_EFFORT` | Prism `reasoning_effort`，默认 `xhigh` | 否 |
| `FILTER_MAX_WORKERS` | 筛选阶段并发上限，默认 5 | 否 |
| `PAPERTOOLS_FILTER_LLM_TIMEOUT` | 筛选阶段单次 LLM 请求超时秒数，默认 45 | 否 |
| `PAPERTOOLS_FILTER_LLM_MAX_RETRIES` | 筛选阶段 LLM 重试次数，默认 1 | 否 |
| `WEBHOOK_URL` | 失败/完成通知 webhook | 否 |
| `PAPERTOOLS_DAILY_WINDOW_DAYS` | 每日任务滚动补抓天数，默认 4 | 否 |
| `JINA_API_TOKEN` | Jina Reader API（全文获取）| 否 |

筛选规则在 `src/utils/config.py` 的 `PAPER_FILTER_PROMPT` 中定义。

## 命令

```bash
papertools run                        # 运行完整流水线
papertools run --mode quick           # 快速测试（10篇）
papertools run --date 2026-03-28      # 指定日期
papertools run --start-date 2026-03-26 --end-date 2026-03-28
papertools serve                      # 启动本地服务器
papertools clean                      # 清理缓存
papertools check                      # 检查环境
```

## 定时运行

```bash
crontab -e
# 每天早上 8 点自动运行
0 8 * * * cd /path/to/PaperTools && papertools run --skip-serve >> logs/cron.log 2>&1
```

## 流水线

```
爬取 arXiv → LLM 筛选 → LLM 聚类 → 摘要/总结生成 → 网页生成
```

每个阶段产出独立的 JSON 文件，可以从任意阶段恢复：`papertools run --start-from cluster`

## 更多文档

- [完整配置参考](docs/configuration.md)
- [流水线详解](docs/pipeline.md)
- [部署指南](docs/deployment.md)（GitHub Pages、crontab）
