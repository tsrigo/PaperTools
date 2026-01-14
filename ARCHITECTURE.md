# PaperTools 架构文档

## 概述

PaperTools 是一个学术论文自动化处理流水线，包括：爬取、筛选、总结、网页生成和部署。

## 目录结构

```
PaperTools/
├── src/                     # 源代码
│   ├── core/               # 核心模块
│   │   ├── crawl_arxiv.py      # arXiv 论文爬取
│   │   ├── paper_filter.py     # 论文筛选 (LLM)
│   │   ├── generate_summary.py # 论文总结生成
│   │   ├── generate_unified_index.py  # 网页生成
│   │   ├── serve_webpages.py   # 本地服务器
│   │   └── pipeline.py         # 流水线编排
│   └── utils/              # 工具模块
│       ├── config.py           # 配置管理
│       ├── cache_manager.py    # 缓存管理
│       ├── logger.py           # 日志系统
│       └── io.py               # IO 工具
├── tests/                  # 测试代码
├── templates/              # Jinja2 模板
├── scripts/                # 维护脚本
├── arxiv_paper/            # 爬取的原始论文 (JSON)
├── domain_paper/           # 筛选后的论文
├── summary/                # 带总结的论文
├── webpages/               # 生成的网页
├── cache/                  # 三级缓存
└── logs/                   # 日志文件
```

## 数据流

```
crawl_arxiv.py
    │
    ▼
arxiv_paper/*.json (原始论文数据)
    │
    ▼
paper_filter.py (LLM 筛选)
    │
    ▼
domain_paper/filtered_papers_*.json (筛选后)
domain_paper/excluded_papers_*.json (排除的)
    │
    ▼
generate_summary.py (LLM 总结)
    │
    ▼
summary/*_with_summary2.json (带中文总结)
summary/daily_overview_*.md (每日速览)
    │
    ▼
generate_unified_index.py
    │
    ▼
webpages/index.html (交互式网页)
webpages/data/*.json (按日期的数据)
```

## 核心模块说明

### crawl_arxiv.py
- 从 arXiv 爬取指定类别的论文
- 支持日期范围筛选
- 使用缓存避免重复爬取
- 多线程并发爬取

### paper_filter.py
- 使用 LLM 判断论文是否符合研究主题
- 流式响应避免超时
- 输出筛选原因

### generate_summary.py
- 使用 Jina API 获取论文全文
- 使用 LLM 生成中文总结
- 生成每日论文速览
- 重试机制处理 API 限流

### generate_unified_index.py
- 生成交互式单页应用
- 支持暗色模式
- 收藏功能 (localStorage)
- 分页按需加载

### pipeline.py
- 编排整个流水线
- 支持断点续跑
- 进度跟踪和日志

## 配置

### 环境变量 (.env)

```bash
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL=gpt-4
JINA_API_TOKEN=your-jina-token
```

### config.py 主要配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| MAX_WORKERS | 并发线程数 | 2 |
| TEMPERATURE | LLM 温度 | 0.1 |
| REQUEST_TIMEOUT | 请求超时 | 300s |
| CACHE_EXPIRY_DAYS | 缓存过期天数 | 30 |

## 缓存系统

三级缓存机制：
1. **papers**: 爬取的原始论文
2. **summaries**: 生成的总结
3. **webpages**: 网页相关数据

缓存键使用 MD5 哈希生成，确保唯一性。

## 错误处理

- 所有 API 调用都有重试机制
- 流式响应避免 Cloudflare 524 超时
- 失败任务记录到单独文件

## 扩展指南

### 添加新的论文类别

1. 修改 `config.py` 的 `CRAWL_CATEGORIES`
2. 更新 `generate_unified_index.py` 的 `category_names`

### 修改筛选条件

修改 `config.py` 的 `PAPER_FILTER_PROMPT`

### 自定义总结格式

修改 `generate_summary.py` 中的 prompt 模板
