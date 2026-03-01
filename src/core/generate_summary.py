#!/usr/bin/env python3
"""
论文总结生成脚本 - 直接添加到JSON文件
Paper summary generation script - adds summary2 field to JSON file
"""

import json
import os
import re
import requests
import time
import argparse
from typing import Optional, Dict, List
from tqdm import tqdm
from openai import OpenAI, OpenAIError
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from functools import wraps

# 导入配置
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.config import (  # noqa: E402
    API_KEY, BASE_URL, MODEL, SUMMARY_DIR, TEMPERATURE, REQUEST_DELAY, REQUEST_TIMEOUT, MAX_WORKERS,
    ENABLE_CACHE, JINA_MAX_REQUESTS_PER_MINUTE, JINA_MAX_RETRIES, JINA_BACKOFF_FACTOR
)
from src.utils.cache_manager import CacheManager  # noqa: E402


class JinaRateLimiter:
    """Jina API速率限制器 - 20 RPM"""
    
    def __init__(self, max_requests_per_minute: int = 20):
        self.max_requests_per_minute = max_requests_per_minute
        self.min_interval = 60.0 / max_requests_per_minute  # 每个请求之间的最小间隔（秒）
        self.last_request_time = 0
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        """如果需要的话，等待以满足速率限制"""
        with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                time.sleep(wait_time)
            
            self.last_request_time = time.time()


# 全局Jina速率限制器实例
jina_rate_limiter = JinaRateLimiter(max_requests_per_minute=JINA_MAX_REQUESTS_PER_MINUTE)


def retry_on_failure(max_retries: int = None, backoff_factor: float = None, apply_rate_limit: bool = False):
    """重试装饰器，支持速率限制和指数退避"""
    if max_retries is None:
        max_retries = JINA_MAX_RETRIES
    if backoff_factor is None:
        backoff_factor = JINA_BACKOFF_FACTOR

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    # 如果需要，在每次尝试前应用速率限制
                    if apply_rate_limit:
                        jina_rate_limiter.wait_if_needed()
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = backoff_factor ** attempt
                        print(f"⚠️ API请求失败 (尝试 {attempt + 1}/{max_retries}), {wait_time:.2f}秒后重试: {e}")
                        time.sleep(wait_time)
                    else:
                        print(f"❌ API请求失败，已达到最大重试次数: {e}")
                except Exception as e:
                    # 对于其他非网络相关的异常，直接抛出
                    raise e

            # 如果所有重试都失败了，抛出最后一个异常
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def retry_on_openai_error(max_retries: int = 6, backoff_factor: float = 2.0):
    """
    OpenAI API 重试装饰器
    专门处理 OpenAI API 调用中的网络错误、超时等异常

    Args:
        max_retries: 最大重试次数
        backoff_factor: 退避因子（指数退避）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (OpenAIError, requests.exceptions.RequestException, ConnectionError, TimeoutError) as e:
                    last_exception = e
                    error_msg = str(e)

                    # 判断是否是可重试的错误
                    retryable_errors = [
                        'Connection error',
                        'timeout',
                        'Too Many Requests',
                        'Rate limit',
                        'Service Unavailable',
                        '503',
                        '502',
                        '500'
                    ]

                    is_retryable = any(err in error_msg for err in retryable_errors)

                    if is_retryable and attempt < max_retries - 1:
                        wait_time = backoff_factor ** attempt
                        print(f"⚠️ OpenAI API调用失败 (尝试 {attempt + 1}/{max_retries}), {wait_time:.2f}秒后重试: {error_msg}")
                        time.sleep(wait_time)
                    else:
                        if attempt == max_retries - 1:
                            print(f"❌ OpenAI API调用失败，已达到最大重试次数: {error_msg}")
                        raise e
                except Exception as e:
                    # 对于其他非网络相关的异常，直接抛出
                    print(f"❌ 发生非网络错误: {e}")
                    raise e

            # 如果所有重试都失败了，抛出最后一个异常
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


@retry_on_failure(apply_rate_limit=True)
def fetch_paper_content_from_jinja(arxiv_url: str, cache_manager: Optional[CacheManager] = None) -> Optional[str]:
    """
    使用jinja.ai获取论文完整内容，支持缓存
    
    Args:
        arxiv_url: arXiv论文链接
        cache_manager: 缓存管理器
    
    Returns:
        论文的完整文本内容，如果获取失败则返回None
    """
    # 🚀 优化：首先检查缓存
    if cache_manager and ENABLE_CACHE:
        cached_paper = cache_manager.get_paper_cache(arxiv_url)
        if cached_paper and cached_paper.get('data', {}).get('content'):
            # print(f"📋 使用缓存的论文内容: {arxiv_url}")
            return cached_paper['data']['content']
    
    # 如果缓存中没有，才调用jina.ai API
    print(f"🌐 从jina.ai获取论文内容: {arxiv_url}")
    
    # 处理不同格式的链接
    if arxiv_url.startswith('/arxiv/'):
        # 相对路径格式: /arxiv/2509.18083
        arxiv_id = arxiv_url.replace('/arxiv/', '')
        pdf_url = f'https://arxiv.org/pdf/{arxiv_id}'
    elif '/abs/' in arxiv_url:
        # 完整abs链接转换为pdf链接
        pdf_url = arxiv_url.replace('/abs/', '/pdf/')
    elif '/pdf/' in arxiv_url:
        # 已经是pdf链接
        pdf_url = arxiv_url
    else:
        # 假设是arXiv ID
        pdf_url = f'https://arxiv.org/pdf/{arxiv_url}'
        
    # 使用jinja.ai API
    jinja_url = f'https://r.jina.ai/{pdf_url}'
    headers = {}
    try:
        from src.utils.config import JINA_API_TOKEN as _JINA_TOKEN
    except Exception:
        _JINA_TOKEN = ""
    if _JINA_TOKEN:
        headers["Authorization"] = f"Bearer {_JINA_TOKEN}"
    
    response = requests.get(jinja_url, headers=headers or None, timeout=REQUEST_TIMEOUT)
    
    if response.status_code == 200:
        content = response.content.decode('utf-8')
        
        # 🚀 优化：保存到缓存
        if cache_manager and ENABLE_CACHE:
            cache_manager.set_paper_cache(arxiv_url, {'content': content})
            print(f"💾 已缓存论文内容: {arxiv_url}")
        
        return content
    else:
        # 对于HTTP错误，抛出异常以触发重试机制
        response.raise_for_status()


def extract_arxiv_id_from_link(link: str) -> Optional[str]:
    """从arXiv链接中提取论文ID"""
    patterns = [
        r'arxiv\.org/abs/(\d+\.\d+)',
        r'arxiv\.org/pdf/(\d+\.\d+)',
        r'(\d{4}\.\d{4,5})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return match.group(1)
    return None


@retry_on_openai_error(max_retries=6, backoff_factor=2.0)
def generate_combined_summary(paper_content: str, original_summary: str, client: OpenAI, model: str, temperature: float, paper_title: str = "", cache_manager: Optional[CacheManager] = None) -> Tuple[str, str]:
    """
    使用大模型同时生成论文总结和摘要翻译
    
    Args:
        paper_content: 论文完整内容
        original_summary: 原始英文摘要
        client: OpenAI客户端
        model: 使用的模型
        temperature: 生成温度
        paper_title: 论文标题（用于缓存）
        cache_manager: 缓存管理器
    
    Returns:
        tuple: (生成的总结, 摘要翻译)
    """
    # 尝试从缓存获取
    if cache_manager and ENABLE_CACHE:
        cache_key = f"combined_summary_{paper_title}"
        cached_data = cache_manager.get_summary_cache(cache_key, paper_content + original_summary)
        if cached_data and "|||" in cached_data:
            summary, translation = cached_data.split("|||", 1)
            return summary.strip(), translation.strip()

    prompt = f"""请根据以下论文内容和原始摘要，完成两个任务：
