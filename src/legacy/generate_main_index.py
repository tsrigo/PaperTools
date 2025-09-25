#!/usr/bin/env python3
"""
主索引页面生成脚本
Main index page generator for time-based webpage structure
"""

import os
import json
from datetime import datetime
from typing import List, Dict
from pathlib import Path

# 导入配置
try:
    from config import WEBPAGES_DIR, DATE_FORMAT, ENABLE_TIME_BASED_STRUCTURE
except ImportError:
    WEBPAGES_DIR = "webpages"
    DATE_FORMAT = "%Y-%m-%d"
    ENABLE_TIME_BASED_STRUCTURE = True

from cache_manager import get_available_dates


def generate_main_index(webpages_dir: str = WEBPAGES_DIR) -> None:
    """生成主索引页面"""
    if not os.path.exists(webpages_dir):
        print(f"❌ 网页目录不存在: {webpages_dir}")
        return
    
    # 获取可用日期
    available_dates = get_available_dates(webpages_dir) if ENABLE_TIME_BASED_STRUCTURE else []
    
    # 统计信息
    total_papers = 0
    date_stats = []
    
    if ENABLE_TIME_BASED_STRUCTURE and available_dates:
        # 如果有 summary 目录，尝试从其中的按日 JSON 统计更精确的论文数
        project_root = os.path.abspath(os.path.join(webpages_dir, os.pardir))
        summary_dir = os.path.join(project_root, "summary")
        for date in available_dates:
            date_dir = os.path.join(webpages_dir, date)
            index_exists = os.path.exists(os.path.join(date_dir, 'index.html'))
            paper_count = 0
            # 优先从 summary 中的当天 JSON 读取条目数
            if os.path.isdir(summary_dir):
                summary_json = os.path.join(summary_dir, f"filtered_papers_{date}_with_summary2.json")
                if os.path.exists(summary_json):
                    try:
                        with open(summary_json, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            # data 可能是 list 或 dict，统一为长度
                            paper_count = len(data) if isinstance(data, list) else len(list(data))
                    except Exception:
                        paper_count = 0
            # 如果 summary 不可用或读取失败，则回退到统计网页
            if paper_count == 0 and os.path.exists(date_dir):
                try:
                    # 优先解析当天 index.html 中的论文条目（data-arxiv-id 标记）
                    date_index_file = os.path.join(date_dir, 'index.html')
                    if os.path.exists(date_index_file):
                        try:
                            with open(date_index_file, 'r', encoding='utf-8', errors='ignore') as f:
                                html = f.read()
                            # 简单计数 data-arxiv-id 出现次数
                            paper_count = html.count('data-arxiv-id=')
                        except Exception:
                            paper_count = 0
                    # 若没有当天 index 或计数仍为 0，则回退统计子目录数量（另一种结构）
                    if paper_count == 0:
                        paper_count = len([d for d in os.listdir(date_dir)
                                          if os.path.isdir(os.path.join(date_dir, d)) and d != '__pycache__'])
                except Exception:
                    paper_count = 0

            date_stats.append({
                'date': date,
                'count': paper_count,
                'has_index': index_exists
            })
            total_papers += paper_count
    
    # 生成HTML
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>学术论文网页集合 - 主页</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.6;
            color: #1d1d1f;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px 20px;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 60px;
            color: white;
        }}
        
        .header h1 {{
            font-size: 4rem;
            font-weight: 700;
            margin-bottom: 20px;
            text-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }}
        
        .header p {{
            font-size: 1.3rem;
            opacity: 0.9;
            max-width: 600px;
            margin: 0 auto;
        }}
        
        .stats-overview {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 40px;
            margin-bottom: 40px;
            backdrop-filter: blur(20px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            text-align: center;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 30px;
            margin-top: 30px;
        }}
        
        .stat-item {{
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 16px;
            color: white;
            text-align: center;
        }}
        
        .stat-number {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 10px;
        }}
        
        .stat-label {{
            font-size: 1rem;
            opacity: 0.9;
        }}
        
        .dates-list {{
            max-width: 800px;
            margin: 30px auto 0;
        }}
        
        .date-item {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            backdrop-filter: blur(20px);
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
            transition: all 0.3s ease;
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-left: 4px solid #667eea;
        }}
        
        .date-item:hover {{
            transform: translateX(8px);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
            border-left-color: #764ba2;
        }}
        
        .date-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}
        
        .date-title {{
            font-size: 1.2rem;
            font-weight: 600;
            color: #1d1d1f;
            flex: 1;
        }}
        
        .date-index {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
            font-weight: 600;
            flex-shrink: 0;
        }}
        
        .date-meta {{
            display: flex;
            gap: 15px;
            align-items: center;
            margin-bottom: 15px;
            font-size: 0.9rem;
            color: #86868b;
        }}
        
        .paper-count {{
            background: #f5f5f7;
            color: #666;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }}
        
        .date-status {{
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        
        .status-indicator {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #34c759;
        }}
        
        .status-indicator.disabled {{
            background: #ff3b30;
        }}
        
        .date-actions {{
            display: flex;
            gap: 12px;
            align-items: center;
        }}
        
        .action-button {{
            padding: 8px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 500;
            font-size: 0.9rem;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }}
        
        .primary-button {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        
        .primary-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }}
        
        .disabled {{
            opacity: 0.5;
            pointer-events: none;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 60px;
            color: rgba(255, 255, 255, 0.8);
        }}
        
        .footer p {{
            margin-bottom: 10px;
        }}
        
        @media (max-width: 768px) {{
            .header h1 {{
                font-size: 2.5rem;
            }}
            
            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
            
            .dates-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 学术论文网页集合</h1>
            <p>基于AI生成的交互式学术论文网页，按时间组织，支持历史浏览</p>
        </div>
        
        <div class="stats-overview">
            <h2>📊 统计概览</h2>
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-number">{len(available_dates)}</div>
                    <div class="stat-label">处理天数</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{total_papers}</div>
                    <div class="stat-label">论文总数</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{len([d for d in date_stats if d['has_index']])}</div>
                    <div class="stat-label">可用日期</div>
                </div>
            </div>
        </div>
        
        <div class="dates-list">
"""
    
    # 添加日期项目（按时间倒序）
    for index, date_info in enumerate(date_stats, 1):
        date = date_info['date']
        count = date_info['count']
        has_index = date_info['has_index']
        
        # 格式化日期显示
        try:
            date_obj = datetime.strptime(date, DATE_FORMAT)
            formatted_date = date_obj.strftime('%Y年%m月%d日')
            weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][date_obj.weekday()]
            date_display = f"{formatted_date} {weekday}"
        except:
            date_display = date
        
        disabled_class = "" if has_index else "disabled"
        status_class = "" if has_index else "disabled"
        
        html_content += f"""
            <div class="date-item">
                <div class="date-header">
                    <div class="date-title">{date_display}</div>
                    <div class="date-index">{index}</div>
                </div>
                
                <div class="date-meta">
                    <div class="paper-count">{count} 篇论文</div>
                    <div class="date-status">
                        <div class="status-indicator {status_class}"></div>
                        {'网页可用' if has_index else '暂无网页'}
                    </div>
                </div>
                
                <div class="date-actions">
                    <a href="{date}/index.html" class="action-button primary-button {disabled_class}">
                        📅 {'浏览 ' + date if has_index else '暂无网页'}
                    </a>
                </div>
            </div>
"""
    
    html_content += f"""
        </div>
        
        <div class="footer">
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>🎯 时间划分 | 📋 智能缓存 | 🌐 交互式浏览</p>
        </div>
    </div>
</body>
</html>
"""
    
    # 保存主索引文件
    main_index_path = os.path.join(webpages_dir, 'index.html')
    try:
        with open(main_index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"✅ 已生成主索引页面: {main_index_path}")
        print(f"📊 统计: {len(available_dates)} 天，{total_papers} 篇论文")
    except Exception as e:
        print(f"❌ 生成主索引页面失败: {e}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='生成主索引页面')
    parser.add_argument('--webpages-dir', default=WEBPAGES_DIR,
                       help=f'网页目录 (默认: {WEBPAGES_DIR})')
    
    args = parser.parse_args()
    generate_main_index(args.webpages_dir)


if __name__ == "__main__":
    main()

