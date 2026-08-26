# PaperTools

[![CI](https://github.com/tsrigo/PaperTools/actions/workflows/ci.yml/badge.svg)](https://github.com/tsrigo/PaperTools/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

PaperTools 是一个面向日常研究阅读的 arXiv 论文处理系统。它从指定的 arXiv 分类获取论文，经过筛选、聚类和内容生成，最后输出一个可以直接浏览和部署的静态网站。

[查看在线页面](https://tsrigo.github.io/PaperTools/) · [报告问题](https://github.com/tsrigo/PaperTools/issues) · [参与开发](CONTRIBUTING.md)

> PaperTools 目前处于 Alpha 阶段。仓库内置的筛选规则主要关注 LLM Agent 及其演化研究，生成流程需要自行准备兼容 OpenAI API 格式的模型服务。

## 项目包含什么

- 从 `cs.AI`、`cs.CL` 和 `cs.LG` 等 arXiv 分类获取论文；
- 使用语言模型完成主题筛选、论文聚类和中文内容生成；
- 为每篇论文整理原始摘要、中文摘要、研究逻辑、方法、核心观点和研究价值；
- 按日期和主题生成每日概览及论文列表；
- 生成可以在本地浏览或部署到 GitHub Pages 的静态网站；
- 缓存已经完成的处理结果，并支持从中间阶段继续执行。

处理流程如下：

```text
arXiv → 主题筛选 → 聚类 → 论文解读与每日概览 → 静态网站
```

## 直接浏览已有内容

仓库已经包含生成后的网站。只想查看页面时，不需要配置 API：

```bash
git clone https://github.com/tsrigo/PaperTools.git
cd PaperTools
python -m http.server 8080 --directory webpages
```

然后访问 <http://localhost:8080>。也可以直接打开上方的在线页面。

## 生成自己的论文页面

### 1. 准备环境

需要 Python 3.10 或更高版本。建议在虚拟环境中安装：

```bash
git clone https://github.com/tsrigo/PaperTools.git
cd PaperTools

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .
```

如果希望优先在本地提取论文全文，可以安装相应的可选依赖：

```bash
python -m pip install -e ".[extract-all]"
```

不安装这些依赖时，系统可以使用远程文档提取服务作为后备方案。

### 2. 配置模型服务

```bash
cp .env.example .env
```

编辑 `.env`，填写自己的 API 地址、密钥和模型名。PaperTools 调用兼容 OpenAI API 格式的聊天补全接口。首次使用只需要关注以下三类信息：

- API 地址和密钥；
- 筛选与聚类使用的模型；
- 内容生成使用的模型。

不同服务商使用的模型 ID 和速率限制并不相同。`.env.example` 同时包含基础配置和本仓库维护任务使用的高级配置，请删除自己无法使用的服务商与模型占位值，只保留实际可用的配置。当前版本还没有把不同服务商的内容生成配置统一为一组通用字段，具体对应关系见[配置参考](docs/configuration.md)。请勿提交包含真实密钥的 `.env` 文件。

### 3. 检查环境

```bash
papertools check
```

该命令会检查基础依赖、配置文件和可用的文档提取方式，不会开始生成论文页面。

### 4. 先完成一次小规模运行

```bash
papertools run --mode quick --date YYYY-MM-DD --skip-serve
```

请将日期替换为 arXiv 有论文更新的日期。周末、节假日或没有符合筛选条件的日期不会生成空页面。

流水线成功完成后，启动本地网站：

```bash
papertools serve
```

命令会显示本地访问地址。完整运行可以使用：

```bash
papertools run --mode full --date YYYY-MM-DD --skip-serve
```

完整流程会产生多次模型调用和全文请求，实际耗时与候选论文数量、模型速度及接口限额有关。

## 调整论文范围

默认规则服务于本仓库当前维护的 LLM Agent 研究页面，并不是通用的全学科推荐器。生成自己的页面前，建议检查以下两处：

- arXiv 分类和运行规模位于 [`src/utils/config.py`](src/utils/config.py)；
- 主题筛选要求位于同一文件的 `PAPER_FILTER_PROMPT`。

命令行也可以临时指定分类：

```bash
papertools run \
  --date YYYY-MM-DD \
  --categories cs.AI cs.CL \
  --max-papers-total 100 \
  --skip-serve
```

修改筛选范围后，应先使用 `--mode quick` 检查入选论文数量和内容，再执行完整生成。

## 输出目录

| 目录 | 内容 |
| --- | --- |
| `arxiv_paper/` | 从 arXiv 获取的原始论文元数据 |
| `domain_paper/` | 筛选结果和聚类结果 |
| `summary/` | 论文解读与每日概览 |
| `webpages/` | 可以直接浏览和部署的网站 |
| `cache/` | 可复用的提取和生成缓存 |

这些阶段会依次检查输入。生成失败、字段缺失或内容不完整时，流程会停止，不会把中间结果当作可发布页面。

如果某个阶段已经成功，可以从后续阶段继续执行：

```bash
papertools run --start-from cluster --date YYYY-MM-DD --skip-serve
papertools run --start-from summary --date YYYY-MM-DD --skip-serve
papertools run --start-from unified --skip-serve
```

更多阶段说明和输入输出格式见[流水线文档](docs/pipeline.md)。

## 部署与定时更新

生成的网站位于 `webpages/`，可以部署到任何静态网站托管服务。本仓库提供 GitHub Pages 工作流，也提供带有工作区检查、运行锁和发布校验的每日更新脚本。

定时发布涉及拉取最新代码、处理接口失败、验证页面内容和推送仓库，不建议直接把 `papertools run` 写入生产环境的 cron。完整步骤见[部署指南](docs/deployment.md)。发布数据必须通过以下检查：

```bash
python scripts/validate_published_payloads.py --webpages-dir webpages
```

校验失败的日期不应提交或部署。详细规则见[发布质量门禁](docs/QUALITY_GATES.md)。

## 开发

安装开发依赖并运行本地检查：

```bash
python -m pip install -e ".[dev]"
make test
make lint
make security
```

`make ci` 可以执行主要的 CI 检查。提交修改前请阅读[贡献指南](CONTRIBUTING.md)。安全问题请按照[安全策略](SECURITY.md)中的方式报告。

## 文档

- [配置参考](docs/configuration.md)
- [流水线说明](docs/pipeline.md)
- [部署指南](docs/deployment.md)
- [发布质量门禁](docs/QUALITY_GATES.md)
- [贡献指南](CONTRIBUTING.md)
- [行为准则](CODE_OF_CONDUCT.md)

## License

PaperTools 使用 [MIT License](LICENSE)。
