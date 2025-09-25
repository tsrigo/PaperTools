#!/usr/bin/env python3
"""
本地网页服务器
Local web server for serving generated academic paper webpages
"""

import os
import sys
import http.server
import socketserver
import webbrowser
import argparse
from pathlib import Path
import json
import urllib.parse
import shutil
import re

# 导入配置
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.config import WEBPAGES_DIR, ENABLE_TIME_BASED_STRUCTURE, DATE_FORMAT
from src.utils.cache_manager import get_available_dates


class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义HTTP请求处理器，添加CORS与简单API"""
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[{self.log_date_time_string()}] {format % args}")

    # ---- 简单的用户状态存取 ----
    def _state_file_for_date(self, date_str: str) -> str:
        # 状态文件保存在对应日期目录下
        return os.path.join('.', date_str, '.user_state.json')

    def _load_state(self, date_str: str) -> dict:
        state_file = self._state_file_for_date(date_str)
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"deleted_ids": [], "read_ids": []}
        return {"deleted_ids": [], "read_ids": []}

    def _save_state(self, date_str: str, state: dict) -> None:
        state_file = self._state_file_for_date(date_str)
        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 保存状态失败({date_str}): {e}")

    # ---- 预检请求 ----
    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    # ---- API: 获取状态 ----
    def _handle_get_state(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        date_str = params.get('date', [''])[0]
        if not date_str:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "missing date"}).encode('utf-8'))
            return
        state = self._load_state(date_str)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(state).encode('utf-8'))

    # ---- API: 删除论文 ----
    def _handle_delete(self, payload: dict):
        date_str = payload.get('date', '')
        arxiv_id = payload.get('arxiv_id', '')
        paper_dir = payload.get('paper_dir', '')  # 可选，若提供则删除该目录
        title = payload.get('title', '')  # 可选，用于尝试匹配目录
        if not date_str or not arxiv_id:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "missing date or arxiv_id"}).encode('utf-8'))
            return

        state = self._load_state(date_str)
        if arxiv_id not in state["deleted_ids"]:
            state["deleted_ids"].append(arxiv_id)
        # 同时从已读里移除它
        if arxiv_id in state.get("read_ids", []):
            state["read_ids"].remove(arxiv_id)
        self._save_state(date_str, state)

        # 删除对应目录（若提供且存在）
        deleted_dir = False
        if paper_dir:
            # 只允许删除日期目录下的子路径，避免越权
            safe_base = os.path.abspath(os.path.join('.', date_str))
            target_path = os.path.abspath(os.path.join('.', paper_dir))
            if target_path.startswith(safe_base) and os.path.isdir(target_path):
                try:
                    shutil.rmtree(target_path)
                    deleted_dir = True
                except Exception as e:
                    print(f"⚠️ 删除目录失败: {target_path}: {e}")
        else:
            # 未提供具体目录时，尝试在日期目录下根据标题猜测目录
            try:
                date_dir = os.path.abspath(os.path.join('.', date_str))
                if os.path.isdir(date_dir) and title:
                    # 生成安全标题（与生成逻辑相似）
                    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)[:100]
                    # 在日期目录下查找包含安全标题的子目录
                    for name in os.listdir(date_dir):
                        sub = os.path.join(date_dir, name)
                        if os.path.isdir(sub) and safe_title in name:
                            try:
                                shutil.rmtree(sub)
                                deleted_dir = True
                                break
                            except Exception as e:
                                print(f"⚠️ 删除推测目录失败: {sub}: {e}")
            except Exception as e:
                print(f"⚠️ 查找推测目录失败: {e}")

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "deleted_dir": deleted_dir}).encode('utf-8'))

    # ---- API: 勾选阅读状态 ----
    def _handle_toggle_read(self, payload: dict):
        date_str = payload.get('date', '')
        arxiv_id = payload.get('arxiv_id', '')
        read = bool(payload.get('read', False))
        if not date_str or not arxiv_id:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "missing date or arxiv_id"}).encode('utf-8'))
            return

        state = self._load_state(date_str)
        read_ids = set(state.get("read_ids", []))
        if read:
            read_ids.add(arxiv_id)
        else:
            read_ids.discard(arxiv_id)
        state["read_ids"] = sorted(read_ids)
        self._save_state(date_str, state)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode('utf-8'))

    def do_GET(self):
        if self.path.startswith('/api/state'):
            return self._handle_get_state()
        return super().do_GET()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0') or 0)
        try:
            body = self.rfile.read(length) if length > 0 else b''
            payload = json.loads(body.decode('utf-8') or '{}')
        except Exception:
            payload = {}

        if self.path == '/api/delete':
            return self._handle_delete(payload)
        if self.path == '/api/toggle-read':
            return self._handle_toggle_read(payload)

        self.send_response(404)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"error": "not found"}).encode('utf-8'))


def find_available_port(start_port: int = 8080, max_attempts: int = 100) -> int:
    """找到可用的端口"""
    import socket
    
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    
    raise RuntimeError(f"无法找到可用端口 (尝试范围: {start_port}-{start_port + max_attempts})")


def list_directory_contents(directory: str) -> None:
    """列出目录内容，支持时间导航显示"""
    if not os.path.exists(directory):
        print(f"❌ 目录不存在: {directory}")
        return
    
    print(f"📂 目录内容 ({directory}):")
    
    # 如果启用时间划分，首先显示可用日期
    if ENABLE_TIME_BASED_STRUCTURE:
        available_dates = get_available_dates(directory)
        if available_dates:
            print("📅 可用日期:")
            for date in available_dates[:10]:  # 只显示最近10天
                date_dir = os.path.join(directory, date)
                if os.path.exists(date_dir):
                    paper_count = len([d for d in os.listdir(date_dir) 
                                     if os.path.isdir(os.path.join(date_dir, d))])
                    index_exists = os.path.exists(os.path.join(date_dir, 'index.html'))
                    status = "✅" if index_exists else "❌"
                    print(f"  {status} {date} ({paper_count} 篇论文)")
            print()
    
    items = []
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        if os.path.isdir(item_path):
            # 检查是否有index.html
            index_file = os.path.join(item_path, 'index.html')
            if os.path.exists(index_file):
                items.append(f"  📄 {item}/ (有网页)")
            else:
                items.append(f"  📁 {item}/ (文件夹)")
        else:
            items.append(f"  📄 {item}")
    
    if items:
        print("📋 文件和文件夹:")
        for item in sorted(items)[:20]:  # 只显示前20项
            print(item)
        
        if len(items) > 20:
            print(f"  ... 还有 {len(items) - 20} 项")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='学术论文网页本地服务器')
    parser.add_argument('--webpages-dir', default=WEBPAGES_DIR,
                       help=f'网页文件目录 (默认: {WEBPAGES_DIR})')
    parser.add_argument('--port', type=int, default=0,
                       help='服务器端口，0表示自动选择 (默认: 0)')
    parser.add_argument('--no-browser', action='store_true',
                       help='不自动打开浏览器')
    parser.add_argument('--list-only', action='store_true',
                       help='仅列出目录内容，不启动服务器')
    parser.add_argument('--date', default=None,
                       help='指定要服务的日期目录 (格式: YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # 处理日期参数
    if args.date and ENABLE_TIME_BASED_STRUCTURE:
        try:
            # 验证日期格式
            from datetime import datetime
            datetime.strptime(args.date, DATE_FORMAT)
            # 构建日期目录路径
            date_dir = os.path.join(args.webpages_dir, args.date)
            if os.path.exists(date_dir):
                args.webpages_dir = date_dir
                print(f"📅 使用日期目录: {args.date}")
            else:
                print(f"❌ 日期目录不存在: {date_dir}")
                return
        except ValueError:
            print(f"❌ 无效的日期格式: {args.date}，应为 YYYY-MM-DD")
            return
    
    # 检查目录是否存在
    if not os.path.exists(args.webpages_dir):
        print(f"❌ 错误: 网页目录不存在: {args.webpages_dir}")
        print("💡 请先运行以下命令生成网页:")
        print("   python generate_webpage.py --input-file <论文文件> --output-dir webpages")
        return
    
    # 仅列出目录内容
    if args.list_only:
        list_directory_contents(args.webpages_dir)
        return
    
    # 切换到网页目录
    original_dir = os.getcwd()
    os.chdir(args.webpages_dir)
    
    # 检查是否有index.html
    if not os.path.exists('index.html'):
        print("⚠️ 警告: 未找到index.html文件")
        list_directory_contents('.')
        print()
    
    try:
        # 确定端口
        if args.port == 0:
            port = find_available_port()
        else:
            port = args.port
        
        # 创建HTTP服务器
        httpd = socketserver.TCPServer(("", port), CustomHTTPRequestHandler)
        
        print(f"🚀 正在启动本地服务器...")
        print(f"📍 服务器地址: http://localhost:{port}")
        print(f"📂 服务目录: {os.path.abspath('.')}")
        print(f"🛑 按 Ctrl+C 停止服务器")
        print("=" * 50)
        
        # 自动打开浏览器
        if not args.no_browser:
            try:
                webbrowser.open(f'http://localhost:{port}')
                print("🌐 已自动打开浏览器")
            except Exception as e:
                print(f"⚠️ 无法自动打开浏览器: {e}")
        
        # 启动服务器
        httpd.serve_forever()
        
    except KeyboardInterrupt:
        print("\n🛑 服务器已停止")
        httpd.shutdown()
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"❌ 端口 {port} 已被占用")
            if args.port == 0:
                print("💡 正在尝试其他端口...")
                try:
                    port = find_available_port(port + 1)
                    httpd = socketserver.TCPServer(("", port), CustomHTTPRequestHandler)
                    print(f"✅ 使用端口 {port}")
                    print(f"📍 服务器地址: http://localhost:{port}")
                    httpd.serve_forever()
                except Exception as retry_e:
                    print(f"❌ 重试失败: {retry_e}")
            else:
                print(f"💡 请尝试其他端口: python serve_webpages.py --port {port + 1}")
        else:
            print(f"❌ 启动服务器时出错: {e}")
    except Exception as e:
        print(f"❌ 未知错误: {e}")
    finally:
        # 恢复原目录
        os.chdir(original_dir)


if __name__ == "__main__":
    main()
