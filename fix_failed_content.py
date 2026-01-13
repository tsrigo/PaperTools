#!/usr/bin/env python3
"""
修复已有数据中失败的内容（翻译、摘要、灵感溯源等）
Fix failed content in existing data
"""

import os
import sys
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
SUMMARY_DIR = PROJECT_ROOT / "summary"

# 失败标记模式
FAILURE_PATTERNS = {
    "summary_translation": [
        "翻译失败",
        "Translation failed",
    ],
    "summary2": [
        "总结生成失败",
        "Summary generation failed",
    ],
    "inspiration_trace": [
        "生成灵感溯源时发生错误",
        "灵感溯源分析生成失败",
    ],
    "research_insights": [
        "研究洞察分析生成失败",
    ],
    "critical_evaluation": [
        "批判性评估生成失败",
    ],
}

# 每日速览失败模式
OVERVIEW_FAILURE_PATTERNS = [
    "生成每日速览时发生错误",
    "Connection error",
]


def is_failed_content(value: str, field: str) -> bool:
    """检查内容是否为失败状态"""
    if not value:
        return True
    patterns = FAILURE_PATTERNS.get(field, [])
    for pattern in patterns:
        if pattern in value:
            return True
    return False


def is_overview_failed(content: str) -> bool:
    """检查每日速览是否失败"""
    if not content:
        return True
    for pattern in OVERVIEW_FAILURE_PATTERNS:
        if pattern in content:
            return True
    return False


def scan_failed_papers(date_str: str = None) -> Dict:
    """扫描失败的论文内容"""
    results = {
        "papers": {},  # {date: [{arxiv_id, failed_fields}, ...]}
        "overviews": [],  # [date, ...]
    }

    # 获取要扫描的文件
    if date_str:
        pattern = f"filtered_papers_{date_str}_with_summary2.json"
        files = list(SUMMARY_DIR.glob(pattern))
    else:
        files = list(SUMMARY_DIR.glob("filtered_papers_*_with_summary2.json"))

    for json_file in sorted(files):
        # 提取日期
        match = re.search(r'(\d{4}-\d{2}-\d{2})', json_file.stem)
        if not match:
            continue
        date = match.group(1)

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                papers = json.load(f)
        except Exception as e:
            print(f"❌ 读取 {json_file} 失败: {e}")
            continue

        failed_papers = []
        for paper in papers:
            failed_fields = []
            for field in FAILURE_PATTERNS.keys():
                value = paper.get(field, "")
                if is_failed_content(value, field):
                    failed_fields.append(field)

            if failed_fields:
                failed_papers.append({
                    "arxiv_id": paper.get("arxiv_id", "unknown"),
                    "title": paper.get("title", "")[:50],
                    "failed_fields": failed_fields,
                })

        if failed_papers:
            results["papers"][date] = failed_papers

    # 扫描每日速览
    for md_file in sorted(SUMMARY_DIR.glob("daily_overview_*.md")):
        match = re.search(r'(\d{4}-\d{2}-\d{2})', md_file.stem)
        if not match:
            continue
        date = match.group(1)

        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            if is_overview_failed(content):
                results["overviews"].append(date)
        except Exception:
            results["overviews"].append(date)

    return results


def print_scan_results(results: Dict):
    """打印扫描结果"""
    total_papers = sum(len(v) for v in results["papers"].values())
    total_dates = len(results["papers"])

    print(f"\n{'='*60}")
    print("📊 扫描结果")
    print(f"{'='*60}")

    if results["papers"]:
        print(f"\n📄 论文内容失败: {total_papers} 篇 (跨 {total_dates} 天)")
        for date, papers in sorted(results["papers"].items(), reverse=True):
            print(f"\n  📅 {date} ({len(papers)} 篇):")
            for p in papers[:5]:  # 只显示前5篇
                fields = ", ".join(p["failed_fields"])
                print(f"     - {p['arxiv_id']}: {fields}")
            if len(papers) > 5:
                print(f"     ... 还有 {len(papers) - 5} 篇")
    else:
        print("\n✅ 没有发现论文内容失败")

    if results["overviews"]:
        print(f"\n📝 每日速览失败: {len(results['overviews'])} 天")
        for date in results["overviews"][:10]:
            print(f"   - {date}")
        if len(results["overviews"]) > 10:
            print(f"   ... 还有 {len(results['overviews']) - 10} 天")
    else:
        print("\n✅ 没有发现每日速览失败")


