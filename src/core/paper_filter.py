#!/usr/bin/env python3
"""
增强版论文筛选脚本
Enhanced paper filtering script with improved functionality
"""

import json
import os
import sys
import argparse
from datetime import datetime
from typing import Tuple
from tqdm import tqdm
from openai import OpenAI, OpenAIError
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入配置
try:
    from src.utils.config import API_KEY, BASE_URL, MODEL, DOMAIN_PAPER_DIR, TEMPERATURE, REQUEST_DELAY, PAPER_FILTER_PROMPT, MAX_WORKERS
except ImportError:
    raise ImportError("⚠️ 错误: 未找到config.py")

def query_llm(title: str, summary: str, client: OpenAI, model: str, temperature: float = TEMPERATURE) -> Tuple[bool, str]:
    """
    使用大模型判断论文是否符合筛选条件
    
    Args:
        title: 论文标题
        summary: 论文摘要
        client: OpenAI客户端
        model: 使用的模型
        temperature: 生成温度
    
    Returns:
        tuple[bool, str]: (是否符合筛选条件, 筛选理由)
    """
    messages = [
        {
            "role": "system",
            "content": "你是一个专业的学术论文筛选助手。请根据给定的筛选条件，准确判断论文是否符合要求。"
        },
        {
            "role": "user",
            "content": PAPER_FILTER_PROMPT.format(title=title, summary=summary)
        }
    ]
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True  # 使用流式响应避免524超时
        )
        # 收集流式响应
        response_text = ""
        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    response_text += delta.content
        response_text = response_text.strip()

        # 解析结果和理由
        result = False
        reason = "解析失败"
        
        # 寻找结果和理由的位置
        reason_index = -1

        lines = response_text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith('结果:') or line.startswith('结果：'):
                # 处理可能存在的全角和半角冒号
                sep = ':' if ':' in line else '：'
                parts = line.split(sep, 1)
                if len(parts) > 1:
                    result_part = parts[1].strip().lower()
                    result = result_part == 'true'
            elif line.startswith('理由:') or line.startswith('理由：'):
                reason_index = i
                break
        
        # 如果找到理由标识，获取后面的所有内容作为理由
        if reason_index >= 0:
            reason_lines = []
            # 处理可能存在的全角和半角冒号
            current_line = lines[reason_index]
            sep = ':' if ':' in current_line else '：'
            parts = current_line.split(sep, 1)
            
            if len(parts) > 1:
                first_line = parts[1].strip()
                if first_line:
                    reason_lines.append(first_line)
            
            # 获取后续所有行作为理由的一部分
            for i in range(reason_index + 1, len(lines)):
                line = lines[i].strip()
                if line:  # 跳过空行
                    reason_lines.append(line)
            
            if reason_lines:
                reason = ' '.join(reason_lines)
        
        return result, reason
        
    except OpenAIError as e:
        error_msg = f"API调用错误: {e}"
        print(f"❌ {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"未知错误: {e}"
        print(f"❌ {error_msg}")
        return False, error_msg

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='增强版论文筛选工具')
    parser.add_argument('--input-file', required=True, 
                       help='输入的JSON文件路径')
    parser.add_argument('--output-dir', default=DOMAIN_PAPER_DIR,
                       help=f'输出目录 (默认: {DOMAIN_PAPER_DIR})')
    parser.add_argument('--api-key', default=API_KEY,
                       help='API密钥')
    parser.add_argument('--base-url', default=BASE_URL,
                       help='API基础URL')
    parser.add_argument('--model', default=MODEL,
                       help='使用的模型')
    parser.add_argument('--temperature', type=float, default=TEMPERATURE,
                       help='生成温度')
    parser.add_argument('--max-papers', type=int, default=0,
                       help='最大处理论文数量，0表示处理所有（推荐处理所有）')
    parser.add_argument('--max-workers', type=int, default=MAX_WORKERS,
                       help=f'最大线程数 (默认: {MAX_WORKERS})')
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input_file):
        print(f"❌ 输入文件未找到: {args.input_file}")
        return
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 初始化OpenAI客户端
    client = OpenAI(
        api_key=args.api_key,
        base_url=args.base_url,
        timeout=180.0,  # 增加超时时间，避免524错误
    )
    
    print("🔍 开始论文筛选")
    print(f"📁 输入文件: {args.input_file}")
    print(f"🤖 使用模型: {args.model}")
    print("=" * 50)
    
    # 加载论文数据
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            papers = json.load(f)
        print(f"📚 成功加载 {len(papers)} 篇论文")
    except Exception as e:
        print(f"❌ 读取文件时出错: {e}")
        return
    
    # 检查是否存在已筛选的结果（断点续传）
    current_date = datetime.now().strftime('%Y%m%d')
    input_filename = os.path.basename(args.input_file)
    date_part = input_filename.split('_')[-1].split('.json')[0] if '_' in input_filename else current_date
    
    output_filename = f"filtered_papers_{date_part}.json"
    output_filepath = os.path.join(args.output_dir, output_filename)
    excluded_filename = f"excluded_papers_{date_part}.json"
    excluded_filepath = os.path.join(args.output_dir, excluded_filename)
    
    # 加载已筛选的论文
    existing_filtered = []
    existing_excluded = []
    processed_arxiv_ids = set()
    
    if os.path.exists(output_filepath):
        try:
            with open(output_filepath, 'r', encoding='utf-8') as f:
                existing_filtered = json.load(f)
            for paper in existing_filtered:
                processed_arxiv_ids.add(paper.get('arxiv_id', ''))
            print(f"🔄 发现已筛选结果: {len(existing_filtered)} 篇论文")
        except Exception as e:
            print(f"⚠️ 读取已筛选文件时出错: {e}")
    
    if os.path.exists(excluded_filepath):
        try:
            with open(excluded_filepath, 'r', encoding='utf-8') as f:
                existing_excluded = json.load(f)
            for paper in existing_excluded:
                processed_arxiv_ids.add(paper.get('arxiv_id', ''))
            print(f"🔄 发现已排除结果: {len(existing_excluded)} 篇论文")
        except Exception as e:
            print(f"⚠️ 读取已排除文件时出错: {e}")
    
    # 过滤出尚未处理的论文
    unprocessed_papers = []
    for paper in papers:
        arxiv_id = paper.get('arxiv_id', '')
        if arxiv_id not in processed_arxiv_ids:
            unprocessed_papers.append(paper)
    
    if processed_arxiv_ids:
        print(f"📊 断点续传: 跳过已处理的 {len(processed_arxiv_ids)} 篇，处理剩余 {len(unprocessed_papers)} 篇")
        papers = unprocessed_papers
    
    if not papers:
        print("✅ 所有论文都已处理完成！")
        return
    
    # 限制处理数量
    if args.max_papers > 0:
        papers = papers[:args.max_papers]
        print(f"🔢 限制处理数量为: {args.max_papers}")
    
    # 多线程筛选论文
    def filter_paper_wrapper(paper):
        """包装函数，用于多线程筛选"""
        title = paper.get('title', '').strip()
        summary = paper.get('summary', '') or paper.get('abstract', '')
        
        if not title or not summary:
            return 'skip', paper, f"跳过论文 (缺少标题或摘要): {title[:50]}...", "缺少标题或摘要"
        
        try:
            is_match, reason = query_llm(title, summary, client, args.model, args.temperature)
            # 添加筛选理由到论文数据中
            paper_with_reason = paper.copy()
            paper_with_reason['filter_reason'] = reason
            
            if is_match:
                return 'include', paper_with_reason, f"✅ 匹配: {title[:50]}...", reason
            else:
                return 'exclude', paper_with_reason, f"⏭️ 不匹配: {title[:50]}...", reason
            
        except Exception as e:
            return 'error', paper, f"❌ 处理论文时出错: {e}", f"处理错误: {e}"
    
    print(f"🔄 使用 {args.max_workers} 个线程并行筛选...")
    print(f"📊 开始处理 {len(papers)} 篇论文...")
    
    filtered_papers = []  # 匹配的论文
    excluded_papers = []  # 被排除的论文（用于人工审核）
    
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # 提交所有筛选任务
        futures = [executor.submit(filter_paper_wrapper, paper) for paper in papers]
        
        # 收集结果
        processed_count = 0
        matched_count = 0
        
        for future in tqdm(as_completed(futures), total=len(papers), desc="筛选论文", 
                          unit="篇", ncols=80):
            try:
                status, paper, message, reason = future.result()
                
                processed_count += 1
                
                if status == 'include':
                    filtered_papers.append(paper)
                    matched_count += 1
                    # print(f"✅ [{matched_count}/{processed_count}] {message}")
                elif status == 'exclude':
                    # 移除summary字段以节省空间，但保留筛选理由
                    excluded_paper = paper.copy()
                    if 'summary' in excluded_paper:
                        del excluded_paper['summary']
                    if 'abstract' in excluded_paper:
                        del excluded_paper['abstract']
                    excluded_papers.append(excluded_paper)
                    # print(f"⏭️ [{matched_count}/{processed_count}] {message}")
                elif status == 'skip':
                    # print(f"⏸️ [{matched_count}/{processed_count}] {message}")
                    pass
                else:  # error
                    print(f"❌ [{matched_count}/{processed_count}] {message}")
                
                # 添加小延时避免API请求过快
                time.sleep(REQUEST_DELAY / args.max_workers)  # 根据线程数调整延时
                
            except Exception as e:
                print(f"❌ 获取筛选结果时出错: {e}")
                continue
    
    # 打印筛选结果
    print("\n📊 筛选完成！")
    print(f"📈 总论文数: {len(papers)}")
    print(f"🎯 筛选后论文数: {len(filtered_papers)}")
    print(f"🚫 被排除论文数: {len(excluded_papers)}")
    print(f"📊 筛选率: {len(filtered_papers)/len(papers)*100:.1f}%")
    
    if filtered_papers:
        print("\n📋 筛选出的论文:")
        for i, paper in enumerate(filtered_papers[:10], 1):  # 只显示前10篇
            print(f"{i:2d}. {paper['title']}")
        if len(filtered_papers) > 10:
            print(f"    ... 还有 {len(filtered_papers) - 10} 篇")
    
    # 合并新筛选结果与已有结果
    all_filtered_papers = existing_filtered + filtered_papers
    all_excluded_papers = existing_excluded + excluded_papers
    
    # 保存筛选结果
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            json.dump(all_filtered_papers, f, ensure_ascii=False, indent=4)
        print(f"\n💾 筛选结果已保存到: {output_filepath}")
        print(f"📊 总计: {len(all_filtered_papers)} 篇筛选通过的论文 (本次新增: {len(filtered_papers)} 篇)")
    except Exception as e:
        print(f"❌ 保存文件时出错: {e}")
        return
    
    # 保存被排除的论文（用于人工审核）
    if all_excluded_papers:
        try:
            with open(excluded_filepath, 'w', encoding='utf-8') as f:
                json.dump(all_excluded_papers, f, ensure_ascii=False, indent=4)
            print(f"🔍 被排除论文已保存到: {excluded_filepath} (总计: {len(all_excluded_papers)} 篇)")
        except Exception as e:
            print(f"❌ 保存被排除论文时出错: {e}")
    
    print("🎉 筛选完成！")


if __name__ == "__main__":
    main()