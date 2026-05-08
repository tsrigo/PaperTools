"""
配置文件 - 统一管理API密钥和模型配置
Configuration file for API keys and model settings
"""

import os
import warnings
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def _get_env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _get_env_int(name: str, default: int, minimum: int = None) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except ValueError:
        warnings.warn(f"{name}={value!r} 不是合法整数，回退到默认值 {default}", RuntimeWarning)
        return default
    if minimum is not None and parsed < minimum:
        warnings.warn(f"{name}={value!r} 小于允许下限 {minimum}，回退到默认值 {default}", RuntimeWarning)
        return default
    return parsed


def _get_env_float(name: str, default: float, minimum: float = None) -> float:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        parsed = float(value)
    except ValueError:
        warnings.warn(f"{name}={value!r} 不是合法数字，回退到默认值 {default}", RuntimeWarning)
        return default
    if minimum is not None and parsed < minimum:
        warnings.warn(f"{name}={value!r} 小于允许下限 {minimum}，回退到默认值 {default}", RuntimeWarning)
        return default
    return parsed


def _get_env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.lower() in ("1", "true", "yes", "on")


def _normalize_model_alias(model: str) -> str:
    aliases = {
        "minimax-m2": "qwen",
        "minimax-m2.5": "qwen",
        "minimax-m2.7": "qwen",
        "minimax/minimax-m2": "qwen",
        "minimax/minimax-m2.5": "qwen",
        "minimax/minimax-m2.7": "qwen",
        "deepseek-reasoner": "deepseek-chat",
        "deepseek/deepseek-chat": "deepseek-chat",
        "deepseek/deepseek-r1": "deepseek-chat",
        "deepseek-r1": "deepseek-chat",
    }
    return aliases.get(model, model)

