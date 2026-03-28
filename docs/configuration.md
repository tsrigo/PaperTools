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
| `WEBHOOK_URL` | 否 | 流水线完成或失败时推送通知的 webhook 地址 |
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
