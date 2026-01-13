#!/usr/bin/env python3
"""
自动修复缺失日期的数据
Auto-fix missing dates data up to today
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "webpages" / "data"
SUMMARY_DIR = PROJECT_ROOT / "summary"


def get_existing_dates():
    """获取已有数据的日期列表"""
    dates = set()

    # 从 webpages/data 目录获取
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("20*.json"):
            date_str = f.stem  # 2026-01-08
            dates.add(date_str)

    return dates


def get_missing_dates(start_date_str: str = None):
    """获取从最新数据日期到今天之间缺失的日期"""
    existing = get_existing_dates()

    if not existing:
        print("❌ 未找到任何已有数据")
        return []

    # 找到最新的日期
    latest_date = max(existing)
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"📅 已有数据最新日期: {latest_date}")
    print(f"📅 今天日期: {today}")

    # 如果指定了起始日期，使用指定的
    if start_date_str:
        start = datetime.strptime(start_date_str, "%Y-%m-%d")
    else:
        start = datetime.strptime(latest_date, "%Y-%m-%d") + timedelta(days=1)

    end = datetime.strptime(today, "%Y-%m-%d")

    # 生成日期范围内的所有工作日（周一到周五，arXiv 只在工作日更新）
    missing = []
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        weekday = current.weekday()

        # 跳过周末 (5=周六, 6=周日)
        if weekday < 5 and date_str not in existing:
            missing.append(date_str)

        current += timedelta(days=1)

    return missing


def check_date_data_exists(date_str: str) -> bool:
    """检查指定日期的数据是否已生成"""
    # 检查 summary 目录是否有该日期的文件
    summary_pattern = f"filtered_papers_{date_str}_with_summary2.json"
    summary_file = SUMMARY_DIR / summary_pattern
    return summary_file.exists()


def run_pipeline_for_date(date_str: str, max_retries: int = 2):
    """为指定日期运行流水线，支持重试"""
    print(f"\n{'='*50}")
    print(f"🔄 处理日期: {date_str}")
    print(f"{'='*50}")

    for attempt in range(max_retries):
        if attempt > 0:
            print(f"\n⚠️  第 {attempt + 1} 次重试...")

        cmd = [
            sys.executable,
            "papertools.py",
            "run",
            "--mode", "full",
            "--date", date_str,
            "--skip-serve"
        ]

        result = subprocess.run(cmd, cwd=PROJECT_ROOT)

        # 检查是否真正生成了数据文件
        if check_date_data_exists(date_str):
            print(f"✅ {date_str} 数据生成成功")
            return True
        else:
            print(f"⚠️  {date_str} 数据未生成，返回码: {result.returncode}")

    print(f"❌ {date_str} 处理失败（已重试 {max_retries} 次）")
    return False


def regenerate_index():
    """重新生成统一页面"""
    print(f"\n{'='*50}")
    print("🔄 重新生成统一页面...")
    print(f"{'='*50}")

    cmd = [sys.executable, "src/core/generate_unified_index.py"]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode == 0


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="自动修复缺失日期的数据"
    )
    parser.add_argument(
        "--start-date",
        help="指定起始日期 (YYYY-MM-DD)，默认从最新数据的下一天开始"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示缺失的日期，不实际运行"
    )
    parser.add_argument(
        "--regenerate-only",
        action="store_true",
        help="只重新生成统一页面，不爬取新数据"
    )

    args = parser.parse_args()

    print("🔍 检查缺失的日期...")

    if args.regenerate_only:
        regenerate_index()
        print("\n✅ 统一页面重新生成完成")
        return

    missing = get_missing_dates(args.start_date)

    if not missing:
        print("✅ 没有缺失的日期，数据已是最新")
        return

    print(f"\n📋 缺失的日期 ({len(missing)} 天):")
    for d in missing:
        print(f"   - {d}")

    if args.dry_run:
        print("\n💡 使用 --dry-run 模式，不实际运行")
        return

    # 逐个处理缺失的日期
    success_count = 0
    failed_dates = []

    for date_str in missing:
        try:
            if run_pipeline_for_date(date_str):
                success_count += 1
            else:
                failed_dates.append(date_str)
        except Exception as e:
            print(f"❌ 处理 {date_str} 时出错: {e}")
            failed_dates.append(date_str)

    # 重新生成统一页面
    regenerate_index()

    # 总结
    print(f"\n{'='*50}")
    print("📊 修复完成总结")
    print(f"{'='*50}")
    print(f"✅ 成功: {success_count} 天")
    if failed_dates:
        print(f"❌ 失败: {len(failed_dates)} 天")
        for d in failed_dates:
            print(f"   - {d}")

    print("\n💡 提示: 运行以下命令查看结果")
    print("   python papertools.py serve")


if __name__ == "__main__":
    main()