# API 配置 - 从.env文件中读取
API_KEY = _get_env_str("OPENAI_API_KEY")
BASE_URL = _get_env_str("OPENAI_BASE_URL")
MODEL = _get_env_str("MODEL")
FILTER_MODEL = _normalize_model_alias(
    _get_env_str("FILTER_MODEL", "qwen")
)  # 筛选用轻量模型
CLUSTER_API_KEY = _get_env_str("CLUSTER_OPENAI_API_KEY", API_KEY)
CLUSTER_BASE_URL = _get_env_str("CLUSTER_OPENAI_BASE_URL", BASE_URL)
CLUSTER_MODEL = _normalize_model_alias(_get_env_str("CLUSTER_MODEL", FILTER_MODEL or MODEL))
DEFAULT_SUMMARY_BASE_URL = "https://api-inference.modelscope.cn/v1"
DEFAULT_SUMMARY_MODEL = "minimax"
DEFAULT_SUMMARY_MODEL_CHAIN = (
    "prism:gpt-5.5,"
    "sjtu:minimax,"
    "sjtu:glm,"
    "sjtu:qwen,"
    "sjtu:deepseek-reasoner,"
    "sjtu:deepseek-chat"
)
SUMMARY_API_KEY = _get_env_str("SUMMARY_OPENAI_API_KEY", API_KEY)
SUMMARY_BASE_URL = _get_env_str("SUMMARY_OPENAI_BASE_URL", DEFAULT_SUMMARY_BASE_URL)
SUMMARY_MODEL = _get_env_str("SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL)
SUMMARY_MODEL_CHAIN = _get_env_str("SUMMARY_MODEL_CHAIN", DEFAULT_SUMMARY_MODEL_CHAIN)
SUMMARY_SJTU_API_KEY = _get_env_str(
    "SUMMARY_SJTU_OPENAI_API_KEY",
    _get_env_str("SJTU_OPENAI_API_KEY", API_KEY),
)
SUMMARY_SJTU_BASE_URL = _get_env_str(
    "SUMMARY_SJTU_OPENAI_BASE_URL",
    _get_env_str("SJTU_OPENAI_BASE_URL", "https://models.sjtu.edu.cn/api/v1/"),
)
SUMMARY_PRISM_API_KEY = _get_env_str(
    "SUMMARY_PRISM_OPENAI_API_KEY",
    _get_env_str("PRISM_OPENAI_API_KEY", ""),
)
SUMMARY_PRISM_BASE_URL = _get_env_str("SUMMARY_PRISM_OPENAI_BASE_URL", "https://ai.prism.uno/v1")
SUMMARY_PRISM_RPM = _get_env_int("SUMMARY_PRISM_RPM", 5, minimum=1)
SUMMARY_PRISM_REASONING_EFFORT = _get_env_str("SUMMARY_PRISM_REASONING_EFFORT", "xhigh")
SUMMARY_PRISM_WINDOW_SECONDS = _get_env_int("SUMMARY_PRISM_WINDOW_SECONDS", 300, minimum=60)
SUMMARY_PRISM_WINDOW_SAFETY_REQUESTS = _get_env_int("SUMMARY_PRISM_WINDOW_SAFETY_REQUESTS", 1, minimum=0)
SUMMARY_PRISM_429_COOLDOWN_SECONDS = _get_env_int("SUMMARY_PRISM_429_COOLDOWN_SECONDS", 300, minimum=0)
SUMMARY_CONTENT_CHAR_LIMIT = _get_env_int("SUMMARY_CONTENT_CHAR_LIMIT", 200000, minimum=10000)

# ReviewGrounder 审稿配置
REVIEWGROUNDER_ENABLED = _get_env_bool("REVIEWGROUNDER_ENABLED", True)
REVIEWGROUNDER_PATH = _get_env_str("REVIEWGROUNDER_PATH", "vendor/ReviewGrounder")
REVIEWGROUNDER_API_KEY = _get_env_str(
    "REVIEWGROUNDER_API_KEY",
    _get_env_str("SUMMARY_PRISM_OPENAI_API_KEY", _get_env_str("OPENAI_API_KEY")),
)
REVIEWGROUNDER_BASE_URL = _get_env_str(
    "REVIEWGROUNDER_BASE_URL",
    _get_env_str(
        "SUMMARY_PRISM_OPENAI_BASE_URL",
        _get_env_str("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    ),
)
REVIEWGROUNDER_MODEL = _get_env_str("REVIEWGROUNDER_MODEL", "gpt-5.5")
REVIEWGROUNDER_REASONING_EFFORT = _get_env_str("REVIEWGROUNDER_REASONING_EFFORT", "xhigh")
REVIEWGROUNDER_MAX_OUTPUT_TOKENS = _get_env_int("REVIEWGROUNDER_MAX_OUTPUT_TOKENS", 16384, minimum=1024)
REVIEWGROUNDER_MAX_RELATED_PAPERS = _get_env_int("REVIEWGROUNDER_MAX_RELATED_PAPERS", 1, minimum=0)
REVIEWGROUNDER_ENABLE_WEB_FALLBACK = _get_env_bool("REVIEWGROUNDER_ENABLE_WEB_FALLBACK", True)
REVIEWGROUNDER_REVIEW_FORMAT = _get_env_str("REVIEWGROUNDER_REVIEW_FORMAT", "ai_researcher")
REVIEWGROUNDER_REFINER_REVIEW_FORMAT = _get_env_str("REVIEWGROUNDER_REFINER_REVIEW_FORMAT", "detailed_gradio")
REVIEWGROUNDER_TIMEOUT_SECONDS = _get_env_int("REVIEWGROUNDER_TIMEOUT_SECONDS", 180, minimum=10)
REVIEWGROUNDER_RPM = _get_env_int("REVIEWGROUNDER_RPM", 5, minimum=0)
REVIEWGROUNDER_MAX_PARALLEL_SUMMARIES = _get_env_int("REVIEWGROUNDER_MAX_PARALLEL_SUMMARIES", 1, minimum=1)
REVIEWGROUNDER_MAX_LLM_CALLS = _get_env_int("REVIEWGROUNDER_MAX_LLM_CALLS", 0, minimum=0)
REVIEWGROUNDER_VERBOSE = _get_env_bool("REVIEWGROUNDER_VERBOSE", False)
REVIEWGROUNDER_JSON_TOOL_RETRIES = _get_env_int("REVIEWGROUNDER_JSON_TOOL_RETRIES", 1, minimum=1)

# Prestige 筛选配置
PRESTIGE_ENABLED = _get_env_bool("PRESTIGE_ENABLED", True)
PRESTIGE_CONTEXT_CHARS = _get_env_int("PRESTIGE_CONTEXT_CHARS", 16000, minimum=1000)
PRESTIGE_RULE_VERSION = _get_env_str("PRESTIGE_RULE_VERSION", "hybrid_v1")

# Webhook notification (optional)
WEBHOOK_URL = _get_env_str("WEBHOOK_URL", "")

# 处理参数
TEMPERATURE = _get_env_float("TEMPERATURE", 0.1, minimum=0.0)
REQUEST_TIMEOUT = _get_env_int("REQUEST_TIMEOUT", 300, minimum=1)  # 5分钟超时
REQUEST_DELAY = _get_env_float("REQUEST_DELAY", 0.8, minimum=0.0)  # 请求间隔（秒），100 RPM ≈ 0.6s/req，留余量

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
ENABLE_CACHE = _get_env_bool("ENABLE_CACHE", True)  # 是否启用缓存机制
CACHE_EXPIRY_DAYS = _get_env_int("CACHE_EXPIRY_DAYS", 30, minimum=1)  # 缓存过期天数

# 爬取配置
MAX_PAPERS_PER_CATEGORY = _get_env_int("MAX_PAPERS_PER_CATEGORY", 5000, minimum=1)  # 增加到5000，获取更多论文
CRAWL_CATEGORIES = ['cs.AI', 'cs.CL', 'cs.LG']
MAX_PAPERS_TOTAL_QUICK = 10
MAX_PAPERS_TOTAL_FULL = 10000
MAX_PAPERS_TOTAL_DEFAULT = 0

# 多线程配置
MAX_WORKERS = _get_env_int("MAX_WORKERS", 20, minimum=1)  # 并发线程数，100 RPM 限额下安全运行
FILTER_MAX_WORKERS = _get_env_int("FILTER_MAX_WORKERS", min(MAX_WORKERS, 5), minimum=1)
SUMMARY_MAX_WORKERS = _get_env_int("SUMMARY_MAX_WORKERS", 5, minimum=1)

# 论文筛选Prompt模板
PAPER_FILTER_PROMPT = """你是一位顶尖的人工智能研究员，正在为一项关于 "LLM智能体及其演化"（LLM-based Agents and their Evolution） 的研究课题筛选前沿论文。请你严格、精准地判断这篇论文是否符合我的研究范围。

我的核心目标: 筛选出那些核心贡献在于 构建、改进或演化 LLM智能体的论文。我的研究焦点是 Agentic AI，特别是以下三个方向及其子方向：

1. 单智能体 (Agentic): 智能体的规划、记忆、工具使用、自我反思等。
2. 多智能体 (Multi-Agent): 多智能体系统中新的协作机制、博弈策略或社会学习方法。**但排除**那些仅讨论多智能体拓扑结构（topology）、通信协议（communication protocol）、消息路由（message routing）、智能体排列编排（orchestration）的论文——这些属于系统工程而非我的研究重点。
3. 自我演化 (Self-Evolving): 智能体通过经验、反思或环境反馈进行自我完善和迭代。

筛选标准 (请按顺序和优先级进行思考):

第一步：核心判断——这篇论文的本质是什么？

- 保留 (Keep): 如果论文的核心是关于构建LLM智能体（Agentic LLM）、多智能体系统（Multi-Agent Systems） 或 自我演化（Self-Evolving） 的方法论或新框架。
- 保留 (Keep): 如果论文研究 coding-agent 的 harness / scaffold / runtime / tool middleware / system prompt / execution environment，并且核心贡献是让这些智能体运行组件通过轨迹、反馈、观测或评估结果自动改进、演化或自适应优化。这里的 harness/scaffold 是智能体能力实现的一部分，不应简单归为普通基础设施。
- 排除 (Exclude):
  1. 非演化型应用 (Non-Evolving Applications): 如果论文只是将LLM（或一个已有的Agentic / Multi-Agent框架）作为工具应用到特定领域去解决该领域的问题（例如生物、医疗、金融、法律、机器人控制等）。
  2. 非Agentic的推理: 如果论文只是关于提高LLM的基础推理能力（如新的CoT变体、逻辑、数学），但其方法不涉及智能体自主规划、工具使用或自我演化框架。
  3. 基础设施: 排除主要关注模型基础设施（Infrastructure）、部署优化、硬件加速的研究；但不要因此排除 coding-agent harness/scaffold/runtime 的自动演化论文。

第二步：正面指标——论文是否包含我的核心关注点？（满足越多，越可能相关）

- 核心范式: `Agentic AI`, `LLM-based Agents`, `Multi-Agent Systems (MAS)`, `Self-Evolving`, `Evolutionary Algorithms`
- 智能体能力: `Planning`, `Tool Use / Tool Augmentation`, `Memory`, `Self-Correction`, `Self-Reflection`, `ReAct`,  `Collaboration`, `Agent Harness`, `Agent Scaffold`, `Agent Runtime`
- 演化机制: `Self-Improvement`, `Self-Refine`, `Generational Evolution`, `Iterative Improvement`

第三步：排除标准——是否为我的研究焦点之外？

- 安全相关（双向排除）: 无论是 "AI for Security"（用AI/LLM解决安全问题，如漏洞检测、恶意代码分析、网络安全）还是 "Security for AI"（针对AI系统的安全防护，如对抗攻击、jailbreak防御、模型安全评估），一律排除。同样排除 `Safety`, `Alignment` (对齐), `Interpretability` (可解释性), `Explainability (XAI)`, `Watermarking` (水印), `Hallucination` (幻觉) 相关论文。
- 多模态与视觉: `Vision`, `Vision-Language`, `MLLMs`, `VLMs`, `Video Understanding`, `3D Vision`, `Diffusion Models` (除非它们被用作智能体感知环境的工具，而不是研究的核心)。
- 图相关技术: 涉及 `Knowledge Graph` (知识图谱)、`Graph Neural Network` (图神经网络)、`Graph Reasoning` (图推理)、`Graph RAG` 等图结构相关技术的论文，一律排除。
- 多智能体拓扑与编排: 仅讨论多智能体系统的拓扑结构设计、通信架构、消息传递协议、智能体编排（orchestration）的论文，排除。

第四步：处理特殊和模糊情况

1. LLM 的应用:
   - 保留 (例外): 如果论文的核心是把“自我演化”机制，应用在特定领域（如“用于化学实验的自我演化智能体”），也应该保留。
   - 排除: 如果该应用不涉及自我演化机制（见第一步的排除规则）。

第五步：最终决策 综合以上分析，请给出你的最终判断。

---
论文标题: {title}
论文摘要: {summary}
---

请严格按照以下格式回答:
结果: [True/False]
理由: [请结合上述筛选标准，用中文详细说明你的判断过程和核心依据。明确指出论文的核心贡献，并解释它为何符合或不符合我的研究目标。]"""

PRESTIGE_FILTER_PROMPT = """你是一个极其严格的 AI 论文声望筛选助手。目标不是找“可能还不错”的论文，而是大幅压缩每天需要阅读的论文数量，因此必须采用高门槛标准，但对“大厂/知名公司”的论文应当明确保留倾向。

你的任务：只根据作者和机构信息，判断这篇论文是否因为“大牛作者”、“顶级机构”，或“知名大公司/大厂”而值得保留。

保留条件（满足任一即可）：
1. 作者中有 AI / ML / LLM 领域公认的高影响力研究者、知名 PI、长期一线核心作者。
2. 机构中出现明显的顶级学术机构、顶级工业研究机构或头部 AI 实验室，并且论文明显来自这些团队。
3. 机构中出现全球知名大型科技公司、头部互联网公司、头部芯片/云计算/软件公司、知名工业界研究团队，也应当倾向保留。

排除条件（任一满足即可排除）：
1. 作者和机构都没有明显强信号。
2. 机构只是普通高校、小公司、普通研究院，或者只是非知名企业部门，且你不能确定其是否属于头部公司或知名团队。
3. 机构信息缺失、模糊，且作者里也没有明确的大牛。
4. 你拿不准时，一律返回 False。

判断原则：
- 这是硬筛，不是宽松推荐，标准必须高。
- 不要因为题目热门、方向前沿就保留；这里只看作者和机构声望。
- 如果作者机构已经是公认顶级学府、顶级研究机构或全球知名大公司，单凭机构本身就可以返回 True，不需要再额外要求“大牛作者”。
- 学校方面，可参考但不限于：Stanford、MIT、CMU、Berkeley、Princeton、Oxford、Cambridge、THU、PKU、SJTU、USTC、HKUST、NUS、NTU、UIUC。
- 研究机构方面，可参考但不限于：OpenAI、DeepMind、Anthropic、Google Research、Meta AI/FAIR、Microsoft Research。
- 大公司/知名公司方面，也应视为强信号，例如但不限于：Google、Meta、Microsoft、Amazon、Apple、NVIDIA、ByteDance、Alibaba、Tencent、Huawei、IBM、Salesforce、Adobe。
- 上述只是例子，不是白名单；但如果机构明显属于全球知名大公司或知名科技公司，应倾向返回 True，而不是因为“不是学术名校/顶级实验室”就排除。

---
论文标题: {title}
作者: {authors}
机构信息: {affiliations}
---

请严格按照以下格式回答:
结果: [True/False]
理由: [请用中文说明是否命中了大牛作者、顶级机构，或知名大公司/大厂；若排除，明确说明是因为缺少足够强的声望信号，或机构信息不足以支撑保留。]"""

# Prestige 白名单
# 规则：命中白名单时直接保留；只有未命中白名单时才交给 LLM 做补充判断。
PRESTIGE_AUTHOR_WHITELIST = {
    "Yann LeCun": ["yann lecun", "yann le cun"],
    "Geoffrey Hinton": ["geoffrey hinton"],
    "Andrew Ng": ["andrew ng"],
    "Fei-Fei Li": ["fei fei li", "feifei li"],
    "Percy Liang": ["percy liang"],
    "Chelsea Finn": ["chelsea finn"],
    "Sergey Levine": ["sergey levine"],
    "Pieter Abbeel": ["pieter abbeel"],
    "Jeff Dean": ["jeff dean"],
    "Demis Hassabis": ["demis hassabis"],
    "David Silver": ["david silver"],
    "Ilya Sutskever": ["ilya sutskever"],
    "Noam Shazeer": ["noam shazeer"],
    "Tie-Yan Liu": ["tie yan liu", "tie-yan liu"],
}

PRESTIGE_INSTITUTION_WHITELIST = {
    "Stanford University": ["stanford", "stanford university"],
    "Massachusetts Institute of Technology": ["mit", "massachusetts institute of technology"],
    "Carnegie Mellon University": ["cmu", "carnegie mellon", "carnegie mellon university"],
    "University of California, Berkeley": ["berkeley", "uc berkeley", "university of california berkeley"],
    "Princeton University": ["princeton", "princeton university"],
    "University of Oxford": ["oxford", "university of oxford"],
    "University of Cambridge": ["cambridge", "university of cambridge"],
    "Harvard University": ["harvard", "harvard university"],
    "Columbia University": ["columbia", "columbia university"],
    "Cornell University": ["cornell", "cornell university"],
    "University of Illinois Urbana-Champaign": ["uiuc", "university of illinois urbana champaign"],
    "University of Washington": ["university of washington", "uw seattle", "uw"],
    "ETH Zurich": ["eth zurich", "ethz", "eth"],
    "EPFL": ["epfl", "ecole polytechnique federale de lausanne"],
    "University of California, Los Angeles": ["ucla", "university of california los angeles"],
    "University of California, San Diego": ["ucsd", "university of california san diego"],
    "Tsinghua University": ["thu", "tsinghua", "tsinghua university"],
    "Peking University": ["pku", "peking university"],
    "Shanghai Jiao Tong University": ["sjtu", "shanghai jiao tong university"],
    "University of Science and Technology of China": ["ustc", "university of science and technology of china"],
    "Harbin Institute of Technology": ["hit", "hit shenzhen", "harbin institute of technology"],
    "Hong Kong University of Science and Technology": ["hkust", "hong kong university of science and technology"],
    "National University of Singapore": ["nus", "national university of singapore"],
    "Nanyang Technological University": ["ntu", "nanyang technological university"],
    "National Taiwan University": ["national taiwan university"],
    "Chinese University of Hong Kong": ["cuhk", "chinese university of hong kong"],
    "Fudan University": ["fudan", "fudan university"],
    "Zhejiang University": ["zhejiang university", "zju"],
}

PRESTIGE_COMPANY_WHITELIST = {
    "OpenAI": ["openai"],
    "Google": ["google", "google research", "google deepmind", "deepmind"],
    "Meta": ["meta", "meta ai", "fair", "facebook ai research"],
    "Microsoft": ["microsoft", "microsoft research", "msr"],
    "Anthropic": ["anthropic"],
    "Amazon": ["amazon", "aws", "amazon web services"],
    "Apple": ["apple"],
    "NVIDIA": ["nvidia"],
    "ByteDance": ["bytedance", "byte dance"],
    "Alibaba": ["alibaba", "alibaba group"],
    "Tencent": ["tencent"],
    "Huawei": ["huawei"],
    "IBM": ["ibm"],
    "Salesforce": ["salesforce"],
    "Adobe": ["adobe"],
    "Baidu": ["baidu"],
    "Allen Institute for AI": ["allen institute for ai", "ai2"],
}

# Jina API配置
JINA_MAX_REQUESTS_PER_MINUTE = _get_env_int("JINA_MAX_REQUESTS_PER_MINUTE", 20, minimum=1)
JINA_MAX_RETRIES = _get_env_int("JINA_MAX_RETRIES", 3, minimum=1)
JINA_BACKOFF_FACTOR = _get_env_float("JINA_BACKOFF_FACTOR", 2.0, minimum=1.0)
JINA_REQUEST_TIMEOUT = _get_env_int("JINA_REQUEST_TIMEOUT", min(REQUEST_TIMEOUT, 45), minimum=1)
JINA_API_TOKEN = _get_env_str("JINA_API_TOKEN")  # 可选：为r.jina.ai添加Bearer Token

# 统一文档提取配置
DOCUMENT_EXTRACTOR_CHAIN = _get_env_str("DOCUMENT_EXTRACTOR_CHAIN", "docling,pymupdf4llm,jina")
DOCUMENT_EXTRACT_OCR_MODE = _get_env_str("DOCUMENT_EXTRACT_OCR_MODE", "auto")
DOCUMENT_EXTRACT_TIMEOUT = _get_env_int("DOCUMENT_EXTRACT_TIMEOUT", REQUEST_TIMEOUT, minimum=1)
DOCUMENT_EXTRACT_REMOTE_FALLBACK = _get_env_bool("DOCUMENT_EXTRACT_REMOTE_FALLBACK", True)
