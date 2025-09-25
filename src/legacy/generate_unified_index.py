#!/usr/bin/env python3
"""
生成统一的HTML页面，包含所有论文数据
Generate unified HTML page with all paper data
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

def load_paper_data() -> Dict[str, List[Dict[str, Any]]]:
    """加载论文数据"""
    papers_by_date = {}
    summary_dir = Path("summary")
    
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

def generate_unified_html() -> str:
    """生成统一的HTML页面"""
    papers_by_date = load_paper_data()
    
    # 读取HTML模板
    template_path = Path("unified_index.html")
    if not template_path.exists():
        raise FileNotFoundError("unified_index.html 模板文件不存在")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 按分类组织论文数据
    category_names = {
        'cs.AI': 'Artificial Intelligence',
        'cs.CL': 'Computation and Language', 
        'cs.LG': 'Machine Learning',
        'cs.CV': 'Computer Vision and Pattern Recognition',
        'cs.MA': 'Multiagent Systems'
    }
    
    # 生成JavaScript数据
    js_data = "const realPapers = {\n"
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
                js_data += f'                    "summary2": "{escape_js_string(paper.get("summary2", ""))}"\n'
                js_data += "                },\n"
            
            js_data += "            ]\n"
            js_data += "        },\n"
        js_data += "    ],\n"
    js_data += "};\n"
    
    # 替换模板中的mock数据
    mock_data_start = html_content.find('const mockPapers = {')
    if mock_data_start == -1:
        raise ValueError("找不到mockPapers数据定义")
    
    # 找到对应的结束位置
    brace_count = 0
    pos = mock_data_start + len('const mockPapers = ')
    start_pos = pos
    
    while pos < len(html_content):
        if html_content[pos] == '{':
            brace_count += 1
        elif html_content[pos] == '}':
            brace_count -= 1
            if brace_count == 0:
                break
        pos += 1
    
    if brace_count != 0:
        raise ValueError("找不到mockPapers数据的结束位置")
    
    # 替换数据
    replacement = js_data.replace('const realPapers', 'const mockPapers')
    html_content = html_content[:mock_data_start] + replacement + html_content[pos + 2:]
    
    return html_content

def main():
    """主函数"""
    try:
        html_content = generate_unified_html()
        
        # 确保webpages目录存在
        webpages_dir = Path("webpages")
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
