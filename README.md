# PaperTools

[English](README_EN.md) | 中文

PaperTools 是一个完整的学术论文处理流水线，提供自动化的论文爬取、智能筛选、总结生成和网页生成功能。

## 功能特点

- **自动爬取**: 从arXiv等学术平台自动爬取最新论文
- **AI智能筛选**: 使用大语言模型按研究领域智能筛选论文
- **自动总结**: 基于jinja.ai获取完整论文内容，生成高质量中文总结
- **网页生成**: 将论文转换为现代化设计的交互式HTML网页
- **本地部署**: 一键启动本地服务器，便于浏览和分享
- **多线程处理**: 所有组件支持并行处理，提升性能
- **交互功能**: 支持论文收藏、已读状态跟踪和删除，状态持久化保存

## 系统要求

- Python 3.7+
- 网络连接（用于API调用和内容获取）
- 推荐：4GB+ RAM（处理大量论文时）

## 安装使用

### 环境设置

```bash
# 1. 复制配置模板
cp .env.example .env

# 2. 编辑 .env 文件，设置你的API密钥
# OPENAI_API_KEY=your_actual_api_key_here
# OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
# MODEL=glm-4.5-flash

# 3. 检查并安装依赖
python papertools.py check
```

### 快速开始

```bash
# 全量模式：处理1000篇论文（默认）
python papertools.py run

# 快速模式：处理10篇论文
python papertools.py run --mode quick

# 查看结果
python papertools.py serve

# 获取帮助
python papertools.py --help
```

## 使用说明

### 主要命令

```bash
# 运行论文处理流水线
python papertools.py run [选项]
  --mode {quick,full}     # 处理模式：quick(10篇) 或 full(1000篇，默认)
  --date YYYY-MM-DD       # 处理指定日期的论文
  --categories cs.AI cs.CL # 指定论文类别
  --max-papers-total N    # 自定义论文数量

# 启动网页服务器
python papertools.py serve

# 清理缓存文件
python papertools.py clean

# 检查环境和依赖
python papertools.py check
```

### 高级用法：独立模块使用

如需单独使用某个模块：

```bash
# 1. 爬取论文
python src/core/crawl_arxiv.py --categories cs.AI cs.CV --max-papers 100

# 2. 筛选论文
python src/core/select_.py --input-file arxiv_paper/papers.json

# 3. 生成总结
python src/core/generate_summary.py --input-file domain_paper/filtered_papers.json

# 4. 生成网页
python src/core/generate_webpage.py --input-file domain_paper/filtered_papers.json

# 5. 启动服务器
python src/core/serve_webpages.py --port 8080
```

## 配置说明

### 环境变量

在 `.env` 文件中配置：

```bash
# API配置
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
MODEL=glm-4.5-flash

# 可选：Jina API Token（用于获取完整论文内容）
JINA_API_TOKEN=your_jina_token_here
```

### `config.py` 的作用与配置项

`src/utils/config.py` 是项目的集中配置入口，用于：
- 统一读取 `.env` 中的敏感信息（API 密钥、基址、模型名等）
- 定义默认运行参数（如温度、超时、并发等）
- 约定目录结构与缓存策略
- 维护论文筛选 Prompt 模板与爬取策略

主要配置项一览（默认值见 `src/utils/config.py`）：
- **API 配置**：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MODEL`（从 `.env` 读取）
- **处理参数**：`TEMPERATURE`、`REQUEST_TIMEOUT`、`REQUEST_DELAY`
- **目录结构**：`ARXIV_PAPER_DIR`、`DOMAIN_PAPER_DIR`、`SUMMARY_DIR`、`WEBPAGES_DIR`
- **时间划分**：`DATE_FORMAT`、`ENABLE_TIME_BASED_STRUCTURE`
- **缓存设置**：`CACHE_DIR`、`ENABLE_CACHE`、`CACHE_EXPIRY_DAYS`
- **爬取限制**：`MAX_PAPERS_PER_CATEGORY`、`CRAWL_CATEGORIES`
- **并发控制**：`MAX_WORKERS`
- **筛选模板**：`PAPER_FILTER_PROMPT`
- **Jina API**：`JINA_API_TOKEN`、`JINA_MAX_REQUESTS_PER_MINUTE`、`JINA_MAX_RETRIES`、`JINA_BACKOFF_FACTOR`

覆盖与优先级建议：
- 与密钥/端点/模型相关的字段，优先在 `.env` 中配置（不建议直接改代码）。
- 与数量、类别、日期等运行期选项，优先使用命令行参数覆盖（见下方“使用示例”），其效果通常优先于代码默认值。
- 其他通用默认值（如并发、缓存、目录），可视需要修改 `src/utils/config.py` 后重跑。

典型自定义示例：
```bash
# 通过 .env 切换到自建网关与模型
OPENAI_BASE_URL=https://api.your-gateway.com/v1
MODEL=your-model-name

