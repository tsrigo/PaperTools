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
from pathlib import Path
from typing import Optional, Dict, List
from tqdm import tqdm
from openai import OpenAI, OpenAIError
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from functools import wraps

# 导入配置
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.config import (
    API_KEY, BASE_URL, MODEL, SUMMARY_DIR, TEMPERATURE, REQUEST_DELAY, REQUEST_TIMEOUT, MAX_WORKERS,
    ENABLE_CACHE, JINA_MAX_REQUESTS_PER_MINUTE, JINA_MAX_RETRIES, JINA_BACKOFF_FACTOR, JINA_API_TOKEN
)
from src.utils.cache_manager import CacheManager


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


def retry_on_failure(max_retries: int = None, backoff_factor: float = None):
    """重试装饰器"""
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
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt < max_retries - 1:  # 不是最后一次尝试
                        wait_time = backoff_factor ** attempt
                        print(f"⚠️ Jina API请求失败（尝试 {attempt + 1}/{max_retries}），{wait_time}秒后重试: {e}")
                        time.sleep(wait_time)
                    else:
                        print(f"❌ Jina API请求失败，已达到最大重试次数: {e}")
                except Exception as e:
                    # 对于非网络相关的异常，直接抛出
                    raise e
            
            # 如果所有重试都失败了，抛出最后一个异常
            raise last_exception
        
        return wrapper
    return decorator


@retry_on_failure()
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
    
    # 应用速率限制
    jina_rate_limiter.wait_if_needed()
    
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
        raise requests.exceptions.HTTPError(f"jinja.ai请求失败，状态码: {response.status_code}")


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


def translate_summary(summary: str, client: OpenAI, model: str, temperature: float, paper_title: str = "", cache_manager: Optional[CacheManager] = None) -> str:
    """
    翻译英文摘要为中文
    
    Args:
        summary: 英文摘要
        client: OpenAI客户端
        model: 使用的模型
        temperature: 生成温度
        paper_title: 论文标题（用于缓存）
        cache_manager: 缓存管理器
    
    Returns:
        中文翻译
    """
    # 尝试从缓存获取
    if cache_manager and ENABLE_CACHE:
        cache_key = f"translation_{paper_title}_{summary[:100]}"
        cached_translation = cache_manager.get_summary_cache(cache_key, summary)
        if cached_translation:
            # print(f"📋 使用缓存的翻译: {paper_title[:50]}...")
            return cached_translation

    # 构建翻译prompt
    prompt = f"""请将以下英文学术论文摘要翻译成中文，要求：

1. 保持学术性和准确性
2. 专业术语保持英文原文，用括号标注中文解释
3. 语言流畅自然，符合中文学术表达习惯
4. 保持原文的逻辑结构和重点

英文摘要：
{summary}

请提供中文翻译："""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system", 
                    "content": "你是一个专业的学术论文翻译助手，擅长将英文学术论文摘要准确翻译成中文。"
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=temperature
        )
        translation = response.choices[0].message.content
        
        # 保存到缓存
        if cache_manager and ENABLE_CACHE:
            cache_key = f"translation_{paper_title}_{summary[:100]}"
            cache_manager.set_summary_cache(cache_key, summary, translation)
        
        return translation
        
    except Exception as e:
        print(f"❌ 翻译摘要时出错: {e}")
        return "翻译失败"


