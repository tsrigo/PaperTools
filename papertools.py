#!/usr/bin/env python3
"""
PaperTools - 学术论文处理工具统一入口
Academic Paper Processing Tools - Unified Entry Point
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime

def check_python_version():
    """检查Python版本"""
    if sys.version_info < (3, 7):
        print("❌ 错误: 需要Python 3.7或更高版本")
        sys.exit(1)

def check_and_install_dependencies():
    """检查并自动安装缺失的依赖"""
    required_packages = {
        'requests': 'requests>=2.28.0',
        'bs4': 'beautifulsoup4>=4.11.0', 
        'openai': 'openai>=1.0.0',
        'tqdm': 'tqdm>=4.64.0',
        'dotenv': 'python-dotenv>=1.0.0'
    }
    
    missing_packages = []
    for package, pip_name in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(pip_name)
    
    if missing_packages:
        print(f"📦 检测到缺失的依赖包: {', '.join(missing_packages)}")
        print("🔄 正在自动安装...")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + missing_packages)
            print("✅ 依赖安装完成")
        except subprocess.CalledProcessError:
            print("❌ 自动安装失败，请手动运行: pip install -r requirements.txt")
            return False
    return True

def check_config():
    """检查配置文件"""
    if not os.path.exists('src/utils/config.py'):
        print("❌ 错误: 未找到src/utils/config.py文件")
        return False
    
    # 检查.env文件或环境变量
    if not os.path.exists('.env'):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key or api_key == 'your_api_key_here':
            print("⚠️  警告: 未找到.env文件，请确保设置了正确的API密钥")
            print("💡 建议: 复制.env.example为.env并填入你的API密钥")
    
    return True

def clean_cache():
    """清理缓存文件"""
    import shutil
    cache_dirs = ['cache', '__pycache__']
    temp_files = ['*.pyc', '*.pyo', '*.log']
    
    print("🧹 清理缓存文件...")
    for cache_dir in cache_dirs:
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            print(f"  ✅ 已删除: {cache_dir}/")
    
    # 清理Python缓存文件
    for root, dirs, files in os.walk('.'):
        for dir_name in dirs[:]:  # 使用切片复制避免修改正在遍历的列表
            if dir_name == '__pycache__':
                shutil.rmtree(os.path.join(root, dir_name))
                dirs.remove(dir_name)
                print(f"  ✅ 已删除: {os.path.join(root, dir_name)}/")
    
    print("🎉 缓存清理完成")

def serve_webpages():
    """启动网页服务器"""
    if os.path.exists('webpages/index.html'):
        print("🌐 启动网页服务器...")
        subprocess.run([sys.executable, 'src/core/serve_webpages.py'])
    elif os.path.exists('summary') and any(f.endswith('.json') for f in os.listdir('summary')):
        print("📄 未找到统一页面，正在生成...")
        subprocess.run([sys.executable, 'src/core/pipeline.py', '--start-from', 'unified', '--skip-serve'])
        if os.path.exists('webpages/index.html'):
            subprocess.run([sys.executable, 'src/core/serve_webpages.py'])
    else:
        print("❌ 错误: 未找到论文数据")
        print("💡 请先运行: python papertools.py run")

def run_pipeline(args):
    """运行完整流水线"""
    # 构建pipeline.py的参数
    cmd = [sys.executable, 'src/core/pipeline.py']
    
    # 根据模式设置默认参数
    if args.mode == 'quick':
        cmd.extend(['--max-papers-total', '10'])
    elif args.mode == 'full':
        cmd.extend(['--max-papers-total', '1000'])
    
    # 添加其他参数
    if args.date:
        cmd.extend(['--date', args.date])
    if args.categories:
        cmd.extend(['--categories'] + args.categories)
    if args.max_papers_total:
        cmd.extend(['--max-papers-total', str(args.max_papers_total)])
    if args.skip_serve:
        cmd.extend(['--skip-serve'])
    
    print("🚀 启动论文处理流水线...")
    subprocess.run(cmd)

def main():
    parser = argparse.ArgumentParser(
        description='🎓 PaperTools - 学术论文处理工具',
        epilog="""
使用示例:
  python papertools.py run                     # 全量模式：处理1000篇论文
  python papertools.py run --mode quick        # 快速模式：处理10篇论文  
  python papertools.py serve                   # 启动网页服务器
  python papertools.py clean                   # 清理缓存文件
  python papertools.py run --date 2025-09-24   # 处理指定日期论文
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # run 子命令
    run_parser = subparsers.add_parser('run', help='运行论文处理流水线')
    run_parser.add_argument('--mode', choices=['quick', 'full'], default='full',
                           help='运行模式: quick(10篇) 或 full(1000篇)')
    run_parser.add_argument('--date', help='处理指定日期的论文 (YYYY-MM-DD)')
    run_parser.add_argument('--categories', nargs='+', 
                           default=['cs.AI', 'cs.CL', 'cs.CV', 'cs.LG', 'cs.MA'],
                           help='论文类别')
    run_parser.add_argument('--max-papers-total', type=int, help='总处理数量')
    run_parser.add_argument('--skip-serve', action='store_true', help='跳过启动服务器步骤')
    
    # serve 子命令
    subparsers.add_parser('serve', help='启动网页服务器')
    
    # clean 子命令  
    subparsers.add_parser('clean', help='清理缓存文件')
    
    # check 子命令
    subparsers.add_parser('check', help='检查环境和依赖')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 基本检查
    check_python_version()
    
    if args.command == 'clean':
        clean_cache()
    elif args.command == 'check':
        print("🔍 检查环境...")
        deps_ok = check_and_install_dependencies()
        config_ok = check_config()
        if deps_ok and config_ok:
            print("✅ 环境检查通过")
        else:
            print("❌ 环境检查失败")
    elif args.command == 'serve':
        serve_webpages()
    elif args.command == 'run':
        if not check_and_install_dependencies():
            return
        if not check_config():
            return
        run_pipeline(args)

if __name__ == "__main__":
    main()
