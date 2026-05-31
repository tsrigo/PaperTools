# 配置参考

## 环境变量（`.env`）

从 `.env.example` 复制并填写：

```bash
cp .env.example .env
```

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | 是 | LLM API 密钥 |
| `OPENAI_BASE_URL` | 是 | API 端点地址，例如 `https://api.openai.com/v1` |
| `MODEL` | 是 | 模型名称，例如 `gpt-4o`、`deepseek-chat` |
| `FILTER_MODEL` | 否 | 筛选阶段模型；不会使用 Prism summary provider |
| `CLUSTER_MODEL` | 否 | 聚类阶段模型，默认跟随 `FILTER_MODEL` |
| `CLUSTER_OPENAI_API_KEY` | 否 | 聚类阶段 API 密钥；不填则使用 `OPENAI_API_KEY` |
| `CLUSTER_OPENAI_BASE_URL` | 否 | 聚类阶段 API 端点；不填则使用 `OPENAI_BASE_URL` |
| `PAPERTOOLS_CLUSTER_MODEL_CHAIN` | 否 | 聚类模型回退链；OpenRouter 下自动把 `qwen`、`minimax`、`deepseek-chat` 等短别名归一化为 provider-prefixed ID |
| `SUMMARY_MODEL_CHAIN` | 否 | 总结/翻译阶段模型回退链，默认 `prism:gpt-5.5,sjtu:minimax,sjtu:glm,sjtu:qwen,sjtu:deepseek-reasoner,sjtu:deepseek-chat` |
| `SUMMARY_SJTU_OPENAI_API_KEY` | 否 | 致远一号总结/翻译 API 密钥，只用于筛选后的内容生成 |
| `SUMMARY_SJTU_OPENAI_BASE_URL` | 否 | 致远一号 OpenAI-compatible base URL，默认 `https://models.sjtu.edu.cn/api/v1/` |
| `SUMMARY_SJTU_RPM` | 否 | SJTU 总结 provider 的共享 RPM 限制，默认 `2`；同一 key/base URL 下多个模型共用节流和 429 冷却状态 |
| `SUMMARY_SJTU_WINDOW_SECONDS` | 否 | SJTU 总结 provider 的滚动窗口秒数，默认 `300` |
| `SUMMARY_SJTU_WINDOW_SAFETY_REQUESTS` | 否 | SJTU 总结 provider 的滚动窗口安全余量，默认 `1` |
| `SUMMARY_SJTU_429_COOLDOWN_SECONDS` | 否 | SJTU 429 后冷却秒数，默认 `300` |
| `SUMMARY_PRISM_OPENAI_API_KEY` | 否 | Prism 总结/翻译 API 密钥，只用于筛选后的内容生成 |
| `SUMMARY_PRISM_OPENAI_BASE_URL` | 否 | Prism OpenAI-compatible base URL，默认 `https://ai.prism.uno/v1` |
| `SUMMARY_PRISM_RPM` | 否 | Prism provider 每分钟请求上限，默认 `5` |
| `SUMMARY_PRISM_REASONING_EFFORT` | 否 | Prism `reasoning_effort` 参数，默认 `xhigh`；留空则不传 |
| `SUMMARY_PRISM_WINDOW_SECONDS` | 否 | Prism 滚动限额窗口秒数，默认 `300` |
| `SUMMARY_PRISM_WINDOW_SAFETY_REQUESTS` | 否 | Prism 滚动窗口安全余量，默认 `1` |
| `SUMMARY_PRISM_429_COOLDOWN_SECONDS` | 否 | Prism 429 后冷却秒数，默认 `300` |
| `REVIEWGROUNDER_API_KEY` | 否 | ReviewGrounder 审稿模型 API key；不填则优先回退 `SUMMARY_PRISM_OPENAI_API_KEY`，再回退 `OPENAI_API_KEY` |
| `REVIEWGROUNDER_BASE_URL` | 否 | ReviewGrounder 审稿模型 API 地址；不填则优先回退 `SUMMARY_PRISM_OPENAI_BASE_URL`，再回退 `OPENAI_BASE_URL` |
| `REVIEWGROUNDER_MODEL` | 否 | ReviewGrounder backbone，默认 `gpt-5.5` |
| `REVIEWGROUNDER_REASONING_EFFORT` | 否 | ReviewGrounder reasoning effort，默认 `xhigh` |
| `REVIEWGROUNDER_RPM` | 否 | ReviewGrounder backbone 的进程级滚动 RPM 限制，默认 `5` |
| `REVIEWGROUNDER_MAX_RELATED_PAPERS` | 否 | 每篇目标论文最多纳入的 related papers，默认 `1`，用于适配 5 RPM 后端 |
| `FILTER_MAX_WORKERS` | 否 | 筛选阶段最大并发，默认 `5`，用于降低筛选模型尾延迟和限流风险 |
| `PAPERTOOLS_FILTER_LLM_TIMEOUT` | 否 | 筛选阶段单次 LLM 请求超时秒数，默认 `45` |
| `PAPERTOOLS_FILTER_LLM_MAX_RETRIES` | 否 | 筛选阶段 LLM 重试次数，默认 `1` |
| `PAPERTOOLS_FILTER_EXTRACT_CHAIN` | 否 | 筛选阶段 prestige 机构抽取链，默认 `docling,pymupdf4llm,jina`，优先本地抽取，远程兜底 |
| `PAPERTOOLS_TOPIC_HEURISTIC_TOPIC_BYPASS_MIN_SCORE` | 否 | 强主题确定性命中的 LLM 细筛旁路最低分，默认 `30`；安全/图/视觉等硬排除风险仍交给 LLM 判定 |
| `WEBHOOK_URL` | 否 | 流水线完成或失败时推送通知的 webhook 地址 |
| `PAPERTOOLS_DAILY_WINDOW_DAYS` | 否 | 每日 cron wrapper 默认滚动补抓天数，默认 `4` |
| `PAPERTOOLS_DAILY_START_DATE` | 否 | 手动覆盖每日 cron wrapper 的补抓起始日期 |
| `PAPERTOOLS_DAILY_END_DATE` | 否 | 手动覆盖每日 cron wrapper 的补抓结束日期 |
| `JINA_API_TOKEN` | 否 | Jina Reader API 令牌，用于获取论文全文。不填则跳过全文拉取 |