1. 生成一个专业的中文学术总结。
2. 将原始英文摘要翻译成高质量的中文。

论文内容:
{paper_content[:50000]} 

原始摘要:
{original_summary}

请按照以下格式返回，中间用 "|||" 分隔：
[总结内容]
|||
[翻译内容]

总结要求：
1. 突出核心贡献、方法创新和实验验证。
2. 控制在200字以内。
3. 专业术语保持英文。

翻译要求：
1. 保持学术性和准确性，语言流畅自然。
2. 专业术语保持英文原文，用括号标注中文解释。"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个专业的学术论文助手，擅长总结和翻译科研论文。"},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            stream=True
        )
        result = ""
        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    result += delta.content
        
        if "|||" in result:
            summary, translation = result.split("|||", 1)
            summary = summary.strip()
            translation = translation.strip()
        else:
            summary = result.strip()
            translation = "翻译失败"

        # 保存到缓存
        if cache_manager and ENABLE_CACHE:
            cache_key = f"combined_summary_{paper_title}"
            cache_manager.set_summary_cache(cache_key, paper_content + original_summary, f"{summary}|||{translation}")
        
        return summary, translation
        
    except Exception as e:
        print(f"❌ 生成总结和翻译时出错: {e}")
        return "总结生成失败", "翻译失败"


