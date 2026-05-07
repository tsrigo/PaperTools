#!/usr/bin/env python3
"""
增强版论文筛选脚本
Enhanced paper filtering script with topic + prestige hard filters
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI, OpenAIError
from tqdm import tqdm

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入配置
try:
    from src.core.generate_summary import (  # noqa: E402
        strip_think_tags,
    )
    from src.utils.cache_manager import CacheManager  # noqa: E402
    from src.utils.config import (  # noqa: E402
        API_KEY,
        BASE_URL,
        DOMAIN_PAPER_DIR,
        ENABLE_CACHE,
        FILTER_MODEL,
        MAX_WORKERS,
        PAPER_FILTER_PROMPT,
        PRESTIGE_AUTHOR_WHITELIST,
        PRESTIGE_COMPANY_WHITELIST,
        PRESTIGE_CONTEXT_CHARS,
        PRESTIGE_ENABLED,
        PRESTIGE_FILTER_PROMPT,
        PRESTIGE_INSTITUTION_WHITELIST,
        PRESTIGE_RULE_VERSION,
        REQUEST_DELAY,
        TEMPERATURE,
    )
except ImportError as exc:
    raise ImportError(f"⚠️ 错误: 未找到依赖模块: {exc}") from exc

from src.document_extraction import ExtractionManager  # noqa: E402
from src.utils.exceptions import ValidationError  # noqa: E402
from src.utils.io import save_json  # noqa: E402
from src.utils.retry import retry_with_backoff  # noqa: E402
from src.utils.validation import validate_non_negative_int, validate_positive_int  # noqa: E402


SOURCE_METADATA_FIELDS = (
    'index',
    'title',
    'link',
    'arxiv_id',
    'authors',
    'summary',
    'abstract',
    'subjects',
    'date',
    'source_date',
    'category',
    'crawl_time',
)

FILTER_LLM_TIMEOUT = float(os.getenv("PAPERTOOLS_FILTER_LLM_TIMEOUT", "45"))
FILTER_LLM_MAX_RETRIES = int(os.getenv("PAPERTOOLS_FILTER_LLM_MAX_RETRIES", "1"))
FILTER_EXTRACT_CHAIN = os.getenv("PAPERTOOLS_FILTER_EXTRACT_CHAIN", "jina")
FILTER_EXTRACT_TIMEOUT = int(os.getenv("PAPERTOOLS_FILTER_EXTRACT_TIMEOUT", "45"))
PRESTIGE_LLM_ENABLED = os.getenv("PAPERTOOLS_PRESTIGE_LLM_ENABLED", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PRESTIGE_AFFILIATION_FETCH_ENABLED = os.getenv(
    "PAPERTOOLS_PRESTIGE_AFFILIATION_FETCH_ENABLED",
    "0",
).lower() in {
    "1",
    "true",
    "yes",
    "on",
}


class LLMResponseParseError(ValueError):
    """Raised when a filter LLM response cannot be parsed safely."""


def has_non_empty_text(value: Any) -> bool:
    """Return True when a value is meaningful display text."""
    return isinstance(value, str) and bool(value.strip())


def write_status_file(status_file: Optional[str], payload: Dict[str, Any]) -> None:
    """Best-effort structured status for the pipeline wrapper."""
    if not status_file:
        return
    try:
        status_dir = os.path.dirname(status_file)
        if status_dir:
            os.makedirs(status_dir, exist_ok=True)
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"⚠️ 写入状态文件失败: {exc}")


def build_source_paper_index(papers: List[dict]) -> Dict[str, dict]:
    """Index freshly crawled papers by arXiv id for repairing resumed results."""
    source_by_id: Dict[str, dict] = {}
    for paper in papers:
        arxiv_id = (paper.get('arxiv_id') or '').strip()
        if arxiv_id:
            source_by_id[arxiv_id] = paper
    return source_by_id


def repair_paper_metadata_from_source(paper: dict, source_paper: Optional[dict]) -> Tuple[dict, bool]:
    """Backfill metadata that older filter outputs may have dropped."""
    if not source_paper:
        return paper, False

    repaired = paper.copy()
    changed = False

    for field in SOURCE_METADATA_FIELDS:
        source_value = source_paper.get(field)
        if source_value is None:
            continue

        current_value = repaired.get(field)
        if field in {'summary', 'abstract'}:
            should_repair = has_non_empty_text(source_value) and not has_non_empty_text(current_value)
        else:
            should_repair = current_value in (None, '') and source_value not in (None, '')

        if should_repair:
            repaired[field] = source_value
            changed = True

    return repaired, changed


def parse_llm_response(response_text: str) -> Tuple[bool, str]:
    """解析 LLM 响应中的结果和理由。"""
    response_text = strip_think_tags(response_text).strip()

    result_match = re.search(r'结果[:：]\s*(True|False)', response_text, flags=re.IGNORECASE)
    reason_match = re.search(r'理由[:：]\s*(.*)', response_text, flags=re.DOTALL)

    if not result_match:
        preview = response_text[:500] if response_text else "<empty response>"
        raise LLMResponseParseError(f"无法解析 LLM 筛选结果字段: {preview}")

    result = result_match.group(1).lower() == 'true'
    reason = ""

    if reason_match:
        reason = reason_match.group(1).strip()
    elif response_text:
        reason = response_text

    return result, reason


@retry_with_backoff(max_retries=FILTER_LLM_MAX_RETRIES, initial_delay=2.0, max_delay=8.0)
def run_llm_prompt(prompt: str, system: str, client: OpenAI, model: str,
                   temperature: float = TEMPERATURE) -> str:
    """执行 LLM prompt，并返回原始文本。"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        stream=False,
        timeout=FILTER_LLM_TIMEOUT,
    )

    response_text = ""
    if response.choices:
        message = response.choices[0].message
        if message and message.content:
            response_text = message.content

    return strip_think_tags(response_text)


