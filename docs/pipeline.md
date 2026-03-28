# 流水线详解

## 概览

```
爬取 (crawl) → 筛选 (filter) → 聚类 (cluster) → 总结 (summarize) → 网页生成 (unified) → 服务 (serve)
```

每个阶段输出独立的 JSON 文件，阶段之间通过文件衔接，可以从任意阶段断点续跑。

---

## 阶段 1：爬取（crawl）

**脚本**：`src/core/crawl_arxiv.py`

**做什么**：通过 [papers.cool](https://papers.cool) API 抓取指定 arXiv 类别的最新论文列表，包含标题、摘要、作者、arxiv ID 等元数据。

**输入**：无（直接访问远程 API）

**输出**：`arxiv_paper/<date>_<categories>.json`，例如 `arxiv_paper/2026-03-28_cs.AI_cs.CL_cs.LG_cs.MA.json`

**独立运行**：

```bash
python src/core/crawl_arxiv.py \
  --categories cs.AI cs.CL cs.LG \
  --max-papers 5000 \
  --output-dir arxiv_paper \
  --date 2026-03-28
```

**关键参数**：

| 参数 | 说明 |
|------|------|
| `--categories` | arXiv 类别，空格分隔 |
| `--max-papers` | 每个类别最大爬取数 |
| `--date` | 指定日期（`YYYY-MM-DD`），默认最新 |
| `--start-date` / `--end-date` | 指定日期范围 |

---

## 阶段 2：筛选（filter）

**脚本**：`src/core/paper_filter.py`

**做什么**：对每篇论文调用 LLM，根据 `PAPER_FILTER_PROMPT` 判断是否与研究方向相关，保留匹配论文，丢弃无关论文。

**输入**：`arxiv_paper/<date>_*.json`

**输出**：
- `domain_paper/filtered_papers_<date>.json`（保留的论文）
- `domain_paper/excluded_papers_<date>.json`（排除的论文，含理由）

**独立运行**：

```bash
python src/core/paper_filter.py \
  --input-file arxiv_paper/2026-03-28_cs.AI_cs.CL_cs.LG_cs.MA.json \
  --output-dir domain_paper \
  --max-papers 100
```

---

## 阶段 3：聚类（cluster）

**脚本**：`src/core/cluster_papers.py`

**做什么**：将筛选后的论文按研究主题分组。使用 LLM 以 60 篇为一批进行聚类，识别 3-8 个主题簇（如 "Multi-Agent Collaboration"、"Tool Use & Planning"），多批次结果再经 LLM 合并去重。每篇论文获得一个 `cluster` 字段。

**输入**：`domain_paper/filtered_papers_<date>.json`

**输出**：`domain_paper/clustered_<date>.json`

**独立运行**：

```bash
python src/core/cluster_papers.py \
  --input-file domain_paper/filtered_papers_2026-03-28.json \
  --output-dir domain_paper
```

---

## 阶段 4：总结（summarize）

**脚本**：`src/core/generate_summary.py`

**做什么**：
1. 可选地通过 Jina Reader API（`r.jina.ai`）获取论文全文（需要 `JINA_API_TOKEN`）
2. 调用 LLM 为每篇论文生成以下内容，写入 JSON 的对应字段：
   - `summary2`：中文论文摘要/总结
   - `inspiration_trace`：创新思路的演进分析（从挑战识别到解决方案的逻辑链）
   - `research_insights`：对读者的启发性观点

**输入**：`domain_paper/clustered_<date>.json`（或 `filtered_papers_<date>.json`，若跳过聚类）

**输出**：`summary/clustered_<date>_with_summary2.json`

**独立运行**：

```bash
python src/core/generate_summary.py \
  --input-file domain_paper/clustered_2026-03-28.json \
  --output-dir summary \
  --skip-existing
```

**关键参数**：

| 参数 | 说明 |
|------|------|
| `--skip-existing` | 跳过已有 `summary2` 的论文，用于增量更新 |
| `--max-workers` | 并发线程数 |

---

## 阶段 5：网页生成（unified）

**脚本**：`src/core/generate_unified_index.py`

**做什么**：扫描 `summary/` 目录下所有 `*_with_summary2.json` 文件，生成一个单页面 HTML（`webpages/index.html`）。界面按日期和聚类主题组织论文，支持折叠展开、收藏、已读标记。

**输入**：`summary/*_with_summary2.json`（自动扫描，无需指定）

**输出**：`webpages/index.html`，`webpages/data/index.json`

**独立运行**：

```bash
python src/core/generate_unified_index.py
```

无命令行参数，目录由 `config.py` 中的 `SUMMARY_DIR` 和 `WEBPAGES_DIR` 控制。

---

## 阶段 6：服务（serve）

**脚本**：`src/core/serve_webpages.py`

**做什么**：启动本地 HTTP 服务器，在浏览器中展示 `webpages/` 目录下的网页。支持简单的用户状态持久化（收藏、已读、删除）。

**输入**：`webpages/` 目录

**独立运行**：

```bash
python src/core/serve_webpages.py --webpages-dir webpages --port 8080
```

访问 `http://localhost:8080` 查看结果。

---

## 流程控制选项

### `--start-from`

从指定阶段开始，自动跳过之前的所有阶段：

```bash
papertools run --start-from cluster   # 跳过 crawl、filter，从 cluster 开始
papertools run --start-from summary   # 跳过 crawl、filter、cluster
papertools run --start-from unified   # 只重新生成网页
```

合法值：`crawl`、`filter`、`cluster`、`summary`、`unified`、`serve`

### `--skip-*` 标志

跳过单个阶段：

```bash
papertools run --skip-crawl           # 使用已有的爬取结果
papertools run --skip-serve           # 不启动服务器（适合 cron）
papertools run --skip-cluster         # 跳过聚类（较快）
```

可用标志：`--skip-crawl`、`--skip-filter`、`--skip-cluster`、`--skip-summary`、`--skip-unified`、`--skip-serve`

### `--mode`

```bash
papertools run --mode quick    # 只处理 10 篇论文（快速测试）
papertools run --mode full     # 处理最多 10000 篇论文
```

未指定时使用 `MAX_PAPERS_TOTAL_DEFAULT`（默认 100 篇）。