@retry_on_openai_error(max_retries=6, backoff_factor=2.0)
def generate_inspiration_trace(paper_content: str, client: OpenAI, model: str, temperature: float, paper_title: str = "", cache_manager: Optional[CacheManager] = None) -> str:
    """
    生成论文的灵感溯源分析
    
    Args:
        paper_content: 论文完整内容
        client: OpenAI客户端
        model: 使用的模型
        temperature: 生成温度
        paper_title: 论文标题（用于缓存）
        cache_manager: 缓存管理器
    
    Returns:
        生成的灵感溯源分析
    """
    # 尝试从缓存获取
    if cache_manager and ENABLE_CACHE:
        cache_key = f"inspiration_{paper_title}"
        cached_trace = cache_manager.get_summary_cache(cache_key, paper_content)
        if cached_trace:
            return cached_trace
    
    # 构建prompt
    prompt = f"""请基于以下学术论文内容，系统性地推演作者提出其核心方法的逻辑链，目标就是还原作者产出这篇文章的思考过程（重思路，轻方法）。

{paper_content}

要求：首先完整提取出introduction中“讲故事”（引入problem）的逻辑（不涉及具体的方法等）然后，压缩成一个有序列表。最后一点需要是"研究问题"（一个问句）。
从这个研究问题出发，逐步聚焦，展现从观察、假设到形成最终方法论的思考过程。

语言简洁明了，突出逻辑链条。
请聚焦于思想的演进脉络，而不是方法的具体实现细节。
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个学术思维分析专家，擅长追溯和分析学术论文中的创新思路和逻辑演进。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=temperature,
            stream=True  # 使用流式响应避免524超时
        )
        # 收集流式响应
        inspiration_trace = ""
        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    inspiration_trace += delta.content
        
        # 保存到缓存
        if cache_manager and ENABLE_CACHE:
            cache_key = f"inspiration_{paper_title}"
            cache_manager.set_summary_cache(cache_key, paper_content, inspiration_trace)
        
        return inspiration_trace

    except Exception as e:
        print(f"❌ 生成灵感溯源失败: {e}")
        return "生成灵感溯源时发生错误"


@retry_on_openai_error(max_retries=6, backoff_factor=2.0)
def generate_daily_overview(papers: List[Dict], client: OpenAI, model: str, temperature: float, date_str: str = "", cache_manager: Optional[CacheManager] = None) -> str:
    """
    生成"今日AI论文速览"
    
    Args:
        papers: 论文列表
        client: OpenAI客户端
        model: 使用的模型
        temperature: 生成温度
        date_str: 日期字符串（用于缓存和标题）
        cache_manager: 缓存管理器
    
    Returns:
        生成的每日速览
    """
    # 尝试从缓存获取
    if cache_manager and ENABLE_CACHE:
        cache_key = f"daily_overview_{date_str}"
        # 使用所有论文标题的组合作为内容指纹
        content_fingerprint = "_".join([p.get('title', '')[:30] for p in papers[:10]])
        cached_overview = cache_manager.get_summary_cache(cache_key, content_fingerprint)
        if cached_overview:
            print(f"📋 使用缓存的每日速览: {date_str}")
            return cached_overview
    
    # 构建论文信息列表
    papers_info = []
    for paper in papers:
        paper_info = f"""[{paper.get('title', 'Unknown Title')}]
ArXiv ID: {paper.get('arxiv_id', 'Unknown')}
[类别: {paper.get('category', 'Unknown')}]
[发布日期: {date_str}]
{paper.get('summary', 'No summary available')}
---"""
        papers_info.append(paper_info)
    
    papers_text = "\n\n".join(papers_info)
    
    # 构建prompt
    prompt = f"""## Prompt: 生成"今日AI论文速览"

### 1. 角色 (Role)
你是一位顶尖的AI研究分析师和科技媒体主编，风格类似于 Andrej Karpathy 或知名科技通讯（如 "Import AI", "The Batch"）的作者。你的专长是将复杂、零散的学术论文信息，提炼、整合并转化为一个结构清晰、重点突出、易于理解的每日速览。你的读者是AI领域的研究人员、工程师和爱好者，他们时间宝贵，希望快速掌握今日最重要的研究动态和核心思想。

### 2. 核心任务 (Core Task)
你的任务是根据我提供的一系列当日AI论文的摘要，生成一篇名为"今日AI论文速览"的综合性报告。这份报告需要：
- 首先进行全局分析，识别出当天研究的宏观趋势和若干个核心主题。
- 然后将论文进行归类，组织到对应的主题下。
- 最后精炼总结每篇论文，并给出画龙点睛的亮点分析。

### 3. 输出结构与要求 (Output Structure & Requirements)
请严格按照以下结构和要求生成你的报告。

#### 一、 报告标题
- 固定格式：### 今日AI论文速览 ({date_str})

#### 二、 开篇导语
- 写一个简短（3-5句话）的引言段落，高度概括当天所有论文的核心研究方向和主要趋势。

#### 三、 主题分类与论文速览
- 识别主题：通读所有论文后，请识别出2-5个主要的研究主题。如果论文主题非常分散，可以创建一个名为"其他前沿研究"的类别。
- 创建主题板块：为每个主题创建一个板块，并起一个客观，具备概括性的标题。
    - 标题风格建议: 可以是"问题式"（如"LLM的记忆力能否被'外挂'增强？"）、"趋势式"（如"效率为王：推理加速新方法涌现"）、或"概念式"（如"解码黑箱：深入探究模型内部机理"）。