def query_topic_llm(title: str, summary: str, client: OpenAI, model: str,
                    temperature: float = TEMPERATURE) -> Tuple[bool, str]:
    """使用主题筛选 prompt 判断论文是否相关。"""
    response_text = run_llm_prompt(
        PAPER_FILTER_PROMPT.format(title=title, summary=summary),
        "你是一个专业的学术论文筛选助手。请根据给定的筛选条件，准确判断论文是否符合要求。",
        client,
        model,
        temperature,
    )
    return parse_llm_response(response_text)


def query_prestige_llm(title: str, authors: str, affiliations: str, client: OpenAI,
                       model: str, temperature: float = TEMPERATURE,
                       cache_manager: Optional[CacheManager] = None) -> Tuple[bool, str]:
    """使用 prestige prompt 判断论文是否命中大牛/顶级机构。"""
    cache_key = f"prestige_filter_v3_{title}"
    cache_content = f"{authors}\n{affiliations}"

    if cache_manager and ENABLE_CACHE:
        cached_response = cache_manager.get_summary_cache(cache_key, cache_content)
        if cached_response:
            return parse_llm_response(cached_response)

    response_text = run_llm_prompt(
        PRESTIGE_FILTER_PROMPT.format(
            title=title,
            authors=authors,
            affiliations=affiliations,
        ),
        "你是一个极其严格的 AI 论文声望筛选助手。只根据作者和机构判断是否值得保留。",
        client,
        model,
        temperature,
    )

    if cache_manager and ENABLE_CACHE:
        cache_manager.set_summary_cache(cache_key, cache_content, response_text)

    return parse_llm_response(response_text)


def normalize_text(text: str) -> str:
    """归一化文本，便于白名单匹配。"""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def extract_institution_names(affiliations: str) -> List[str]:
    """从机构提取结果中解析机构名称列表。"""
    if not affiliations:
        return []

    cleaned = strip_think_tags(affiliations).strip()
    fence_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        data = json.loads(cleaned)
    except Exception:
        return [cleaned] if cleaned else []

    if not isinstance(data, dict):
        return [cleaned] if cleaned else []

    names = []
    seen = set()
    for inst in data.get('institutions', []):
        if not isinstance(inst, dict):
            continue
        name = (inst.get('name') or '').strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def find_whitelist_matches(values: List[str], whitelist: Dict[str, List[str]]) -> List[Dict[str, str]]:
    """在给定文本列表中查找白名单命中项。"""
    matches = []
    seen = set()

    for value in values:
        normalized_value = f" {normalize_text(value)} "
        if normalized_value.strip() == "":
            continue

        for canonical, aliases in whitelist.items():
            for alias in aliases:
                normalized_alias = normalize_text(alias)
                if not normalized_alias:
                    continue
                if f" {normalized_alias} " in normalized_value:
                    key = (canonical, value)
                    if key not in seen:
                        matches.append({
                            'canonical': canonical,
                            'matched_text': value,
                            'alias': alias,
                        })
                        seen.add(key)
                    break

    return matches


