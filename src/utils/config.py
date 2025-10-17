"""
配置文件 - 统一管理API密钥和模型配置
Configuration file for API keys and model settings
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# API 配置 - 从.env文件中读取
API_KEY = os.getenv("OPENAI_API_KEY", "your_api_key_here")  
BASE_URL = os.getenv("OPENAI_BASE_URL")
MODEL = os.getenv("MODEL")

# 处理参数
TEMPERATURE = 0.1
REQUEST_TIMEOUT = 300  # 增加到5分钟
REQUEST_DELAY = 3  # 增加请求间隔

# 目录配置
ARXIV_PAPER_DIR = "arxiv_paper"
DOMAIN_PAPER_DIR = "domain_paper" 
SUMMARY_DIR = "summary"
WEBPAGES_DIR = "webpages"

# 时间划分配置
DATE_FORMAT = "%Y-%m-%d"  # 日期格式
ENABLE_TIME_BASED_STRUCTURE = True  # 是否启用按时间划分的目录结构

# 缓存配置
CACHE_DIR = "cache"
ENABLE_CACHE = True  # 是否启用缓存机制
CACHE_EXPIRY_DAYS = 30  # 缓存过期天数

# 爬取配置
MAX_PAPERS_PER_CATEGORY = 5000  # 增加到5000，获取更多论文
CRAWL_CATEGORIES = ['cs.AI', 'cs.CL', 'cs.LG', 'cs.MA']
MAX_PAPERS_TOTAL_QUICK = 10
MAX_PAPERS_TOTAL_FULL = 10000
MAX_PAPERS_TOTAL_DEFAULT = 100

# 多线程配置
MAX_WORKERS = 10  # 默认线程数

# 论文筛选Prompt模板
PAPER_FILTER_PROMPT = """你是一位顶尖的人工智能研究员，正在为一项关于 "LLM智能体及其演化"（LLM-based Agents and their Evolution） 的研究课题筛选前沿论文。请你严格、精准地判断这篇论文是否符合我的研究范围。

我的核心目标: 筛选出那些核心贡献在于 构建、改进或演化 LLM智能体的论文。我的研究焦点是 Agentic AI，特别是以下三个方向及其子方向：

1. 单智能体 (Agentic): 智能体的规划、记忆、工具使用、自我反思等。
2. 多智能体 (Multi-Agent): 智能体间的协作、通信、博弈、社会学习等。
3. 自我演化 (Self-Evolving): 智能体通过经验、反思或环境反馈进行自我完善和迭代。

筛选标准 (请按顺序和优先级进行思考):

第一步：核心判断——这篇论文的本质是什么？

- 保留 (Keep): 如果论文的核心是关于构建LLM智能体（Agentic LLM）、多智能体系统（Multi-Agent Systems） 或 自我演化（Self-Evolving） 的方法论或新框架。
- 排除 (Exclude):
  1. 非演化型应用 (Non-Evolving Applications): 如果论文只是将LLM（或一个已有的Agentic / Multi-Agent框架）作为工具应用到特定领域去解决该领域的问题（例如生物、医疗、金融、法律、机器人控制等）。
  2. 非Agentic的推理: 如果论文只是关于提高LLM的基础推理能力（如新的CoT变体、逻辑、数学），但其方法不涉及智能体自主规划、工具使用或自我演化框架。
  3. 基础设施: 排除主要关注模型基础设施（Infrastructure）、部署优化、硬件加速的研究。

第二步：正面指标——论文是否包含我的核心关注点？（满足越多，越可能相关）

- 核心范式: `Agentic AI`, `LLM-based Agents`, `Multi-Agent Systems (MAS)`, `Self-Evolving`, `Evolutionary Algorithms`
- 智能体能力: `Planning`, `Tool Use / Tool Augmentation`, `Memory`, `Self-Correction`, `Self-Reflection`, `ReAct`
- 多智能体: `Collaboration`, `Communication`, `Negotiation`, `Social Learning`, `Agent Society`
- 演化机制: `Self-Improvement`, `Self-Refine`, `Generational Evolution`, `Iterative Improvement`

第三步：排除标准——是否为我的研究焦点之外？

- 安全与对齐: 只要论文的主要贡献是关于 `Safety`, `Security`, `Interpretability` (可解释性), `Explainability (XAI)`, `Alignment` (对齐), `Watermarking` (水印), 或 `Hallucination` (幻觉)，一律排除。
- 多模态与视觉: `Vision`, `Vision-Language`, `MLLMs`, `VLMs`, `Video Understanding`, `3D Vision`, `Diffusion Models` (除非它们被用作智能体感知环境的工具，而不是研究的核心)。

第四步：处理特殊和模糊情况 (核心规则)

1. 推理/规划 (Reasoning/Planning):
   - 保留: 如果论文是关于智能体如何进行规划或在复杂任务中进行多步推理（如 ReAct、ToT 或新的Agentic框架）。
   - 排除: 如果只是关于提高LLM本身基础Token预测的数学或逻辑能力（如新的数据集、非Agentic的微调方法）。
2. 自我演化的应用 (Self-Evolving Applications):
   - 保留 (例外): 按照你的要求，如果论文的核心是提出一种新的“自我演化”机制，即使它被应用在特定领域（如“用于化学实验的自我演化智能体”），也应该保留。
   - 排除: 如果该应用不涉及自我演化机制（见第一步的排除规则）。

第五步：最终决策 综合以上分析，请给出你的最终判断。

---
论文标题: {title}
论文摘要: {summary}
---

请严格按照以下格式回答:
结果: [True/False]
理由: [请结合上述筛选标准，用中文详细说明你的判断过程和核心依据。明确指出论文的核心贡献，并解释它为何符合或不符合我的研究目标。]"""

# Jina API配置
JINA_MAX_REQUESTS_PER_MINUTE = 20  # Jina API速率限制：20 RPM
JINA_MAX_RETRIES = 3  # Jina API最大重试次数
JINA_BACKOFF_FACTOR = 2.0  # 重试退避因子
JINA_API_TOKEN = os.getenv("JINA_API_TOKEN")  # 可选：为r.jina.ai添加Bearer Token