- 撰写论文要点:
    - 在每个主题板块下，用**项目符号 (bullet points)** 列出相关的论文。
    - 每篇论文的总结应**高度精炼（2-4句话）**，突出其**核心贡献（解决了什么问题）**和**关键发现/方法（提出了什么）**。不要直接复制摘要，而是要进行提炼和改写。
    - **关键标识符**：在每篇论文总结的末尾，必须加上其代号，格式为 **(ArXiv ID [类别])**。例如：(2509.21128 [cs.AI])。这是**强制要求**。
    - **突出重点**：使用**粗体**来标记论文中提出的**关键术语、模型名称或核心概念**，例如 **InfoQA**, **Tree-GRPO**, **"RL压缩 vs. SFT扩展"**。

#### 四、 今日看点 (Highlights)
- 在报告的最后，创建一个名为`### 今日看点`的板块。
- 在这个板块下，用3-4个项目符号总结出当天最值得关注的几个亮点。这部分是你作为主编的深度洞察，是报告的点睛之笔。
- 请从以下角度寻找看点：
    - 趋势观察: 是否有某个研究方向（如MoE、具身智能）出现了多篇高质量论文，形成了一股小浪潮？
    - 颠覆性观点: 是否有某篇论文挑战了现有SOTA或主流认知？（例如，证明了 Scaling Law 在某场景下失效）
    - 跨界融合: 是否有研究将两个看似无关的领域（如博弈论与多模态）巧妙地结合起来？
    - 潜力技术: 哪项研究提出的方法或工具在未来具有广泛的应用潜力？

### 4. 风格指南 (Style Guide)
- 语言: 使用简体中文。
- 语调: 专业、深刻，同时富有洞察力。避免使用营销号式的夸张词汇，但要能用精准的语言激发读者的阅读兴趣。做到客观与启发性的平衡。
- 核心原则: 结构化和重点突出是关键。确保读者可以一目了然地抓住当天研究的核心脉络。

---

### 今日论文列表：

{papers_text}

---

