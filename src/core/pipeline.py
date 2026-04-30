#!/usr/bin/env python3
"""
完整的学术论文处理流水线
Complete academic paper processing pipeline: crawl -> filter -> summarize -> generate webpages -> serve
"""

import os
import sys
import json
import argparse
import subprocess
import time
from datetime import datetime
from typing import List, Optional

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入配置
try:
    from src.utils.config import (
        API_KEY, BASE_URL, MODEL, FILTER_MODEL,
        CLUSTER_API_KEY, CLUSTER_BASE_URL, CLUSTER_MODEL,
        SUMMARY_API_KEY, SUMMARY_BASE_URL, SUMMARY_MODEL, SUMMARY_MODEL_CHAIN,
        SUMMARY_SJTU_API_KEY, SUMMARY_SJTU_BASE_URL,
        SUMMARY_PRISM_API_KEY, SUMMARY_PRISM_BASE_URL, SUMMARY_PRISM_RPM,
        SUMMARY_PRISM_REASONING_EFFORT,
        SUMMARY_MAX_WORKERS, FILTER_MAX_WORKERS, TEMPERATURE,
        ARXIV_PAPER_DIR, DOMAIN_PAPER_DIR, SUMMARY_DIR, WEBPAGES_DIR,
        CRAWL_CATEGORIES, MAX_PAPERS_PER_CATEGORY, MAX_WORKERS, MAX_PAPERS_TOTAL_DEFAULT
    )
except ImportError:
    raise ImportError("⚠️ 错误: 未找到config.py")

from src.utils.notify import notify_failures, notify_pipeline_complete
from src.utils.exceptions import ValidationError
from src.utils.validation import (
    validate_date_inputs,
    validate_non_negative_int,
    validate_positive_int,
)


def count_paper_records(json_path: Optional[str]) -> Optional[int]:
    """Count papers in either list-shaped pipeline files or generated page data."""
    if not json_path or not os.path.exists(json_path):
        return None

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None

    if isinstance(data, list):
        return len(data)

    if isinstance(data, dict):
        papers = data.get("papers")
        if isinstance(papers, list):
            return len(papers)

        clusters = data.get("clusters")
        if isinstance(clusters, list):
            return sum(
                len(cluster.get("papers", []))
                for cluster in clusters
                if isinstance(cluster, dict)
            )

    return None


def directory_has_json_files(directory: str) -> bool:
    """Return True when a pipeline data directory contains JSON candidates."""
    return os.path.exists(directory) and any(
        name.endswith(".json")
        for name in os.listdir(directory)
    )