# 运行时临时指定类别与数量（覆盖 config 默认）
python papertools.py run --categories cs.AI cs.CL --max-papers-total 200
```

### 使用示例

```bash
# 全量处理（1000篇论文，默认）
python papertools.py run

# 快速测试（10篇论文）
python papertools.py run --mode quick

# 处理特定类别
python papertools.py run --categories cs.AI cs.CL

# 处理指定日期
python papertools.py run --date 2025-09-24

# 自定义论文数量
python papertools.py run --max-papers-total 500
```

## 项目结构

```
PaperTools/
├── papertools.py              # 主入口点
├── requirements.txt           # 依赖包
├── .env.example              # 环境变量模板
├── README.md                 # 中文文档
├── README_EN.md              # 英文文档
├── src/                      # 源代码目录
│   ├── core/                 # 核心功能模块
│   │   ├── pipeline.py       # 主流水线脚本
│   │   ├── crawl_arxiv.py    # 论文爬取
│   │   ├── select_.py        # 论文筛选
│   │   ├── generate_summary.py # 总结生成
│   │   ├── generate_webpage.py # 网页生成
│   │   └── serve_webpages.py # 本地服务器
│   ├── utils/                # 工具和配置
│   │   ├── config.py         # 配置文件
│   │   └── cache_manager.py  # 缓存管理
│   └── legacy/               # 旧版本/实验性代码
├── arxiv_paper/              # 爬取的原始论文
├── domain_paper/             # 筛选后的论文
├── summary/                  # 生成的总结
└── webpages/                 # 生成的网页
```

## 使用场景

**AI研究**
- 跟踪LLM和推理技术最新进展
- 研究智能体和多智能体系统
- 了解强化学习在AI中的应用
- 探索工具使用和进化算法

**学术研究**
- 快速了解特定领域最新进展
- 生成论文总结用于文献综述
- 创建优雅的论文展示页面
- 构建个人研究知识库

**教学辅助**
- 为学生提供AI前沿论文理解辅助
- 创建课程相关论文资源库
- 制作交互式学习材料
- 展示研究领域发展脉络

**团队协作**
- 分享团队关注的AI论文
- 统一的论文管理和展示
- 便于团队讨论和评论
- 跟踪竞品和相关工作

## 故障排除

### 环境检查
```bash
# 检查环境和依赖
python papertools.py check
```

### 常见问题

**API调用失败**
```bash
# 检查API密钥配置
cat .env
# 确保 OPENAI_API_KEY 已正确设置
```

**依赖缺失**
```bash
# 自动安装缺失的依赖
python papertools.py check
# 或手动安装
pip install -r requirements.txt
```

**网页服务器启动失败**
```bash
# 先生成网页内容
python papertools.py run
# 再启动服务器
python papertools.py serve
```

**缓存问题**
```bash
# 清理所有缓存文件
python papertools.py clean
```

### 调试模式
```bash
# 测试少量论文
python papertools.py run --max-papers-total 10

# 快速模式测试
python papertools.py run --mode quick
```

## 许可证

MIT License

## 贡献

欢迎贡献！请随时提交Issues和Pull Requests来改进这个项目。

## 支持

如有问题或建议，请通过GitHub Issues联系我们。

---

如果这个项目对你有帮助，请给个星标支持！