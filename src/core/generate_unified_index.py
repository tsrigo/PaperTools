#!/usr/bin/env python3
"""
独立的统一HTML页面生成脚本
不依赖外部模板，直接生成完整的HTML页面
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any

# 导入配置
try:
    from src.utils.config import SUMMARY_DIR, WEBPAGES_DIR
except ImportError:
    SUMMARY_DIR = "summary"
    WEBPAGES_DIR = "webpages"

# 分页配置
INITIAL_DAYS = 3  # 初始加载的天数（其余通过"加载更多"按需加载）
LOAD_MORE_DAYS = 7  # 每次"加载更多"加载的天数

def load_paper_data() -> Dict[str, List[Dict[str, Any]]]:
    """加载论文数据"""
    papers_by_date = {}
    summary_dir = Path(SUMMARY_DIR)

    for json_file in summary_dir.glob("*_with_summary2.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                papers = json.load(f)

            filename = json_file.stem
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
            if date_match:
                date = date_match.group(1)
                if date in papers_by_date and len(papers_by_date[date]) >= len(papers):
                    continue
                papers_by_date[date] = papers
                print(f"加载了 {len(papers)} 篇论文，日期: {date}")
        except Exception as e:
            print(f"加载文件 {json_file} 时出错: {e}")

    return papers_by_date


def load_daily_overviews() -> Dict[str, str]:
    """加载每日AI论文速览"""
    overviews = {}
    summary_dir = Path(SUMMARY_DIR)

    # 查找所有的每日速览Markdown文件
    for md_file in summary_dir.glob("daily_overview_*.md"):
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 从文件名提取日期
            filename = md_file.stem
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
            if date_match:
                date = date_match.group(1)
                overviews[date] = content
                print(f"加载了每日速览，日期: {date}")
        except Exception as e:
            print(f"加载每日速览文件 {md_file} 时出错: {e}")

    return overviews

def escape_js_string(text: str) -> str:
    """转义JavaScript字符串"""
    if not text:
        return ""
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def organize_papers_by_cluster(papers: List[Dict]) -> List[Dict]:
    """将论文按聚类组织，按论文数量降序排列"""
    clusters = {}
    for paper in papers:
        cluster = paper.get('cluster', 'Other')
        if cluster not in clusters:
            clusters[cluster] = []
        clusters[cluster].append(paper)
    result = []
    for cluster_name, cluster_papers in sorted(clusters.items(), key=lambda x: (-len(x[1]), x[0])):
        result.append({
            "name": cluster_name,
            "count": len(cluster_papers),
            "papers": cluster_papers
        })
    return result


def collect_all_tags(papers: List[Dict]) -> List[Dict]:
    """Collect all unique tags with counts for the tag filter bar.
    arXiv category tags (cs.XX) are listed first, then cluster tags."""
    arxiv_counts = {}
    cluster_counts = {}
    for paper in papers:
        tags = paper.get('tags', []) or []
        cluster = paper.get('cluster', 'Other')
        cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
        for tag in tags:
            arxiv_counts[tag] = arxiv_counts.get(tag, 0) + 1
    result = []
    # arXiv categories first (e.g. cs.AI, cs.LG)
    for tag, count in sorted(arxiv_counts.items(), key=lambda x: (-x[1], x[0])):
        result.append({"name": tag, "count": count})
    # Then cluster names
    for tag, count in sorted(cluster_counts.items(), key=lambda x: (-x[1], x[0])):
        result.append({"name": tag, "count": count})
    return result


def save_date_data_files(papers_by_date: Dict, daily_overviews: Dict) -> List[str]:
    """将每个日期的数据保存为独立的 JSON 文件"""
    data_dir = Path(WEBPAGES_DIR) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    all_dates = sorted(papers_by_date.keys(), reverse=True)

    for date in all_dates:
        papers = papers_by_date[date]
        organized = organize_papers_by_cluster(papers)
        tags = collect_all_tags(papers)

        date_data = {
            "date": date,
            "clusters": organized,
            "tags": tags,
            "overview": daily_overviews.get(date, "")
        }

        date_file = data_dir / f"{date}.json"
        with open(date_file, 'w', encoding='utf-8') as f:
            json.dump(date_data, f, ensure_ascii=False)
        print(f"保存数据文件: {date_file}")

    # 生成日期索引文件
    index_data = {
        "dates": all_dates,
        "initial_days": INITIAL_DAYS,
        "load_more_days": LOAD_MORE_DAYS
    }
    index_file = data_dir / "index.json"
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"保存索引文件: {index_file}")

    return all_dates

def generate_complete_html() -> str:
    """生成完整的HTML页面"""
    papers_by_date = load_paper_data()
    daily_overviews = load_daily_overviews()

    # 保存所有日期的数据到独立文件
    all_dates = save_date_data_files(papers_by_date, daily_overviews)

    # 只取最近 INITIAL_DAYS 天的数据嵌入 HTML
    initial_dates = all_dates[:INITIAL_DAYS]

    # 生成JavaScript数据 - 只包含初始数据
    js_data = "const allPapers = {\n"
    for date in initial_dates:
        papers = papers_by_date.get(date, [])
        organized = organize_papers_by_cluster(papers)

        js_data += f'    "{date}": [\n'
        for cluster_info in organized:
            js_data += "        {\n"
            js_data += f'            "name": "{escape_js_string(cluster_info["name"])}",\n'
            js_data += f'            "count": {cluster_info["count"]},\n'
            js_data += '            "papers": [\n'

            for paper in cluster_info["papers"]:
                tags_json = json.dumps(paper.get("tags", []), ensure_ascii=False)
                js_data += "                {\n"
                js_data += f'                    "title": "{escape_js_string(paper.get("title", ""))}",\n'
                js_data += f'                    "arxiv_id": "{escape_js_string(paper.get("arxiv_id", ""))}",\n'
                js_data += f'                    "authors": "{escape_js_string(paper.get("authors", ""))}",\n'
                js_data += f'                    "summary": "{escape_js_string(paper.get("summary", ""))}",\n'
                js_data += f'                    "category": "{escape_js_string(paper.get("category", ""))}",\n'
                js_data += f'                    "cluster": "{escape_js_string(paper.get("cluster", "Other"))}",\n'
                js_data += f'                    "tags": {tags_json},\n'
                js_data += f'                    "filter_reason": "{escape_js_string(paper.get("filter_reason", ""))}",\n'
                js_data += f'                    "intro_logic": "{escape_js_string(paper.get("intro_logic", ""))}",\n'
                js_data += f'                    "core_insight": "{escape_js_string(paper.get("core_insight", ""))}",\n'
                js_data += f'                    "methodology": "{escape_js_string(paper.get("methodology", ""))}",\n'
                js_data += f'                    "additional_insights": "{escape_js_string(paper.get("additional_insights", ""))}",\n'
                js_data += f'                    "research_value": "{escape_js_string(paper.get("research_value", ""))}",\n'
                js_data += f'                    "affiliations": "{escape_js_string(paper.get("affiliations", ""))}",\n'
                js_data += f'                    "summary_translation": "{escape_js_string(paper.get("summary_translation", ""))}"\n'
                js_data += "                },\n"

            js_data += "            ]\n"
            js_data += "        },\n"
        js_data += "    ],\n"
    js_data += "};\n\n"

    # 生成 allPaperTags 数据
    js_data += "const allPaperTags = {\n"
    for date in initial_dates:
        papers = papers_by_date.get(date, [])
        tags = collect_all_tags(papers)
        tags_json = json.dumps(tags, ensure_ascii=False)
        js_data += f'    "{date}": {tags_json},\n'
    js_data += "};\n\n"

    # 添加所有可用日期列表（用于按需加载）
    js_data += f"const availableDates = {json.dumps(all_dates)};\n"
    js_data += f"const loadedDates = new Set({json.dumps(initial_dates)});\n"
    js_data += f"const LOAD_MORE_DAYS = {LOAD_MORE_DAYS};\n\n"

    # 添加每日速览数据 - 只包含初始数据
    js_data += "const dailyOverviewsRaw = {\n"
    for date in initial_dates:
        overview = daily_overviews.get(date, "")
        if overview:
            js_data += f'    "{date}": {json.dumps(overview)},\n'
    js_data += "};\n"
    # 在客户端，我们再将解析后的字符串赋值给 dailyOverviews
    js_data += "const dailyOverviews = {};\n"
    js_data += "for (const date in dailyOverviewsRaw) {\n"
    js_data += "    dailyOverviews[date] = dailyOverviewsRaw[date];\n"
    js_data += "}\n"

    # 完整的HTML模板
    html_template = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PaperTools - 学术论文集合</title>
    <!-- 引入 Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- 引入 Marked.js 用于 Markdown 渲染 -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        /* 微软雅黑字体 */
        body {{
            font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
            -ms-overflow-style: none;  /* IE and Edge */
            scrollbar-width: none;  /* Firefox */
        }}
        body::-webkit-scrollbar {{
            display: none;
        }}

        /* 移动端优化 */
        @media (max-width: 640px) {{
            body {{
                font-size: 14px;
            }}

            /* 改善可点击区域 */
            button, a {{
                min-height: 44px;
                min-width: 44px;
            }}

            /* 优化间距 */
            .container {{
                padding-left: 12px !important;
                padding-right: 12px !important;
            }}
        }}

        /* 星标样式 */
        .star-button {{
            transition: color 0.2s ease-in-out;
        }}
        .star-button.starred {{
            color: #fbbf24;
        }}
        .star-button:not(.starred) {{
            color: #9ca3af;
        }}
        .star-button:hover {{
            color: #fbbf24;
        }}
        /* 删除按钮样式 */
        .delete-button {{
            transition: all 0.2s ease-in-out;
        }}
        .delete-button:hover {{
            color: #ef4444;
            transform: scale(1.1);
        }}
        /* 论文项目样式 */
        .paper-item {{
            transition: all 0.3s ease-in-out;
        }}
        .paper-item.hidden-paper {{
            opacity: 0.3;
            transform: scale(0.98);
        }}
        /* 平滑过渡 */
        .rotate-90-transition {{
            transition: transform 0.2s ease-in-out;
        }}

        /* 可折叠部分样式 */
        .collapsible-header {{
            cursor: pointer;
            display: flex;
            align-items: center;
            font-weight: 600;
            padding: 8px 0;
            user-select: none;
            color: #1e40af;
            transition: all 0.2s ease-in-out;
        }}
        .dark .collapsible-header {{
            color: #60a5fa;
        }}
        .collapsible-header:hover {{
            opacity: 0.8;
        }}
        .collapsible-header::before {{
            content: "▶";
            margin-right: 8px;
            transition: transform 0.3s ease;
            font-size: 0.8em;
        }}
        .collapsible-header.open::before {{
            transform: rotate(90deg);
        }}
        .collapsible-content {{
            display: none;
        }}
        .collapsible-content.open {{
            display: block;
        }}
        .collapsible-content .inner {{
            padding-top: 8px;
        }}

        /* Markdown 内容样式 */
        .markdown-content {{
            line-height: 1.6;
        }}
        .markdown-content h1 {{
            font-size: 1.5em;
            font-weight: bold;
            margin-top: 1em;
            margin-bottom: 0.5em;
            color: #1e40af;
        }}
        .dark .markdown-content h1 {{
            color: #60a5fa;
        }}
        .markdown-content h2 {{
            font-size: 1.3em;
            font-weight: bold;
            margin-top: 0.8em;
            margin-bottom: 0.4em;
            color: #1e40af;
        }}
        .dark .markdown-content h2 {{
            color: #60a5fa;
        }}
        .markdown-content h3 {{
            font-size: 1.1em;
            font-weight: bold;
            margin-top: 0.6em;
            margin-bottom: 0.3em;
            color: #1e40af;
        }}
        .dark .markdown-content h3 {{
            color: #60a5fa;
        }}
        .markdown-content h4 {{
            font-size: 1em;
            font-weight: bold;
            margin-top: 0.5em;
            margin-bottom: 0.25em;
            color: #2563eb;
        }}
        .dark .markdown-content h4 {{
            color: #93c5fd;
        }}
        .markdown-content p {{
            margin-bottom: 0.8em;
        }}
        .markdown-content ul, .markdown-content ol {{
            margin-left: 1.5em;
            margin-bottom: 0.8em;
        }}
        .markdown-content ul {{
            list-style-type: disc;
        }}
        .markdown-content ol {{
            list-style-type: decimal;
        }}
        .markdown-content li {{
            margin-bottom: 0.3em;
        }}
        .markdown-content code {{
            background-color: #f1f5f9;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-family: monospace;
            font-size: 0.9em;
        }}
        .dark .markdown-content code {{
            background-color: #334155;
        }}
        .markdown-content pre {{
            background-color: #f1f5f9;
            padding: 1em;
            border-radius: 5px;
            overflow-x: auto;
            margin-bottom: 0.8em;
        }}
        .dark .markdown-content pre {{
            background-color: #334155;
        }}
        .markdown-content pre code {{
            background-color: transparent;
            padding: 0;
        }}
        .markdown-content blockquote {{
            border-left: 3px solid #cbd5e1;
            padding-left: 1em;
            margin-left: 0;
            margin-bottom: 0.8em;
            color: #64748b;
        }}
        .dark .markdown-content blockquote {{
            border-left-color: #475569;
            color: #94a3b8;
        }}
        .markdown-content strong {{
            font-weight: 600;
        }}
        .markdown-content em {{
            font-style: italic;
        }}

        /* Tag filter button styles */
        .tag-btn {{
            padding: 4px 14px;
            font-size: 0.875rem;
            border-radius: 9999px;
            border: 1px solid #cbd5e1;
            background: transparent;
            color: #64748b;
            cursor: pointer;
            transition: all 0.15s;
            white-space: nowrap;
        }}
        .tag-btn:hover {{ border-color: #3b82f6; color: #3b82f6; }}
        .tag-btn.active {{ background: #3b82f6; color: white; border-color: #3b82f6; }}
        .dark .tag-btn {{ border-color: #475569; color: #94a3b8; }}
        .dark .tag-btn:hover {{ border-color: #60a5fa; color: #60a5fa; }}
        .dark .tag-btn.active {{ background: #2563eb; color: white; border-color: #2563eb; }}

        /* Tag badge styles */
        .tag-badge {{
            display: inline-block;
            padding: 1px 6px;
            font-size: 0.7rem;
            border-radius: 9999px;
            background: #dbeafe;
            color: #1e40af;
            margin-right: 4px;
        }}
        .tag-badge.tag-arxiv {{
            background: #e0f2fe;
            color: #0369a1;
        }}
        .dark .tag-badge {{ background: #1e3a5f; color: #7dd3fc; }}
        .dark .tag-badge.tag-arxiv {{ background: #164e63; color: #67e8f9; }}

        /* 作者机构上标样式 */
        .author-aff {{
            vertical-align: super;
            font-size: 0.65em;
            color: #3b82f6;
            margin-left: 1px;
        }}
        .dark .author-aff {{
            color: #60a5fa;
        }}

        /* TOC 侧边栏样式 - 固定在左侧 */
        #toc-sidebar {{
            position: fixed;
            left: 0;
            top: 0;
            width: 220px;
            height: 100vh;
            z-index: 35;
            background: white;
            border-right: 1px solid #e2e8f0;
            transition: transform 0.3s ease;
            overflow: hidden;
        }}
        .dark #toc-sidebar {{
            background: #1e293b;
            border-right-color: #334155;
        }}
        #toc-sidebar.collapsed {{
            transform: translateX(-100%);
        }}
        #toc-inner {{
            padding: 1rem 0.5rem;
            height: 100%;
            overflow-y: auto;
            scrollbar-width: thin;
        }}
        #toc-inner::-webkit-scrollbar {{
            width: 4px;
        }}
        #toc-inner::-webkit-scrollbar-thumb {{
            background: #cbd5e1;
            border-radius: 2px;
        }}
        .dark #toc-inner::-webkit-scrollbar-thumb {{
            background: #475569;
        }}
        .toc-date {{
            cursor: pointer;
            padding: 6px 10px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.875rem;
            transition: background 0.15s;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .toc-date:hover {{
            background: #e2e8f0;
        }}
        .dark .toc-date:hover {{
            background: #334155;
        }}
        .toc-date.active {{
            background: #dbeafe;
            color: #1e40af;
        }}
        .dark .toc-date.active {{
            background: #1e3a5f;
            color: #93c5fd;
        }}
        .toc-date-arrow {{
            transition: transform 0.2s;
            font-size: 0.65rem;
        }}
        .toc-date-arrow.open {{
            transform: rotate(90deg);
        }}
        .toc-papers {{
            display: none;
            padding-left: 1.2rem;
        }}
        .toc-papers.open {{
            display: block;
        }}
        .toc-paper {{
            cursor: pointer;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 0.8rem;
            line-height: 1.4;
            color: #64748b;
            transition: background 0.15s, color 0.15s;
            display: block;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 100%;
        }}
        .toc-paper:hover {{
            background: #f1f5f9;
            color: #1e40af;
        }}
        .dark .toc-paper {{
            color: #94a3b8;
        }}
        .dark .toc-paper:hover {{
            background: #1e293b;
            color: #93c5fd;
        }}
        .toc-paper.active {{
            background: #eff6ff;
            color: #1d4ed8;
            font-weight: 500;
        }}
        .dark .toc-paper.active {{
            background: #1e3a5f;
            color: #93c5fd;
        }}
        /* TOC 切换按钮 - 左侧 */
        #toc-toggle {{
            position: fixed;
            left: 220px;
            top: 50%;
            transform: translateY(-50%);
            z-index: 40;
            width: 28px;
            height: 56px;
            border-radius: 0 6px 6px 0;
            background: #3b82f6;
            color: white;
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 2px 0 8px rgba(0,0,0,0.15);
            transition: left 0.3s ease, background 0.2s;
        }}
        #toc-toggle:hover {{
            background: #2563eb;
        }}
        #toc-toggle svg {{
            transition: transform 0.3s;
        }}
        #toc-toggle:not(.sidebar-open) {{
            left: 0;
        }}
        @media (max-width: 1023px) {{
            #toc-sidebar {{
                width: 240px;
            }}
            #toc-toggle {{
                left: 240px;
            }}
            #toc-toggle:not(.sidebar-open) {{
                left: 0;
            }}
        }}
        @media (max-width: 767px) {{
            #toc-sidebar {{
                width: 260px;
                box-shadow: 4px 0 16px rgba(0,0,0,0.1);
            }}
            #toc-toggle {{
                left: 260px;
            }}
            #toc-toggle:not(.sidebar-open) {{
                left: 0;
            }}
        }}
    </style>
    <script>
        // Tailwind CSS 暗色模式配置
        if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {{
            document.documentElement.classList.add('dark')
        }} else {{
            document.documentElement.classList.remove('dark')
        }}
    </script>
</head>
<body class="bg-slate-50 dark:bg-slate-900 font-sans text-slate-800 dark:text-slate-200">

    <!-- 撤销删除的Toast -->
    <div id="undo-toast" class="fixed top-4 right-4 bg-red-500 text-white px-3 sm:px-4 py-2 rounded-lg shadow-lg z-50 hidden max-w-xs sm:max-w-sm">
        <div class="flex items-center space-x-2">
            <span id="toast-message" class="text-sm sm:text-base">已删除</span>
            <span id="countdown" class="text-xs sm:text-sm opacity-75"></span>
            <button id="undo-btn" class="ml-2 px-2 py-1 bg-white text-red-500 rounded text-xs sm:text-sm hover:bg-gray-100">撤销</button>
        </div>
    </div>

    <!-- TOC 切换按钮 -->
    <button id="toc-toggle" class="hidden lg:flex sidebar-open" onclick="toggleTocSidebar()" title="切换目录">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"></polyline>
        </svg>
    </button>

    <div class="flex mx-auto max-w-none">
    <!-- 主内容区域 -->
    <div class="w-full lg:w-3/5 mx-auto p-3 sm:p-4 lg:p-6">
        <!-- 头部导航栏 -->
        <header class="mb-4 sm:mb-6">
            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 sm:gap-4">
                <h1 class="text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white">PaperTools</h1>
                <div class="flex flex-wrap items-center gap-2 sm:gap-3 w-full sm:w-auto">
                    <!-- 统计信息 -->
                    <div class="text-xs sm:text-sm text-slate-600 dark:text-slate-400">
                        总计 <span id="total-papers">0</span> 篇论文
                    </div>
                    <!-- 筛选按钮 -->
                    <button id="filter-starred" class="px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600 focus:outline-none transition-colors whitespace-nowrap">
                        只看收藏
                    </button>
                    <button id="filter-all" class="px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none transition-colors whitespace-nowrap">
                        显示全部
                    </button>
                    <!-- 中英文摘要切换按钮 -->
                    <button id="summary-toggle" class="px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600 focus:outline-none transition-colors whitespace-nowrap">
                        中文摘要
                    </button>
                    <button id="theme-toggle" class="p-1.5 sm:p-2 rounded-full hover:bg-slate-200 dark:hover:bg-slate-700 focus:outline-none flex-shrink-0">
                        <!-- 太阳图标 (浅色模式) -->
                        <svg id="theme-icon-light" class="h-5 w-5 sm:h-6 sm:w-6 text-slate-600 dark:text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                        </svg>
                        <!-- 月亮图标 (深色模式) -->
                        <svg id="theme-icon-dark" class="h-5 w-5 sm:h-6 sm:w-6 text-slate-600 dark:text-slate-300 hidden" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                        </svg>
                    </button>
                    <!-- GitHub 图标按钮 -->
                    <a href="https://github.com/tsrigo/PaperTools" target="https://github.com/tsrigo/PaperTools" title="GitHub 项目主页"
                       class="p-1.5 sm:p-2 rounded-full hover:bg-slate-200 dark:hover:bg-slate-700 focus:outline-none flex-shrink-0">
                        <svg class="h-5 w-5 sm:h-6 sm:w-6 text-slate-700 dark:text-slate-200" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                            <path fill-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.021c0 4.428 2.865 8.184 6.839 9.504.5.092.682-.217.682-.483 0-.237-.009-.868-.014-1.703-2.782.605-3.369-1.342-3.369-1.342-.454-1.155-1.11-1.463-1.11-1.463-.908-.62.069-.608.069-.608 1.004.07 1.532 1.032 1.532 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.339-2.221-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.254-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.025A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.295 2.748-1.025 2.748-1.025.546 1.378.202 2.396.1 2.65.64.7 1.028 1.595 1.028 2.688 0 3.847-2.337 4.695-4.566 4.944.359.309.678.919.678 1.852 0 1.336-.012 2.417-.012 2.747 0 .268.18.579.688.481C19.138 20.2 22 16.447 22 12.021 22 6.484 17.523 2 12 2z" clip-rule="evenodd"/>
                        </svg>
                    </a>
                </div>
            </div>
        </header>

        <!-- 主要内容区域 -->
        <main class="space-y-6 sm:space-y-8" id="main-content">
            <!-- 加载提示 -->
            <div id="loading" class="text-center py-8">
                <div class="inline-flex items-center px-4 py-2 font-semibold leading-6 text-sm shadow rounded-md text-slate-500 bg-white dark:bg-slate-800 transition ease-in-out duration-150">
                    <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-slate-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    加载中...
                </div>
            </div>
        </main>
    </div>
    </div>

    <!-- 左侧 TOC 侧边栏（固定定位） -->
    <aside id="toc-sidebar" class="hidden lg:block">
        <div id="toc-inner">
            <div class="flex items-center justify-between mb-2 px-2">
                <span class="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">目录</span>
            </div>
            <nav id="toc-list"></nav>
        </div>
    </aside>

    <script>
        {js_data}

        // 全局状态管理
        let starredPapers = new Set();
        let readPapers = new Set();
        let deletedPapers = new Set();
        let pendingDeletes = new Map();
        let showChineseSummary = true; // 默认显示中文摘要
        let showOnlyStarred = false; // 筛选状态：是否只显示收藏的论文
        let isLoadingMore = false; // 是否正在加载更多
        let activeTagFilters = {{}}; // {{date: Set of active tag names}}

        // 获取未加载的日期
        function getUnloadedDates() {{
            return availableDates.filter(date => !loadedDates.has(date));
        }}

        // Tag filter toggle
        function toggleTagFilter(date, tagName) {{
            if (!activeTagFilters[date]) activeTagFilters[date] = new Set();
            const filters = activeTagFilters[date];
            if (tagName === 'All') {{
                filters.clear();
            }} else if (filters.has(tagName)) {{
                filters.delete(tagName);
            }} else {{
                filters.add(tagName);
            }}
            renderPapers();
        }}

        // Check if paper matches active tag filters for its date
        function paperMatchesFilters(paper, date) {{
            const filters = activeTagFilters[date];
            if (!filters || filters.size === 0) return true;
            if (filters.has(paper.cluster)) return true;
            return (paper.tags || []).some(tag => filters.has(tag));
        }}

        // 加载更多日期的数据
        async function loadMoreDates() {{
            if (isLoadingMore) return;

            const unloadedDates = getUnloadedDates();
            if (unloadedDates.length === 0) {{
                showSimpleToast('已加载全部数据');
                return;
            }}

            isLoadingMore = true;
            const loadBtn = document.getElementById('load-more-btn');
            if (loadBtn) {{
                loadBtn.disabled = true;
                loadBtn.innerHTML = '<span class="animate-spin inline-block mr-2">⏳</span>加载中...';
            }}

            const datesToLoad = unloadedDates.slice(0, LOAD_MORE_DAYS);
            let loadedCount = 0;

            for (const date of datesToLoad) {{
                try {{
                    const response = await fetch(`data/${{date}}.json`);
                    if (!response.ok) continue;

                    const dateData = await response.json();

                    // 将数据添加到 allPapers
                    allPapers[date] = dateData.clusters;
                    allPaperTags[date] = dateData.tags;

                    // 添加每日速览
                    if (dateData.overview) {{
                        dailyOverviews[date] = dateData.overview;
                    }}

                    loadedDates.add(date);
                    loadedCount++;
                }} catch (e) {{
                    console.error(`加载 ${{date}} 数据失败:`, e);
                }}
            }}

            isLoadingMore = false;

            if (loadedCount > 0) {{
                renderPapers();
                showSimpleToast(`已加载 ${{loadedCount}} 天的数据`);
            }}

            updateLoadMoreButton();
        }}

        // 更新"加载更多"按钮状态
        function updateLoadMoreButton() {{
            const loadBtn = document.getElementById('load-more-btn');
            const unloadedCount = getUnloadedDates().length;

            if (loadBtn) {{
                if (unloadedCount === 0) {{
                    loadBtn.style.display = 'none';
                }} else {{
                    loadBtn.style.display = 'inline-flex';
                    loadBtn.disabled = false;
                    loadBtn.innerHTML = `📥 加载更多 (还有 ${{unloadedCount}} 天)`;
                }}
            }}
        }}

        // 从localStorage加载状态
        function loadState() {{
            const starred = localStorage.getItem('starred_papers');
            const read = localStorage.getItem('read_papers');
            const deleted = localStorage.getItem('deleted_papers');
            const summaryLang = localStorage.getItem('summary_language');

            if (starred) starredPapers = new Set(JSON.parse(starred));
            if (read) readPapers = new Set(JSON.parse(read));
            if (deleted) deletedPapers = new Set(JSON.parse(deleted));
            if (summaryLang !== null) showChineseSummary = summaryLang === 'chinese';
        }}

        // 保存状态到localStorage
        function saveState() {{
            localStorage.setItem('starred_papers', JSON.stringify([...starredPapers]));
            localStorage.setItem('read_papers', JSON.stringify([...readPapers]));
            localStorage.setItem('deleted_papers', JSON.stringify([...deletedPapers]));
            localStorage.setItem('summary_language', showChineseSummary ? 'chinese' : 'english');
        }}

        // 显示撤销删除的Toast
        function showUndoToast(message, seconds, onUndo, onExpire) {{
            const toast = document.getElementById('undo-toast');
            const msgEl = document.getElementById('toast-message');
            const cdEl = document.getElementById('countdown');
            const undoBtn = document.getElementById('undo-btn');

            msgEl.textContent = message;
            let remaining = seconds;
            cdEl.textContent = `(${{remaining}}s)`;
            toast.classList.remove('hidden');

            let intervalId = setInterval(() => {{
                remaining -= 1;
                cdEl.textContent = `(${{remaining}}s)`;
                if (remaining <= 0) {{
                    clearInterval(intervalId);
                    toast.classList.add('hidden');
                    try {{ onExpire && onExpire(); }} catch (e) {{}}
                }}
            }}, 1000);

            let expireTimer = setTimeout(() => {{
                clearInterval(intervalId);
                toast.classList.add('hidden');
                try {{ onExpire && onExpire(); }} catch (e) {{}}
            }}, seconds * 1000);

            const cleanup = () => {{
                clearInterval(intervalId);
                clearTimeout(expireTimer);
                toast.classList.add('hidden');
            }};

            const onUndoClick = () => {{
                cleanup();
                try {{ onUndo && onUndo(); }} catch (e) {{}}
            }};

            undoBtn.removeEventListener('click', onUndoClick);
            undoBtn.addEventListener('click', onUndoClick);
        }}

        // 显示简单的提示信息
        function showSimpleToast(message) {{
            // 创建一个简单的toast元素
            const toast = document.createElement('div');
            toast.className = 'fixed top-4 right-4 bg-green-500 text-white px-4 py-2 rounded-lg shadow-lg z-50 transition-all duration-300';
            toast.textContent = message;

            document.body.appendChild(toast);

            // 3秒后自动消失
            setTimeout(() => {{
                toast.style.opacity = '0';
                toast.style.transform = 'translateY(-10px)';
                setTimeout(() => {{
                    document.body.removeChild(toast);
                }}, 300);
            }}, 3000);
        }}

        // 通过按钮删除论文（避免JavaScript字符串转义问题）
        function deletePaperByButton(button) {{
            const arxivId = button.getAttribute('data-arxiv-id');
            const title = button.getAttribute('data-title');
            deletePaper(arxivId, title);
        }}

        // 删除论文
        function deletePaper(arxivId, title) {{
            const paperEl = document.querySelector(`[data-arxiv-id="${{arxivId}}"]`);
            if (!paperEl) return;
            const listItem = paperEl.closest('li');
            const sectionEl = paperEl.closest('section[data-date-section]');

            // 添加删除动画效果
            paperEl.style.transition = 'all 0.3s ease-out';
            paperEl.style.transform = 'scale(0.95)';
            paperEl.style.opacity = '0.5';

            setTimeout(() => {{
                // 立即删除并保存状态
                deletedPapers.add(arxivId);
                saveState();

                // 移除DOM元素
                if (listItem) {{
                    listItem.remove();
                }} else {{
                    paperEl.remove();
                }}

                updateDateSection(sectionEl);
                updateStats();
                buildToc();

                // 显示简单的删除提示
                showSimpleToast(`已删除: ${{title}}`);
            }}, 300);
        }}

        // 切换星标状态
        function toggleStar(arxivId) {{
            if (starredPapers.has(arxivId)) {{
                starredPapers.delete(arxivId);
            }} else {{
                starredPapers.add(arxivId);
            }}
            saveState();

            // 如果当前是只看收藏模式，需要重新渲染
            if (showOnlyStarred) {{
                renderPapers();
            }} else {{
                // 否则只更新星标按钮状态
                const starBtn = document.querySelector(`[data-arxiv-id="${{arxivId}}"] .star-button`);
                if (starBtn) {{
                    if (starredPapers.has(arxivId)) {{
                        starBtn.classList.add('starred');
                    }} else {{
                        starBtn.classList.remove('starred');
                    }}
                }}
            }}
        }}

        // 切换已读状态
        function toggleRead(arxivId) {{
            const checkbox = document.querySelector(`[data-arxiv-id="${{arxivId}}"] input[type="checkbox"]`);
            if (!checkbox) return;

            if (checkbox.checked) {{
                readPapers.add(arxivId);
            }} else {{
                readPapers.delete(arxivId);
            }}
            saveState();
        }}

        // 切换摘要语言
        function toggleSummaryLanguage() {{
            showChineseSummary = !showChineseSummary;
            const toggleBtn = document.getElementById('summary-toggle');
            toggleBtn.textContent = showChineseSummary ? '中文摘要' : 'English Summary';

            // 更新所有摘要显示
            document.querySelectorAll('.summary-section').forEach(section => {{
                const chineseContent = section.querySelector('.chinese-summary');
                const englishContent = section.querySelector('.english-summary');

                if (showChineseSummary) {{
                    if (chineseContent) chineseContent.style.display = 'block';
                    if (englishContent) englishContent.style.display = 'none';
                }} else {{
                    if (chineseContent) chineseContent.style.display = 'none';
                    if (englishContent) englishContent.style.display = 'block';
                }}
            }});

            saveState();
        }}

        // 更新统计信息
        function updateStats() {{
            const visiblePapers = document.querySelectorAll('.paper-item:not(.hidden-paper)').length;
            document.getElementById('total-papers').textContent = visiblePapers;
        }}

        function updateDateSection(sectionEl) {{
            if (!sectionEl) return;
            const totalPapers = sectionEl.querySelectorAll('.paper-item').length;
            const header = sectionEl.querySelector('[data-date-heading]');

            if (header) {{
                const dateLabel = header.dataset.dateHeading || header.textContent.split(' ')[0];
                header.textContent = `${{dateLabel}} (${{totalPapers}} 篇论文)`;
            }}

            if (totalPapers === 0) {{
                sectionEl.remove();
            }}
        }}

        // 可折叠功能
        function toggleCollapsible(header) {{
            const content = header.nextElementSibling;
            const isOpen = header.classList.contains('open');

            if (isOpen) {{
                header.classList.remove('open');
                content.classList.remove('open');
            }} else {{
                header.classList.add('open');
                content.classList.add('open');
                // Lazy render: parse markdown only when first opened
                lazyRenderMarkdown(content);
            }}
        }}

        // Map of element ID -> raw markdown content for lazy rendering
        const mdRawContent = {{}};

        // Register raw markdown content for lazy rendering
        function registerMarkdown(id, content) {{
            if (id && content) mdRawContent[id] = content;
        }}

        // Parse markdown for all unrendered .markdown-content elements inside a container
        function lazyRenderMarkdown(container) {{
            if (typeof marked === 'undefined') return;
            container.querySelectorAll('.markdown-content:not([data-rendered])').forEach(el => {{
                const raw = mdRawContent[el.id];
                if (raw) {{
                    try {{
                        el.innerHTML = marked.parse(raw);
                    }} catch (e) {{
                        el.textContent = raw;
                    }}
                    el.setAttribute('data-rendered', '1');
                }}
            }});
        }}

        // Render markdown only for currently visible (open) sections
        function renderVisibleMarkdown() {{
            if (typeof marked === 'undefined') return;
            marked.setOptions({{ breaks: true, gfm: true, headerIds: false, mangle: false }});
            // Render open collapsible sections
            document.querySelectorAll('.collapsible-content.open').forEach(c => lazyRenderMarkdown(c));
            // Render overview sections (top-level, not inside collapsible)
            document.querySelectorAll('.markdown-content:not([data-rendered])').forEach(el => {{
                if (!el.closest('.collapsible-content')) {{
                    const raw = mdRawContent[el.id];
                    if (raw) {{
                        try {{ el.innerHTML = marked.parse(raw); }} catch (e) {{ el.textContent = raw; }}
                        el.setAttribute('data-rendered', '1');
                    }}
                }}
            }});
        }}

        // 创建论文HTML
        function formatAuthorsWithAffiliations(authorsStr, affiliationsStr) {{
            if (!affiliationsStr) return authorsStr;
            try {{
                // 解析 JSON（可能被包在 ```json ... ``` 中）
                let jsonStr = affiliationsStr;
                const match = jsonStr.match(/```json\s*([\s\S]*?)\s*```/);
                if (match) jsonStr = match[1];
                const objMatch = jsonStr.match(/\{{[\s\S]*\}}/);
                if (objMatch) jsonStr = objMatch[0];
                const data = JSON.parse(jsonStr);

                // 兼容旧格式（数组）
                if (Array.isArray(data)) {{
                    const authors = authorsStr.split(/,\s*/);
                    const affMap = {{}};
                    data.forEach(a => {{ if (a.name && a.affiliation) affMap[a.name.trim().toLowerCase()] = a.affiliation; }});
                    return authors.map(a => {{
                        const aff = affMap[a.trim().toLowerCase()];
                        return aff ? `${{a.trim()}}<sup class="aff-sup" title="${{aff}}">${{aff}}</sup>` : a.trim();
                    }}).join(', ');
                }}

                if (!data.authors || !data.institutions) return authorsStr;

                // 新格式：论文式数字角标
                const instMap = {{}};
                data.institutions.forEach(inst => {{ instMap[inst.id] = inst.name; }});

                // 渲染作者行
                const authorParts = data.authors.map(a => {{
                    let sups = [];
                    if (a.affiliations && a.affiliations.length > 0) {{
                        sups = sups.concat(a.affiliations.map(String));
                    }}
                    if (a.markers && a.markers.length > 0) {{
                        sups = sups.concat(a.markers);
                    }}
                    const supStr = sups.length > 0
                        ? `<sup class="aff-sup">${{sups.join(',')}}</sup>`
                        : '';
                    return `${{a.name}}${{supStr}}`;
                }});

                // 渲染机构列表
                const instLine = data.institutions.map(inst =>
                    `<sup class="aff-sup">${{inst.id}}</sup>${{inst.name}}`
                ).join('&ensp;');

                // 渲染脚注
                let footLine = '';
                if (data.footnotes && data.footnotes.length > 0) {{
                    footLine = data.footnotes.map(fn =>
                        `<sup class="aff-sup">${{fn.marker}}</sup>${{fn.text}}`
                    ).join('&ensp;');
                }}

                let html = authorParts.join(', ');
                html += `<div class="text-xs text-slate-500 dark:text-slate-400 mt-1">${{instLine}}</div>`;
                if (footLine) {{
                    html += `<div class="text-xs text-slate-400 dark:text-slate-500 mt-0.5 italic">${{footLine}}</div>`;
                }}
                return html;
            }} catch (e) {{
                return authorsStr;
            }}
        }}

        function createPaperHTML(paper, date) {{
            const isStarred = starredPapers.has(paper.arxiv_id);
            const isRead = readPapers.has(paper.arxiv_id);
            const isDeleted = deletedPapers.has(paper.arxiv_id);

            // 如果论文已被删除，直接返回空字符串，不渲染
            if (isDeleted) {{
                return '';
            }}

            // 如果启用了只看收藏筛选，且论文未被收藏，则不渲染
            if (showOnlyStarred && !isStarred) {{
                return '';
            }}

            // Check tag filters
            if (!paperMatchesFilters(paper, date)) {{
                return '';
            }}

            // Register raw markdown content for lazy rendering
            const aid = paper.arxiv_id;
            registerMarkdown(`filter-reason-${{aid}}`, paper.filter_reason);
            registerMarkdown(`intro-logic-${{aid}}`, paper.intro_logic);
            registerMarkdown(`core-insight-${{aid}}`, paper.core_insight);
            registerMarkdown(`methodology-${{aid}}`, paper.methodology);
            registerMarkdown(`additional-insights-${{aid}}`, paper.additional_insights);
            registerMarkdown(`research-value-${{aid}}`, paper.research_value);
            // summary_translation and summary are plain text, rendered directly (no markdown)


            // Build tag badges HTML
            const clusterBadge = paper.cluster ? `<span class="tag-badge">${{paper.cluster}}</span>` : '';
            const tagBadges = (paper.tags || []).map(tag => `<span class="tag-badge tag-arxiv">${{tag}}</span>`).join('');

            return `
                <div class="paper-item bg-white dark:bg-slate-800/50 rounded-lg shadow-sm p-4 sm:p-6" data-arxiv-id="${{paper.arxiv_id}}">
                    <!-- 论文标题和操作按钮 -->
                    <div class="flex items-start justify-between mb-3 sm:mb-4">
                        <div class="flex items-start space-x-2 sm:space-x-3 flex-1 min-w-0">
                            <!-- 星标按钮 -->
                            <button class="star-button ${{isStarred ? 'starred' : ''}} mt-1 flex-shrink-0" onclick="toggleStar('${{paper.arxiv_id}}')" title="点击收藏">
                                <svg class="h-5 w-5 sm:h-6 sm:w-6" viewBox="0 0 20 20" fill="currentColor">
                                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                                </svg>
                            </button>
                            <!-- 论文标题 -->
                            <h3 class="text-base sm:text-lg font-semibold text-black dark:text-white leading-tight break-words">${{paper.title}}</h3>
                        </div>
                        <!-- 删除按钮 -->
                        <button class="delete-button text-slate-400 hover:text-red-500 ml-2 sm:ml-4 flex-shrink-0" onclick="deletePaperByButton(this)" data-arxiv-id="${{paper.arxiv_id}}" data-title="${{paper.title.replace(/"/g, '&quot;')}}" title="删除">
                            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>

                    <!-- 论文元信息 -->
                    <div class="space-y-2 mb-3 sm:mb-4">
                        <div class="flex flex-wrap items-center gap-2 sm:gap-4 text-xs sm:text-sm text-slate-600 dark:text-slate-400">
                            <span class="break-all"><strong>ArXiv ID:</strong> ${{paper.arxiv_id}}</span>
                            ${{clusterBadge}}
                            ${{tagBadges}}
                            <span class="whitespace-nowrap">${{date}}</span>
                        </div>
                        <div class="text-xs sm:text-sm text-black dark:text-white break-words">
                            <strong>作者:</strong> ${{formatAuthorsWithAffiliations(paper.authors, paper.affiliations)}}
                        </div>
                    </div>

                    <!-- 已读复选框 -->
                    <div class="mb-3 sm:mb-4">
                        <label class="inline-flex items-center">
                            <input type="checkbox" ${{isRead ? 'checked' : ''}} onchange="toggleRead('${{paper.arxiv_id}}')" class="rounded border-gray-300 text-blue-600 shadow-sm focus:border-blue-300 focus:ring focus:ring-blue-200 focus:ring-opacity-50 w-4 h-4">
                            <span class="ml-2 text-xs sm:text-sm text-slate-600 dark:text-slate-400">已阅读</span>
                        </label>
                    </div>

                    ${{paper.summary || paper.summary_translation ? `
                    <!-- 原始摘要 (默认展开，英文优先) -->
                    <div class="mb-3 sm:mb-4">
                        <div class="collapsible-header open text-sm sm:text-base" onclick="toggleCollapsible(this)">原始摘要</div>
                        <div class="collapsible-content open">
                            <div class="inner">
                                <div class="summary-section bg-green-50/70 dark:bg-green-950/20 border-l-3 border-green-300 p-3 sm:p-4 rounded-r-lg">
                                    ${{paper.summary ? `
                                    <div class="english-summary text-xs sm:text-sm text-black dark:text-white leading-relaxed break-words" style="display: block; white-space: pre-line;">
                                        ${{paper.summary}}
                                    </div>
                                    ` : ''}}
                                    ${{paper.summary_translation ? `
                                    <div class="chinese-summary text-xs sm:text-sm text-black dark:text-white leading-relaxed break-words" style="display: none; white-space: pre-line;">
                                        ${{paper.summary_translation}}
                                    </div>
                                    ` : ''}}
                                </div>
                            </div>
                        </div>
                    </div>
                    ` : ''}}

                    ${{paper.intro_logic ? `
                    <!-- Introduction逻辑 (默认折叠) -->
                    <div class="mb-3 sm:mb-4">
                        <div class="collapsible-header text-sm sm:text-base" onclick="toggleCollapsible(this)">Introduction 逻辑链</div>
                        <div class="collapsible-content">
                            <div class="inner">
                                <div class="bg-yellow-50/70 dark:bg-yellow-950/20 border-l-3 border-yellow-300 p-3 sm:p-4 rounded-r-lg">
                                    <div class="text-xs sm:text-sm text-black dark:text-white leading-relaxed markdown-content break-words" id="intro-logic-${{paper.arxiv_id}}">
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    ` : ''}}

                    ${{paper.core_insight ? `
                    <!-- 核心洞察 (默认折叠) -->
                    <div class="mb-3 sm:mb-4">
                        <div class="collapsible-header text-sm sm:text-base" onclick="toggleCollapsible(this)">核心切入点 / Pain Point</div>
                        <div class="collapsible-content">
                            <div class="inner">
                                <div class="bg-orange-50/70 dark:bg-orange-950/20 border-l-3 border-orange-300 p-3 sm:p-4 rounded-r-lg">
                                    <div class="text-xs sm:text-sm text-black dark:text-white leading-relaxed markdown-content break-words" id="core-insight-${{paper.arxiv_id}}">
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    ` : ''}}

                    ${{paper.methodology ? `
                    <!-- 方法论解读 (默认折叠) -->
                    <div class="mb-3 sm:mb-4">
                        <div class="collapsible-header text-sm sm:text-base" onclick="toggleCollapsible(this)">方法论解读</div>
                        <div class="collapsible-content">
                            <div class="inner">
                                <div class="bg-purple-50/70 dark:bg-purple-950/20 border-l-3 border-purple-300 p-3 sm:p-4 rounded-r-lg">
                                    <div class="text-xs sm:text-sm text-black dark:text-white leading-relaxed markdown-content break-words" id="methodology-${{paper.arxiv_id}}">
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    ` : ''}}

                    ${{paper.additional_insights ? `
                    <!-- 延伸洞察 (默认折叠) -->
                    <div class="mb-3 sm:mb-4">
                        <div class="collapsible-header text-sm sm:text-base" onclick="toggleCollapsible(this)">延伸洞察</div>
                        <div class="collapsible-content">
                            <div class="inner">
                                <div class="bg-red-50/70 dark:bg-red-950/20 border-l-3 border-red-300 p-3 sm:p-4 rounded-r-lg">
                                    <div class="text-xs sm:text-sm text-black dark:text-white leading-relaxed markdown-content break-words" id="additional-insights-${{paper.arxiv_id}}">
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    ` : ''}}

                    ${{paper.research_value ? `
                    <!-- 研究价值评估 (默认折叠) -->
                    <div class="mb-3 sm:mb-4">
                        <div class="collapsible-header text-sm sm:text-base" onclick="toggleCollapsible(this)">研究价值</div>
                        <div class="collapsible-content">
                            <div class="inner">
                                <div class="bg-teal-50/70 dark:bg-teal-950/20 border-l-3 border-teal-300 p-3 sm:p-4 rounded-r-lg">
                                    <div class="text-xs sm:text-sm text-black dark:text-white leading-relaxed markdown-content break-words" id="research-value-${{paper.arxiv_id}}">
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    ` : ''}}

                    ${{paper.filter_reason ? `
                    <!-- 筛选原因 (默认折叠，放最后) -->
                    <div class="mb-3 sm:mb-4">
                        <div class="collapsible-header text-sm sm:text-base" onclick="toggleCollapsible(this)">筛选原因</div>
                        <div class="collapsible-content">
                            <div class="inner">
                                <div class="bg-blue-50/70 dark:bg-blue-950/20 border-l-3 border-blue-300 p-3 sm:p-4 rounded-r-lg">
                                    <div class="text-xs sm:text-sm text-black dark:text-white leading-relaxed markdown-content break-words" id="filter-reason-${{paper.arxiv_id}}">
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    ` : ''}}

                    <!-- 论文链接 -->
                    <div class="flex flex-wrap gap-2">
                        <a href="https://arxiv.org/abs/${{paper.arxiv_id}}" target="_blank"
                           class="inline-flex items-center px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-md transition-colors whitespace-nowrap">
                            📄 arXiv 原文
                        </a>
                        <a href="https://arxiv.org/pdf/${{paper.arxiv_id}}.pdf" target="_blank"
                           class="inline-flex items-center px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-md transition-colors whitespace-nowrap">
                            📋 PDF 下载
                        </a>
                        <a href="https://papers.cool/arxiv/${{paper.arxiv_id}}" target="_blank"
                           class="inline-flex items-center px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors whitespace-nowrap">
                            🔥 Cool Paper
                        </a>
                    </div>
                </div>
            `;
        }}

        // 创建聚类HTML
        // Collect all papers from all clusters for a date into a flat list
        function collectPapersForDate(clusters, date) {{
            let html = '';
            let count = 0;
            clusters.forEach(cluster => {{
                if (cluster.papers) {{
                    cluster.papers.forEach(paper => {{
                        const paperHTML = createPaperHTML(paper, date);
                        if (paperHTML) {{
                            html += `<li>${{paperHTML}}</li>`;
                            count++;
                        }}
                    }});
                }}
            }});
            return {{ html, count }};
        }}

        // Build tag filter bar HTML for a given date
        function buildTagFilterBar(date) {{
            const tags = allPaperTags[date];
            if (!tags || tags.length === 0) return '';
            const filters = activeTagFilters[date] || new Set();
            const allActive = filters.size === 0;
            let html = '<div class="flex flex-wrap gap-1.5 mb-3">';
            html += `<button class="tag-btn ${{allActive ? 'active' : ''}}" onclick="toggleTagFilter('${{date}}','All')">All</button>`;
            tags.forEach(tag => {{
                const isActive = filters.has(tag.name);
                html += `<button class="tag-btn ${{isActive ? 'active' : ''}}" onclick="toggleTagFilter('${{date}}','${{tag.name.replace(/'/g, "\\\\'")}}')">${{tag.name}} &times;${{tag.count}}</button>`;
            }});
            html += '</div>';
            return html;
        }}

        // 渲染论文列表
        function renderPapers() {{
            const mainContent = document.getElementById('main-content');
            const loading = document.getElementById('loading');

            if (loading) {{
                loading.classList.add('hidden');
            }}

            let html = '';
            let totalPapers = 0;

            for (const date in allPapers) {{
                const clusters = allPapers[date];
                if (clusters.length === 0) continue;

                const {{ html: papersHTML, count: dateVisibleTotal }} = collectPapersForDate(clusters, date);

                totalPapers += dateVisibleTotal;

                // 如果该日期下没有可见论文，跳过
                if (dateVisibleTotal === 0) continue;

                html += `
                    <section class="mb-6 sm:mb-8" data-date-section="${{date}}">
                        <h2 class="text-base sm:text-lg font-medium text-slate-500 dark:text-slate-400 mb-3 sm:mb-4" data-date-heading="${{date}}">${{date}} (${{dateVisibleTotal}} 篇论文)</h2>
                `;

                // 添加该日期的AI论文速览（如果存在）
                if (dailyOverviews[date]) {{
                    html += `
                        <div class="mb-3 sm:mb-4 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-slate-800 dark:to-slate-700 rounded-lg shadow-md p-3 sm:p-5">
                            <div class="collapsible-header" onclick="toggleCollapsible(this)">
                                <svg class="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-blue-600 dark:text-blue-400 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z"></path>
                                </svg>
                                <span class="font-semibold text-slate-900 dark:text-white text-sm sm:text-base">今日AI论文速览</span>
                            </div>
                            <div class="collapsible-content">
                                <div class="inner">
                                    <div class="markdown-content text-slate-700 dark:text-slate-200 text-xs sm:text-sm" id="overview-${{date}}">
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                }}

                // Add tag filter bar
                html += buildTagFilterBar(date);

                html += `
                        <div class="bg-white dark:bg-slate-800/50 rounded-lg shadow-sm p-3 sm:p-4 lg:p-6">
                            <ul class="space-y-3 sm:space-y-4">
                                ${{papersHTML}}
                            </ul>
                        </div>
                    </section>
                `;
            }}

            // 添加"加载更多"按钮
            const unloadedCount = getUnloadedDates().length;
            if (unloadedCount > 0) {{
                html += `
                    <div class="text-center py-6">
                        <button id="load-more-btn" onclick="loadMoreDates()"
                            class="inline-flex items-center px-6 py-3 text-base font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-md transition-all duration-200 hover:shadow-lg">
                            📥 加载更多 (还有 ${{unloadedCount}} 天)
                        </button>
                    </div>
                `;
            }}

            mainContent.innerHTML = html;
            updateStats();

            // Register overview markdown and render visible content
            for (const date in dailyOverviews) {{
                registerMarkdown(`overview-${{date}}`, dailyOverviews[date]);
            }}
            renderVisibleMarkdown();

            // 应用当前摘要语言设置
            document.querySelectorAll('.summary-section').forEach(section => {{
                const chineseContent = section.querySelector('.chinese-summary');
                const englishContent = section.querySelector('.english-summary');

                if (showChineseSummary) {{
                    if (chineseContent) chineseContent.style.display = 'block';
                    if (englishContent) englishContent.style.display = 'none';
                }} else {{
                    if (chineseContent) chineseContent.style.display = 'none';
                    if (englishContent) englishContent.style.display = 'block';
                }}
            }});

            // 更新 TOC
            buildToc();

        }}

        // 主题切换功能
        function setupThemeToggle() {{
            const themeToggleBtn = document.getElementById('theme-toggle');
            const lightIcon = document.getElementById('theme-icon-light');
            const darkIcon = document.getElementById('theme-icon-dark');

            function updateThemeIcon() {{
                if (document.documentElement.classList.contains('dark')) {{
                    lightIcon.classList.add('hidden');
                    darkIcon.classList.remove('hidden');
                }} else {{
                    lightIcon.classList.remove('hidden');
                    darkIcon.classList.add('hidden');
                }}
            }}

            updateThemeIcon();

            themeToggleBtn.addEventListener('click', () => {{
                document.documentElement.classList.toggle('dark');
                localStorage.theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
                updateThemeIcon();
            }});
        }}

        // 设置摘要语言切换功能
        function setupSummaryToggle() {{
            const summaryToggleBtn = document.getElementById('summary-toggle');

            // 初始化按钮文本
            summaryToggleBtn.textContent = showChineseSummary ? '中文摘要' : 'English Summary';

            summaryToggleBtn.addEventListener('click', toggleSummaryLanguage);
        }}

        // 设置筛选功能
        function setupFilter() {{
            const filterStarredBtn = document.getElementById('filter-starred');
            const filterAllBtn = document.getElementById('filter-all');

            filterStarredBtn.addEventListener('click', () => {{
                showOnlyStarred = true;
                updateFilterButtons();
                renderPapers();
            }});

            filterAllBtn.addEventListener('click', () => {{
                showOnlyStarred = false;
                updateFilterButtons();
                renderPapers();
            }});

            updateFilterButtons();
        }}

        // 更新筛选按钮状态
        function updateFilterButtons() {{
            const filterStarredBtn = document.getElementById('filter-starred');
            const filterAllBtn = document.getElementById('filter-all');

            if (showOnlyStarred) {{
                filterStarredBtn.className = 'px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors';
                filterAllBtn.className = 'px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500 transition-colors';
            }} else {{
                filterStarredBtn.className = 'px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500 transition-colors';
                filterAllBtn.className = 'px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors';
            }}
        }}

        // ========== TOC 侧边栏功能 ==========
        let tocSidebarOpen = true;

        function toggleTocSidebar() {{
            const sidebar = document.getElementById('toc-sidebar');
            const toggle = document.getElementById('toc-toggle');
            tocSidebarOpen = !tocSidebarOpen;
            if (tocSidebarOpen) {{
                sidebar.classList.remove('collapsed');
                toggle.classList.add('sidebar-open');
                toggle.querySelector('svg').style.transform = 'rotate(180deg)';
            }} else {{
                sidebar.classList.add('collapsed');
                toggle.classList.remove('sidebar-open');
                toggle.querySelector('svg').style.transform = 'rotate(0deg)';
            }}
            localStorage.setItem('tocSidebarOpen', tocSidebarOpen);
        }}

        function buildToc() {{
            const tocList = document.getElementById('toc-list');
            if (!tocList) return;

            let html = '';
            // 遍历所有可用日期，不仅仅是已加载的
            for (const date of availableDates) {{
                const isLoaded = loadedDates.has(date);
                let papers = [];

                if (isLoaded && allPapers[date]) {{
                    const clusters = allPapers[date];
                    clusters.forEach(cluster => {{
                        if (cluster.papers) {{
                            cluster.papers.forEach(paper => {{
                                if (!deletedPapers.has(paper.arxiv_id) && (!showOnlyStarred || starredPapers.has(paper.arxiv_id))) {{
                                    if (paperMatchesFilters(paper, date)) {{
                                        papers.push(paper);
                                    }}
                                }}
                            }});
                        }}
                    }});
                }}

                const countLabel = isLoaded ? papers.length : '...';
                const dimClass = isLoaded ? '' : ' opacity-50';

                html += `<div class="mb-1" data-toc-date="${{date}}">`;
                html += `<div class="toc-date${{dimClass}}" onclick="tocToggleDate(this, '${{date}}')" data-toc-date-btn="${{date}}">`;
                html += `<span class="toc-date-arrow">▶</span>`;
                html += `<span>${{date}}</span>`;
                html += `<span class="text-xs text-slate-400 ml-auto">${{countLabel}}</span>`;
                html += `</div>`;
                html += `<div class="toc-papers" data-toc-papers="${{date}}">`;
                if (isLoaded) {{
                    papers.forEach(paper => {{
                        const title = paper.title.length > 50 ? paper.title.substring(0, 47) + '...' : paper.title;
                        html += `<div class="toc-paper" onclick="tocScrollToPaper('${{paper.arxiv_id}}')" data-toc-paper="${{paper.arxiv_id}}" title="${{paper.title.replace(/"/g, '&quot;')}}">${{title}}</div>`;
                    }});
                }} else {{
                    html += `<div class="toc-paper opacity-50" onclick="tocLoadAndScrollToDate('${{date}}')">点击加载...</div>`;
                }}
                html += `</div></div>`;
            }}
            tocList.innerHTML = html;
        }}

        async function tocLoadAndScrollToDate(date) {{
            // 加载该日期之前的所有未加载日期
            const unloaded = getUnloadedDates();
            const idx = unloaded.indexOf(date);
            if (idx < 0) return;
            const datesToLoad = unloaded.slice(0, idx + 1);
            for (const d of datesToLoad) {{
                try {{
                    const response = await fetch(`data/${{d}}.json`);
                    if (response.ok) {{
                        const dateData = await response.json();
                        allPapers[d] = dateData.clusters || [];
                        allPaperTags[d] = dateData.tags || [];
                        if (dateData.overview) dailyOverviews[d] = dateData.overview;
                        loadedDates.add(d);
                    }}
                }} catch (e) {{
                    console.error(`加载 ${{d}} 失败:`, e);
                }}
            }}
            renderPapers();
            // 等待 DOM 更新后滚动
            setTimeout(() => tocScrollToDate(date), 100);
        }}

        function tocToggleDate(el, date) {{
            const isLoaded = loadedDates.has(date);
            if (!isLoaded) {{
                tocLoadAndScrollToDate(date);
                return;
            }}
            const arrow = el.querySelector('.toc-date-arrow');
            const papers = document.querySelector(`[data-toc-papers="${{date}}"]`);
            if (papers) {{
                papers.classList.toggle('open');
                arrow.classList.toggle('open');
            }}
            // 同时滚动到对应日期
            tocScrollToDate(date);
        }}

        function tocScrollToPaper(arxivId) {{
            const el = document.querySelector(`[data-arxiv-id="${{arxivId}}"]`);
            if (el) {{
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                // 短暂高亮
                el.style.outline = '2px solid #3b82f6';
                el.style.outlineOffset = '2px';
                setTimeout(() => {{
                    el.style.outline = '';
                    el.style.outlineOffset = '';
                }}, 2000);
            }}
        }}

        function tocScrollToDate(date) {{
            const section = document.querySelector(`[data-date-section="${{date}}"]`);
            if (section) {{
                section.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }}
        }}

        // 滚动时高亮当前可见的日期
        let tocScrollTimer = null;
        function setupTocScrollSpy() {{
            window.addEventListener('scroll', () => {{
                if (tocScrollTimer) clearTimeout(tocScrollTimer);
                tocScrollTimer = setTimeout(() => {{
                    const sections = document.querySelectorAll('[data-date-section]');
                    let currentDate = null;
                    const scrollTop = window.scrollY + 100;

                    sections.forEach(section => {{
                        if (section.offsetTop <= scrollTop) {{
                            currentDate = section.getAttribute('data-date-section');
                        }}
                    }});

                    // 更新 TOC 高亮
                    document.querySelectorAll('.toc-date').forEach(el => el.classList.remove('active'));
                    if (currentDate) {{
                        const activeBtn = document.querySelector(`[data-toc-date-btn="${{currentDate}}"]`);
                        if (activeBtn) {{
                            activeBtn.classList.add('active');
                            // 确保活跃日期在 TOC 可视区域内
                            const tocInner = document.getElementById('toc-inner');
                            if (tocInner) {{
                                const btnRect = activeBtn.getBoundingClientRect();
                                const tocRect = tocInner.getBoundingClientRect();
                                if (btnRect.top < tocRect.top || btnRect.bottom > tocRect.bottom) {{
                                    activeBtn.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
                                }}
                            }}
                        }}
                    }}
                }}, 100);
            }});
        }}

        // 初始化应用
        document.addEventListener('DOMContentLoaded', function() {{
            loadState();
            setupThemeToggle();
            setupSummaryToggle();
            setupFilter();
            renderPapers();
            buildToc();
            setupTocScrollSpy();

            // 恢复 TOC 侧边栏状态
            const savedTocState = localStorage.getItem('tocSidebarOpen');
            if (savedTocState === 'false') {{
                tocSidebarOpen = true; // will be toggled to false
                toggleTocSidebar();
            }}
        }});
    </script>
</body>
</html>'''

    return html_template

def main():
    """主函数"""
    try:
        html_content = generate_complete_html()

        # 确保webpages目录存在
        webpages_dir = Path(WEBPAGES_DIR)
        webpages_dir.mkdir(exist_ok=True)

        # 写入输出文件到webpages目录
        output_path = webpages_dir / "index.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"成功生成统一HTML页面: {output_path}")

    except Exception as e:
        print(f"生成HTML页面时出错: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
