#!/usr/bin/env python3
"""
Simple HTTP server to serve the unified HTML page
"""

import http.server
import socketserver
import webbrowser
import os
from pathlib import Path

def main():
    PORT = 8000
    
    # Change to the project directory
    os.chdir(Path(__file__).parent)
    
    Handler = http.server.SimpleHTTPRequestHandler
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving unified HTML at http://localhost:{PORT}")
        print(f"访问 http://localhost:{PORT}/index.html 查看统一页面")
        print("按 Ctrl+C 停止服务器")
        
        # 自动打开浏览器
        try:
            webbrowser.open(f'http://localhost:{PORT}/index.html')
        except:
            pass
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止")

if __name__ == "__main__":
    main()