请现在生成"今日AI论文速览"报告："""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一位顶尖的AI研究分析师和科技媒体主编，擅长将复杂的学术论文信息提炼成结构清晰、重点突出的每日速览。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=temperature,
            stream=True  # 使用流式响应避免524超时
        )
        # 收集流式响应
        daily_overview = ""
        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    daily_overview += delta.content
        
        # 保存到缓存
        if cache_manager and ENABLE_CACHE:
            cache_key = f"daily_overview_{date_str}"
            content_fingerprint = "_".join([p.get('title', '')[:30] for p in papers[:10]])
            cache_manager.set_summary_cache(cache_key, content_fingerprint, daily_overview)
        
        return daily_overview

    except Exception as e:
        print(f"❌ 生成每日速览失败: {e}")
        return f"# 今日AI论文速览 ({date_str})\n\n生成每日速览时发生错误: {e}"


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='论文总结生成工具')
    parser.add_argument('--input-file', required=True,
                       help='输入的JSON文件路径')
    parser.add_argument('--output-dir', default=SUMMARY_DIR,
                       help=f'输出目录（JSON文件保存位置，默认: {SUMMARY_DIR})')
    parser.add_argument('--api-key', default=API_KEY,
                       help='API密钥')
    parser.add_argument('--base-url', default=BASE_URL,
                       help='API基础URL')
    parser.add_argument('--model', default=MODEL,
                       help='使用的模型')
    parser.add_argument('--temperature', type=float, default=TEMPERATURE,
                       help='生成温度')
    parser.add_argument('--max-papers', type=int, default=0,
                       help='最大处理论文数量，0表示处理所有（推荐处理所有）')
    parser.add_argument('--skip-existing', action='store_true',
                       help='跳过已有summary2字段的论文')
    parser.add_argument('--max-workers', type=int, default=MAX_WORKERS,
                       help=f'最大线程数 (默认: {MAX_WORKERS})')
    parser.add_argument('--disable-cache', action='store_true',
                       help='禁用缓存机制')
    
    args = parser.parse_args()
    
    # 初始化缓存管理器
    cache_manager = None
    if not args.disable_cache and ENABLE_CACHE:
        cache_manager = CacheManager()
    
    # 检查输入文件
    if not os.path.exists(args.input_file):
        print(f"❌ 输入文件未找到: {args.input_file}")
        return
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 初始化OpenAI客户端
    client = OpenAI(
        api_key=args.api_key,
        base_url=args.base_url,
        timeout=180.0,  # 增加超时时间到180秒，避免524错误
    )
    
    print("📝 开始生成论文总结")
    print(f"📁 输入文件: {args.input_file}")
    print(f"📂 输出目录: {args.output_dir}")
    print(f"🤖 使用模型: {args.model}")
    print("=" * 50)
    
    # 加载论文数据
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            papers = json.load(f)
        print(f"📚 成功加载 {len(papers)} 篇论文")
    except Exception as e:
        print(f"❌ 读取文件时出错: {e}")
        return
    
    # 限制处理数量
    if args.max_papers > 0:
        papers = papers[:args.max_papers]
        print(f"🔢 限制处理数量为: {args.max_papers}")
    
    # 多线程处理论文
    def process_paper_wrapper(paper_with_index):
        """包装函数，用于多线程处理"""
        index, paper = paper_with_index
        paper_title = paper.get('title', 'Untitled Paper')
        paper_link = paper.get('link', '')
        
        # 检查是否已有summary2字段且不为空
        if args.skip_existing and paper.get('summary2'):
            return 'skipped', index, paper, f"⏭️ 跳过已有总结的论文: {paper_title[:50]}..."
        
        try:
            # 优化：先检查是否有缓存的总结和翻译，避免不必要的内容获取
            original_summary = paper.get('summary', '')
            
            # 检查总结缓存（使用虚拟内容先检查）
            cached_summary = None
            cached_translation = None
            cached_inspiration = None

            if cache_manager and ENABLE_CACHE:
                # 先用论文链接作为键检查是否有缓存的内容
                paper_content_cache = cache_manager.get_paper_cache(paper_link)
                if paper_content_cache and paper_content_cache.get('data', {}).get('content'):
                    cached_paper_content = paper_content_cache['data']['content']
                    # 检查是否有对应的联合总结缓存
                    cache_key = f"combined_summary_{paper_title}"
                    cached_combined = cache_manager.get_summary_cache(cache_key, cached_paper_content + original_summary)
                    if cached_combined and "|||" in cached_combined:
                        cached_summary, cached_translation = cached_combined.split("|||", 1)
                        cached_summary = cached_summary.strip()
                        cached_translation = cached_translation.strip()
                    
                    # 检查灵感溯源缓存
                    inspiration_cache_key = f"inspiration_{paper_title}"
                    cached_inspiration = cache_manager.get_summary_cache(inspiration_cache_key, cached_paper_content)

                    # 如果都有缓存，直接返回
                    if cached_summary and cached_inspiration:
                        paper_copy = paper.copy()
                        paper_copy['summary2'] = cached_summary
                        paper_copy['inspiration_trace'] = cached_inspiration
                        paper_copy['summary_translation'] = cached_translation or "无需翻译"
                        paper_copy['summary_generated_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
                        paper_copy['summary_model'] = args.model
                        return 'success', index, paper_copy, f"📋 使用缓存: {paper_title[:50]}..."
            
            # 如果没有完整缓存，才获取论文内容
            paper_content = None
            
            # 先尝试从缓存获取论文内容
            if cache_manager and ENABLE_CACHE:
                paper_cache = cache_manager.get_paper_cache(paper_link)
                if paper_cache and paper_cache.get('data', {}).get('content'):
                    paper_content = paper_cache['data']['content']
            
            # 如果缓存中没有内容，才从jina.ai获取
            if not paper_content:
                paper_content = fetch_paper_content_from_jinja(paper_link, cache_manager)
                if not paper_content:
                    return 'failed', index, paper, f"❌ 无法获取论文内容: {paper_title}"
            
            # 检查内容长度并截断
            if len(paper_content) > 100000:
                paper_content = paper_content[:100000] + "\n\n[内容已截断...]"
            
            # 生成联合总结和翻译
            summary, summary_translation = generate_combined_summary(paper_content, original_summary, client, args.model, args.temperature, paper.get('title', ''), cache_manager)
            
            # 生成灵感溯源分析
            inspiration_trace = ""
            try:
                inspiration_trace = generate_inspiration_trace(paper_content, client, args.model, args.temperature, paper.get('title', ''), cache_manager)
            except Exception as e:
                print(f"⚠️ 生成灵感溯源失败 {paper_title[:30]}: {e}")
                inspiration_trace = "灵感溯源分析生成失败"
            
            # 添加总结到论文数据中
            paper_copy = paper.copy()
            paper_copy['summary2'] = summary
            paper_copy['inspiration_trace'] = inspiration_trace
            paper_copy['summary_translation'] = summary_translation
            paper_copy['summary_generated_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
            paper_copy['summary_model'] = args.model

            return 'success', index, paper_copy, f"✅ 成功生成总结和分析: {paper_title[:50]}..."
            
        except Exception as e:
            return 'failed', index, paper, f"❌ 处理论文时出错 {paper_title}: {e}"
    
    print(f"🔄 使用 {args.max_workers} 个线程并行生成总结...")
    
    processed = 0
    skipped = 0
    failed = 0
    updated_papers = papers.copy()  # 创建副本用于更新
    
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # 提交所有处理任务，传入索引和论文数据
        futures = [executor.submit(process_paper_wrapper, (i, paper)) for i, paper in enumerate(papers)]
        
        # 收集结果
        for future in tqdm(as_completed(futures), total=len(papers), desc="生成总结"):
            try:
                status, index, updated_paper, message = future.result()
                # print(message)
                
                if status == 'success':
                    processed += 1
                    updated_papers[index] = updated_paper  # 更新对应位置的论文数据
                elif status == 'skipped':
                    skipped += 1
                else:  # failed
                    failed += 1
                
                # 添加延时避免API请求过快
                time.sleep(REQUEST_DELAY / args.max_workers)
                
            except Exception as e:
                print(f"❌ 获取处理结果时出错: {e}")
                failed += 1
                continue
    
    # 保存更新后的JSON文件
    if processed > 0:
        # 生成输出文件名
        input_filename = os.path.basename(args.input_file)
        name_without_ext = os.path.splitext(input_filename)[0]
        output_filename = f"{name_without_ext}_with_summary2.json"
        output_path = os.path.join(args.output_dir, output_filename)
        
        # 保存更新后的数据
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(updated_papers, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 已保存更新后的JSON文件: {output_path}")
        
        # 生成"今日AI论文速览"
        print("\n📰 正在生成今日AI论文速览...")
        try:
            # 从文件名中提取日期
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', input_filename)
            date_str = date_match.group(1) if date_match else time.strftime('%Y-%m-%d')
            
            daily_overview = generate_daily_overview(
                updated_papers, 
                client, 
                args.model, 
                args.temperature, 
                date_str, 
                cache_manager
            )
            
            # 保存每日速览到独立的 Markdown 文件
            overview_filename = f"daily_overview_{date_str}.md"
            overview_path = os.path.join(args.output_dir, overview_filename)
            with open(overview_path, 'w', encoding='utf-8') as f:
                f.write(daily_overview)
            
            print(f"✅ 已生成今日AI论文速览: {overview_path}")
            
        except Exception as e:
            print(f"⚠️ 生成每日速览时出错: {e}")
    
    # 打印统计信息
    print("\n📊 总结生成完成！")
    print(f"✅ 已处理: {processed} 篇论文")
    print(f"⏭️ 已跳过: {skipped} 篇论文")
    print(f"❌ 失败: {failed} 篇论文")
    if processed > 0:
        print(f"📂 输出文件: {output_path}")
    print("🎉 处理完成！")


def generate_papers_list_html(filtered_papers, output_dir):
    """生成过滤后论文列表的HTML页面"""
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    # HTML模板（使用占位符避免 .format 误处理 JS/CSS 花括号）
    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>筛选论文列表</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            text-align: center;
        }}
        .stats {{
            text-align: center;
            margin: 20px 0;
            font-size: 1.1em;
            color: #7f8c8d;
        }}
        .paper-item {{
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            background-color: #fafafa;
        }}
        .paper-title {{
            font-size: 1.3em;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 10px;
        }}
        .paper-meta {{
            color: #7f8c8d;
            font-size: 0.9em;
            margin: 5px 0;
        }}
        .paper-authors {{
            font-style: italic;
            margin: 10px 0;
        }}
        .paper-category {{
            display: inline-block;
            background-color: #3498db;
            color: white;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 0.8em;
            margin: 5px 0;
        }}
        .paper-summary {{
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px;
            margin: 15px 0;
            font-size: 0.95em;
        }}
        .paper-original-summary {{
            background-color: #e8f5e8;
            border-left: 4px solid #28a745;
            padding: 10px;
            margin: 15px 0;
            font-size: 0.95em;
        }}
        .filter-reason {{
            background-color: #d1ecf1;
            border-left: 4px solid #17a2b8;
            padding: 10px;
            margin: 15px 0;
            font-size: 0.9em;
        }}
        .paper-links {{
            margin-top: 15px;
        }}
        .paper-links a {{
            display: inline-block;
            background-color: #e74c3c;
            color: white;
            padding: 8px 15px;
            text-decoration: none;
            border-radius: 4px;
            margin-right: 10px;
            margin-bottom: 5px;
            font-size: 0.9em;
        }}
        .paper-links a:hover {{
            background-color: #c0392b;
        }}
        .papers-cool-link {{
            background-color: #9b59b6 !important;
        }}
        .papers-cool-link:hover {{
            background-color: #8e44ad !important;
        }}
        .hidden {{ display: none; }}
        .toast {{
            position: fixed;
            left: 50%;
            bottom: 24px;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.85);
            color: #fff;
            padding: 12px 16px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            z-index: 9999;
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 14px;
        }}
        .toast button {{
            background: #3498db;
            color: #fff;
            border: none;
            border-radius: 4px;
            padding: 6px 10px;
            cursor: pointer;
        }}
        .toast .countdown {{
            opacity: 0.8;
        }}
        
        /* 可折叠部分样式 */
        .collapsible-header {{
            cursor: pointer;
            display: flex;
            align-items: center;
            font-weight: bold;
            padding: 8px 0;
            user-select: none;
            margin-bottom: 5px;
        }}
        .collapsible-header:hover {{
            opacity: 0.8;
        }}
        .collapsible-header::before {{
            content: "▶";
            margin-right: 8px;
            transition: transform 0.3s ease;
            font-size: 0.8em;
        }}
        .collapsible-header.open::before {{
            transform: rotate(90deg);
        }}
        .collapsible-content {{
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }}
        .collapsible-content.open {{
            max-height: 1000px;
        }}
        .collapsible-content .inner {{
            padding-top: 5px;
        }}
        
        /* 灵感溯源的特殊样式 */
        .inspiration-trace {
            background-color: #f8d7da;
            border-left: 4px solid #dc3545;
            padding: 10px;
            margin: 15px 0;
            font-size: 0.9em;
        }
    </style>
    <script>
    // 页面所属日期（由生成器注入）
    const PAGE_DATE = '__DATE_STR__';

    async function loadState(dateStr) {{
        try {{
            const res = await fetch(`/api/state?date=${{encodeURIComponent(dateStr)}}`);
            if (!res.ok) return {{deleted_ids: [], read_ids: []}};
            return await res.json();
        }} catch (e) {{
            return {{deleted_ids: [], read_ids: []}};
        }}
    }}

    const pendingDeletes = new Map(); // arxivId -> timeoutId

    function ensureToast() {{
        let toast = document.getElementById('undo-toast');
        if (!toast) {{
            toast = document.createElement('div');
            toast.id = 'undo-toast';
            toast.className = 'toast hidden';
            toast.innerHTML = '<span class="msg"></span> <span class="countdown"></span> <button class="undo">撤销</button>';
            document.body.appendChild(toast);
        }}
        return toast;
    }}

    function showUndoToast(message, seconds, onUndo, onExpire) {{
        const toast = ensureToast();
        const msgEl = toast.querySelector('.msg');
        const cdEl = toast.querySelector('.countdown');
        const undoBtn = toast.querySelector('.undo');
        msgEl.textContent = message;
        let remaining = seconds;
        cdEl.textContent = `(${remaining}s)`;
        toast.classList.remove('hidden');

        let intervalId = setInterval(() => {{
            remaining -= 1;
            cdEl.textContent = `(${remaining}s)`;
            if (remaining <= 0) {{
                clearInterval(intervalId);
            }}
        }}, 1000);

        const cleanup = () => {{
            clearInterval(intervalId);
            toast.classList.add('hidden');
        }};

        const expireTimer = setTimeout(() => {{
            cleanup();
            try {{ onExpire && onExpire(); }} catch (e) {{}}
        }}, seconds * 1000);

        const onUndoClick = () => {{
            cleanup();
            clearTimeout(expireTimer);
            undoBtn.removeEventListener('click', onUndoClick);
            try {{ onUndo && onUndo(); }} catch (e) {{}}
        }};
        undoBtn.addEventListener('click', onUndoClick);
    }}

    function updateStatsCount() {
        const visibleCount = Array.from(document.querySelectorAll('[data-arxiv-id]')).filter(el => !el.classList.contains('hidden')).length;
        const statsEl = document.querySelector('.stats');
        if (statsEl) {
            statsEl.textContent = `共筛选出 ${visibleCount} 篇论文`;
        }
    }

    function deletePaper(dateStr, arxivId, paperDir, title) {{
        const el = document.querySelector(`[data-arxiv-id="${CSS.escape(arxivId)}"]`);
        if (!el) return;
        // 先隐藏，提供撤销
        el.classList.add('hidden');
        updateStatsCount();
        
        const seconds = 5;
        let apiSucceeded = false;
        showUndoToast('已删除，5秒内可撤销', seconds, () => {
            // 撤销：恢复显示
            el.classList.remove('hidden');
            const t = pendingDeletes.get(arxivId);
            if (t) { clearTimeout(t); pendingDeletes.delete(arxivId); }
            updateStatsCount();
        }, async () => {
            // 倒计时结束，真正调用删除API
            const payload = { date: dateStr, arxiv_id: arxivId };
            if (paperDir) payload.paper_dir = paperDir;
            if (title) payload.title = title;
            try {
                const res = await fetch('/api/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                apiSucceeded = res.ok;
                if (!res.ok) {
                    // 失败则恢复显示
                    el.classList.remove('hidden');
                }
            } catch (e) {
                el.classList.remove('hidden');
            } finally {
                pendingDeletes.delete(arxivId);
                if (apiSucceeded) {
                    // 确认删除后，从DOM彻底移除，避免搜索可见
                    el.remove();
                }
                updateStatsCount();
            }
        });

        // 额外的保险timer引用（便于手动清理）
        const timerId = setTimeout(() => {}, seconds * 1000);
        pendingDeletes.set(arxivId, timerId);
    }}

    async function toggleRead(dateStr, arxivId, checkbox) {{
        const payload = {{ date: dateStr, arxiv_id: arxivId, read: checkbox.checked }};
        const res = await fetch('/api/toggle-read', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(payload) }});
        if (!res.ok) {{
            alert('保存阅读状态失败');
            checkbox.checked = !checkbox.checked;
        }}
    }}

    // 可折叠功能
    function initializeCollapsible() {{
        document.querySelectorAll('.collapsible-header').forEach(header => {{
            header.addEventListener('click', function() {{
                const content = this.nextElementSibling;
                const isOpen = header.classList.contains('open');
                
                if (isOpen) {{
                    header.classList.remove('open');
                    content.classList.remove('open');
                }} else {{
                    header.classList.add('open');
                    content.classList.add('open');
                }}
            }});
        }});
    }}

    document.addEventListener('DOMContentLoaded', async () => {{
        try {{
            // 初始化可折叠功能
            initializeCollapsible();
            
            // 优先从路径中解析 /YYYY-MM-DD/index.html；若服务根目录即日期目录，则回退到 PAGE_DATE
            const parts = location.pathname.split('/').filter(Boolean);
            let dateStr = parts.length >= 2 ? parts[parts.length - 2] : '';
            if (!dateStr && typeof PAGE_DATE === 'string' && PAGE_DATE) {{
                dateStr = PAGE_DATE;
            }}
            if (!dateStr) return;
            const state = await loadState(dateStr);
            const deleted = new Set(state.deleted_ids || []);
            const read = new Set(state.read_ids || []);
            // 移除已删除的项
            document.querySelectorAll('[data-arxiv-id]').forEach(el => {{
                const id = el.getAttribute('data-arxiv-id');
                if (deleted.has(id)) {{
                    el.remove();
                }} else {{
                    // 设置已读勾选
                    const checkbox = el.querySelector('input[type="checkbox"]');
                    if (checkbox && read.has(id)) {{
                        checkbox.checked = true;
                    }}
                }}
            }});
            // 更新顶部统计数量
            updateStatsCount();
        }} catch (e) {{
            console.warn('初始化状态失败', e);
        }}
    }});
    </script>
</head>
<body>
    <div class="container">
        <h1>筛选论文列表</h1>
        <div class="stats">共筛选出 __PAPER_COUNT__ 篇论文</div>
        
        __PAPERS_HTML__
    </div>
</body>
</html>"""
    # 还原 CSS/JS 花括号为单括号
    html_template = html_template.replace("{{", "{").replace("}}", "}")
    
    # 生成每篇论文的HTML
    papers_html = ""
    for idx, paper in enumerate(filtered_papers, 1):
        arxiv_id = paper.get('arxiv_id', 'Unknown')
        papers_cool_url = f"https://papers.cool/arxiv/{arxiv_id}"
        title = paper.get('title', 'Unknown Title')
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)[:100]
        paper_dir_name = f"{idx:03d}_{safe_title}"
        
        paper_html = f"""
        <div class="paper-item" data-arxiv-id="{arxiv_id}">
            <div class="paper-title">{title}
                <span style=\"float:right; cursor:pointer; color:#e74c3c;\" title=\"删除\" onclick=\"deletePaper('{os.path.basename(output_dir)}','{arxiv_id}','{os.path.basename(output_dir)}/{paper_dir_name}','{title.replace('"','&quot;')}')\">✖</span>
            </div>
            <div class="paper-meta">ArXiv ID: {arxiv_id}</div>
            <div class="paper-authors">作者: {paper.get('authors', 'Unknown')}</div>
            <div class="paper-category">{paper.get('category', 'Unknown')}</div>
            <div class=\"paper-meta\">
                <label><input type=\"checkbox\" onchange=\"toggleRead('{os.path.basename(output_dir)}','{arxiv_id}', this)\"> 已阅读</label>
            </div>
            
            <!-- 筛选原因 (默认折叠) -->
            <div class="collapsible-header">筛选原因</div>
            <div class="collapsible-content">
                <div class="inner">
                    <div class="filter-reason">
                        {paper.get('filter_reason', '无特定原因')}
                    </div>
                </div>
            </div>
            
            <!-- AI摘要 (默认展开) -->
            <div class="collapsible-header open">AI摘要</div>
            <div class="collapsible-content open">
                <div class="inner">
                    <div class="paper-summary">
                        {paper.get('summary2', '暂无AI摘要')}
                    </div>
                </div>
            </div>
            
            <!-- 原始摘要 (默认展开) -->
            <div class="collapsible-header open">原始摘要（中文翻译）</div>
            <div class="collapsible-content open">
                <div class="inner">
                    <div class="paper-original-summary">
                        {paper.get('summary_translation', paper.get('summary', '暂无摘要翻译'))}
                    </div>
                </div>
            </div>
            
            <!-- 灵感溯源 (默认折叠) -->
            <div class="collapsible-header">灵感溯源</div>
            <div class="collapsible-content">
                <div class="inner">
                    <div class="inspiration-trace">
                        {paper.get('inspiration_trace', '暂无灵感溯源分析')}
                    </div>
                </div>
            </div>

            <div class="paper-links">
                <a href="https://arxiv.org/abs/{arxiv_id}" target="_blank">ArXiv原文</a>
                <a href="https://arxiv.org/pdf/{arxiv_id}.pdf" target="_blank">下载PDF</a>
                <a href="{papers_cool_url}" target="_blank" class="papers-cool-link">Papers.cool</a>
            </div>
        </div>
        """
        papers_html += paper_html
    
    # 填充模板（避免 str.format 解析 JS 模板中的 {remaining} 等）
    html_content = (
        html_template
        .replace("__PAPER_COUNT__", str(len(filtered_papers)))
        .replace("__PAPERS_HTML__", papers_html)
        .replace("__DATE_STR__", os.path.basename(output_dir))
    )
    
    # 写入HTML文件
    html_file = os.path.join(output_dir, 'index.html')
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return html_file


if __name__ == "__main__":
    main()
