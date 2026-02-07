# PaperTools

[English](README_EN.md) | 中文

PaperTools 是一个完整的学术论文处理流水线，提供自动化的论文爬取、智能筛选、总结生成和网页生成功能。

## 功能特点

- **自动爬取**: 从arXiv等学术平台自动爬取最新论文
- **LLM智能筛选**: 使用大语言模型按研究领域智能筛选论文
- **自动总结**: 基于jinja.ai获取完整论文内容，生成高质量中文总结
- **灵感溯源**: 深度分析论文创新思路的演进过程，从挑战识别到解决方案的完整逻辑链
- **网页生成**: 将论文转换为现代化设计的交互式HTML网页，支持可折叠内容展示
- **本地部署**: 一键启动本地服务器，便于浏览和分享
- **交互功能**: 支持论文收藏、已读状态跟踪和删除，状态持久化保存

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API 密钥
cp .env.example .env
# 编辑 .env，填入你的 OPENAI_API_KEY、OPENAI_BASE_URL、MODEL

# 3. 运行
python papertools.py run --mode quick   # 快速测试（10篇）
python papertools.py run                # 完整运行
```

## 常用命令

```bash
python papertools.py run [选项]         # 运行流水线
  --mode {quick,full}                   #   处理模式
  --date YYYY-MM-DD                     #   指定日期
  --categories cs.AI cs.CL              #   指定类别
  --max-papers-total N                  #   自定义数量

python papertools.py serve              # 启动本地服务器
python papertools.py check              # 检查环境依赖
python papertools.py clean              # 清理缓存
python papertools.py --help             # 查看帮助
```

<details>
<summary>高级用法：独立模块</summary>

```bash
python src/core/crawl_arxiv.py --categories cs.AI cs.CV --max-papers 100
python src/core/paper_filter.py --input-file arxiv_paper/papers.json
python src/core/generate_summary.py --input-file domain_paper/filtered_papers.json
python src/core/generate_unified_index.py
python src/core/serve_webpages.py --port 8080
```

</details>

## 🚀 部署到 GitHub Pages

您可以将生成的论文网站免费发布到 GitHub Pages，方便公开访问和分享。推荐使用 Fork + GitHub Actions 的方式实现全自动部署。

### 步骤 1: Fork 本仓库
点击本页面右上角的 **Fork** 按钮，将此项目复制到您自己的 GitHub 账户下。

### 步骤 2: 配置 Pages 和 Actions 权限

1.  **配置 Pages 源**:
    *   在您 Fork 后的仓库页面，进入 `Settings` > `Pages`。
    *   在 `Build and deployment` 下的 `Source` 选项中，选择 `GitHub Actions`。

2.  **配置 Actions 权限 (关键步骤)**:
    *   在仓库页面，进入 `Settings` > `Actions` > `General`。
    *   滚动到 `Workflow permissions` 部分。
    *   选择 `Read and write permissions`。
    *   勾选 `Allow GitHub Actions to create and approve pull requests`。
    *   点击 `Save`。

    *此设置为 Actions 提供了将构建好的网站文件推送到 `gh-pages` 分支所需的权限。*

### 步骤 3: 触发自动部署并访问
- **首次部署**: 完成上述配置后，Actions 会自动运行一次（或手动在 `Actions` 标签页触发 `Deploy to GitHub Pages`），等待几分钟即可。
- **更新网站**: 如果您想定制筛选规则，可以修改 `src/utils/config.py` 中的 `PAPER_FILTER_PROMPT`，然后将更改推送到您仓库的 `main` 分支。GitHub Actions 会自动重新生成和部署网站。

部署成功后，您的网站将在 `https://<您的用户名>.github.io/<仓库名>/` 上可用。

### 备选方案：手动部署
如果您不想使用 Actions，也可以在本地生成网站后，将 `webpages` 目录的内容手动上传到任何静态网站托管服务。

## 配置说明
项目的核心配置集中在两个文件：`.env` 用于存放敏感信息和环境特定变量，`src/utils/config.py` 用于定义程序的默认行为和参数。

### 环境变量 (`.env`)

在项目根目录创建一个 `.env` 文件（可从 `.env.example` 复制）来配置以下内容：

```bash
# API配置 (必需)
OPENAI_API_KEY=your_api_key_here         # 你的大模型API密钥
OPENAI_BASE_URL=https://api.example.com/v1 # API的访问地址
MODEL=your_model_name                    # 使用的模型名称

# Jina API配置 (可选，用于全文阅读)
JINA_API_TOKEN=your_jina_token_here      # Jina Reader API的令牌
```

### 核心配置文件 (`src/utils/config.py`)

此文件定义了流水线的各种默认行为。你可以根据自己的需求进行定制。

#### 主要配置参数

-   **API与请求相关**
    -   `TEMPERATURE`: 模型生成内容的温度，越低结果越稳定。
    -   `REQUEST_TIMEOUT`: API请求超时时间（秒）。
    -   `REQUEST_DELAY`: 两次请求之间的延迟（秒），用于避免速率限制。

-   **目录配置**
    -   `ARXIV_PAPER_DIR`, `DOMAIN_PAPER_DIR`, `SUMMARY_DIR`, `WEBPAGES_DIR`: 定义了流水线各个阶段产出文件的存储目录。

-   **缓存配置**
    -   `ENABLE_CACHE`: 是否启用缓存，建议保持 `True` 以节省时间和API调用成本。
    -   `CACHE_EXPIRY_DAYS`: 缓存的有效天数。

-   **爬取与处理数量**
    -   `CRAWL_CATEGORIES`: 默认爬取的arXiv类别。
    -   `MAX_PAPERS_PER_CATEGORY`: 每个类别最多爬取的论文数。
    -   `MAX_PAPERS_TOTAL_QUICK`: `quick` 模式下处理的总论文数。
    -   `MAX_PAPERS_TOTAL_FULL`: `full` 模式下处理的总论文数。
    -   `MAX_PAPERS_TOTAL_DEFAULT`: 直接运行 `pipeline.py` 时的默认处理数量。

-   **并发控制**
    -   `MAX_WORKERS`: 全局最大并发线程数，适用于爬取、筛选和总结等多个步骤。

#### 重点：定制你的论文筛选标准 (`PAPER_FILTER_PROMPT`)

`PAPER_FILTER_PROMPT` 是一个Prompt模板，用于指导大语言模型判断一篇论文是否符合你的研究兴趣。

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
│   │   ├── paper_filter.py   # 论文筛选
│   │   ├── generate_summary.py # 总结和灵感溯源生成
│   │   ├── generate_unified_index.py # 统一网页生成
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

## 贡献

欢迎贡献！请随时提交Issues和Pull Requests来改进这个项目。

## 支持

如有问题或建议，请通过GitHub Issues联系我们。

---

如果这个项目对你有帮助，请星标支持！
