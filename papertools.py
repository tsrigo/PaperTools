#!/usr/bin/env python3
"""
PaperTools - 学术论文处理工具统一入口
Academic Paper Processing Tools - Unified Entry Point
"""

import os
import sys
import subprocess
import argparse

from src.utils.config import (
    CRAWL_CATEGORIES,
    MAX_PAPERS_TOTAL_QUICK,
    MAX_PAPERS_TOTAL_FULL,
)

MIN_PYTHON_VERSION = (3, 10)
MIN_PYTHON_VERSION_TEXT = ".".join(str(part) for part in MIN_PYTHON_VERSION)


def check_python_version():
    """检查Python版本"""
    if sys.version_info < MIN_PYTHON_VERSION:
        print(f"❌ 错误: 需要Python {MIN_PYTHON_VERSION_TEXT}或更高版本")
        sys.exit(1)


def check_and_install_dependencies(install_missing: bool = False) -> bool:
    """Check required imports and optionally install missing runtime packages."""
    required_packages = {
        "requests": "requests>=2.28.0",
        "bs4": "beautifulsoup4>=4.11.0",
        "openai": "openai>=1.0.0",
        "tqdm": "tqdm>=4.64.0",
        "dotenv": "python-dotenv>=1.0.0",
    }

    missing_packages = []
    for package, pip_name in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(pip_name)

    if missing_packages:
        print(f"📦 检测到缺失的依赖包: {', '.join(missing_packages)}")
        if not install_missing:
            print("❌ 依赖缺失，未自动修改当前 Python 环境。")
            print("💡 请先运行: python -m pip install -e .")
            print("💡 或显式执行: papertools check --install-missing")
            return False

        print("🔄 正在按显式请求安装缺失依赖...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install"] + missing_packages
            )
            print("✅ 依赖安装完成")
        except subprocess.CalledProcessError:
            print("❌ 自动安装失败，请手动运行: python -m pip install -e .")
            return False
    return True


