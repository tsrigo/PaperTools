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
PAPER_FILTER_PROMPT = """你是一位顶尖的人工智能研究员，正在为一项关于"大语言模型通用推理能力"的研究课题筛选前沿论文。请你严格、精准地判断这篇论文是否符合我的研究范围。

我的核心目标:
筛选出那些致力于提高大语言模型（LLM）本身的『通用推理能力』的论文。

筛选标准 (请按顺序和优先级进行思考):

第一步：核心判断——这篇论文的本质是什么？
- 保留: 如果论文的核心是关于改进LLM的基础能力、提出新的训练范式、增强其逻辑、数学、规划、多步推理等通用能力。例如，关于思维链(CoT)、强化学习优化、智能体协作框架、工具使用、自我进化等方法论的研究。
- 排除: 如果论文的核心是将LLM作为一种工具，应用到某个特定领域去解决该领域的问题。这包括但不限于生物、医疗、化学、金融、法律、社会学、机器人控制、自动驾驶等。同时，也要排除主要关注模型基础设施（Infrastructure）、部署优化、硬件加速的研究。

第二步：正面指标——论文是否包含以下主题？（满足越多，越可能相关）
- 核心概念: Large language models, LLMs
- 能力方向: reasoning (尤其是 math reasoning, logical reasoning), planning, problem-solving
- 训练方法: reinforcement learning (RLHF, RL), evolution, self-evolve
- 新兴范式: llm-based agents, multi-agent systems, tool use, deep research

第三步：排除标准——论文是否主要聚焦于以下领域？（只要主要焦点是其一，就应排除）
- 多模态与视觉: Vision, Vision-Language, MLLMs, VLMs, Video Understanding, 3D Vision, Reconstruction, Diffusion Models
- 特定应用领域: Medical, Chemical, Biological, Sociological, Robotic, Robot Control, Domain Specific Applications
- 模型可靠性（应用层面）: Watermarking, Safety, Security 

第四步：处理特殊和模糊情况
- 智能体/工具使用: 如果是提出一种通用的智能体协作框架或工具使用方法来增强LLM的通用问题解决能力，应该保留。如果只是将智能体/工具应用在特定领域（如"用于化学实验自动化的智能体"），应该排除。
- 幻觉/可解释性/安全: 如果论文提出一种新方法来减少幻觉、增强模型内在的可解释性或安全性，从而提升模型的通用可靠性和推理质量，应该保留。如果只是对这些现象的社会学研究或应用层面的讨论，应该排除。

第五步：最终决策
综合以上分析，请给出你的最终判断。

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
