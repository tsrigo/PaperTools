#!/usr/bin/env python3
"""
独立的统一HTML页面生成脚本
不依赖外部模板，直接生成完整的HTML页面
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# 导入配置
try:
    from src.utils.config import SUMMARY_DIR, WEBPAGES_DIR
except ImportError:
    SUMMARY_DIR = "summary"
    WEBPAGES_DIR = "webpages"

def load_paper_data() -> Dict[str, List[Dict[str, Any]]]:
    """加载论文数据"""
    papers_by_date = {}
    summary_dir = Path(SUMMARY_DIR)
    
    # 查找所有的论文JSON文件
    for json_file in summary_dir.glob("filtered_papers_*_with_summary2.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                papers = json.load(f)
            
            # 从文件名提取日期
            filename = json_file.stem
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
            if date_match:
                date = date_match.group(1)
                papers_by_date[date] = papers
                print(f"加载了 {len(papers)} 篇论文，日期: {date}")
        except Exception as e:
            print(f"加载文件 {json_file} 时出错: {e}")
    
    return papers_by_date

def escape_js_string(text: str) -> str:
    """转义JavaScript字符串"""
    if not text:
        return ""
    return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')

def generate_complete_html() -> str:
    """生成完整的HTML页面"""
    papers_by_date = load_paper_data()
    
    # 按分类组织论文数据
    category_names = {
        'cs.AI': 'Artificial Intelligence',
        'cs.CL': 'Computation and Language', 
        'cs.LG': 'Machine Learning',
        'cs.CV': 'Computer Vision and Pattern Recognition',
        'cs.MA': 'Multiagent Systems'
    }
    
    # 生成JavaScript数据
    js_data = "const allPapers = {\n"
    for date, papers in sorted(papers_by_date.items(), reverse=True):
        # 按分类组织论文
        categories = {}
        for paper in papers:
            category = paper.get('category', 'Unknown')
            if category not in categories:
                categories[category] = []
            categories[category].append(paper)
        
        js_data += f'    "{date}": [\n'
        for category, category_papers in sorted(categories.items()):
            category_name = category_names.get(category, category)
            js_data += "        {\n"
            js_data += f'            "name": "{escape_js_string(category_name)}",\n'
            js_data += f'            "count": {len(category_papers)},\n'
            js_data += '            "papers": [\n'
            
            for paper in category_papers:
                js_data += "                {\n"
                js_data += f'                    "title": "{escape_js_string(paper.get("title", ""))}",\n'
                js_data += f'                    "arxiv_id": "{escape_js_string(paper.get("arxiv_id", ""))}",\n'
                js_data += f'                    "authors": "{escape_js_string(paper.get("authors", ""))}",\n'
                js_data += f'                    "summary": "{escape_js_string(paper.get("summary", ""))}",\n'
                js_data += f'                    "category": "{escape_js_string(paper.get("category", ""))}",\n'
                js_data += f'                    "filter_reason": "{escape_js_string(paper.get("filter_reason", ""))}",\n'
                js_data += f'                    "summary2": "{escape_js_string(paper.get("summary2", ""))}",\n'
                js_data += f'                    "summary_translation": "{escape_js_string(paper.get("summary_translation", ""))}"\n'
                js_data += "                },\n"
            
            js_data += "            ]\n"
            js_data += "        },\n"
        js_data += "    ],\n"
    js_data += "};\n"
    
    # 完整的HTML模板
    html_template = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MyArxiv - 学术论文集合</title>
    <!-- 引入 Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
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
    <div id="undo-toast" class="fixed top-4 right-4 bg-red-500 text-white px-4 py-2 rounded-lg shadow-lg z-50 hidden">
        <div class="flex items-center space-x-2">
            <span id="toast-message">已删除</span>
            <span id="countdown" class="text-sm opacity-75"></span>
            <button id="undo-btn" class="ml-2 px-2 py-1 bg-white text-red-500 rounded text-sm hover:bg-gray-100">撤销</button>
        </div>
    </div>

    <div class="container mx-auto w-3/5 max-w-none p-4 sm:p-6">
        <!-- 头部导航栏 -->
        <header class="flex justify-between items-center mb-6">
            <h1 class="text-3xl font-bold text-slate-900 dark:text-white">MyArxiv</h1>
            <div class="flex items-center space-x-4">
                <!-- 统计信息 -->
                <div class="text-sm text-slate-600 dark:text-slate-400">
                    总计 <span id="total-papers">0</span> 篇论文
                </div>
                <!-- 中英文摘要切换按钮 -->
                <button id="summary-toggle" class="px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500 transition-colors">
                    中文摘要
                </button>
                <button id="theme-toggle" class="p-2 rounded-full hover:bg-slate-200 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500">
                    <!-- 太阳图标 (浅色模式) -->
                    <svg id="theme-icon-light" class="h-6 w-6 text-slate-600 dark:text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                    <!-- 月亮图标 (深色模式) -->
                    <svg id="theme-icon-dark" class="h-6 w-6 text-slate-600 dark:text-slate-300 hidden" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                </button>
            </div>
        </header>

        <!-- 主要内容区域 -->
        <main class="space-y-8" id="main-content">
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

    <script>
        {js_data}

        // 全局状态管理
        let starredPapers = new Set();
        let readPapers = new Set();
        let deletedPapers = new Set();
        let pendingDeletes = new Map();
        let showChineseSummary = true; // 默认显示中文摘要

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

        // 删除论文
        function deletePaper(arxivId, title) {{
            const paperEl = document.querySelector(`[data-arxiv-id="${{arxivId}}"]`);
            if (!paperEl) return;
            
            // 立即隐藏
            paperEl.classList.add('hidden-paper');
            deletedPapers.add(arxivId);
            saveState();
            updateStats();
            
            // 设置撤销计时器
            const timerId = setTimeout(() => {{
                paperEl.remove();
                pendingDeletes.delete(arxivId);
                updateStats();
            }}, 5000);
            
            pendingDeletes.set(arxivId, timerId);
            
            showUndoToast('已删除，5秒内可撤销', 5, () => {{
                // 撤销删除
                paperEl.classList.remove('hidden-paper');
                deletedPapers.delete(arxivId);
                const t = pendingDeletes.get(arxivId);
                if (t) {{ 
                    clearTimeout(t); 
                    pendingDeletes.delete(arxivId); 
                }}
                saveState();
                updateStats();
            }});
        }}

        // 切换星标状态
        function toggleStar(arxivId) {{
            const starBtn = document.querySelector(`[data-arxiv-id="${{arxivId}}"] .star-button`);
            if (!starBtn) return;
            
            if (starredPapers.has(arxivId)) {{
                starredPapers.delete(arxivId);
                starBtn.classList.remove('starred');
            }} else {{
                starredPapers.add(arxivId);
                starBtn.classList.add('starred');
            }}
            saveState();
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

        // 创建论文HTML
        function createPaperHTML(paper, date) {{
            const isStarred = starredPapers.has(paper.arxiv_id);
            const isRead = readPapers.has(paper.arxiv_id);
            const isDeleted = deletedPapers.has(paper.arxiv_id);
            
            return `
                <div class="paper-item bg-white dark:bg-slate-800/50 rounded-lg shadow-sm p-6 ${{isDeleted ? 'hidden-paper' : ''}}" data-arxiv-id="${{paper.arxiv_id}}">
                    <!-- 论文标题和操作按钮 -->
                    <div class="flex items-start justify-between mb-4">
                        <div class="flex items-start space-x-3 flex-1">
                            <!-- 星标按钮 -->
                            <button class="star-button ${{isStarred ? 'starred' : ''}} mt-1 flex-shrink-0" onclick="toggleStar('${{paper.arxiv_id}}')" title="点击收藏">
                                <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                                </svg>
                            </button>
                            <!-- 论文标题 -->
                            <h3 class="text-lg font-semibold text-black dark:text-white leading-tight">${{paper.title}}</h3>
                        </div>
                        <!-- 删除按钮 -->
                        <button class="delete-button text-slate-400 hover:text-red-500 ml-4 flex-shrink-0" onclick="deletePaper('${{paper.arxiv_id}}', '${{paper.title.replace(/'/g, "\\\\'")}}'))" title="删除">
                            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>

                    <!-- 论文元信息 -->
                    <div class="space-y-2 mb-4">
                        <div class="flex flex-wrap items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
                            <span><strong>ArXiv ID:</strong> ${{paper.arxiv_id}}</span>
                            <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
                                ${{paper.category}}
                            </span>
                            <span>${{date}}</span>
                        </div>
                        <div class="text-sm text-black dark:text-white">
                            <strong>作者:</strong> ${{paper.authors}}
                        </div>
                    </div>

                    <!-- 已读复选框 -->
                    <div class="mb-4">
                        <label class="inline-flex items-center">
                            <input type="checkbox" ${{isRead ? 'checked' : ''}} onchange="toggleRead('${{paper.arxiv_id}}')" class="rounded border-gray-300 text-blue-600 shadow-sm focus:border-blue-300 focus:ring focus:ring-blue-200 focus:ring-opacity-50">
                            <span class="ml-2 text-sm text-slate-600 dark:text-slate-400">已阅读</span>
                        </label>
                    </div>

                    ${{paper.filter_reason ? `
                    <!-- 筛选原因 -->
                    <div class="bg-blue-50/70 dark:bg-blue-950/20 border-l-3 border-blue-300 p-4 mb-4 rounded-r-lg">
                        <div class="text-sm text-black dark:text-white leading-relaxed">
                            <strong class="font-medium text-blue-600 dark:text-blue-400">筛选原因:</strong> ${{paper.filter_reason}}
                        </div>
                    </div>
                    ` : ''}}

                    ${{paper.summary2 ? `
                    <!-- AI总结 -->
                    <div class="bg-yellow-50/70 dark:bg-yellow-950/20 border-l-3 border-yellow-300 p-4 mb-4 rounded-r-lg">
                        <div class="text-sm text-black dark:text-white leading-relaxed">
                            <strong class="font-medium text-yellow-600 dark:text-yellow-400">AI总结:</strong> ${{paper.summary2}}
                        </div>
                    </div>
                    ` : ''}}

                    ${{paper.summary || paper.summary_translation ? `
                    <!-- 原始摘要 -->
                    <div class="summary-section bg-green-50/70 dark:bg-green-950/20 border-l-3 border-green-300 p-4 mb-4 rounded-r-lg">
                        ${{paper.summary_translation ? `
                        <div class="chinese-summary text-sm text-black dark:text-white leading-relaxed" style="display: block;">
                            <strong class="font-medium text-green-600 dark:text-green-400">原始摘要:</strong> ${{paper.summary_translation}}
                        </div>
                        ` : ''}}
                        ${{paper.summary ? `
                        <div class="english-summary text-sm text-black dark:text-white leading-relaxed" style="display: none;">
                            <strong class="font-medium text-green-600 dark:text-green-400">Original Abstract:</strong> ${{paper.summary}}
                        </div>
                        ` : ''}}
                    </div>
                    ` : ''}}

                    <!-- 论文链接 -->
                    <div class="flex flex-wrap gap-2">
                        <a href="https://arxiv.org/abs/${{paper.arxiv_id}}" target="_blank" 
                           class="inline-flex items-center px-3 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-md transition-colors">
                            📄 arXiv 原文
                        </a>
                        <a href="https://arxiv.org/pdf/${{paper.arxiv_id}}.pdf" target="_blank" 
                           class="inline-flex items-center px-3 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-md transition-colors">
                            📋 PDF 下载
                        </a>
                        <a href="https://papers.cool/arxiv/${{paper.arxiv_id}}" target="_blank" 
                           class="inline-flex items-center px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors">
                            🔥 Cool Paper
                        </a>
                    </div>
                </div>
            `;
        }}

        // 创建分类HTML
        function createCategoryHTML(category, date) {{
            const categoryId = `category-${{date}}-${{category.name.replace(/\\s+/g, '-')}}`;
            let papersHTML = '';
            
            if (category.papers && category.papers.length > 0) {{
                category.papers.forEach(paper => {{
                    papersHTML += `
                        <li>
                            ${{createPaperHTML(paper, date)}}
                        </li>
                    `;
                }});
            }} else {{
                papersHTML = '<li class="pl-7 text-sm text-slate-500 dark:text-slate-400">此分类下暂无论文。</li>';
            }}
            
            return `
                <li class="mb-4">
                    <div class="category-toggle flex items-center justify-between cursor-pointer p-3 rounded-md hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors" data-target="${{categoryId}}">
                        <div class="flex items-center space-x-3">
                            <svg class="h-4 w-4 text-slate-500 rotate-90-transition transform transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                            </svg>
                            <span class="font-medium text-sky-700 dark:text-sky-400">${{category.name}}</span>
                        </div>
                        <span class="text-xs font-mono bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-full px-2 py-0.5">${{category.count}}</span>
                    </div>
                    <div id="${{categoryId}}" class="category-content hidden pl-1 pt-2 border-l border-slate-200 dark:border-slate-700 ml-4">
                        <ul class="space-y-4">
                            ${{papersHTML}}
                        </ul>
                    </div>
                </li>
            `;
        }}

        // 渲染论文列表
        function renderPapers() {{
            const mainContent = document.getElementById('main-content');
            const loading = document.getElementById('loading');
            
            loading.classList.add('hidden');
            
            let html = '';
            let totalPapers = 0;
            
            for (const date in allPapers) {{
                const categories = allPapers[date];
                if (categories.length === 0) continue;
                
                const dateTotal = categories.reduce((sum, cat) => sum + cat.count, 0);
                totalPapers += dateTotal;
                
                html += `
                    <section class="mb-8">
                        <h2 class="text-lg font-medium text-slate-500 dark:text-slate-400 mb-4">${{date}} (${{dateTotal}} 篇论文)</h2>
                        <div class="bg-white dark:bg-slate-800/50 rounded-lg shadow-sm p-4 sm:p-6">
                            <ul class="space-y-2">
                `;
                
                categories.forEach(category => {{
                    html += createCategoryHTML(category, date);
                }});
                
                html += `
                            </ul>
                        </div>
                    </section>
                `;
            }}
            
            mainContent.innerHTML = html;
            updateStats();
            
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
            
            // 添加分类展开/折叠功能
            document.querySelectorAll('.category-toggle').forEach(button => {{
                button.addEventListener('click', () => {{
                    const targetId = button.getAttribute('data-target');
                    const content = document.getElementById(targetId);
                    const icon = button.querySelector('svg');
                    
                    content.classList.toggle('hidden');
                    icon.classList.toggle('rotate-90');
                }});
            }});
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

        // 初始化应用
        document.addEventListener('DOMContentLoaded', function() {{
            loadState();
            setupThemeToggle();
            setupSummaryToggle();
            renderPapers();
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