def evaluate_prestige_whitelist(authors: str, affiliations: str) -> Tuple[bool, str, str, dict]:
    """先用白名单做确定性筛选，未命中时再回退到 LLM。"""
    institution_names = extract_institution_names(affiliations)
    author_matches = find_whitelist_matches([authors], PRESTIGE_AUTHOR_WHITELIST)
    institution_matches = find_whitelist_matches(institution_names, PRESTIGE_INSTITUTION_WHITELIST)
    company_matches = find_whitelist_matches(institution_names, PRESTIGE_COMPANY_WHITELIST)

    match_payload = {
        'authors': [m['canonical'] for m in author_matches],
        'institutions': [m['canonical'] for m in institution_matches],
        'companies': [m['canonical'] for m in company_matches],
        'institution_names': institution_names,
    }

    reasons = []
    if author_matches:
        reasons.append("白名单命中大牛作者: " + ", ".join(m['canonical'] for m in author_matches))
    if institution_matches:
        reasons.append("白名单命中顶级学术机构: " + ", ".join(m['canonical'] for m in institution_matches))
    if company_matches:
        reasons.append("白名单命中知名公司/研究机构: " + ", ".join(m['canonical'] for m in company_matches))

    if reasons:
        source = 'whitelist'
        if author_matches and not institution_matches and not company_matches:
            source = 'whitelist_author'
        elif company_matches and not author_matches and not institution_matches:
            source = 'whitelist_company'
        elif institution_matches and not author_matches and not company_matches:
            source = 'whitelist_institution'
        return True, "；".join(reasons), source, match_payload

    return False, "", 'llm', match_payload


def resolve_missing_affiliations_prestige(
    title: str,
    authors: str,
    fetch_reason: str,
    paper_with_reason: dict,
    client: OpenAI,
    model: str,
    temperature: float,
    cache_manager: Optional[CacheManager] = None,
) -> Tuple[bool, dict, str]:
    """Apply the prestige hard filter when affiliation extraction is unavailable."""
    whitelist_match, whitelist_reason, whitelist_source, whitelist_matches = evaluate_prestige_whitelist(
        authors,
        "",
    )
    paper_with_reason['affiliations'] = ""
    paper_with_reason['prestige_matches'] = whitelist_matches
    paper_with_reason['prestige_rule_version'] = PRESTIGE_RULE_VERSION

    if whitelist_match:
        paper_with_reason['prestige_result'] = True
        paper_with_reason['prestige_reason'] = f"{whitelist_reason}；机构信息缺失: {fetch_reason}"
        paper_with_reason['prestige_source'] = whitelist_source
        paper_with_reason['prestige_status'] = 'verified'
        return True, paper_with_reason, paper_with_reason['prestige_reason']

    if not PRESTIGE_LLM_ENABLED:
        prestige_reason = f"机构信息缺失且未命中确定性白名单，按 prestige 硬筛排除: {fetch_reason}"
        paper_with_reason['prestige_result'] = False
        paper_with_reason['prestige_reason'] = prestige_reason
        paper_with_reason['prestige_source'] = 'deterministic_missing_affiliations'
        paper_with_reason['prestige_status'] = 'rejected'
        paper_with_reason['exclude_stage'] = 'prestige'
        return False, paper_with_reason, prestige_reason

    missing_affiliations_context = f"机构信息缺失。提取失败原因: {fetch_reason}"
    try:
        prestige_match, prestige_reason = query_prestige_llm(
            title,
            authors,
            missing_affiliations_context,
            client,
            model,
            temperature,
            cache_manager,
        )
    except Exception as exc:
        prestige_match = False
        prestige_reason = f"机构信息缺失且声望 LLM 判断失败，按硬筛排除: {exc}"

    paper_with_reason['prestige_result'] = prestige_match
    paper_with_reason['prestige_reason'] = f"{prestige_reason}\n\n机构提取状态: {fetch_reason}"
    paper_with_reason['prestige_source'] = 'llm_missing_affiliations'
    paper_with_reason['prestige_status'] = 'verified' if prestige_match else 'rejected'

    if not prestige_match:
        paper_with_reason['exclude_stage'] = 'prestige'

    return prestige_match, paper_with_reason, paper_with_reason['prestige_reason']


def get_affiliation_context(paper_content: str) -> str:
    """只保留首段上下文，控制机构提取成本。"""
    return paper_content[:PRESTIGE_CONTEXT_CHARS]