class ProgressTracker:
    """进度跟踪器"""
    
    def __init__(self, total_steps: int = 6):
        self.total_steps = total_steps
        self.current_step = 0
        self.step_names = [
            "爬取arXiv论文",
            "筛选相关论文",
            "论文聚类",
            "生成论文总结",
            "生成统一页面",
            "启动本地服务器"
        ]
        self.start_time = time.time()
        
    def log_with_timestamp(self, message: str, level: str = "INFO"):
        """带时间戳的日志输出"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        elapsed = time.time() - self.start_time
        elapsed_str = f"{elapsed:.1f}s"
        print(f"[{timestamp}] [{elapsed_str:>6}] {message}")
    
    def start_step(self, step_name: str):
        """开始一个步骤"""
        self.current_step += 1
        step_progress = f"({self.current_step}/{self.total_steps})"
        self.log_with_timestamp(f"🔄 步骤{self.current_step}: {step_name} {step_progress}")
        print("-" * 50)
        
    def complete_step(self, step_name: str, success: bool = True):
        """完成一个步骤"""
        status = "✅ 完成" if success else "❌ 失败"
        self.log_with_timestamp(f"{status}: {step_name}")
        print()
        
    def skip_step(self, step_name: str):
        """跳过一个步骤"""
        self.current_step += 1
        self.log_with_timestamp(f"⏭️ 跳过步骤{self.current_step}: {step_name}")
        print()
        
    def show_summary(self):
        """显示总结"""
        total_time = time.time() - self.start_time
        self.log_with_timestamp(f"🎉 流水线执行完成! 总耗时: {total_time:.1f}秒")


def redact_command(cmd: List[str]) -> str:
    """Return a log-safe command string without secrets."""
    redacted = []
    redact_next = False
    for part in cmd:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        if part in {
            "--api-key",
            "--summary-api-key",
            "--summary-sjtu-api-key",
            "--summary-prism-api-key",
        }:
            redacted.append(part)
            redact_next = True
            continue
        if (
            part.startswith("--api-key=")
            or part.startswith("--summary-api-key=")
            or part.startswith("--summary-sjtu-api-key=")
            or part.startswith("--summary-prism-api-key=")
        ):
            key, _ = part.split("=", 1)
            redacted.append(f"{key}=<redacted>")
            continue
        redacted.append(part)
    return " ".join(redacted)


def run_command(cmd: List[str], description: str, progress_tracker: ProgressTracker = None) -> bool:
    """
    运行命令并处理结果
    
    Args:
        cmd: 要运行的命令列表
        description: 命令描述
        progress_tracker: 进度跟踪器
    
    Returns:
        bool: 是否成功
    """
    if progress_tracker:
        progress_tracker.log_with_timestamp(f"🔄 开始: {description}")
        progress_tracker.log_with_timestamp(f"   命令: {redact_command(cmd)}")
    else:
        print(f"🔄 {description}...")
        print(f"   命令: {redact_command(cmd)}")
    
    start_time = time.time()
    
    try:
        # 使用实时输出而不是捕获输出，这样可以看到进度条
        subprocess.run(cmd, text=True, check=True)
        duration = time.time() - start_time
        
        if progress_tracker:
            progress_tracker.log_with_timestamp(f"✅ 完成: {description} (耗时: {duration:.1f}秒)")
        else:
            print(f"✅ {description} 完成")
            
        return True
        
    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        
        if progress_tracker:
            progress_tracker.log_with_timestamp(f"❌ 失败: {description} (耗时: {duration:.1f}秒)")
            progress_tracker.log_with_timestamp(f"   错误码: {e.returncode}")
        else:
            print(f"❌ {description} 失败")
            print(f"   错误码: {e.returncode}")
            
        return False
        
    except Exception as e:
        duration = time.time() - start_time
        if progress_tracker:
            progress_tracker.log_with_timestamp(f"❌ 异常: {description} - {e} (耗时: {duration:.1f}秒)")
        else:
            print(f"❌ {description} 出错: {e}")
        return False



def find_latest_file(directory: str, pattern: str = "*.json") -> Optional[str]:
    """找到目录中最新的匹配文件，优先选择合并文件和筛选结果文件"""
    try:
        from glob import glob
        files = glob(os.path.join(directory, pattern))
        if not files:
            return None
        # domain_paper 优先 filtered_papers
        if 'domain_paper' in directory:
            filtered_files = [f for f in files if 'filtered_papers' in f and 'excluded' not in f]
            if filtered_files:
                return max(filtered_files, key=os.path.getmtime)
        # arxiv_paper 优先合并文件
        combined_files = [f for f in files if '_cs.' in f and f.count('_cs.') > 1]
        if combined_files:
            return max(combined_files, key=os.path.getmtime)
        return max(files, key=os.path.getmtime)
    except Exception as e:
        print(f"❌ 查找文件时出错: {e}")
        return None

def find_file_by_date(directory: str, date_str: str, pattern: str = "*.json") -> Optional[str]:
    """
    在目录中查找包含指定日期字符串的文件，优先选择 filtered/合并文件，找不到则 fallback 到最新。
    date_str: 格式 YYYY-MM-DD
    """
    from glob import glob
    files = glob(os.path.join(directory, pattern))
    if not files:
        return None
    # 先精确匹配日期
    date_files = [f for f in files if date_str in os.path.basename(f)]
    if date_files:
        # domain_paper 优先 filtered_papers
        if 'domain_paper' in directory:
            filtered_files = [f for f in date_files if 'filtered_papers' in f and 'excluded' not in f]
            if filtered_files:
                return max(filtered_files, key=os.path.getmtime)
        # arxiv_paper 优先合并文件
        if 'arxiv_paper' in directory:
            combined_files = [f for f in date_files if '_cs.' in f and f.count('_cs.') > 1]
            if combined_files:
                return max(combined_files, key=os.path.getmtime)
        return max(date_files, key=os.path.getmtime)
    # fallback: 依然按原有逻辑找最新
    return find_latest_file(directory, pattern)


def check_file_exists(filepath: str, description: str) -> bool:
    """检查文件是否存在"""
    if os.path.exists(filepath):
        print(f"✅ 找到{description}: {filepath}")
        return True
    else:
        print(f"❌ 未找到{description}: {filepath}")
        return False


def main() -> int:
    """主函数"""
    parser = argparse.ArgumentParser(description='完整的学术论文处理流水线')
    
    # 基本参数
    parser.add_argument('--api-key', default=API_KEY, help='API密钥')
    parser.add_argument('--base-url', default=BASE_URL, help='API基础URL')
    parser.add_argument('--model', default=MODEL, help='使用的模型')
    parser.add_argument('--summary-api-key', default=SUMMARY_API_KEY, help='总结生成API密钥')
    parser.add_argument('--summary-base-url', default=SUMMARY_BASE_URL, help='总结生成API基础URL')
    parser.add_argument('--summary-model', default=SUMMARY_MODEL, help='总结生成模型')
    parser.add_argument('--summary-model-chain', default=SUMMARY_MODEL_CHAIN, help='总结模型回退链')
    parser.add_argument('--summary-sjtu-api-key', default=SUMMARY_SJTU_API_KEY, help='总结SJTU兜底API密钥')
    parser.add_argument('--summary-sjtu-base-url', default=SUMMARY_SJTU_BASE_URL, help='总结SJTU兜底API基础URL')
    parser.add_argument('--summary-prism-api-key', default=SUMMARY_PRISM_API_KEY, help='Prism总结API密钥')
    parser.add_argument('--summary-prism-base-url', default=SUMMARY_PRISM_BASE_URL, help='Prism总结API基础URL')
    parser.add_argument('--summary-prism-rpm', type=int, default=SUMMARY_PRISM_RPM, help='Prism总结RPM限制')
    parser.add_argument('--summary-prism-reasoning-effort', default=SUMMARY_PRISM_REASONING_EFFORT,
                       help='Prism reasoning_effort 参数，留空则不传')
    parser.add_argument('--temperature', type=float, default=TEMPERATURE, help='生成温度')
    
    # 流程控制
    parser.add_argument('--skip-crawl', action='store_true', help='跳过爬取步骤')
    parser.add_argument('--skip-filter', action='store_true', help='跳过筛选步骤')
    parser.add_argument('--skip-summary', action='store_true', help='跳过总结步骤')
    parser.add_argument('--skip-unified', action='store_true', help='跳过统一页面生成步骤')
    parser.add_argument('--skip-cluster', action='store_true', help='跳过聚类步骤')
    parser.add_argument('--skip-serve', action='store_true', help='跳过启动服务器步骤')
    parser.add_argument('--start-from', choices=['crawl', 'filter', 'cluster', 'summary', 'unified', 'serve'], default=None,
                       help='从指定阶段开始执行，自动跳过之前的阶段')
    
    # 参数配置
    parser.add_argument('--categories', nargs='+', default=CRAWL_CATEGORIES,
                       help='要爬取的类别')
    parser.add_argument('--max-papers-per-category', type=int, default=MAX_PAPERS_PER_CATEGORY,
                       help='每个类别最大爬取数量')
    parser.add_argument('--max-papers-total', type=int, default=MAX_PAPERS_TOTAL_DEFAULT,
                       help='总共处理的最大论文数量')
    parser.add_argument('--max-workers', type=int, default=MAX_WORKERS,
                       help=f'最大线程数 (默认: {MAX_WORKERS})')
    parser.add_argument('--date', default=None,
                       help='指定日期 (格式: YYYY-MM-DD)，用于爬取特定日期的论文和组织网页')
    parser.add_argument('--start-date', default=None,
                       help='起始日期 (格式: YYYY-MM-DD)，与--end-date一起使用指定日期范围')
    parser.add_argument('--end-date', default=None,
                       help='结束日期 (格式: YYYY-MM-DD)，与--start-date一起使用指定日期范围')
    
    # 输入输出目录
    parser.add_argument('--crawl-input-file', help='爬取步骤的输入文件（如果跳过爬取）')
    parser.add_argument('--filter-input-file', help='筛选步骤的输入文件（如果跳过筛选）')
    
    args = parser.parse_args()

    try:
        validate_positive_int(args.max_papers_per_category, "--max-papers-per-category")
        validate_non_negative_int(args.max_papers_total, "--max-papers-total")
        validate_positive_int(args.max_workers, "--max-workers")
        validate_positive_int(args.summary_prism_rpm, "--summary-prism-rpm")
        args.date, args.start_date, args.end_date = validate_date_inputs(
            date=args.date,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    except ValidationError as exc:
        progress = ProgressTracker()
        progress.log_with_timestamp(f"❌ 参数校验失败: {exc}")
        return 2

    # 根据 --start-from 自动设置跳过标志
    stage_order = ['crawl', 'filter', 'cluster', 'summary', 'unified', 'serve']
    if args.start_from:
        try:
            start_idx = stage_order.index(args.start_from)
            if start_idx > 0:
                args.skip_crawl = True
            if start_idx > 1:
                args.skip_filter = True
            if start_idx > 2:
                args.skip_cluster = True
            if start_idx > 3:
                args.skip_summary = True
            if start_idx > 4:
                args.skip_unified = True
        except ValueError:
            pass
    
    # 初始化进度跟踪器
    progress = ProgressTracker()
    
    print("🚀 启动完整的学术论文处理流水线")
    print("=" * 60)
    progress.log_with_timestamp(f"🤖 使用模型: {args.model}")
    progress.log_with_timestamp(f"📝 总结模型链: {args.summary_model_chain}")
    progress.log_with_timestamp(f"📊 每类最大论文数: {args.max_papers_per_category}")
    progress.log_with_timestamp(f"🔢 总处理数量: {args.max_papers_total}")
    progress.log_with_timestamp(f"🧵 最大线程数: {args.max_workers}")
    
    # 处理日期参数
    use_date_range = args.start_date and args.end_date
    date_lookup_key = f"{args.start_date}_to_{args.end_date}" if use_date_range else args.date
    
    if use_date_range:
        progress.log_with_timestamp(f"📅 日期范围: {args.start_date} 到 {args.end_date}")
    elif args.date:
        progress.log_with_timestamp(f"📅 指定日期: {args.date}")
    else:
        progress.log_with_timestamp("📅 爬取模式: 最新论文")
    print("=" * 60)
    
    # 创建必要的目录
    for directory in [ARXIV_PAPER_DIR, DOMAIN_PAPER_DIR, SUMMARY_DIR, WEBPAGES_DIR]:
        os.makedirs(directory, exist_ok=True)
    
    # 记录处理的文件路径
    crawl_output_file = None
    filter_output_file = None
    cluster_output_file = None
    

    # ============ 步骤1: 爬取论文 ============
    if not args.skip_crawl:
        progress.start_step("爬取arXiv论文")
        cmd = [
            sys.executable, "src/core/crawl_arxiv.py",
            "--categories"] + args.categories + [
            "--max-papers", str(args.max_papers_per_category),
            "--output-dir", ARXIV_PAPER_DIR,
            "--delay", "1.0",
            "--max-workers", str(args.max_workers)
        ]
        if use_date_range:
            cmd.extend(["--start-date", args.start_date, "--end-date", args.end_date])
        elif args.date:
            cmd.extend(["--date", args.date])
        if not run_command(cmd, "爬取论文", progress):
            progress.complete_step("爬取论文", False)
            progress.log_with_timestamp("❌ 爬取失败，流水线终止")
            return 1
        # 按日期查找爬取文件
        if date_lookup_key:
            crawl_output_file = find_file_by_date(ARXIV_PAPER_DIR, date_lookup_key, "*.json")
        else:
            crawl_output_file = find_latest_file(ARXIV_PAPER_DIR, "*.json")
        if not crawl_output_file:
            progress.complete_step("爬取论文", False)
            progress.log_with_timestamp("❌ 未找到爬取输出文件")
            return 1
        progress.complete_step("爬取论文", True)
    else:
        progress.skip_step("爬取arXiv论文")
        crawl_output_file = args.crawl_input_file
        if not crawl_output_file or not check_file_exists(crawl_output_file, "爬取输入文件"):
            if date_lookup_key:
                crawl_output_file = find_file_by_date(ARXIV_PAPER_DIR, date_lookup_key, "*.json")
            else:
                crawl_output_file = find_latest_file(ARXIV_PAPER_DIR, "*.json")
            if not crawl_output_file:
                progress.log_with_timestamp("❌ 未找到可用的爬取文件")
                return 1
    progress.log_with_timestamp(f"📄 使用爬取文件: {crawl_output_file}")
    
    # ============ 步骤2: 筛选论文 ============
    if not args.skip_filter:
        progress.start_step("筛选相关论文")
        cmd = [
            sys.executable, "src/core/paper_filter.py",
            "--input-file", crawl_output_file,
            "--output-dir", DOMAIN_PAPER_DIR,
            "--api-key", args.api_key,
            "--base-url", args.base_url,
            "--model", FILTER_MODEL,
            "--temperature", str(args.temperature),
            "--max-papers", str(args.max_papers_total),
            "--max-workers", str(min(args.max_workers, FILTER_MAX_WORKERS))
        ]
        progress.log_with_timestamp(f"🔍 筛选使用模型: {FILTER_MODEL}")
        progress.log_with_timestamp(f"🧵 筛选并发: {min(args.max_workers, FILTER_MAX_WORKERS)}")
        if not run_command(cmd, "筛选论文", progress):
            progress.complete_step("筛选论文", False)
            progress.log_with_timestamp("❌ 筛选失败，流水线终止")
            return 1
        # 按日期查找筛选文件
        if date_lookup_key:
            filter_output_file = find_file_by_date(DOMAIN_PAPER_DIR, date_lookup_key, "*.json")
        else:
            filter_output_file = find_latest_file(DOMAIN_PAPER_DIR, "*.json")
        if not filter_output_file:
            progress.complete_step("筛选论文", False)
            progress.log_with_timestamp("❌ 未找到筛选输出文件")
            return 1
        progress.complete_step("筛选论文", True)
    else:
        progress.skip_step("筛选相关论文")
        filter_output_file = args.filter_input_file
        if not filter_output_file or not check_file_exists(filter_output_file, "筛选输入文件"):
            if date_lookup_key:
                filter_output_file = find_file_by_date(DOMAIN_PAPER_DIR, date_lookup_key, "*.json")
            else:
                filter_output_file = find_latest_file(DOMAIN_PAPER_DIR, "*.json")
            if not filter_output_file:
                progress.log_with_timestamp("❌ 未找到可用的筛选文件")
                return 1
    progress.log_with_timestamp(f"📄 使用筛选文件: {filter_output_file}")
    
    # 检查筛选结果
    zero_filtered_papers = False
    try:
        with open(filter_output_file, 'r', encoding='utf-8') as f:
            filtered_papers = json.load(f)
        progress.log_with_timestamp(f"📊 筛选后论文数量: {len(filtered_papers)}")

        if len(filtered_papers) == 0:
            zero_filtered_papers = True
            progress.log_with_timestamp("⚠️ 筛选后没有论文，跳过聚类和总结，继续生成页面与通知")
    except Exception as e:
        progress.log_with_timestamp(f"❌ 读取筛选文件失败: {e}")
        return 1

    # ============ 步骤3: 论文聚类 ============
    cluster_output_file = filter_output_file  # default fallback

    if zero_filtered_papers:
        progress.skip_step("论文聚类")
        progress.log_with_timestamp("📄 当前日期无筛选结果，直接使用筛选文件生成零结果页面")
    elif not args.skip_cluster:
        progress.start_step("论文聚类")
        cmd = [
            sys.executable, "src/core/cluster_papers.py",
            "--input-file", filter_output_file,
            "--output-dir", DOMAIN_PAPER_DIR,
            "--api-key", CLUSTER_API_KEY,
            "--base-url", CLUSTER_BASE_URL,
            "--model", CLUSTER_MODEL,
            "--temperature", str(args.temperature),
        ]
        progress.log_with_timestamp(f"🗂️ 聚类使用模型: {CLUSTER_MODEL}")
        if run_command(cmd, "论文聚类", progress):
            # Find the cluster output file
            from glob import glob
            cluster_files = glob(os.path.join(DOMAIN_PAPER_DIR, "clustered_*.json"))
            if date_lookup_key:
                date_cluster_files = [f for f in cluster_files if date_lookup_key in f]
                if date_cluster_files:
                    cluster_output_file = max(date_cluster_files, key=os.path.getmtime)
                elif cluster_files:
                    cluster_output_file = max(cluster_files, key=os.path.getmtime)
            elif cluster_files:
                cluster_output_file = max(cluster_files, key=os.path.getmtime)

            if cluster_output_file and os.path.exists(cluster_output_file):
                progress.log_with_timestamp(f"📄 聚类输出文件: {cluster_output_file}")
            else:
                cluster_output_file = filter_output_file
                progress.log_with_timestamp("⚠️ 未找到聚类输出文件，使用筛选文件继续")
            progress.complete_step("论文聚类", True)
        else:
            progress.complete_step("论文聚类", False)
            progress.log_with_timestamp("⚠️ 聚类失败，使用筛选文件继续")
            cluster_output_file = filter_output_file
            notify_failures("cluster", ["Clustering stage failed, falling back to filtered papers"])
    else:
        progress.skip_step("论文聚类")
        from glob import glob
        cluster_files = glob(os.path.join(DOMAIN_PAPER_DIR, "clustered_*.json"))
        if date_lookup_key:
            date_cluster_files = [f for f in cluster_files if date_lookup_key in f]
            if date_cluster_files:
                cluster_output_file = max(date_cluster_files, key=os.path.getmtime)
                progress.log_with_timestamp(f"📄 使用已有的聚类文件: {cluster_output_file}")
        elif cluster_files:
            cluster_output_file = max(cluster_files, key=os.path.getmtime)
            progress.log_with_timestamp(f"📄 使用已有的聚类文件: {cluster_output_file}")

    progress.log_with_timestamp(f"📄 使用聚类文件: {cluster_output_file}")

    # ============ 步骤4: 生成论文总结 ============
    summary_output_file = cluster_output_file  # 默认使用聚类后的文件

    if zero_filtered_papers:
        progress.skip_step("生成论文总结")
    elif not args.skip_summary:
        progress.start_step("生成论文总结")

        cmd = [
            sys.executable, "src/core/generate_summary.py",
            "--input-file", cluster_output_file,
            "--output-dir", SUMMARY_DIR,
            "--api-key", args.summary_api_key,
            "--base-url", args.summary_base_url,
            "--model", args.summary_model,
            "--model-chain", args.summary_model_chain,
            "--sjtu-api-key", args.summary_sjtu_api_key,
            "--sjtu-base-url", args.summary_sjtu_base_url,
            "--prism-api-key", args.summary_prism_api_key,
            "--prism-base-url", args.summary_prism_base_url,
            "--prism-rpm", str(args.summary_prism_rpm),
            "--prism-reasoning-effort", args.summary_prism_reasoning_effort,
            "--temperature", str(args.temperature),
            "--skip-existing",
            "--max-workers", str(min(args.max_workers, SUMMARY_MAX_WORKERS))
        ]
        
        if run_command(cmd, "生成论文总结", progress):
            # 查找生成的带有summary2的JSON文件
            cluster_filename = os.path.basename(cluster_output_file)
            name_without_ext = os.path.splitext(cluster_filename)[0]
            summary_output_filename = f"{name_without_ext}_with_summary2.json"
            summary_output_file = os.path.join(SUMMARY_DIR, summary_output_filename)

            if os.path.exists(summary_output_file):
                progress.log_with_timestamp(f"📄 使用带总结的文件: {summary_output_file}")
            else:
                progress.log_with_timestamp("⚠️ 未找到带总结的JSON文件，使用原始聚类文件")
                summary_output_file = cluster_output_file
            progress.complete_step("生成论文总结", True)
        else:
            progress.complete_step("生成论文总结", False)
            progress.log_with_timestamp("⚠️ 总结生成失败，但继续执行后续步骤")
            notify_failures("summary", ["Summary stage failed, falling back to clustered papers"])
    else:
        progress.skip_step("生成论文总结")
        # 如果跳过总结，尝试使用已存在的带summary2文件
        try:
            if cluster_output_file:
                cluster_filename = os.path.basename(cluster_output_file)
                name_without_ext = os.path.splitext(cluster_filename)[0]
                candidate = os.path.join(SUMMARY_DIR, f"{name_without_ext}_with_summary2.json")
                if os.path.exists(candidate):
                    summary_output_file = candidate
                    progress.log_with_timestamp(f"📄 使用已有的带总结文件: {summary_output_file}")
                else:
                    progress.log_with_timestamp("⚠️ 未找到匹配的带总结文件，使用当前聚类/筛选文件")
            else:
                progress.log_with_timestamp("⚠️ 无筛选文件可用于匹配总结，继续使用筛选文件")
        except Exception as e:
            progress.log_with_timestamp(f"⚠️ 检查已有总结文件时出错: {e}")
    
    # ============ 步骤5: 生成统一页面 ============
    unified_generation_ok = True
    if not args.skip_unified:
        progress.start_step("生成统一页面")
        
        try:
            # 检查必要文件
            if not os.path.exists("src/core/generate_unified_index.py"):
                progress.log_with_timestamp("❌ 未找到 src/core/generate_unified_index.py，无法生成页面")
                unified_generation_ok = False
                progress.complete_step("生成统一页面", False)
            elif not (
                directory_has_json_files(SUMMARY_DIR)
                or directory_has_json_files(DOMAIN_PAPER_DIR)
                or directory_has_json_files(os.path.join(WEBPAGES_DIR, "data"))
            ):
                progress.log_with_timestamp("❌ 未找到论文数据文件，无法生成页面")
                unified_generation_ok = False
                progress.complete_step("生成统一页面", False)
            else:
                # 运行统一页面生成脚本
                cmd = [sys.executable, "src/core/generate_unified_index.py"]
                
                if run_command(cmd, "生成统一页面", progress):
                    unified_page_path = os.path.join(WEBPAGES_DIR, "index.html")
                    if os.path.exists(unified_page_path):
                        progress.log_with_timestamp(f"✅ 统一页面已生成: {unified_page_path}")
                        progress.complete_step("生成统一页面", True)
                    else:
                        progress.log_with_timestamp("❌ 统一页面生成脚本运行成功但未找到输出文件")
                        unified_generation_ok = False
                        progress.complete_step("生成统一页面", False)
                else:
                    unified_generation_ok = False
                    progress.complete_step("生成统一页面", False)
        except Exception as e:
            progress.log_with_timestamp(f"❌ 统一页面生成失败: {e}")
            unified_generation_ok = False
            progress.complete_step("生成统一页面", False)
    else:
        progress.skip_step("生成统一页面")
    
    # ============ 步骤6: 启动本地服务器 ============
    if not args.skip_serve:
        progress.start_step("启动本地服务器")
        
        # 检查是否有网页文件
        if os.path.exists(WEBPAGES_DIR) and os.listdir(WEBPAGES_DIR):
            progress.log_with_timestamp("🚀 启动本地服务器，访问网页...")
            progress.log_with_timestamp(f"📂 网页目录: {WEBPAGES_DIR}")
            progress.log_with_timestamp("💡 按 Ctrl+C 停止服务器")
            
            # 直接调用服务器模块
            try:
                cmd = [sys.executable, "src/core/serve_webpages.py", "--webpages-dir", WEBPAGES_DIR]
                subprocess.run(cmd)
                progress.complete_step("启动本地服务器", True)
            except KeyboardInterrupt:
                progress.log_with_timestamp("\n🛑 服务器已停止")
                progress.complete_step("启动本地服务器", True)
        else:
            progress.log_with_timestamp("⚠️ 网页目录为空，跳过服务器启动")
            progress.complete_step("启动本地服务器", False)
    else:
        progress.skip_step("启动本地服务器")
    
    # ============ 完成总结 ============
    print("\n" + "=" * 60)
    progress.show_summary()
    print("📊 处理总结:")
    
    if crawl_output_file and os.path.exists(crawl_output_file):
        try:
            with open(crawl_output_file, 'r', encoding='utf-8') as f:
                crawl_papers = json.load(f)
            progress.log_with_timestamp(f"  📥 爬取论文: {len(crawl_papers)} 篇")
        except Exception:
            progress.log_with_timestamp(f"  📥 爬取文件: {crawl_output_file}")
    
    if filter_output_file and os.path.exists(filter_output_file):
        try:
            with open(filter_output_file, 'r', encoding='utf-8') as f:
                filter_papers = json.load(f)
            progress.log_with_timestamp(f"  🔍 筛选论文: {len(filter_papers)} 篇")
        except Exception:
            progress.log_with_timestamp(f"  🔍 筛选文件: {filter_output_file}")
    
    summary_count = None
    if summary_output_file and summary_output_file.endswith("_with_summary2.json"):
        summary_count = count_paper_records(summary_output_file)

    if summary_count is not None:
        progress.log_with_timestamp(f"  📝 生成总结: {summary_count} 篇")
    elif os.path.exists(SUMMARY_DIR):
        progress.log_with_timestamp("  📝 生成总结: 0 篇")
    
    if os.path.exists(WEBPAGES_DIR):
        webpage_dirs = len([d for d in os.listdir(WEBPAGES_DIR) if os.path.isdir(os.path.join(WEBPAGES_DIR, d))])
        progress.log_with_timestamp(f"  🌐 生成网页: {webpage_dirs} 个")
    
    print("\n📁 输出目录:")
    progress.log_with_timestamp(f"  - 爬取结果: {ARXIV_PAPER_DIR}")
    progress.log_with_timestamp(f"  - 筛选结果: {DOMAIN_PAPER_DIR}")
    progress.log_with_timestamp(f"  - 论文总结: {SUMMARY_DIR}")
    progress.log_with_timestamp(f"  - 交互网页: {WEBPAGES_DIR}")
    
    unified_page_path = os.path.join(WEBPAGES_DIR, "index.html")
    if os.path.exists(unified_page_path):
        progress.log_with_timestamp(f"  ✨ 统一页面: {unified_page_path}")
    
    print("\n🌐 手动启动服务器:")
    progress.log_with_timestamp(f"  python src/core/serve_webpages.py --webpages-dir {WEBPAGES_DIR}")
    
    # Send pipeline completion notification
    try:
        stats = {}
        crawled_count = count_paper_records(crawl_output_file)
        filtered_count = count_paper_records(filter_output_file)
        clustered_count = count_paper_records(cluster_output_file)
        if crawled_count is not None:
            stats['crawled'] = crawled_count
        if filtered_count is not None:
            stats['filtered'] = filtered_count
        if clustered_count is not None:
            stats['clustered'] = clustered_count
        if summary_count is not None:
            stats['summarized'] = summary_count
        notify_pipeline_complete(stats)
    except Exception:
        pass  # notification is best-effort

    print("\n✨ 流水线执行完成！")
    return 0 if unified_generation_ok else 1


if __name__ == "__main__":
    sys.exit(main())
