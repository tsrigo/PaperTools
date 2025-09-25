#!/usr/bin/env python3
"""
优化版论文总结生成脚本 - 专门针对缓存复用优化
Fast paper summary generation script - optimized for cache reuse
"""

import json
import os
import argparse
import time
from pathlib import Path
from typing import Optional, Dict, List
from tqdm import tqdm
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 导入配置
try:
    from config import (
        API_KEY, BASE_URL, MODEL, SUMMARY_DIR, TEMPERATURE, REQUEST_DELAY, 
        REQUEST_TIMEOUT, MAX_WORKERS, ENABLE_CACHE
    )
except ImportError:
    API_KEY = "your_api_key_here"
    BASE_URL = "https://api.x.ai/v1"
    MODEL = "grok-3-mini"
    SUMMARY_DIR = "summary"
    TEMPERATURE = 0.1
    REQUEST_DELAY = 2
    REQUEST_TIMEOUT = 120
    MAX_WORKERS = 4
    ENABLE_CACHE = True

# 导入缓存管理器
from cache_manager import CacheManager
from generate_summary import (
    fetch_paper_content_from_jinja, generate_summary, 
    translate_summary, jina_rate_limiter
)


def process_papers_fast(papers: List[Dict], args, client: OpenAI, cache_manager: Optional[CacheManager] = None):
    """
    快速处理论文 - 优化版本
    
    主要优化：
    1. 优先检查JSON中已有的summary2
    2. 然后检查缓存
    3. 最后才获取论文内容
    """
    
    def process_paper_fast(paper_with_index):
        index, paper = paper_with_index
        paper_title = paper.get('title', 'Untitled Paper')
        paper_link = paper.get('link', '')
        
        # 第一优先级：检查JSON中是否已有summary2
        if args.skip_existing and paper.get('summary2') and paper.get('summary2').strip():
            return 'skipped', index, paper, f"⏭️ JSON中已有总结: {paper_title[:50]}..."
        
        # 第二优先级：检查缓存中的完整结果
        if cache_manager and ENABLE_CACHE:
            try:
                # 检查是否有缓存的论文内容
                paper_cache = cache_manager.get_paper_cache(paper_link)
                if paper_cache and paper_cache.get('data', {}).get('content'):
                    cached_content = paper_cache['data']['content']
                    
                    # 检查是否有对应的总结缓存
                    cached_summary = cache_manager.get_summary_cache(paper_title, cached_content)
                    
                    # 检查翻译缓存
                    cached_translation = None
                    original_summary = paper.get('summary', '')
                    if original_summary:
                        cache_key = f"translation_{paper_title}_{original_summary[:100]}"
                        cached_translation = cache_manager.get_summary_cache(cache_key, original_summary)
                    
                    # 如果缓存完整，直接使用
                    if cached_summary:
                        paper_copy = paper.copy()
                        paper_copy['summary2'] = cached_summary
                        paper_copy['summary_translation'] = cached_translation or "无需翻译"
                        paper_copy['summary_generated_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
                        paper_copy['summary_model'] = args.model
                        return 'success', index, paper_copy, f"📋 使用完整缓存: {paper_title[:50]}..."
            except Exception as e:
                print(f"⚠️ 检查缓存时出错 {paper_title[:30]}: {e}")
        
        # 第三优先级：需要获取内容并生成
        try:
            # 尝试从缓存获取论文内容
            paper_content = None
            if cache_manager and ENABLE_CACHE:
                paper_cache = cache_manager.get_paper_cache(paper_link)
                if paper_cache and paper_cache.get('data', {}).get('content'):
                    paper_content = paper_cache['data']['content']
            
            # 如果缓存中没有内容，从jina.ai获取
            if not paper_content:
                paper_content = fetch_paper_content_from_jinja(paper_link)
                if not paper_content:
                    return 'failed', index, paper, f"❌ 无法获取论文内容: {paper_title}"
                
                # 保存到缓存
                if cache_manager and ENABLE_CACHE:
                    cache_manager.set_paper_cache(paper_link, {'content': paper_content})
            
            # 截断过长内容
            if len(paper_content) > 200000:
                paper_content = paper_content[:200000] + "\n\n[内容已截断...]"
            
            # 生成总结
            summary = generate_summary(paper_content, client, args.model, args.temperature, paper_title, cache_manager)
            
            # 翻译摘要
            summary_translation = ""
            original_summary = paper.get('summary', '')
            if original_summary:
                try:
                    summary_translation = translate_summary(original_summary, client, args.model, args.temperature, paper_title, cache_manager)
                except Exception as e:
                    print(f"⚠️ 翻译失败 {paper_title[:30]}: {e}")
                    summary_translation = "翻译失败"
            
            # 返回结果
            paper_copy = paper.copy()
            paper_copy['summary2'] = summary
            paper_copy['summary_translation'] = summary_translation
            paper_copy['summary_generated_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
            paper_copy['summary_model'] = args.model
            
            return 'success', index, paper_copy, f"✅ 新生成: {paper_title[:50]}..."
            
        except Exception as e:
            return 'failed', index, paper, f"❌ 处理出错 {paper_title}: {e}"
    
    # 执行处理
    print(f"🔄 使用 {args.max_workers} 个线程快速处理...")
    
    processed = 0
    skipped = 0
    failed = 0
    updated_papers = papers.copy()
    
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(process_paper_fast, (i, paper)) for i, paper in enumerate(papers)]
        
        for future in tqdm(as_completed(futures), total=len(papers), desc="快速处理"):
            try:
                status, index, updated_paper, message = future.result()
                
                if status == 'success':
                    processed += 1
                    updated_papers[index] = updated_paper
                elif status == 'skipped':
                    skipped += 1
                else:
                    failed += 1
                
                # 减少延时，因为大部分都是缓存
                time.sleep(REQUEST_DELAY / (args.max_workers * 4))  # 减少到1/4
                
            except Exception as e:
                print(f"❌ 处理异常: {e}")
                failed += 1
    
    return updated_papers, processed, skipped, failed


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='快速论文总结生成工具（缓存优化版）')
    parser.add_argument('--input-file', required=True, help='输入JSON文件')
    parser.add_argument('--output-dir', default=SUMMARY_DIR, help='输出目录')
    parser.add_argument('--api-key', default=API_KEY, help='API密钥')
    parser.add_argument('--base-url', default=BASE_URL, help='API基础URL')
    parser.add_argument('--model', default=MODEL, help='使用的模型')
    parser.add_argument('--temperature', type=float, default=TEMPERATURE, help='生成温度')
    parser.add_argument('--max-papers', type=int, default=0, help='最大处理数量')
    parser.add_argument('--skip-existing', action='store_true', help='跳过已有summary2的论文')
    parser.add_argument('--max-workers', type=int, default=MAX_WORKERS, help='最大线程数')
    parser.add_argument('--disable-cache', action='store_true', help='禁用缓存')
    
    args = parser.parse_args()
    
    # 初始化缓存管理器
    cache_manager = None
    if not args.disable_cache and ENABLE_CACHE:
        cache_manager = CacheManager()
        stats = cache_manager.get_cache_stats()
        print(f"📊 缓存统计: 论文内容={stats['papers']}, 总结={stats['summaries']}, 总计={stats['total']}")
    
    # 检查输入文件
    if not os.path.exists(args.input_file):
        print(f"❌ 输入文件未找到: {args.input_file}")
        return
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 初始化客户端
    client = OpenAI(api_key=args.api_key, base_url=args.base_url)
    
    print(f"📝 快速论文总结生成")
    print(f"📁 输入文件: {args.input_file}")
    print(f"📂 输出目录: {args.output_dir}")
    print(f"🤖 模型: {args.model}")
    print("=" * 50)
    
    # 加载数据
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            papers = json.load(f)
        print(f"📚 加载 {len(papers)} 篇论文")
    except Exception as e:
        print(f"❌ 读取文件错误: {e}")
        return
    
    # 限制数量
    if args.max_papers > 0:
        papers = papers[:args.max_papers]
        print(f"🔢 限制处理: {args.max_papers}")
    
    # 快速处理
    start_time = time.time()
    updated_papers, processed, skipped, failed = process_papers_fast(
        papers, args, client, cache_manager
    )
    elapsed = time.time() - start_time
    
    # 保存结果
    if processed > 0:
        input_filename = os.path.basename(args.input_file)
        name_without_ext = os.path.splitext(input_filename)[0]
        output_filename = f"{name_without_ext}_with_summary2.json"
        output_path = os.path.join(args.output_dir, output_filename)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(updated_papers, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 已保存: {output_path}")
    
    # 统计
    print(f"\n📊 处理完成！耗时: {elapsed:.1f}秒")
    print(f"✅ 处理: {processed} 篇")
    print(f"⏭️ 跳过: {skipped} 篇")
    print(f"❌ 失败: {failed} 篇")
    if processed > 0:
        print(f"⚡ 平均速度: {processed/elapsed:.1f} 篇/秒")


if __name__ == "__main__":
    main()