def query_affiliations_llm(paper_content: str, authors: str, client: OpenAI, model: str,
                           temperature: float, paper_title: str = "",
                           cache_manager: Optional[CacheManager] = None) -> str:
    """Extract affiliation JSON with the bounded non-streaming filter client."""
    cache_key = f"filter_affiliations_v1_{paper_title}"

    if cache_manager and ENABLE_CACHE:
        cached_response = cache_manager.get_summary_cache(cache_key, paper_content)
        if cached_response:
            return strip_think_tags(cached_response).strip()

    prompt = f"""{paper_content}

---

上面是一篇学术论文的内容。论文作者列表为：{authors}

请从论文中提取完整的作者-机构对应关系和所有角标信息（equal contribution、corresponding author、脚注等）。通常在论文的第一页标题下方会标注这些信息。

请严格按以下 JSON 格式输出，不要输出其他内容：
```json
{{
  "authors": [
    {{"name": "作者全名", "affiliations": [1], "markers": ["*"]}},
    {{"name": "作者全名", "affiliations": [1, 2], "markers": []}}
  ],
  "institutions": [
    {{"id": 1, "name": "机构简称"}},
    {{"id": 2, "name": "机构简称"}}
  ],
  "footnotes": [
    {{"marker": "*", "text": "Equal contribution"}},
    {{"marker": "†", "text": "Corresponding author"}}
  ]
}}
```

要求：
1. `affiliations` 是机构编号数组，一个作者可能属于多个机构
2. `markers` 是该作者拥有的特殊角标（如 *、†、‡），没有则为空数组
3. `institutions` 按编号排列，机构名称必须使用最短常见缩写
4. `footnotes` 包含论文中的角标说明
5. 如果找不到某作者的机构，`affiliations` 为空数组
6. 保持作者顺序与论文一致"""

    response_text = run_llm_prompt(
        prompt,
        "你是一个学术信息提取助手。请精确提取作者机构信息，只输出 JSON，不要输出其他内容。",
        client,
        model,
        temperature,
    )

    if cache_manager and ENABLE_CACHE:
        cache_manager.set_summary_cache(cache_key, paper_content, response_text)

    return response_text.strip()


def fetch_affiliations_for_prestige(paper: dict, client: OpenAI, model: str, temperature: float,
                                    cache_manager: Optional[CacheManager] = None,
                                    document_extractor: Optional[ExtractionManager] = None,
                                    api_key: str = API_KEY,
                                    base_url: str = BASE_URL) -> Tuple[Optional[str], str]:
    """为 prestige 筛选提取机构信息。"""
    paper_link = paper.get('link') or paper.get('arxiv_id', '')
    paper_title = paper.get('title', '')
    authors = paper.get('authors', '')

    if not paper_link:
        return None, "缺少论文链接，无法获取机构信息"

    extractor = document_extractor or ExtractionManager(cache_manager=cache_manager)
    try:
        paper_content = extractor.extract(paper_link).content
    except Exception as exc:
        return None, f"无法获取论文前置内容，待后续重试机构提取: {exc}"
    if not paper_content:
        return None, "无法获取论文前置内容，待后续重试机构提取"

    truncated_content = get_affiliation_context(paper_content)
    if not truncated_content.strip():
        return None, "论文前置内容为空，待后续重试机构提取"

    affiliations = query_affiliations_llm(
        truncated_content,
        authors,
        client,
        model,
        temperature,
        paper_title,
        cache_manager,
    )
    affiliations = affiliations.strip()

    if not affiliations:
        return None, "机构提取结果为空，待后续重试机构提取"

    return affiliations, "机构提取成功"


def compact_excluded_paper(paper: dict) -> dict:
    """精简被排除论文的冗余字段。"""
    excluded_paper = paper.copy()
    excluded_paper.pop('summary', None)
    excluded_paper.pop('abstract', None)
    return excluded_paper


def extract_date_part_from_filename(filename: str, fallback: str) -> str:
    """Preserve full YYYY-MM-DD_to_YYYY-MM-DD range labels from upstream files."""
    range_match = re.search(r'(\d{4}-\d{2}-\d{2}_to_\d{4}-\d{2}-\d{2})', filename)
    if range_match:
        return range_match.group(1)

    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if date_match:
        return date_match.group(1)

    return fallback


def is_current_filtered_schema(paper: dict) -> bool:
    """判断保留结果是否符合当前筛选结构。"""
    if 'filter_reason' not in paper:
        return False
    if not PRESTIGE_ENABLED:
        return True
    if paper.get('prestige_rule_version') != PRESTIGE_RULE_VERSION:
        return False

    prestige_result = paper.get('prestige_result')
    if prestige_result is True:
        return True

    return False


def is_current_excluded_schema(paper: dict) -> bool:
    """判断排除结果是否符合当前筛选结构。"""
    if 'filter_reason' not in paper:
        return False
    if not PRESTIGE_ENABLED:
        return True
    stage = paper.get('exclude_stage')
    if stage in {'keyword', 'topic'}:
        return True
    if stage != 'prestige' or paper.get('prestige_rule_version') != PRESTIGE_RULE_VERSION:
        return False
    if paper.get('prestige_source') == 'missing_affiliations':
        return False
    return paper.get('prestige_result') is False


