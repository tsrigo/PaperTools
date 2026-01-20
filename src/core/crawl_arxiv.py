#!/usr/bin/env python3
"""
增强版arXiv论文爬取脚本
Enhanced arXiv paper crawler with improved functionality
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import sys
from datetime import datetime
import time
import argparse
from typing import List, Dict, Tuple, Set
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入配置
try:
    from src.utils.config import ARXIV_PAPER_DIR, CRAWL_CATEGORIES, MAX_PAPERS_PER_CATEGORY, MAX_WORKERS, DATE_FORMAT
    from src.utils.cache_manager import CacheManager
except ImportError:
    # 如果没有config文件，使用默认配置
    ARXIV_PAPER_DIR = "arxiv_paper"
    CRAWL_CATEGORIES = ['cs.AI', 'cs.CL', 'cs.CV', 'cs.LG', 'cs.MA']
    MAX_PAPERS_PER_CATEGORY = 1000
    MAX_WORKERS = 4
    DATE_FORMAT = "%Y-%m-%d"
    CacheManager = None

# 全局缓存管理器
_cache_manager = None

def get_cache_manager():
    """获取缓存管理器单例"""
    global _cache_manager
    if _cache_manager is None and CacheManager is not None:
        _cache_manager = CacheManager()
    return _cache_manager

# 基础URL模板
base_url = "https://papers.cool/arxiv/{}?show={}"
# 按日期查询的URL模板
date_url = "https://papers.cool/arxiv/{}?date={}&show={}"

def _normalize_date_to_yyyy_mm_dd(raw_text: str) -> str:
    """从任意包含日期的字符串中提取并规范化为 YYYY-MM-DD。

    支持的示例：
    - 2025-09-24
    - 2025/09/24
    - 2025.09.24
    - 2025-09-24T12:34:56Z
    - 2025/09/24 10:00
    返回规范化后的日期字符串；若无法提取，返回空字符串。
    """
    if not raw_text:
        return ""

    text = raw_text.strip()

    # 统一 T 分隔的日期时间
    if 'T' in text:
        text = text.split('T', 1)[0]

    # 常见分隔符替换为 '-'
    text = text.replace('/', '-').replace('.', '-')

    # 匹配 YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if not m:
        return ""

    year, month, day = m.groups()
    try:
        dt = datetime(int(year), int(month), int(day))
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return ""

def _extract_date_from_div(div) -> str:
    """尽可能从论文条目的 DOM 结构中提取并规范化日期为 YYYY-MM-DD。"""
    # 1) 原选择器
    date_p = div.find('p', class_='metainfo date')
    date_span = date_p.find('span', class_='date-data') if date_p else None
    if date_span and date_span.text:
        norm = _normalize_date_to_yyyy_mm_dd(date_span.text)
        if norm:
            return norm

    # 2) 回退：任何 class 含 "date" 的元素
    any_date_el = div.find(lambda tag: tag.has_attr('class') and any('date' in c for c in tag['class']))
    if any_date_el and any_date_el.text:
        norm = _normalize_date_to_yyyy_mm_dd(any_date_el.text)
        if norm:
            return norm

    # 3) 回退：在整块文本里用正则提取
    block_text = div.get_text(separator=' ', strip=True)
    norm = _normalize_date_to_yyyy_mm_dd(block_text)
    return norm

def scrape_papers_for_date_range(category: str, max_papers: int, delay: float, start_date: str, end_date: str, use_cache: bool = True) -> Tuple[List[Dict], Set[str]]:
    """
    爬取指定日期范围内的论文

    Args:
        category: 论文类别
        max_papers: 最大爬取数量
        delay: 请求间隔时间
        start_date: 起始日期，格式为 'YYYY-MM-DD'
        end_date: 结束日期，格式为 'YYYY-MM-DD'
        use_cache: 是否使用缓存

    Returns:
        Tuple[List[Dict], Set[str]]: (论文列表, 论文ID集合)
    """
    from datetime import datetime, timedelta

    all_papers = []
    all_paper_ids = set()

    # 解析日期
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    print(f"🔍 正在爬取类别 {category}，日期范围: {start_date} 到 {end_date}")

    # 遍历日期范围
    current_dt = start_dt
    while current_dt <= end_dt:
        current_date_str = current_dt.strftime('%Y-%m-%d')
        print(f"  📅 爬取日期: {current_date_str}")

        papers, paper_ids = scrape_papers(category, max_papers, delay, current_date_str, use_cache)

        # 合并结果，避免重复
        for paper in papers:
            paper_id = paper.get('arxiv_id', '') or paper['link'].split('/')[-1]
            if paper_id not in all_paper_ids:
                all_papers.append(paper)
                all_paper_ids.add(paper_id)

        current_dt += timedelta(days=1)

        # 添加额外延时避免请求过快
        time.sleep(delay)

    print(f"✅ 日期范围爬取完成 {category}: {len(all_papers)} 篇去重论文")
    return all_papers, all_paper_ids


def scrape_papers(category: str, max_papers: int = MAX_PAPERS_PER_CATEGORY, delay: float = 1.0, target_date: str = None, use_cache: bool = True) -> Tuple[List[Dict], Set[str]]:
    """
    爬取指定类别的论文

    Args:
        category: 论文类别，如 'cs.AI'
        max_papers: 最大爬取数量
        delay: 请求间隔时间
        target_date: 目标日期，格式为 'YYYY-MM-DD'，如果为None则爬取最新论文
        use_cache: 是否使用缓存

    Returns:
        Tuple[List[Dict], Set[str]]: (论文列表, 论文ID集合)
    """
    # 尝试从缓存获取
    cache_manager = get_cache_manager()
    cache_date = target_date or datetime.now().strftime('%Y-%m-%d')

    if use_cache and cache_manager:
        cached_papers = cache_manager.get_crawl_cache(category, cache_date)
        if cached_papers is not None:
            print(f"📦 从缓存加载 {category} ({cache_date}): {len(cached_papers)} 篇论文")
            paper_ids = set(p.get('arxiv_id', p['link'].split('/')[-1]) for p in cached_papers)
            return cached_papers, paper_ids

    if target_date:
        url = date_url.format(category, target_date, max_papers)
        print(f"🔍 正在爬取类别 {category}，日期: {target_date}，最大数量: {max_papers}")
    else:
        url = base_url.format(category, max_papers)
        print(f"🔍 正在爬取类别 {category}，最大数量: {max_papers}")
    
    papers = []
    paper_ids = set()
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # 添加延时避免请求过快
        time.sleep(delay)
        
    except requests.RequestException as e:
        print(f"❌ 获取 {category} 失败: {e}")
        return papers, paper_ids

    soup = BeautifulSoup(response.text, 'html.parser')
    paper_divs = soup.find_all('div', class_='panel paper')

    print(f"📄 找到 {len(paper_divs)} 个论文条目")
    
    for div in tqdm(paper_divs, desc=f"解析 {category}", leave=False):
        paper_id = div.get('id', '')
        if paper_id in paper_ids:
            continue

        # 提取论文信息
        index_span = div.find('span', class_='index notranslate')
        index = index_span.text.strip() if index_span else ''

        title_a = div.find('a', class_='title-link')
        title = title_a.text.strip() if title_a else ''
        link = title_a['href'] if title_a else ''

        authors_p = div.find('p', class_='metainfo authors notranslate')
        authors_list = [a.text.strip() for a in authors_p.find_all('a', class_='author notranslate')] if authors_p else []
        authors = ', '.join(authors_list)

        summary_p = div.find('p', class_='summary')
        summary = summary_p.text.strip() if summary_p else ''

        subjects_p = div.find('p', class_='metainfo subjects')
        subjects_list = [a.text.strip() for a in subjects_p.find_all('a', class_=lambda x: x and x.startswith('subject-'))] if subjects_p else []
        subjects = ', '.join(subjects_list)

        # 解析发布日期，带有多重回退与规范化
        date = _extract_date_from_div(div)

        # 提取arXiv ID
        arxiv_id = ''
        if link:
            arxiv_id = link.split('/')[-1] if '/' in link else link

        paper = {
            'index': index,
            'title': title,
            'link': link,
            'arxiv_id': arxiv_id,
            'authors': authors,
            'summary': summary,
            'subjects': subjects,
            'date': date,
            'category': category,
            'crawl_time': datetime.now().isoformat()
        }

        papers.append(paper)
        paper_ids.add(paper_id)

    print(f"✅ 成功爬取 {len(papers)} 篇论文 ({category})")

    # 保存到缓存
    if use_cache and cache_manager and papers:
        cache_manager.set_crawl_cache(category, cache_date, papers)
        print(f"💾 已缓存 {category} ({cache_date}): {len(papers)} 篇论文")

    return papers, paper_ids

def save_papers(all_papers: Dict, selected_categories: List[str], output_dir: str, current_date: str, target_date: str = None) -> str:
    """仅保存所有论文的合并文件到JSON。"""
    
    # 如果指定了目标日期，使用目标日期作为文件名后缀
    # 如果没有指定目标日期，从论文数据中推断最常见的发布日期
    if target_date:
        date_suffix = target_date
    else:
        # 从论文中推断最常见的发布日期
        paper_dates = []
        for paper in all_papers.values():
            paper_date = paper.get('date', '')
            if not paper_date:
                continue
            norm = _normalize_date_to_yyyy_mm_dd(paper_date)
            if norm:
                paper_dates.append(norm)
        
        if paper_dates:
            # 使用最新的论文发布日期
            date_suffix = max(paper_dates)
            print(f"📅 从论文数据中推断出发布日期: {date_suffix}")
        else:
            # 如果无法推断，使用当前日期
            date_suffix = current_date
            print(f"⚠️ 无法推断论文发布日期，使用当前日期: {date_suffix}")

    # 只保存合并文件
    combined_filename = f"{'_'.join(sorted(selected_categories))}_paper_{date_suffix}.json"
    combined_filepath = os.path.join(output_dir, combined_filename)
    with open(combined_filepath, 'w', encoding='utf-8') as f:
        json.dump(list(all_papers.values()), f, ensure_ascii=False, indent=4)
    print(f"📚 已保存 {len(all_papers)} 篇去重论文到 {combined_filepath}")
    
    return combined_filepath


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='增强版arXiv论文爬取工具')
    parser.add_argument('--categories', nargs='+', default=['all'], 
                       help='要爬取的类别，可选: cs.AI cs.CL cs.CV cs.LG cs.MA 或 all')
    parser.add_argument('--max-papers', type=int, default=MAX_PAPERS_PER_CATEGORY,
                       help=f'每个类别最大爬取数量 (默认: {MAX_PAPERS_PER_CATEGORY})')
    parser.add_argument('--output-dir', default=ARXIV_PAPER_DIR,
                       help=f'输出目录 (默认: {ARXIV_PAPER_DIR})')
    parser.add_argument('--delay', type=float, default=1.0,
                       help='请求间隔时间，秒 (默认: 1.0)')
    parser.add_argument('--max-workers', type=int, default=MAX_WORKERS,
                       help=f'最大线程数 (默认: {MAX_WORKERS})')
    parser.add_argument('--date', default=None,
                       help='指定日期 (格式: YYYY-MM-DD)，不指定则爬取最新论文')
    parser.add_argument('--start-date', default=None,
                       help='起始日期 (格式: YYYY-MM-DD)，与--end-date一起使用指定日期范围')
    parser.add_argument('--end-date', default=None,
                       help='结束日期 (格式: YYYY-MM-DD)，与--start-date一起使用指定日期范围')
    parser.add_argument('--no-cache', action='store_true',
                       help='禁用缓存，强制重新爬取')
    parser.add_argument('--clear-cache', action='store_true',
                       help='清理过期缓存后退出')

    args = parser.parse_args()

    # 处理清理缓存请求
    if args.clear_cache:
        cache_manager = get_cache_manager()
        if cache_manager:
            cache_manager.clean_expired_cache()
            stats = cache_manager.get_cache_stats()
            print("📊 缓存统计:")
            for cache_type, count in stats.items():
                print(f"  {cache_type}: {count}")
        else:
            print("⚠️ 缓存管理器不可用")
        return
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 获取当前日期
    current_date = datetime.now().strftime(DATE_FORMAT)
    
    # 处理类别选择
    selected_categories = args.categories
    if 'all' in selected_categories:
        selected_categories = CRAWL_CATEGORIES
    
    # 验证类别
    valid_categories = [cat for cat in selected_categories if cat in CRAWL_CATEGORIES]
    if not valid_categories:
        print("❌ 没有选择有效的类别。可用类别:", CRAWL_CATEGORIES)
        return
    
    # 处理日期参数
    use_date_range = args.start_date and args.end_date
    if use_date_range and args.date:
        print("❌ 不能同时指定单个日期和日期范围")
        return
    
    print("🚀 开始爬取arXiv论文")
    print(f"📋 选择的类别: {valid_categories}")
    print(f"📊 每类最大数量: {args.max_papers}")
    print(f"📁 输出目录: {args.output_dir}")
    print(f"💾 缓存: {'禁用' if args.no_cache else '启用'}")
    
    if use_date_range:
        print(f"📅 日期范围: {args.start_date} 到 {args.end_date}")
    elif args.date:
        print(f"📅 目标日期: {args.date}")
    else:
        print("📅 爬取模式: 最新论文")
    print("=" * 50)
    
    # 存储所有论文，避免重复
    all_papers = {}
    global_paper_ids = set()
    
    # 多线程爬取各类别论文
    use_cache = not args.no_cache

    def scrape_category_wrapper(category):
        """包装函数，用于多线程执行"""
        try:
            if use_date_range:
                return scrape_papers_for_date_range(category, args.max_papers, args.delay, args.start_date, args.end_date, use_cache)
            else:
                return scrape_papers(category, args.max_papers, args.delay, args.date, use_cache)
        except Exception as e:
            print(f"❌ 爬取类别 {category} 时出错: {e}")
            return [], set()
    
    print(f"🔄 使用 {args.max_workers} 个线程并行爬取...")
    
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # 提交所有爬取任务
        future_to_category = {
            executor.submit(scrape_category_wrapper, category): category 
            for category in valid_categories
        }
        
        # 收集结果
        for future in tqdm(as_completed(future_to_category), total=len(valid_categories), desc="爬取类别"):
            category = future_to_category[future]
            try:
                category_papers, paper_ids = future.result()
                
                for paper in category_papers:
                    paper_id = paper.get('arxiv_id', '') or paper['link'].split('/')[-1]
                    if paper_id not in global_paper_ids:
                        all_papers[paper_id] = paper
                        global_paper_ids.add(paper_id)
                        
            except Exception as e:
                print(f"❌ 处理类别 {category} 结果时出错: {e}")
                continue
    
    if not all_papers:
        print("❌ 没有成功爬取到任何论文")
        return
    
    # 保存论文
    if use_date_range:
        # 对于日期范围，使用起始日期作为主要标识
        target_date_for_filename = f"{args.start_date}_to_{args.end_date}"
    else:
        target_date_for_filename = args.date
    
    output_file = save_papers(all_papers, valid_categories, args.output_dir, current_date, target_date_for_filename)
    
    # 打印统计信息
    print("\n" + "=" * 50)
    print("🎉 爬取完成！")
    print(f"📊 总共爬取: {len(all_papers)} 篇去重论文")
    print(f"📂 主输出文件: {output_file}")
    print("=" * 50)


if __name__ == "__main__":
    main()