"""
配置文件 - 统一管理API密钥和模型配置
Configuration file for API keys and model settings
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# API 配置 - 从.env文件中读取
API_KEY = os.getenv("OPENAI_API_KEY")  
BASE_URL = os.getenv("OPENAI_BASE_URL")
MODEL = os.getenv("MODEL")

# 处理参数
TEMPERATURE = 0.1
REQUEST_TIMEOUT = 300  # 增加到5分钟
REQUEST_DELAY = 5  # 增加请求间隔，避免524错误

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
MAX_WORKERS = 2  # 降低线程数，避免并发过多导致524错误

# 论文筛选Prompt模板（精简版，避免API超时）
PAPER_FILTER_PROMPT = """判断论文是否关于 LLM智能体（Agentic AI）。

研究范围：
1. 单智能体：规划、记忆、工具使用、自我反思
2. 多智能体：协作、通信、博弈
3. 自我演化：通过反馈自我完善

排除：
- 纯应用（医疗/金融/法律等领域应用）
- 纯推理（CoT、数学推理，不涉及智能体）
- 安全/对齐/可解释性
- 多模态/视觉/图神经网络
- 基础设施/部署优化

论文标题: {title}
论文摘要: {summary}

回答格式：
结果: [True/False]
理由: [简要说明]"""

# Jina API配置
JINA_MAX_REQUESTS_PER_MINUTE = 20  # Jina API速率限制：20 RPM
JINA_MAX_RETRIES = 3  # Jina API最大重试次数
JINA_BACKOFF_FACTOR = 2.0  # 重试退避因子
JINA_API_TOKEN = os.getenv("JINA_API_TOKEN")  # 可选：为r.jina.ai添加Bearer Token