def main() -> int:
    """主函数"""
    parser = argparse.ArgumentParser(description='增强版论文筛选工具')
    parser.add_argument('--input-file', required=True, help='输入的 JSON 文件路径')
    parser.add_argument('--output-dir', default=DOMAIN_PAPER_DIR, help=f'输出目录 (默认: {DOMAIN_PAPER_DIR})')
    parser.add_argument('--api-key', default=API_KEY, help='API 密钥')
    parser.add_argument('--base-url', default=BASE_URL, help='API 基础 URL')
    parser.add_argument('--model', default=FILTER_MODEL, help='使用的筛选模型')
    parser.add_argument('--temperature', type=float, default=TEMPERATURE, help='生成温度')
    parser.add_argument('--max-papers', type=int, default=0, help='最大处理论文数量，0 表示处理所有')
    parser.add_argument('--max-workers', type=int, default=MAX_WORKERS, help=f'最大线程数 (默认: {MAX_WORKERS})')
    parser.add_argument('--status-file', default=None, help='写入结构化筛选状态 JSON')

    args = parser.parse_args()

    try:
        validate_non_negative_int(args.max_papers, "--max-papers")
        validate_positive_int(args.max_workers, "--max-workers")
    except ValidationError as exc:
        print(f"❌ 参数校验失败: {exc}")
        write_status_file(args.status_file, {
            "status": "failed",
            "input_file": args.input_file,
            "failure_reason": f"参数校验失败: {exc}",
        })
        return 2

    if not os.path.exists(args.input_file):
        print(f"❌ 输入文件未找到: {args.input_file}")
        write_status_file(args.status_file, {
            "status": "failed",
            "input_file": args.input_file,
            "failure_reason": "输入文件未找到",
        })
        return 1

    os.makedirs(args.output_dir, exist_ok=True)

    client = OpenAI(
        api_key=args.api_key,
        base_url=args.base_url,
        timeout=FILTER_LLM_TIMEOUT,
        max_retries=0,
    )
    cache_manager = CacheManager() if ENABLE_CACHE else None
    document_extractor = ExtractionManager(
        cache_manager=cache_manager,
        chain=FILTER_EXTRACT_CHAIN,
        request_timeout=FILTER_EXTRACT_TIMEOUT,
    )

    print("🔍 开始论文筛选")
    print(f"📁 输入文件: {args.input_file}")
    print(f"🤖 使用模型: {args.model}")
    print(f"⏱️ Filter LLM timeout: {FILTER_LLM_TIMEOUT}s, retries: {FILTER_LLM_MAX_RETRIES}")
    print(f"🏛️ Prestige 硬筛: {'启用' if PRESTIGE_ENABLED else '关闭'}")
    if PRESTIGE_ENABLED:
        print(f"🏛️ Prestige 机构在线提取: {'启用' if PRESTIGE_AFFILIATION_FETCH_ENABLED else '关闭'}")
        print(f"🏛️ Prestige LLM 兜底判断: {'启用' if PRESTIGE_LLM_ENABLED else '关闭'}")
        print(f"📄 Prestige 上下文截断长度: {PRESTIGE_CONTEXT_CHARS} 字符")
        print(f"📄 Prestige 文档提取链: {FILTER_EXTRACT_CHAIN} (timeout={FILTER_EXTRACT_TIMEOUT}s)")
    print("=" * 50)

    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            papers = json.load(f)
        print(f"📚 成功加载 {len(papers)} 篇论文")
    except Exception as e:
        print(f"❌ 读取文件时出错: {e}")
        write_status_file(args.status_file, {
            "status": "failed",
            "input_file": args.input_file,
            "failure_reason": f"读取文件时出错: {e}",
        })
        return 1

    source_papers_by_id = build_source_paper_index(papers)
    original_paper_count = len(papers)

    current_date = datetime.now().strftime('%Y%m%d')
    input_filename = os.path.basename(args.input_file)
    date_part = extract_date_part_from_filename(input_filename, current_date)

    output_filename = f"filtered_papers_{date_part}.json"
    output_filepath = os.path.join(args.output_dir, output_filename)
    excluded_filename = f"excluded_papers_{date_part}.json"
    excluded_filepath = os.path.join(args.output_dir, excluded_filename)

    existing_filtered = []
    existing_excluded = []
    processed_arxiv_ids = set()
    stale_filtered_count = 0
    stale_excluded_count = 0
    repaired_filtered_count = 0

    if os.path.exists(output_filepath):
        try:
            with open(output_filepath, 'r', encoding='utf-8') as f:
                loaded_filtered = json.load(f)
            for paper in loaded_filtered:
                paper, repaired = repair_paper_metadata_from_source(
                    paper,
                    source_papers_by_id.get(paper.get('arxiv_id', '')),
                )
                if repaired:
                    repaired_filtered_count += 1
                if is_current_filtered_schema(paper):
                    existing_filtered.append(paper)
                    processed_arxiv_ids.add(paper.get('arxiv_id', ''))
                else:
                    stale_filtered_count += 1
            print(f"🔄 发现已筛选结果: {len(existing_filtered)} 篇论文")
        except Exception as e:
            print(f"⚠️ 读取已筛选文件时出错: {e}")

    if os.path.exists(excluded_filepath):
        try:
            with open(excluded_filepath, 'r', encoding='utf-8') as f:
                loaded_excluded = json.load(f)
            for paper in loaded_excluded:
                if is_current_excluded_schema(paper):
                    existing_excluded.append(paper)
                    processed_arxiv_ids.add(paper.get('arxiv_id', ''))
                else:
                    stale_excluded_count += 1
            print(f"🔄 发现已排除结果: {len(existing_excluded)} 篇论文")
        except Exception as e:
            print(f"⚠️ 读取已排除文件时出错: {e}")

    if stale_filtered_count or stale_excluded_count:
        print(
            f"♻️ 忽略旧版筛选结果: 保留集 {stale_filtered_count} 篇, "
            f"排除集 {stale_excluded_count} 篇，将按当前规则重新处理"
        )
    if repaired_filtered_count:
        print(f"🧩 已从爬取源文件回填旧筛选结果元数据: {repaired_filtered_count} 篇")

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
        if repaired_filtered_count:
            try:
                if not save_json(output_filepath, existing_filtered, indent=4, ensure_ascii=False):
                    raise IOError(output_filepath)
                if existing_excluded and not save_json(excluded_filepath, existing_excluded, indent=4, ensure_ascii=False):
                    raise IOError(excluded_filepath)
                print(f"💾 已保存回填后的筛选结果: {output_filepath}")
            except Exception as e:
                print(f"❌ 保存回填结果时出错: {e}")
                return 1
        write_status_file(args.status_file, {
            "status": "ok",
            "input_file": args.input_file,
            "total_input": original_paper_count,
            "processed_existing": len(processed_arxiv_ids),
            "prefiltered_count": 0,
            "filtered_new": 0,
            "filtered_total": len(existing_filtered),
            "error_count": 0,
            "fatal_zero_result": False,
        })
        return 0

    if args.max_papers > 0:
        papers = papers[:args.max_papers]
        print(f"🔢 限制处理数量为: {args.max_papers}")

    required_keywords = ['llm', 'large language model', 'agent']
    pre_filtered = []
    keyword_excluded = []
    for paper in papers:
        text = (paper.get('title', '') + ' ' + (paper.get('summary', '') or paper.get('abstract', ''))).lower()
        if any(kw in text for kw in required_keywords):
            pre_filtered.append(paper)
        else:
            p = paper.copy()
            p['filter_reason'] = f'关键词预筛排除：标题和摘要中未包含 {required_keywords} 中的任一关键词'
            p['exclude_stage'] = 'keyword'
            keyword_excluded.append(compact_excluded_paper(p))

    print(f"🔑 关键词预筛: {len(pre_filtered)} 篇通过, {len(keyword_excluded)} 篇排除")
    keyword_excluded_count = len(keyword_excluded)
    existing_excluded.extend(keyword_excluded)
    prefiltered_count = len(pre_filtered)
    papers = pre_filtered

    if not papers:
        print("✅ 关键词预筛后无论文需要 LLM 筛选")
        excluded_saved = save_json(excluded_filepath, existing_excluded, indent=2, ensure_ascii=False)
        filtered_saved = save_json(output_filepath, existing_filtered, indent=2, ensure_ascii=False)
        write_status_file(args.status_file, {
            "status": "ok" if excluded_saved and filtered_saved else "failed",
            "input_file": args.input_file,
            "total_input": original_paper_count,
            "processed_existing": len(processed_arxiv_ids),
            "prefiltered_count": prefiltered_count,
            "filtered_new": 0,
            "filtered_total": len(existing_filtered),
            "keyword_excluded": keyword_excluded_count,
            "topic_excluded": 0,
            "prestige_excluded": 0,
            "error_count": 0,
            "fatal_zero_result": False,
        })
        return 0 if excluded_saved and filtered_saved else 1

    def filter_paper_wrapper(paper: dict):
        """包装函数，用于多线程筛选。"""
        title = paper.get('title', '').strip()
        summary = paper.get('summary', '') or paper.get('abstract', '')
        authors = paper.get('authors', '')

        if not title or not summary:
            return 'skip', paper, f"跳过论文 (缺少标题或摘要): {title[:50]}...", "缺少标题或摘要"

        try:
            topic_match, topic_reason = query_topic_llm(title, summary, client, args.model, args.temperature)
            paper_with_reason = paper.copy()
            paper_with_reason['filter_reason'] = topic_reason

            if not topic_match:
                paper_with_reason['exclude_stage'] = 'topic'
                return 'exclude_topic', paper_with_reason, f"⏭️ 主题不匹配: {title[:50]}...", topic_reason

            if not PRESTIGE_ENABLED:
                return 'include', paper_with_reason, f"✅ 匹配: {title[:50]}...", topic_reason

            if PRESTIGE_AFFILIATION_FETCH_ENABLED:
                try:
                    affiliations, fetch_reason = fetch_affiliations_for_prestige(
                        paper_with_reason,
                        client,
                        args.model,
                        args.temperature,
                        cache_manager,
                        document_extractor,
                        args.api_key,
                        args.base_url,
                    )
                except Exception as exc:
                    affiliations = None
                    fetch_reason = f"机构提取失败: {exc}"
            else:
                affiliations = None
                fetch_reason = (
                    "Prestige 机构在线提取默认关闭；"
                    "如需启用请设置 PAPERTOOLS_PRESTIGE_AFFILIATION_FETCH_ENABLED=1"
                )

            paper_with_reason['affiliations'] = affiliations or ""

            if not affiliations:
                prestige_match, paper_with_reason, prestige_reason = resolve_missing_affiliations_prestige(
                    title,
                    authors,
                    fetch_reason,
                    paper_with_reason,
                    client,
                    args.model,
                    args.temperature,
                    cache_manager,
                )
                if prestige_match:
                    return 'include', paper_with_reason, f"✅ Prestige 作者命中: {title[:50]}...", prestige_reason
                return 'exclude_prestige', paper_with_reason, f"🚫 Prestige 信息缺失且未命中: {title[:50]}...", prestige_reason

            whitelist_match, whitelist_reason, whitelist_source, whitelist_matches = evaluate_prestige_whitelist(
                authors,
                affiliations,
            )
            paper_with_reason['prestige_matches'] = whitelist_matches
            paper_with_reason['prestige_rule_version'] = PRESTIGE_RULE_VERSION

            if whitelist_match:
                paper_with_reason['prestige_result'] = True
                paper_with_reason['prestige_reason'] = whitelist_reason
                paper_with_reason['prestige_source'] = whitelist_source
                return 'include', paper_with_reason, f"✅ 白名单命中: {title[:50]}...", whitelist_reason

            if not PRESTIGE_LLM_ENABLED:
                prestige_reason = "未命中确定性 prestige 白名单，跳过不稳定的 prestige LLM 判断并按硬筛排除"
                paper_with_reason['prestige_result'] = False
                paper_with_reason['prestige_reason'] = prestige_reason
                paper_with_reason['prestige_source'] = 'deterministic_whitelist'
                paper_with_reason['prestige_status'] = 'rejected'
                paper_with_reason['exclude_stage'] = 'prestige'
                return 'exclude_prestige', paper_with_reason, f"🚫 Prestige 未命中: {title[:50]}...", prestige_reason

            prestige_match, prestige_reason = query_prestige_llm(
                title,
                authors,
                affiliations,
                client,
                args.model,
                args.temperature,
                cache_manager,
            )
            paper_with_reason['prestige_result'] = prestige_match
            paper_with_reason['prestige_reason'] = prestige_reason
            paper_with_reason['prestige_source'] = 'llm'

            if prestige_match:
                return 'include', paper_with_reason, f"✅ 通过双重筛选: {title[:50]}...", prestige_reason

            paper_with_reason['exclude_stage'] = 'prestige'
            return 'exclude_prestige', paper_with_reason, f"🚫 Prestige 未命中: {title[:50]}...", prestige_reason

        except OpenAIError as e:
            return 'error', paper, f"❌ API 调用失败: {e}", f"处理错误: {e}"
        except Exception as e:
            return 'error', paper, f"❌ 处理论文时出错: {e}", f"处理错误: {e}"

    print(f"🔄 使用 {args.max_workers} 个线程并行筛选...")
    print(f"📊 开始处理 {len(papers)} 篇论文...")

    filtered_papers = []
    excluded_papers = []
    topic_excluded_count = 0
    prestige_excluded_count = 0
    error_count = 0

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [executor.submit(filter_paper_wrapper, paper) for paper in papers]

        processed_count = 0
        matched_count = 0

        for future in tqdm(as_completed(futures), total=len(papers), desc="筛选论文", unit="篇", ncols=80):
            try:
                status, paper, message, _reason = future.result()
                processed_count += 1

                if status == 'include':
                    filtered_papers.append(paper)
                    matched_count += 1
                elif status == 'exclude_topic':
                    excluded_papers.append(compact_excluded_paper(paper))
                    topic_excluded_count += 1
                elif status == 'exclude_prestige':
                    excluded_papers.append(compact_excluded_paper(paper))
                    prestige_excluded_count += 1
                elif status == 'skip':
                    pass
                else:
                    error_count += 1
                    print(f"❌ [{matched_count}/{processed_count}] {message}")

                time.sleep(REQUEST_DELAY / max(args.max_workers, 1))

                try:
                    all_filtered = existing_filtered + filtered_papers
                    all_excluded = existing_excluded + excluded_papers
                    save_json(output_filepath, all_filtered, indent=4, ensure_ascii=False)
                    save_json(excluded_filepath, all_excluded, indent=4, ensure_ascii=False)
                except Exception:
                    pass

            except Exception as e:
                print(f"❌ 获取筛选结果时出错: {e}")
                continue

    print("\n📊 筛选完成！")
    print(f"📈 总论文数: {len(papers)}")
    print(f"🎯 筛选后论文数: {len(filtered_papers)}")
    print(f"🔑 关键词排除数: {keyword_excluded_count}")
    print(f"🚫 主题排除数: {topic_excluded_count}")
    if PRESTIGE_ENABLED:
        print(f"🏛️ Prestige 排除数: {prestige_excluded_count}")
    print(f"🗂️ 被排除论文数: {keyword_excluded_count + len(excluded_papers)}")
    print(f"📊 筛选率: {len(filtered_papers) / len(papers) * 100:.1f}%")
    if error_count:
        print(f"⚠️ 处理错误数: {error_count}")

    if filtered_papers:
        print("\n📋 筛选出的论文:")
        for i, paper in enumerate(filtered_papers[:10], 1):
            print(f"{i:2d}. {paper['title']}")
        if len(filtered_papers) > 10:
            print(f"    ... 还有 {len(filtered_papers) - 10} 篇")

    all_filtered_papers = existing_filtered + filtered_papers
    all_excluded_papers = existing_excluded + excluded_papers

    try:
        if not save_json(output_filepath, all_filtered_papers, indent=4, ensure_ascii=False):
            raise IOError(output_filepath)
        print(f"\n💾 筛选结果已保存到: {output_filepath}")
        print(f"📊 总计: {len(all_filtered_papers)} 篇筛选通过的论文 (本次新增: {len(filtered_papers)} 篇)")
    except Exception as e:
        print(f"❌ 保存文件时出错: {e}")
        return 1

    if all_excluded_papers:
        try:
            if not save_json(excluded_filepath, all_excluded_papers, indent=4, ensure_ascii=False):
                raise IOError(excluded_filepath)
            print(f"🔍 被排除论文已保存到: {excluded_filepath} (总计: {len(all_excluded_papers)} 篇)")
        except Exception as e:
            print(f"❌ 保存被排除论文时出错: {e}")
            return 1

    fatal_zero_result = error_count > 0 and len(filtered_papers) == 0
    status_payload = {
        "status": "failed" if fatal_zero_result else "ok",
        "input_file": args.input_file,
        "output_file": output_filepath,
        "excluded_file": excluded_filepath,
        "total_input": original_paper_count,
        "processed_existing": len(processed_arxiv_ids),
        "processed_new": processed_count,
        "prefiltered_count": prefiltered_count,
        "filtered_new": len(filtered_papers),
        "filtered_total": len(all_filtered_papers),
        "keyword_excluded": keyword_excluded_count,
        "topic_excluded": topic_excluded_count,
        "prestige_excluded": prestige_excluded_count,
        "error_count": error_count,
        "fatal_zero_result": fatal_zero_result,
    }
    if fatal_zero_result:
        status_payload["failure_reason"] = (
            f"筛选阶段 {error_count} 个错误且本轮筛选结果为 0，拒绝发布疑似异常空结果"
        )
    write_status_file(args.status_file, status_payload)

    if fatal_zero_result:
        print(f"❌ {status_payload['failure_reason']}")
        return 1

    print("🎉 筛选完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
