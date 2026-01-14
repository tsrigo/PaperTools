#!/usr/bin/env python3
"""
修复失败任务的脚本
Fix failed tasks script

检测并重新处理那些灵感溯源、翻译或总结失败的论文
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.generate_summary import (
    generate_summary,
    generate_inspiration_trace,
    translate_summary,
    fetch_paper_content_from_jinja
)
from src.utils.config import API_KEY, BASE_URL, MODEL, TEMPERATURE
from src.utils.cache_manager import CacheManager
from openai import OpenAI


def detect_failed_tasks(summary_file: str) -> Dict:
    """
    检测失败的任务

    Args:
        summary_file: summary JSON 文件路径

    Returns:
        包含失败任务信息的字典
    """
    with open(summary_file, 'r', encoding='utf-8') as f:
        papers = json.load(f)

    failed_tasks = {
        'inspiration_trace': [],  # 灵感溯源失败
        'translation': [],        # 翻译失败
        'summary': [],           # 总结失败
        'all_failed': []         # 全部失败
    }

    for paper in papers:
        arxiv_id = paper.get('arxiv_id', 'unknown')
        title = paper.get('title', 'Unknown')

        # 检查灵感溯源（顶层字段）
        inspiration_trace = paper.get('inspiration_trace', '')
        if not inspiration_trace or '失败' in inspiration_trace or '错误' in inspiration_trace:
            failed_tasks['inspiration_trace'].append({
                'arxiv_id': arxiv_id,
                'title': title,
                'link': paper.get('link', '')
            })

        # 检查翻译（顶层字段）
        summary_translation = paper.get('summary_translation', '')
        if not summary_translation or '失败' in summary_translation:
            failed_tasks['translation'].append({
                'arxiv_id': arxiv_id,
                'title': title,
                'link': paper.get('link', '')
            })

        # 检查总结（summary2 字段）
        summary2 = paper.get('summary2', '')
        if not summary2 or '失败' in summary2:
            failed_tasks['summary'].append({
                'arxiv_id': arxiv_id,
                'title': title,
                'link': paper.get('link', '')
            })

        # 检查是否全部失败
        if (not inspiration_trace or '失败' in inspiration_trace or '错误' in inspiration_trace) and \
           (not summary_translation or '失败' in summary_translation) and \
           (not summary2 or '失败' in summary2):
            failed_tasks['all_failed'].append({
                'arxiv_id': arxiv_id,
                'title': title,
                'link': paper.get('link', '')
            })

    return failed_tasks


def fix_failed_tasks(summary_file: str, task_type: str = 'all', dry_run: bool = False):
    """
    修复失败的任务

    Args:
        summary_file: summary JSON 文件路径
        task_type: 任务类型 (all, inspiration, translation, summary)
        dry_run: 是否只检测不修复
    """
    print(f"📂 读取文件: {summary_file}")

    # 检测失败任务
    failed_tasks = detect_failed_tasks(summary_file)

    # 打印统计信息
    print("\n📊 失败任务统计:")
    print(f"  - 灵感溯源失败: {len(failed_tasks['inspiration_trace'])} 篇")
    print(f"  - 翻译失败: {len(failed_tasks['translation'])} 篇")
    print(f"  - 总结失败: {len(failed_tasks['summary'])} 篇")
    print(f"  - 全部失败: {len(failed_tasks['all_failed'])} 篇")

    if dry_run:
        print("\n🔍 Dry run 模式，仅检测不修复")
        return

    # 初始化 OpenAI 客户端和缓存管理器
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    cache_manager = CacheManager()

    # 读取完整的论文数据
    with open(summary_file, 'r', encoding='utf-8') as f:
        papers = json.load(f)

    # 根据任务类型修复
    print(f"\n🔧 开始修复任务 (类型: {task_type})...")

    fixed_count = 0
    failed_count = 0

    for paper in tqdm(papers, desc="处理论文"):
        arxiv_id = paper.get('arxiv_id', 'unknown')
        title = paper.get('title', 'Unknown')
        link = paper.get('link', '')

        needs_update = False

        # 修复灵感溯源
        if task_type in ['all', 'inspiration']:
            inspiration_trace = paper.get('inspiration_trace', '')
            if not inspiration_trace or '失败' in inspiration_trace or '错误' in inspiration_trace:
                try:
                    # 获取论文内容
                    paper_content = fetch_paper_content_from_jinja(link, cache_manager)
                    if paper_content:
                        # 生成灵感溯源
                        new_inspiration = generate_inspiration_trace(
                            paper_content, client, MODEL, TEMPERATURE, title, cache_manager
                        )
                        paper['inspiration_trace'] = new_inspiration
                        needs_update = True
                        print(f"\n✅ 修复灵感溯源: {title[:50]}...")
                except Exception as e:
                    print(f"\n❌ 修复灵感溯源失败 {title[:30]}: {e}")
                    failed_count += 1

        # 修复翻译
        if task_type in ['all', 'translation']:
            summary_translation = paper.get('summary_translation', '')
            summary2 = paper.get('summary2', '')
            if summary2 and (not summary_translation or '失败' in summary_translation):
                try:
                    # 翻译摘要
                    new_translation = translate_summary(
                        summary2, client, MODEL, TEMPERATURE, title, cache_manager
                    )
                    paper['summary_translation'] = new_translation
                    needs_update = True
                    print(f"\n✅ 修复翻译: {title[:50]}...")
                except Exception as e:
                    print(f"\n❌ 修复翻译失败 {title[:30]}: {e}")
                    failed_count += 1

        # 修复总结
        if task_type in ['all', 'summary']:
            summary2 = paper.get('summary2', '')
            if not summary2 or '失败' in summary2:
                try:
                    # 获取论文内容
                    paper_content = fetch_paper_content_from_jinja(link, cache_manager)
                    if paper_content:
                        # 生成总结
                        new_summary = generate_summary(
                            paper_content, client, MODEL, TEMPERATURE, title, cache_manager
                        )
                        paper['summary2'] = new_summary
                        needs_update = True
                        print(f"\n✅ 修复总结: {title[:50]}...")
                except Exception as e:
                    print(f"\n❌ 修复总结失败 {title[:30]}: {e}")
                    failed_count += 1

        if needs_update:
            fixed_count += 1

    # 保存更新后的文件
    if fixed_count > 0:
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"\n💾 已保存更新: {summary_file}")

    print(f"\n📊 修复完成!")
    print(f"  - 成功修复: {fixed_count} 篇")
    print(f"  - 修复失败: {failed_count} 篇")


def main():
    parser = argparse.ArgumentParser(description='修复失败任务')
    parser.add_argument('--file', type=str, help='指定要修复的 summary JSON 文件')
    parser.add_argument('--dir', type=str, default='summary', help='summary 目录路径 (默认: summary)')
    parser.add_argument('--type', type=str, default='all',
                       choices=['all', 'inspiration', 'translation', 'summary'],
                       help='要修复的任务类型 (默认: all)')
    parser.add_argument('--dry-run', action='store_true', help='只检测不修复')
    parser.add_argument('--pattern', type=str, help='文件名匹配模式 (例如: 2025-12-*)')

    args = parser.parse_args()

    print("🔧 启动失败任务修复工具")
    print("=" * 60)

    if args.file:
        # 修复单个文件
        if not os.path.exists(args.file):
            print(f"❌ 文件不存在: {args.file}")
            return
        fix_failed_tasks(args.file, args.type, args.dry_run)
    else:
        # 批量修复目录中的文件
        summary_dir = Path(args.dir)
        if not summary_dir.exists():
            print(f"❌ 目录不存在: {args.dir}")
            return

        # 查找所有 summary JSON 文件
        pattern = args.pattern or '*_with_summary2.json'
        summary_files = sorted(summary_dir.glob(pattern))

        if not summary_files:
            print(f"❌ 未找到匹配的文件: {pattern}")
            return

        print(f"📁 找到 {len(summary_files)} 个文件")

        for summary_file in summary_files:
            print(f"\n{'=' * 60}")
            fix_failed_tasks(str(summary_file), args.type, args.dry_run)


if __name__ == '__main__':
    main()