def fix_papers_for_date(date_str: str, dry_run: bool = False) -> int:
    """修复指定日期的论文内容"""
    # 延迟导入，避免在扫描时加载
    from src.core.generate_summary import (
        translate_summary,
        generate_summary,
        generate_inspiration_trace,
        generate_research_insights,
        generate_critical_evaluation,
        CacheManager,
    )
    from openai import OpenAI
    from dotenv import load_dotenv

    load_dotenv()

    json_file = SUMMARY_DIR / f"filtered_papers_{date_str}_with_summary2.json"
    if not json_file.exists():
        print(f"❌ 文件不存在: {json_file}")
        return 0

    with open(json_file, 'r', encoding='utf-8') as f:
        papers = json.load(f)

    # 初始化 OpenAI 客户端
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        timeout=180.0,
    )
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    cache_manager = CacheManager()

    fixed_count = 0
    modified = False

    for i, paper in enumerate(papers):
        arxiv_id = paper.get("arxiv_id", "unknown")
        title = paper.get("title", "")
        summary = paper.get("summary", "")

        needs_fix = []
        for field in FAILURE_PATTERNS.keys():
            if is_failed_content(paper.get(field, ""), field):
                needs_fix.append(field)

        if not needs_fix:
            continue

        print(f"\n🔧 修复 {arxiv_id}: {', '.join(needs_fix)}")

        if dry_run:
            continue

        try:
            # 修复翻译
            if "summary_translation" in needs_fix and summary:
                print(f"   - 翻译摘要...")
                translation = translate_summary(
                    summary, client, model, temperature,
                    title, cache_manager
                )
                if not is_failed_content(translation, "summary_translation"):
                    paper["summary_translation"] = translation
                    modified = True
                    print(f"   ✅ 翻译成功")

            # 修复灵感溯源
            if "inspiration_trace" in needs_fix and summary:
                print(f"   - 生成灵感溯源...")
                trace = generate_inspiration_trace(
                    summary, client, model, temperature,
                    title, cache_manager
                )
                if not is_failed_content(trace, "inspiration_trace"):
                    paper["inspiration_trace"] = trace
                    modified = True
                    print(f"   ✅ 灵感溯源成功")

            # 修复研究洞察
            if "research_insights" in needs_fix and summary:
                print(f"   - 生成研究洞察...")
                insights = generate_research_insights(
                    summary, client, model, temperature,
                    title, cache_manager
                )
                if not is_failed_content(insights, "research_insights"):
                    paper["research_insights"] = insights
                    modified = True
                    print(f"   ✅ 研究洞察成功")

            # 修复批判性评估
            if "critical_evaluation" in needs_fix and summary:
                print(f"   - 生成批判性评估...")
                evaluation = generate_critical_evaluation(
                    summary, client, model, temperature,
                    title, cache_manager
                )
                if not is_failed_content(evaluation, "critical_evaluation"):
                    paper["critical_evaluation"] = evaluation
                    modified = True
                    print(f"   ✅ 批判性评估成功")

            fixed_count += 1

        except Exception as e:
            print(f"   ❌ 修复失败: {e}")

    # 保存修改
    if modified and not dry_run:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"\n💾 已保存: {json_file}")

    return fixed_count


def fix_overview_for_date(date_str: str, dry_run: bool = False) -> bool:
    """修复指定日期的每日速览"""
    from src.core.generate_summary import (
        generate_daily_overview,
        CacheManager,
    )
    from openai import OpenAI
    from dotenv import load_dotenv

    load_dotenv()

    json_file = SUMMARY_DIR / f"filtered_papers_{date_str}_with_summary2.json"
    md_file = SUMMARY_DIR / f"daily_overview_{date_str}.md"

    if not json_file.exists():
        print(f"❌ 论文数据不存在: {json_file}")
        return False

    with open(json_file, 'r', encoding='utf-8') as f:
        papers = json.load(f)

    print(f"\n🔧 重新生成每日速览: {date_str}")

    if dry_run:
        return True

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    cache_manager = CacheManager()

    try:
        overview = generate_daily_overview(
            papers, client, model, temperature,
            date_str, cache_manager
        )

        if not is_overview_failed(overview):
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(overview)
            print(f"✅ 每日速览生成成功")
            return True
        else:
            print(f"❌ 每日速览仍然失败")
            return False

    except Exception as e:
        print(f"❌ 生成失败: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="修复已有数据中失败的内容"
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="扫描失败的内容（默认行为）"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="修复失败的内容"
    )
    parser.add_argument(
        "--date",
        help="指定日期 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示要修复的内容，不实际执行"
    )
    parser.add_argument(
        "--papers-only",
        action="store_true",
        help="只修复论文内容"
    )
    parser.add_argument(
        "--overview-only",
        action="store_true",
        help="只修复每日速览"
    )
    parser.add_argument(
        "--regenerate-index",
        action="store_true",
        help="修复后重新生成统一页面"
    )

    args = parser.parse_args()

    # 默认行为是扫描
    if not args.fix:
        args.scan = True

    if args.scan and not args.fix:
        print("🔍 扫描失败的内容...")
        results = scan_failed_papers(args.date)
        print_scan_results(results)

        if results["papers"] or results["overviews"]:
            print(f"\n💡 使用 --fix 参数来修复这些内容")
            print(f"   python fix_failed_content.py --fix")
        return

    if args.fix:
        print("🔧 开始修复失败的内容...")

        if args.dry_run:
            print("⚠️  Dry-run 模式，不会实际修改文件\n")

        results = scan_failed_papers(args.date)

        fixed_papers = 0
        fixed_overviews = 0

        # 修复论文内容
        if not args.overview_only and results["papers"]:
            for date in sorted(results["papers"].keys()):
                print(f"\n{'='*50}")
                print(f"📅 处理日期: {date}")
                print(f"{'='*50}")
                fixed_papers += fix_papers_for_date(date, args.dry_run)

        # 修复每日速览
        if not args.papers_only and results["overviews"]:
            for date in results["overviews"]:
                if fix_overview_for_date(date, args.dry_run):
                    fixed_overviews += 1

        # 重新生成统一页面
        if args.regenerate_index and not args.dry_run:
            print(f"\n{'='*50}")
            print("🔄 重新生成统一页面...")
            print(f"{'='*50}")
            import subprocess
            subprocess.run([
                sys.executable,
                "src/core/generate_unified_index.py"
            ], cwd=PROJECT_ROOT)

        # 总结
        print(f"\n{'='*50}")
        print("📊 修复完成总结")
        print(f"{'='*50}")
        print(f"✅ 修复论文: {fixed_papers} 篇")
        print(f"✅ 修复速览: {fixed_overviews} 天")


if __name__ == "__main__":
    main()