---

## `src/utils/config.py` 参数

此文件定义流水线的运行行为。直接编辑文件修改默认值。

### API 与请求

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TEMPERATURE` | `0.1` | LLM 生成温度。越低结果越稳定，推荐保持低值以提高筛选/聚类一致性 |
| `REQUEST_TIMEOUT` | `300` | 单次 API 请求超时时间（秒） |
| `REQUEST_DELAY` | `5` | 相邻两次请求之间的等待时间（秒），用于避免 API 速率限制 |

### 目录

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ARXIV_PAPER_DIR` | `arxiv_paper` | 爬取阶段输出目录 |
| `DOMAIN_PAPER_DIR` | `domain_paper` | 筛选和聚类阶段输出目录 |
| `SUMMARY_DIR` | `summary` | 总结阶段输出目录 |
| `WEBPAGES_DIR` | `webpages` | 网页生成阶段输出目录 |

### 缓存

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `CACHE_DIR` | `cache` | 缓存文件存储目录 |
| `ENABLE_CACHE` | `True` | 是否启用缓存。启用后可跳过已处理论文，节省 API 调用 |
| `CACHE_EXPIRY_DAYS` | `30` | 缓存有效天数，超期后重新处理 |

### 爬取

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `CRAWL_CATEGORIES` | `['cs.AI', 'cs.CL', 'cs.LG', 'cs.MA']` | 爬取的 arXiv 类别列表 |
| `MAX_PAPERS_PER_CATEGORY` | `5000` | 每个类别最多爬取的论文数量 |
| `MAX_PAPERS_TOTAL_QUICK` | `10` | `--mode quick` 下总处理论文数 |
| `MAX_PAPERS_TOTAL_FULL` | `10000` | `--mode full` 下总处理论文数 |
| `MAX_PAPERS_TOTAL_DEFAULT` | `100` | 未指定 mode 时的默认处理数量 |

### 并发

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MAX_WORKERS` | `1` | 全局最大并发线程数，适用于爬取、筛选、总结阶段。设为 1 可避免 API 速率限制报错（524 错误） |

### Jina API

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `JINA_MAX_REQUESTS_PER_MINUTE` | `20` | Jina API 每分钟最大请求数（与官方免费额度对应） |
| `JINA_MAX_RETRIES` | `3` | Jina 请求失败后的最大重试次数 |
| `JINA_BACKOFF_FACTOR` | `2.0` | 重试指数退避因子 |
| `JINA_API_TOKEN` | 读自 `.env` | Jina API 令牌（同上，优先在 `.env` 中设置） |

---

## `PAPER_FILTER_PROMPT`

### 作用

`PAPER_FILTER_PROMPT` 是论文筛选阶段的 LLM Prompt 模板。筛选阶段对每篇论文调用一次 LLM，将 `{title}` 和 `{summary}` 填入模板，要求模型返回：

```
结果: [True/False]
理由: [...]
```

`True` 表示保留，`False` 表示排除。

### 默认配置

默认 Prompt 针对 **LLM 智能体及其演化** 方向：保留单智能体、多智能体、自我演化相关论文，排除安全/对齐、多模态、纯基础设施类论文。

### 如何自定义

直接编辑 `src/utils/config.py` 中的 `PAPER_FILTER_PROMPT` 字符串。模板中必须保留 `{title}` 和 `{summary}` 两个占位符，模型输出必须包含 `结果: True` 或 `结果: False`。

示例——改为筛选 RAG 相关论文：

```python
PAPER_FILTER_PROMPT = """你是一位研究检索增强生成（RAG）的专家。请判断以下论文是否与 RAG 系统的设计、优化或应用直接相关。

论文标题: {title}
论文摘要: {summary}

请严格按照以下格式回答:
结果: [True/False]
理由: [...]"""
```