def generate_summary(paper_content: str, client: OpenAI, model: str, temperature: float, paper_title: str = "", cache_manager: Optional[CacheManager] = None) -> str:
    """
    使用大模型生成论文总结，支持缓存
    
    Args:
        paper_content: 论文完整内容
        client: OpenAI客户端
        model: 使用的模型
        temperature: 生成温度
        paper_title: 论文标题（用于缓存）
        cache_manager: 缓存管理器
    
    Returns:
        生成的总结
    """
    # 尝试从缓存获取
    if cache_manager and ENABLE_CACHE:
        cached_summary = cache_manager.get_summary_cache(paper_title, paper_content)
        if cached_summary:
            # print(f"📋 使用缓存的总结: {paper_title[:50]}...")
            return cached_summary
    # 构建prompt
    prompt = f"""请根据以下论文内容，生成一个专业的学术总结。

论文内容:
{paper_content}

请按照以下格式生成总结，使用中文回复：

本文旨在 [解决什么问题或实现什么目标]。针对 [特定的输入、数据或场景]，我们提出了一种 [描述核心方法]，并在 [某数据集、benchmark、实验环境] 上通过 [具体评估指标] 验证了其有效性。

要求：
1. 总结应当简洁明了，突出核心贡献
2. 使用中文表述，专业术语保持英文
3. 重点关注方法创新和实验验证
4. 控制在200字以内"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system", 
                    "content": "你是一个专业的学术论文总结助手，能够准确理解论文内容并生成高质量的中文总结。"
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=temperature
            # 移除max_tokens限制，让模型生成更完整的总结
        )
        summary = response.choices[0].message.content
        
        # 保存到缓存
        if cache_manager and ENABLE_CACHE:
            cache_manager.set_summary_cache(paper_title, paper_content, summary)
        
        return summary
        
    except Exception as e:
        print(f"❌ 生成总结时出错: {e}")
        return "总结生成失败"


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
        base_url=args.base_url
    )
    
    print(f"📝 开始生成论文总结")
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
            
            if cache_manager and ENABLE_CACHE:
                # 先用论文链接作为键检查是否有缓存的内容
                paper_content_cache = cache_manager.get_paper_cache(paper_link)
                if paper_content_cache and paper_content_cache.get('data', {}).get('content'):
                    cached_paper_content = paper_content_cache['data']['content']
                    # 检查是否有对应的总结缓存
                    cached_summary = cache_manager.get_summary_cache(paper_title, cached_paper_content)
                    if original_summary:
                        cache_key = f"translation_{paper_title}_{original_summary[:100]}"
                        cached_translation = cache_manager.get_summary_cache(cache_key, original_summary)
                    
                    # 如果都有缓存，直接返回
                    if cached_summary and (not original_summary or cached_translation):
                        paper_copy = paper.copy()
                        paper_copy['summary2'] = cached_summary
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
                    # print(f"📋 使用缓存的论文内容: {paper_title[:50]}...")
            
            # 如果缓存中没有内容，才从jina.ai获取
            if not paper_content:
                paper_content = fetch_paper_content_from_jinja(paper_link, cache_manager)
                if not paper_content:
                    return 'failed', index, paper, f"❌ 无法获取论文内容: {paper_title}"
            
            # 检查内容长度并截断
            if len(paper_content) > 200000:
                paper_content = paper_content[:200000] + "\n\n[内容已截断...]"
            
            # 生成总结（这里会再次检查缓存）
            summary = generate_summary(paper_content, client, args.model, args.temperature, paper.get('title', ''), cache_manager)
            
            # 翻译原始摘要（这里也会检查缓存）
            summary_translation = ""
            if original_summary:
                try:
                    summary_translation = translate_summary(original_summary, client, args.model, args.temperature, paper.get('title', ''), cache_manager)
                except Exception as e:
                    print(f"⚠️ 翻译摘要失败 {paper_title[:30]}: {e}")
                    summary_translation = "翻译失败"
            
            # 添加总结到论文数据中
            paper_copy = paper.copy()
            paper_copy['summary2'] = summary
            paper_copy['summary_translation'] = summary_translation
            paper_copy['summary_generated_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
            paper_copy['summary_model'] = args.model
            
            return 'success', index, paper_copy, f"✅ 成功生成总结和翻译: {paper_title[:50]}..."
            
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
    
    # 打印统计信息
    print(f"\n📊 总结生成完成！")
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

    document.addEventListener('DOMContentLoaded', async () => {{
        try {{
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
            
            <div class="filter-reason">
                <strong>筛选原因:</strong> {paper.get('filter_reason', '无特定原因')}
            </div>
            
            <div class="paper-summary">
                <strong>AI摘要:</strong> {paper.get('summary2', '暂无AI摘要')}
            </div>
            
            <div class="paper-original-summary">
                <strong>原始摘要（中文翻译）:</strong> {paper.get('summary_translation', paper.get('summary', '暂无摘要翻译'))}
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
