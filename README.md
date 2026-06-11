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
| `FILTER_MODEL` | 筛选阶段模型，默认 `qwen` | 否 |
| `PAPERTOOLS_FILTER_MODEL_CHAIN` | 筛选模型回退链；OpenRouter 下自动把短别名归一化为 provider-prefixed ID | 否 |
| `CLUSTER_MODEL` | 聚类阶段模型，默认跟随 `FILTER_MODEL` | 否 |
| `CLUSTER_OPENAI_BASE_URL` | 聚类阶段 API 地址；不填则使用 `OPENAI_BASE_URL` | 否 |
| `PAPERTOOLS_CLUSTER_MODEL_CHAIN` | 聚类模型回退链；OpenRouter 下自动把短别名归一化为 provider-prefixed ID | 否 |
| `SUMMARY_MODEL_CHAIN` | 总结/翻译模型回退链，默认 `sjtu:minimax,sjtu:glm,sjtu:qwen,sjtu:deepseek-chat,sjtu:deepseek-reasoner`；可显式加入 `prism:gpt-5.5` | 否 |
| `SUMMARY_SJTU_OPENAI_API_KEY` | 致远一号总结/翻译 API，不用于筛选 | 否 |
| `SUMMARY_PRISM_OPENAI_API_KEY` | Prism 总结/翻译 API，不用于筛选 | 否 |
| `SUMMARY_SJTU_RPM` | SJTU 总结 provider 的共享 RPM 限制，默认 2；同一 key/base URL 下多个模型共用冷却 | 否 |
| `SUMMARY_PRISM_RPM` | Prism 每分钟请求上限，默认 5 | 否 |
| `SUMMARY_PRISM_REASONING_EFFORT` | Prism `reasoning_effort`，默认 `xhigh` | 否 |
| `SUMMARY_PRISM_WINDOW_SECONDS` | Prism 滚动限额窗口秒数，默认 300 | 否 |
| `SUMMARY_PRISM_WINDOW_SAFETY_REQUESTS` | Prism 滚动窗口安全余量，默认 1 | 否 |
| `SUMMARY_PRISM_429_COOLDOWN_SECONDS` | Prism 429 后冷却秒数，默认 300 | 否 |
| `REVIEWGROUNDER_API_KEY` | ReviewGrounder key；默认优先复用 `SUMMARY_PRISM_OPENAI_API_KEY` | 否 |
| `REVIEWGROUNDER_BASE_URL` | ReviewGrounder base URL；默认优先复用 `SUMMARY_PRISM_OPENAI_BASE_URL` | 否 |
| `REVIEWGROUNDER_MODEL` | ReviewGrounder backbone，默认 `gpt-5.5` | 否 |
| `REVIEWGROUNDER_REASONING_EFFORT` | ReviewGrounder reasoning effort，默认 `xhigh` | 否 |
| `REVIEWGROUNDER_RPM` | ReviewGrounder backbone 的滚动 RPM 限制，默认 `5` | 否 |
| `REVIEWGROUNDER_MAX_RELATED_PAPERS` | 每篇最多纳入的 related papers，默认 `1` | 否 |
| `FILTER_MAX_WORKERS` | 筛选阶段并发上限，默认 5 | 否 |
| `PAPERTOOLS_FILTER_LLM_TIMEOUT` | 筛选阶段单次 LLM 请求超时秒数，默认 120 | 否 |
| `PAPERTOOLS_FILTER_LLM_MAX_RETRIES` | 筛选阶段 LLM 重试次数，默认 1 | 否 |
| `PAPERTOOLS_FILTER_EXTRACT_CHAIN` | 筛选阶段 prestige 机构抽取链，默认 `docling,pymupdf4llm,jina` | 否 |
| `PAPERTOOLS_TOPIC_HEURISTIC_TOPIC_BYPASS_MIN_SCORE` | 强主题确定性命中的 LLM 细筛旁路最低分，默认 30；硬排除风险仍交给 LLM | 否 |
| `PAPERTOOLS_FILTER_SUSPICIOUS_ZERO_MIN_INPUT` | 可疑零结果源论文阈值，默认 500 | 否 |
| `PAPERTOOLS_FILTER_SUSPICIOUS_ZERO_MIN_PREFILTERED` | 可疑零结果关键词候选阈值，默认 100 | 否 |
| `PAPERTOOLS_OPENAI_TRUST_ENV` | OpenAI-compatible API 是否继承系统代理环境，默认 `false` | 否 |
| `PAPERTOOLS_PIPELINE_STAGE_TIMEOUT_SECONDS` | 单个 pipeline 子进程阶段超时秒数，默认 21600；设为 0 可禁用 | 否 |
| `WEBHOOK_URL` | 失败/完成通知 webhook | 否 |
| `PAPERTOOLS_DAILY_WINDOW_DAYS` | 每日任务滚动补抓天数，默认 4 | 否 |
| `PAPERTOOLS_DAILY_PIPELINE_TIMEOUT_SECONDS` | 每日自动发布单次 pipeline 超时秒数，默认 21600（6 小时） | 否 |
| `PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK` | 设为 `1` 时每日 wrapper 跳过远端 `/models` 预检；默认 `0`。默认预检会按筛选、聚类、总结 provider 的实际 endpoint 分组检查模型 | 否 |
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
papertools check --install-missing    # 显式安装缺失的基础依赖
```

## 开发检查

项目支持 CPython 3.10-3.14；CI 会覆盖 `pyproject.toml` 中声明的所有
CPython 版本。

```bash
pip install -e ".[dev]"
pre-commit install  # 可选：提交前运行快速检查
make test       # 隔离外部 pytest 插件，避免全局环境影响测试
make lint       # Ruff lint + format check
make security   # Bandit medium/high security gate
make validate-data  # 校验当前 webpages/data 发布 payload
make pre-commit # 对已跟踪文件运行提交前检查
make ci         # 本地复现主要 CI 检查
```

## 定时运行

```bash
crontab -e
# 每天早上 8 点自动运行、校验并发布 webpages/
0 8 * * * cd /path/to/PaperTools && ./daily_update.sh >> logs/cron.log 2>&1
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
- [质量门禁](docs/QUALITY_GATES.md)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [行为准则](CODE_OF_CONDUCT.md)
