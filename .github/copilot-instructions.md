# PaperTools AI 编程指南

PaperTools 是一个学术论文自动化处理流水线，使用 LLM API 进行智能论文筛选和总结。

## 核心架构模式

### 流水线设计 (Pipeline Pattern)
主流程: `crawl → filter → summarize → generate webpages → serve`
- **主入口**: `papertools.py` - 统一 CLI 接口，处理依赖检查和子模块调度
- **流水线核心**: `src/core/pipeline.py` - 协调所有步骤，支持断点续传和步骤跳过
- **模块化设计**: 每个步骤独立可运行，通过 JSON 文件传递数据

### 配置管理模式
- **集中配置**: `src/utils/config.py` 读取 `.env` 文件，定义所有参数
- **优先级**: 命令行参数 > 环境变量 > 代码默认值
- **关键配置**: API密钥、目录结构、处理限制、缓存策略

### 缓存架构
- **多层缓存**: `src/utils/cache_manager.py` 管理论文内容、总结、网页缓存
- **键值生成**: 使用 MD5 哈希(URL/内容) 作为缓存键
- **过期机制**: 基于文件时间戳的30天过期策略

## 开发工作流程

### 运行模式
```bash
# 完整流程 (推荐用于新功能测试)
python papertools.py run --mode quick  # 10篇论文快速测试
python papertools.py run --mode full   # 1000篇论文完整处理

# 独立模块开发/调试
python src/core/crawl_arxiv.py --categories cs.AI --max-papers 10
python src/core/select_.py --input-file arxiv_paper/papers.json
```

### 断点续传机制
- 每个步骤检查现有输出文件，支持从任意步骤重启
- 使用 `--start-from` 参数跳过前序步骤
- 论文筛选模块自动检测已处理的 arXiv ID

### 目录约定
```
arxiv_paper/     # 爬取原始数据 (JSON格式)  
domain_paper/    # 筛选后数据 (含筛选理由)
summary/         # 总结数据 (添加summary2字段)
webpages/        # 生成HTML网页 (支持交互功能)
cache/           # 三级缓存 papers/summaries/webpages/
```

## 项目特定模式

### 多线程处理模式
- **并发控制**: `MAX_WORKERS` 配置线程数 (默认10)
- **包装函数**: 所有并发操作使用 `*_wrapper` 函数处理异常和结果汇总
- **进度跟踪**: 使用 `tqdm` 和自定义 `ProgressTracker` 类

### LLM 集成模式
- **统一客户端**: OpenAI 兼容接口，支持自定义 base_url
- **Prompt 模板**: `config.py` 中的 `PAPER_FILTER_PROMPT` 定义筛选逻辑
- **速率限制**: Jina API 限制每分钟20次请求，实现退避重试

### 数据流转模式
论文数据在各阶段逐步增强:
1. `crawl`: 基础字段 (title, summary, arxiv_id, link, date)
2. `filter`: 添加 `filter_reason` 字段
3. `summary`: 添加 `summary2` 字段 (中文总结)
4. `webpage`: 转换为交互式 HTML

### Web服务架构
- **自定义处理器**: `CustomHTTPRequestHandler` 扩展标准HTTP服务器
- **状态持久化**: 用户操作(已读/删除)保存在 `.user_state.json`
- **API接口**: `/api/state`, `/api/toggle-read`, `/api/delete` 支持前端交互

## 调试技巧

### 常见问题排查
- **API 失败**: 检查 `.env` 配置和网络连接
- **依赖缺失**: 运行 `python papertools.py check`
- **缓存问题**: 使用 `python papertools.py clean` 清理
- **数据不一致**: 检查 JSON 文件格式和字段完整性

### 日志和输出
- 所有核心模块支持详细日志输出
- 使用带时间戳的 `ProgressTracker` 跟踪执行进度
- 异常处理包含具体的错误上下文

### 测试策略  
- 优先使用 `--mode quick` 进行快速验证
- 使用 `--skip-*` 参数测试单个组件
- 检查各阶段输出文件的数据完整性

当修改核心逻辑时，始终先用小数据集验证，确认数据流转和缓存机制正常工作。