def check_config():
    """检查配置文件"""
    if not os.path.exists("src/utils/config.py"):
        print("❌ 错误: 未找到src/utils/config.py文件")
        return False

    # 检查.env文件或环境变量
    if not os.path.exists(".env"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            print("⚠️  警告: 未找到.env文件，请确保设置了正确的API密钥")
            print("💡 建议: 复制.env.example为.env并填入你的API密钥")

    return True


def report_document_extractor_statuses() -> bool:
    """Show which document-extraction providers are available locally."""
    try:
        from src.document_extraction import (
            get_provider_statuses,
            resolve_provider_chain,
        )
        from src.utils.config import DOCUMENT_EXTRACTOR_CHAIN
    except Exception as exc:
        print(f"⚠️  无法加载文档提取配置: {exc}")
        return False

    print("📄 文档提取 provider 状态:")
    statuses = get_provider_statuses(resolve_provider_chain(DOCUMENT_EXTRACTOR_CHAIN))
    available_local = False
    for status in statuses:
        state = "✅" if status.available else "⚪"
        print(f"  {state} {status.name}: {status.detail}")
        if status.available and status.name != "jina":
            available_local = True

    print(f"  🔗 provider chain: {DOCUMENT_EXTRACTOR_CHAIN}")
    if not available_local:
        print("  ℹ️  当前没有本地提取 provider，可继续使用 Jina 远程兜底。")
    return True


def clean_cache():
    """清理缓存文件"""
    import shutil

    cache_dirs = ["cache", "__pycache__"]

    print("🧹 清理缓存文件...")
    for cache_dir in cache_dirs:
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            print(f"  ✅ 已删除: {cache_dir}/")

    # 清理Python缓存文件
    for root, dirs, files in os.walk("."):
        for dir_name in dirs[:]:  # 使用切片复制避免修改正在遍历的列表
            if dir_name == "__pycache__":
                shutil.rmtree(os.path.join(root, dir_name))
                dirs.remove(dir_name)
                print(f"  ✅ 已删除: {os.path.join(root, dir_name)}/")

    print("🎉 缓存清理完成")


def validate_webpages_for_publication(webpages_dir: str = "webpages") -> bool:
    """Run the same publication validator used by CI and deployment."""
    validator = os.path.join("scripts", "validate_published_payloads.py")
    if not os.path.exists(validator):
        print(f"❌ 发布校验器不存在，拒绝启动网页服务器: {validator}")
        return False

    result = subprocess.run(
        [sys.executable, validator, "--webpages-dir", webpages_dir],
        check=False,
    )
    return result.returncode == 0


def start_web_server() -> int:
    """Start the local static server and return its exit code."""
    print("🌐 启动网页服务器...")
    result = subprocess.run([sys.executable, "src/core/serve_webpages.py"], check=False)
    return result.returncode


def serve_webpages() -> int:
    """启动网页服务器"""
    if os.path.exists("webpages/index.html"):
        if not validate_webpages_for_publication("webpages"):
            return 1
        return start_web_server()
    elif os.path.exists("summary") and any(
        f.endswith(".json") for f in os.listdir("summary")
    ):
        print("📄 未找到统一页面，正在生成...")
        result = subprocess.run(
            [
                sys.executable,
                "src/core/pipeline.py",
                "--start-from",
                "unified",
                "--skip-serve",
            ]
        )
        if result.returncode != 0:
            return result.returncode
        if os.path.exists("webpages/index.html"):
            if not validate_webpages_for_publication("webpages"):
                return 1
            return start_web_server()
        print("❌ 错误: 页面生成后仍未找到 webpages/index.html")
        return 1
    else:
        print("❌ 错误: 未找到论文数据")
        print("💡 请先运行: python papertools.py run")
        return 1


def run_pipeline(args) -> int:
    """运行完整流水线"""
    # 构建pipeline.py的参数
    cmd = [sys.executable, "src/core/pipeline.py"]

    # 根据模式设置默认参数
    if args.mode == "quick":
        cmd.extend(["--max-papers-total", str(MAX_PAPERS_TOTAL_QUICK)])
    elif args.mode == "full":
        cmd.extend(["--max-papers-total", str(MAX_PAPERS_TOTAL_FULL)])

    # 添加其他参数
    if args.date:
        cmd.extend(["--date", args.date])
    if args.start_date:
        cmd.extend(["--start-date", args.start_date])
    if args.end_date:
        cmd.extend(["--end-date", args.end_date])
    if args.categories:
        cmd.extend(["--categories"] + args.categories)
    if args.max_papers_total:
        cmd.extend(["--max-papers-total", str(args.max_papers_total)])
    if args.max_papers_per_category:
        cmd.extend(["--max-papers-per-category", str(args.max_papers_per_category)])
    if args.max_workers:
        cmd.extend(["--max-workers", str(args.max_workers)])
    if args.start_from:
        cmd.extend(["--start-from", args.start_from])
    if args.skip_crawl:
        cmd.extend(["--skip-crawl"])
    if args.skip_filter:
        cmd.extend(["--skip-filter"])
    if args.skip_cluster:
        cmd.extend(["--skip-cluster"])
    if args.skip_summary:
        cmd.extend(["--skip-summary"])
    if args.skip_unified:
        cmd.extend(["--skip-unified"])
    if args.skip_serve:
        cmd.extend(["--skip-serve"])
    if args.status_file:
        cmd.extend(["--status-file", args.status_file])

    print("🚀 启动论文处理流水线...")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="🎓 PaperTools - 学术论文处理工具",
        epilog="""
使用示例:
  python papertools.py run                     # 全量模式：处理1000篇论文
  python papertools.py run --mode quick        # 快速模式：处理10篇论文
  python papertools.py serve                   # 启动网页服务器
  python papertools.py clean                   # 清理缓存文件
  python papertools.py run --date 2025-09-24   # 处理指定日期论文
  python papertools.py run --start-date 2025-09-22 --end-date 2025-09-24
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # run 子命令
    run_parser = subparsers.add_parser("run", help="运行论文处理流水线")
    run_parser.add_argument(
        "--mode",
        choices=["quick", "full"],
        default="full",
        help=f"运行模式: quick({MAX_PAPERS_TOTAL_QUICK}篇) 或 full({MAX_PAPERS_TOTAL_FULL}篇)",
    )
    run_parser.add_argument("--date", help="处理指定日期的论文 (YYYY-MM-DD)")
    run_parser.add_argument("--start-date", help="处理日期范围起始日期 (YYYY-MM-DD)")
    run_parser.add_argument("--end-date", help="处理日期范围结束日期 (YYYY-MM-DD)")
    run_parser.add_argument(
        "--categories", nargs="+", default=CRAWL_CATEGORIES, help="论文类别"
    )
    run_parser.add_argument(
        "--max-papers-per-category", type=int, help="每个类别最大爬取数量"
    )
    run_parser.add_argument("--max-papers-total", type=int, help="总处理数量")
    run_parser.add_argument("--max-workers", type=int, help="最大线程数")
    run_parser.add_argument(
        "--start-from",
        choices=["crawl", "filter", "cluster", "summary", "unified", "serve"],
        help="从指定阶段开始执行",
    )
    run_parser.add_argument("--skip-crawl", action="store_true", help="跳过爬取步骤")
    run_parser.add_argument("--skip-filter", action="store_true", help="跳过筛选步骤")
    run_parser.add_argument("--skip-cluster", action="store_true", help="跳过聚类步骤")
    run_parser.add_argument("--skip-summary", action="store_true", help="跳过总结步骤")
    run_parser.add_argument(
        "--skip-unified", action="store_true", help="跳过统一页面生成步骤"
    )
    run_parser.add_argument(
        "--skip-serve", action="store_true", help="跳过启动服务器步骤"
    )
    run_parser.add_argument("--status-file", help="写入结构化流水线状态 JSON")

    # serve 子命令
    subparsers.add_parser("serve", help="启动网页服务器")

    # clean 子命令
    subparsers.add_parser("clean", help="清理缓存文件")

    # check 子命令
    check_parser = subparsers.add_parser("check", help="检查环境和依赖")
    check_parser.add_argument(
        "--install-missing",
        action="store_true",
        help="显式安装缺失的基础运行时依赖",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # 基本检查
    check_python_version()

    if args.command == "clean":
        clean_cache()
        return 0
    elif args.command == "check":
        print("🔍 检查环境...")
        deps_ok = check_and_install_dependencies(install_missing=args.install_missing)
        config_ok = check_config()
        providers_ok = report_document_extractor_statuses()
        if deps_ok and config_ok and providers_ok:
            print("✅ 环境检查通过")
            return 0
        else:
            print("❌ 环境检查失败")
            return 1
    elif args.command == "serve":
        return serve_webpages()
    elif args.command == "run":
        if not check_and_install_dependencies():
            return 1
        if not check_config():
            return 1
        return run_pipeline(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
