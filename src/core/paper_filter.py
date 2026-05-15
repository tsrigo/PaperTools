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
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAIError
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
from src.utils.openai_client import create_openai_client  # noqa: E402
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

def env_int(name: str, default: int, minimum: Optional[int] = None) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except ValueError:
        print(f"⚠️ {name}={value!r} 不是合法整数，回退到默认值 {default}")
        return default
    if minimum is not None and parsed < minimum:
        print(f"⚠️ {name}={value!r} 小于允许下限 {minimum}，回退到默认值 {default}")
        return default
    return parsed


def env_float(name: str, default: float, minimum: Optional[float] = None) -> float:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        parsed = float(value)
    except ValueError:
        print(f"⚠️ {name}={value!r} 不是合法数字，回退到默认值 {default}")
        return default
    if minimum is not None and parsed < minimum:
        print(f"⚠️ {name}={value!r} 小于允许下限 {minimum}，回退到默认值 {default}")
        return default
    return parsed


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


FILTER_LLM_TIMEOUT = env_float("PAPERTOOLS_FILTER_LLM_TIMEOUT", 45, minimum=1)
FILTER_LLM_MAX_RETRIES = env_int("PAPERTOOLS_FILTER_LLM_MAX_RETRIES", 1, minimum=0)
FILTER_PAPER_TIMEOUT = env_float("PAPERTOOLS_FILTER_PAPER_TIMEOUT", 180, minimum=1)
FILTER_EXTRACT_CHAIN = os.getenv("PAPERTOOLS_FILTER_EXTRACT_CHAIN", "jina")
FILTER_EXTRACT_TIMEOUT = env_int("PAPERTOOLS_FILTER_EXTRACT_TIMEOUT", 45, minimum=1)
FILTER_RPM = env_int("PAPERTOOLS_FILTER_RPM", 8, minimum=0)
FILTER_RATE_WINDOW_SECONDS = env_float("PAPERTOOLS_FILTER_RATE_WINDOW_SECONDS", 60, minimum=1)
FILTER_RATE_LIMIT_COOLDOWN_SECONDS = env_float("PAPERTOOLS_FILTER_429_COOLDOWN_SECONDS", 65, minimum=0)
FILTER_MAX_OUTPUT_PAPERS = env_int("PAPERTOOLS_FILTER_MAX_OUTPUT_PAPERS", 15, minimum=0)
FILTER_SUSPICIOUS_ZERO_MIN_INPUT = env_int("PAPERTOOLS_FILTER_SUSPICIOUS_ZERO_MIN_INPUT", 500, minimum=0)
FILTER_SUSPICIOUS_ZERO_MIN_PREFILTERED = env_int(
    "PAPERTOOLS_FILTER_SUSPICIOUS_ZERO_MIN_PREFILTERED",
    100,
    minimum=0,
)
FILTER_MODEL_CHAIN_ENV = (
    os.getenv("PAPERTOOLS_FILTER_MODEL_CHAIN")
    or os.getenv("FILTER_MODEL_CHAIN")
    or ""
)
PRESTIGE_LLM_ENABLED = os.getenv("PAPERTOOLS_PRESTIGE_LLM_ENABLED", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
TOPIC_HEURISTIC_KEEP_ENABLED = env_bool("PAPERTOOLS_TOPIC_HEURISTIC_KEEP_ENABLED", True)
TOPIC_HEURISTIC_BYPASS_PRESTIGE = env_bool("PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE", False)
PRESTIGE_AFFILIATION_FETCH_ENABLED = os.getenv(
    "PAPERTOOLS_PRESTIGE_AFFILIATION_FETCH_ENABLED",
    "1",
).lower() in {
    "1",
    "true",
    "yes",
    "on",
}


class LLMResponseParseError(ValueError):
    """Raised when a filter LLM response cannot be parsed safely."""


def is_suspicious_zero_result(
    total_input: int,
    prefiltered_count: int,
    filtered_total: int,
) -> bool:
    """Treat a large all-rejected candidate pool as a filter anomaly, not a quiet skip."""
    return (
        filtered_total == 0
        and total_input >= FILTER_SUSPICIOUS_ZERO_MIN_INPUT
        and prefiltered_count >= FILTER_SUSPICIOUS_ZERO_MIN_PREFILTERED
    )


_FILTER_RATE_LOCK = threading.Lock()
_FILTER_REQUEST_TIMESTAMPS: List[float] = []
_FILTER_RATE_COOLDOWN_UNTIL = 0.0
_DISABLED_FILTER_MODELS = set()


def split_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def is_openrouter_base_url(base_url: str) -> bool:
    return "openrouter.ai" in (base_url or "").lower()


def normalize_filter_model(model: str, base_url: str = "") -> str:
    """Translate stale local aliases to model ids accepted by the active router."""
    model = (model or "").strip()
    if is_openrouter_base_url(base_url):
        aliases = {
            "qwen": "qwen/qwen3-30b-a3b",
            "minimax": "qwen/qwen3-30b-a3b",
            "minimax-m2": "qwen/qwen3-30b-a3b",
            "minimax-m2.5": "qwen/qwen3-30b-a3b",
            "minimax-m2.7": "qwen/qwen3-30b-a3b",
            "minimax/minimax-m2": "qwen/qwen3-30b-a3b",
            "minimax/minimax-m2.5": "qwen/qwen3-30b-a3b",
            "minimax/minimax-m2.7": "qwen/qwen3-30b-a3b",
            "deepseek-chat": "deepseek/deepseek-chat-v3-0324",
            "deepseek-reasoner": "deepseek/deepseek-chat-v3-0324",
            "deepseek/deepseek-chat": "deepseek/deepseek-chat-v3-0324",
            "deepseek/deepseek-r1": "deepseek/deepseek-chat-v3-0324",
            "deepseek-r1": "deepseek/deepseek-chat-v3-0324",
        }
        return aliases.get(model, model)

    aliases = {
        "minimax-m2": "qwen",
        "minimax-m2.5": "qwen",
        "minimax-m2.7": "qwen",
        "minimax/minimax-m2": "qwen",
        "minimax/minimax-m2.5": "qwen",
        "minimax/minimax-m2.7": "qwen",
        "deepseek-reasoner": "deepseek-chat",
        "deepseek/deepseek-chat": "deepseek-chat",
        "deepseek/deepseek-r1": "deepseek-chat",
        "deepseek-r1": "deepseek-chat",
    }
    return aliases.get(model, model)


def build_filter_model_chain(primary_model: str, base_url: str = "") -> List[str]:
    """Build a de-duplicated topic/prestige filter model fallback chain."""
    configured = split_csv(FILTER_MODEL_CHAIN_ENV)
    raw_models = [primary_model]
    if configured:
        raw_models.extend(configured)
    elif is_openrouter_base_url(base_url):
        raw_models.extend([
            "qwen/qwen3-30b-a3b",
            "deepseek/deepseek-chat-v3-0324",
        ])
    else:
        raw_models.extend([
            "qwen",
            "deepseek-chat",
            "minimax",
        ])

    chain = []
    seen = set()
    for raw_model in raw_models:
        model = normalize_filter_model(raw_model, base_url)
        if not model or model in seen:
            continue
        seen.add(model)
        chain.append(model)
    return chain


def coerce_filter_model_chain(models: Any) -> List[str]:
    if isinstance(models, (list, tuple)):
        raw_models = [str(model) for model in models]
    else:
        raw_models = [str(models)]
    chain = []
    seen = set()
    for raw_model in raw_models:
        model = normalize_filter_model(raw_model)
        if model and model not in seen:
            seen.add(model)
            chain.append(model)
    return chain


def evaluate_topic_heuristic(title: str, summary: str) -> Tuple[bool, str]:
    """Keep high-confidence agent/evolution papers before asking a brittle LLM judge."""
    if not TOPIC_HEURISTIC_KEEP_ENABLED:
        return False, ""

    title = title or ""
    summary = summary or ""
    text = f"{title}\n{summary}".lower()
    compact_text = re.sub(r"\s+", " ", text)
    signals = []

    def has(pattern: str) -> bool:
        return re.search(pattern, compact_text, flags=re.IGNORECASE) is not None

    llm_context = has(r"\b(?:llm|large language model|language model|small language model|foundation model|agentic)\b")

    if has(r"\bagentic\b"):
        signals.append("Agentic")
    if has(r"\bllms?\s+improv(?:e|ing|es)\s+llms?\b"):
        signals.append("LLMs improving LLMs")
    if has(r"\bself[-\s]?(?:evolving|evolution|improving|improvement|refine|refinement)\b"):
        if has(r"\b(?:llm|large language model|language model|instruction following|reinforcement learning|agent)\b"):
            signals.append("Self-Evolving/Self-Improving")
    if has(r"\b(?:llm|large language model|language model|small language model)s?\s+agents?\b"):
        signals.append("LLM Agents")
    if has(r"\blong[-\s]?horizon agents?\b"):
        signals.append("Long-Horizon Agents")
    if llm_context and has(r"\bagents?\b") and has(
        r"\b(?:memory|clarification|long[-\s]?horizon|cooperative|cooperation|tool[-\s]?use|"
        r"tool[-\s]?using|distillation|on[-\s]?policy|verification|elaboration|planning|"
        r"runtime|harness|scaffold|test[-\s]?time)\b"
    ):
        signals.append("Agent capability/behavior")
    if llm_context and has(r"\bmulti[-\s]?agent\b") and not has(r"\b(?:topology|message routing|communication protocol)\b"):
        signals.append("Multi-Agent")
    if has(r"\btest[-\s]?time scaling\b") and has(r"\b(?:agentic|agent|self[-\s]?improv|llms?\s+improv)\b"):
        signals.append("Agentic test-time scaling")

    if not signals:
        return False, ""

    unique_signals = []
    seen = set()
    for signal in signals:
        if signal not in seen:
            seen.add(signal)
            unique_signals.append(signal)

    return True, (
        "确定性主题保留：标题和摘要命中强相关信号 "
        f"({', '.join(unique_signals)})。该规则用于避免模型把明显的 "
        "LLM Agent / Agentic / Self-Evolving 论文误判为过窄范围之外。"
    )


def score_filtered_paper_for_selection(paper: dict) -> int:
    """Rank included papers so the daily page stays readable."""
    title = paper.get('title', '') or ''
    summary = paper.get('summary', '') or paper.get('abstract', '') or ''
    title_text = title.lower()
    text = f"{title}\n{summary}".lower()
    score = 0

    prestige_source = paper.get('prestige_source', '')
    if paper.get('prestige_result') is True and prestige_source != 'topic_heuristic_bypass':
        score += 100
    if paper.get('topic_source') == 'heuristic':
        score += 10

    title_patterns = [
        (r"\bllms?\s+improv(?:e|ing|es)\s+llms?\b", 70),
        (r"\bself[-\s]?(?:evolving|evolution|improving|improvement|refine|refinement)\b", 65),
        (r"\b(?:llm|large language model|language model|small language model)s?\s+agents?\b", 60),
        (r"\blong[-\s]?horizon agents?\b", 85),
        (r"\bagentic\b", 45),
        (r"\btool[-\s]?(?:use|using|calling|augmentation)\b", 38),
        (r"\b(?:memory|experience)\b.*\bagents?\b|\bagents?\b.*\b(?:memory|experience)\b", 35),
        (r"\b(?:coding|code repair|cli agents?|sre agents?|web agents?)\b", 25),
    ]
    for pattern, weight in title_patterns:
        if re.search(pattern, title_text, flags=re.IGNORECASE):
            score += weight

    supporting_patterns = [
        (r"\bself[-\s]?(?:evolving|evolution|improving|improvement|refine|refinement)\b", 18),
        (r"\b(?:llm|large language model|language model|small language model)s?\s+agents?\b", 18),
        (r"\bagentic\b", 12),
        (r"\btool[-\s]?(?:use|using|calling|augmentation)\b", 10),
        (r"\bbenchmark(?:ing)?\b|\bevaluat(?:e|ing|ion)\b", 6),
    ]
    for pattern, weight in supporting_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            score += weight

    penalty_patterns = [
        (r"\b(?:security|cyber|safety|alignment|interpretability|explainability|watermark|hallucination)\b", 90),
        (r"\b(?:medical|clinical|chemical|reaction|biological|biomedical|financial|trading|flight|weather|recommendation|physics)\b", 75),
        (r"\b(?:vision|multimodal|video|vlm|mllm|diffusion|ocr)\b", 80),
        (r"\b(?:knowledge graph|graph neural|graph representation|graph-accelerated|graph reasoning)\b", 60),
        (r"\bsurvey\b", 30),
    ]
    for pattern, penalty in penalty_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            score -= penalty

    if not re.search(
        r"\b(?:agent|agentic|tool[-\s]?calling|tool[-\s]?use|llms?\s+improv|self[-\s]?(?:evolving|improving))\b",
        title_text,
        flags=re.IGNORECASE,
    ):
        score -= 60

    return score


def apply_output_cap(filtered_papers: List[dict], max_papers: int) -> Tuple[List[dict], List[dict]]:
    """Keep the published set capped while preserving overflow as exclusions."""
    for paper in filtered_papers:
        paper['selection_score'] = score_filtered_paper_for_selection(paper)

    if max_papers <= 0 or len(filtered_papers) <= max_papers:
        return filtered_papers, []

    ranked = sorted(
        enumerate(filtered_papers),
        key=lambda item: (
            item[1].get('selection_score', 0),
            item[1].get('prestige_source') != 'topic_heuristic_bypass',
            item[1].get('source_date') or item[1].get('date') or '',
            item[0] * -1,
        ),
        reverse=True,
    )
    selected_indices = {index for index, _paper in ranked[:max_papers]}

    selected = []
    overflow = []
    for index, paper in enumerate(filtered_papers):
        if index in selected_indices:
            selected.append(paper)
            continue
        excluded = compact_excluded_paper(paper)
        excluded['exclude_stage'] = 'selection_cap'
        excluded['filter_reason'] = (
            f"主题相关但超过每日发布上限 {max_papers}，"
            f"按可读性排序压缩；selection_score={paper.get('selection_score', 0)}"
        )
        overflow.append(excluded)

    selected.sort(key=lambda paper: paper.get('selection_score', 0), reverse=True)
    return selected, overflow


def is_filter_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(token in message for token in ("429", "rate limit", "too many requests", "rpm limit"))


def is_invalid_filter_model_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "model" in message
        and any(
            token in message
            for token in (
                "invalid model",
                "invalid model id",
                "invalid model name",
                "not a valid model",
                "not a valid model id",
                "model_not_found",
                "does not exist",
                "not found",
            )
        )
    )


def wait_for_filter_rate_slot() -> None:
    """Throttle request starts across worker threads before hitting provider RPM."""
    global _FILTER_RATE_COOLDOWN_UNTIL

    if FILTER_RPM <= 0:
        return

    while True:
        wait_seconds = 0.0
        with _FILTER_RATE_LOCK:
            now = time.monotonic()
            if _FILTER_RATE_COOLDOWN_UNTIL > now:
                wait_seconds = _FILTER_RATE_COOLDOWN_UNTIL - now
            else:
                cutoff = now - FILTER_RATE_WINDOW_SECONDS
                while _FILTER_REQUEST_TIMESTAMPS and _FILTER_REQUEST_TIMESTAMPS[0] <= cutoff:
                    _FILTER_REQUEST_TIMESTAMPS.pop(0)

                if len(_FILTER_REQUEST_TIMESTAMPS) < FILTER_RPM:
                    _FILTER_REQUEST_TIMESTAMPS.append(now)
                    return

                oldest = _FILTER_REQUEST_TIMESTAMPS[0]
                wait_seconds = max(0.1, FILTER_RATE_WINDOW_SECONDS - (now - oldest) + 0.1)

        time.sleep(wait_seconds)


def note_filter_rate_limit_error() -> None:
    global _FILTER_RATE_COOLDOWN_UNTIL

    if FILTER_RATE_LIMIT_COOLDOWN_SECONDS <= 0:
        return
    with _FILTER_RATE_LOCK:
        _FILTER_RATE_COOLDOWN_UNTIL = max(
            _FILTER_RATE_COOLDOWN_UNTIL,
            time.monotonic() + FILTER_RATE_LIMIT_COOLDOWN_SECONDS,
        )
        _FILTER_REQUEST_TIMESTAMPS.clear()
    print(f"⏳ 筛选 API 触发 429，冷却 {FILTER_RATE_LIMIT_COOLDOWN_SECONDS:.0f}s 后重试")


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
def run_llm_prompt(prompt: str, system: str, client: object, model: str,
                   temperature: float = TEMPERATURE) -> str:
    """执行 LLM prompt，并返回原始文本。"""
    wait_for_filter_rate_slot()
    try:
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
    except OpenAIError as exc:
        if is_filter_rate_limit_error(exc):
            note_filter_rate_limit_error()
        raise

    response_text = ""
    if response.choices:
        message = response.choices[0].message
        if message and message.content:
            response_text = message.content

    return strip_think_tags(response_text)


def run_llm_prompt_with_fallback(prompt: str, system: str, client: object, models: Any,
                                 temperature: float = TEMPERATURE) -> str:
    """Run a filter prompt, skipping stale/invalid model ids when possible."""
    last_exception = None
    attempted = []
    for model in coerce_filter_model_chain(models):
        if model in _DISABLED_FILTER_MODELS:
            continue
        attempted.append(model)
        try:
            return run_llm_prompt(prompt, system, client, model, temperature)
        except OpenAIError as exc:
            last_exception = exc
            if is_invalid_filter_model_error(exc):
                _DISABLED_FILTER_MODELS.add(model)
                print(f"⚠️ 筛选模型不可用，跳过: {model}: {str(exc)[:240]}")
                continue
            raise

    if last_exception:
        raise last_exception
    raise RuntimeError(f"没有可用的筛选模型，已尝试: {', '.join(attempted) or '<none>'}")


def query_topic_llm(title: str, summary: str, client: object, model: Any,
                    temperature: float = TEMPERATURE) -> Tuple[bool, str]:
    """使用主题筛选 prompt 判断论文是否相关。"""
    response_text = run_llm_prompt_with_fallback(
        PAPER_FILTER_PROMPT.format(title=title, summary=summary),
        "你是一个专业的学术论文筛选助手。请根据给定的筛选条件，准确判断论文是否符合要求。",
        client,
        model,
        temperature,
    )
    return parse_llm_response(response_text)


def query_prestige_llm(title: str, authors: str, affiliations: str, client: object,
                       model: Any, temperature: float = TEMPERATURE,
                       cache_manager: Optional[CacheManager] = None) -> Tuple[bool, str]:
    """使用 prestige prompt 判断论文是否命中大牛/顶级机构。"""
    cache_key = f"prestige_filter_v3_{title}"
    cache_content = f"{authors}\n{affiliations}"

    if cache_manager and ENABLE_CACHE:
        cached_response = cache_manager.get_summary_cache(cache_key, cache_content)
        if cached_response:
            return parse_llm_response(cached_response)

    response_text = run_llm_prompt_with_fallback(
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
    client: object,
    model: Any,
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


def query_affiliations_llm(paper_content: str, authors: str, client: object, model: Any,
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

    response_text = run_llm_prompt_with_fallback(
        prompt,
        "你是一个学术信息提取助手。请精确提取作者机构信息，只输出 JSON，不要输出其他内容。",
        client,
        model,
        temperature,
    )

    if cache_manager and ENABLE_CACHE:
        cache_manager.set_summary_cache(cache_key, paper_content, response_text)

    return response_text.strip()


def fetch_affiliations_for_prestige(paper: dict, client: object, model: Any, temperature: float,
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
    if stage in {'keyword', 'topic', 'selection_cap'}:
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

    client = create_openai_client(
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
    filter_model_chain = build_filter_model_chain(args.model, args.base_url)

    print("🔍 开始论文筛选")
    print(f"📁 输入文件: {args.input_file}")
    print(f"🤖 使用模型链: {', '.join(filter_model_chain)}")
    print(f"⏱️ Filter LLM timeout: {FILTER_LLM_TIMEOUT}s, retries: {FILTER_LLM_MAX_RETRIES}")
    print(f"🚦 Filter RPM 限速: {FILTER_RPM if FILTER_RPM > 0 else 'disabled'}/{FILTER_RATE_WINDOW_SECONDS:.0f}s")
    print(f"⏱️ 单篇筛选 watchdog: {FILTER_PAPER_TIMEOUT}s")
    print(f"📌 每日发布上限: {FILTER_MAX_OUTPUT_PAPERS if FILTER_MAX_OUTPUT_PAPERS > 0 else 'disabled'}")
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

    summary_available_count = sum(
        1
        for paper in papers
        if (paper.get('summary') or paper.get('abstract') or '').strip()
    )
    print(f"🧾 摘要字段可用: {summary_available_count}/{len(papers)} 篇；主题模型输入为标题 + 摘要")

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
        try:
            if not save_json(output_filepath, existing_filtered, indent=4, ensure_ascii=False):
                raise IOError(output_filepath)
            if not save_json(excluded_filepath, existing_excluded, indent=4, ensure_ascii=False):
                raise IOError(excluded_filepath)
            if repaired_filtered_count:
                print(f"💾 已保存回填后的筛选结果: {output_filepath}")
            else:
                print(f"💾 已保存空筛选结果: {output_filepath}")
        except Exception as e:
            print(f"❌ 保存筛选结果时出错: {e}")
            write_status_file(args.status_file, {
                "status": "failed",
                "input_file": args.input_file,
                "total_input": original_paper_count,
                "failure_reason": f"保存筛选结果时出错: {e}",
            })
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
            topic_match, topic_reason = evaluate_topic_heuristic(title, summary)
            topic_source = 'heuristic' if topic_match else 'llm'
            if not topic_match:
                topic_match, topic_reason = query_topic_llm(title, summary, client, filter_model_chain, args.temperature)
            paper_with_reason = paper.copy()
            paper_with_reason['filter_reason'] = topic_reason
            paper_with_reason['topic_source'] = topic_source

            if not topic_match:
                paper_with_reason['exclude_stage'] = 'topic'
                return 'exclude_topic', paper_with_reason, f"⏭️ 主题不匹配: {title[:50]}...", topic_reason

            if not PRESTIGE_ENABLED:
                return 'include', paper_with_reason, f"✅ 匹配: {title[:50]}...", topic_reason

            if topic_source == 'heuristic' and TOPIC_HEURISTIC_BYPASS_PRESTIGE:
                paper_with_reason['prestige_result'] = True
                paper_with_reason['prestige_reason'] = "主题强相关确定性保留，跳过 prestige 硬筛"
                paper_with_reason['prestige_source'] = 'topic_heuristic_bypass'
                paper_with_reason['prestige_status'] = 'bypassed'
                paper_with_reason['prestige_matches'] = {
                    'authors': [],
                    'institutions': [],
                    'companies': [],
                    'institution_names': [],
                }
                paper_with_reason['prestige_rule_version'] = PRESTIGE_RULE_VERSION
                return 'include', paper_with_reason, f"✅ 主题强相关保留: {title[:50]}...", topic_reason

            if PRESTIGE_AFFILIATION_FETCH_ENABLED:
                try:
                    affiliations, fetch_reason = fetch_affiliations_for_prestige(
                        paper_with_reason,
                        client,
                        filter_model_chain,
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
                    filter_model_chain,
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
                filter_model_chain,
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
            if "timed out" in str(e).lower():
                paper_with_reason = paper.copy()
                timeout_reason = f"单篇主题筛选 API 超时，按主题排除: {e}"
                paper_with_reason['filter_reason'] = timeout_reason
                paper_with_reason['exclude_stage'] = 'topic'
                return 'exclude_topic', paper_with_reason, f"⏱️ 主题筛选超时: {title[:50]}...", timeout_reason
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
    timed_out_count = 0

    def save_progress() -> None:
        try:
            all_filtered = existing_filtered + filtered_papers
            all_excluded = existing_excluded + excluded_papers
            save_json(output_filepath, all_filtered, indent=4, ensure_ascii=False)
            save_json(excluded_filepath, all_excluded, indent=4, ensure_ascii=False)
        except Exception:
            pass

    executor = ThreadPoolExecutor(max_workers=args.max_workers)
    paper_iter = iter(papers)
    future_metadata = {}
    pending = set()

    def submit_next_paper() -> bool:
        try:
            paper = next(paper_iter)
        except StopIteration:
            return False
        future = executor.submit(filter_paper_wrapper, paper)
        future_metadata[future] = (paper, time.monotonic())
        pending.add(future)
        return True

    for _ in range(min(args.max_workers, len(papers))):
        submit_next_paper()

    processed_count = 0
    matched_count = 0

    with tqdm(total=len(papers), desc="筛选论文", unit="篇", ncols=80) as progress:
        while pending:
            done, _ = wait(pending, timeout=5.0, return_when=FIRST_COMPLETED)
            now = time.monotonic()

            timed_out = [
                future
                for future in pending
                if future not in done and now - future_metadata[future][1] > FILTER_PAPER_TIMEOUT
            ]

            for future in timed_out:
                original_paper, started_at = future_metadata[future]
                pending.remove(future)
                future.cancel()
                processed_count += 1
                timed_out_count += 1
                topic_excluded_count += 1

                paper_with_reason = original_paper.copy()
                timeout_seconds = now - started_at
                paper_with_reason['filter_reason'] = (
                    f"单篇筛选超过 {FILTER_PAPER_TIMEOUT:.0f}s 未返回，"
                    f"本轮按主题筛选超时排除，实际等待 {timeout_seconds:.1f}s"
                )
                paper_with_reason['exclude_stage'] = 'topic'
                excluded_papers.append(compact_excluded_paper(paper_with_reason))
                print(f"⏱️ 单篇筛选超时，按主题排除: {original_paper.get('title', '')[:50]}...")
                save_progress()
                progress.update(1)
                submit_next_paper()

            for future in done:
                if future not in pending:
                    continue
                pending.remove(future)
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
                    save_progress()

                except Exception as e:
                    error_count += 1
                    print(f"❌ 获取筛选结果时出错: {e}")
                finally:
                    progress.update(1)
                    submit_next_paper()

    executor.shutdown(wait=False, cancel_futures=True)

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
    if timed_out_count:
        print(f"⏱️ 单篇筛选超时数: {timed_out_count}")

    if filtered_papers:
        print("\n📋 筛选出的论文:")
        for i, paper in enumerate(filtered_papers[:10], 1):
            print(f"{i:2d}. {paper['title']}")
        if len(filtered_papers) > 10:
            print(f"    ... 还有 {len(filtered_papers) - 10} 篇")

    all_filtered_papers = existing_filtered + filtered_papers
    all_excluded_papers = existing_excluded + excluded_papers
    selection_cap_excluded_count = 0
    all_filtered_papers, selection_cap_excluded = apply_output_cap(
        all_filtered_papers,
        FILTER_MAX_OUTPUT_PAPERS,
    )
    if selection_cap_excluded:
        selection_cap_excluded_count = len(selection_cap_excluded)
        all_excluded_papers.extend(selection_cap_excluded)
        print(
            f"📌 每日发布上限压缩: 保留 {len(all_filtered_papers)} 篇，"
            f"额外转入排除 {selection_cap_excluded_count} 篇"
        )

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

    anomalous_zero_result = is_suspicious_zero_result(
        original_paper_count,
        prefiltered_count,
        len(all_filtered_papers),
    )
    fatal_zero_result = (error_count > 0 and len(all_filtered_papers) == 0) or anomalous_zero_result
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
        "selection_cap_excluded": selection_cap_excluded_count,
        "error_count": error_count,
        "timed_out_count": timed_out_count,
        "suspicious_zero_result": anomalous_zero_result,
        "suspicious_zero_min_input": FILTER_SUSPICIOUS_ZERO_MIN_INPUT,
        "suspicious_zero_min_prefiltered": FILTER_SUSPICIOUS_ZERO_MIN_PREFILTERED,
        "fatal_zero_result": fatal_zero_result,
    }
    if fatal_zero_result:
        if error_count > 0:
            status_payload["failure_reason"] = (
                f"筛选阶段 {error_count} 个错误且本轮筛选结果为 0，拒绝发布疑似异常空结果"
            )
        else:
            status_payload["failure_reason"] = (
                "筛选阶段源论文和关键词候选很多但最终入选 0 篇，拒绝静默跳过疑似异常空结果 "
                f"(total_input={original_paper_count}, prefiltered={prefiltered_count}, "
                f"thresholds={FILTER_SUSPICIOUS_ZERO_MIN_INPUT}/"
                f"{FILTER_SUSPICIOUS_ZERO_MIN_PREFILTERED})"
            )
    write_status_file(args.status_file, status_payload)

    if fatal_zero_result:
        print(f"❌ {status_payload['failure_reason']}")
        if timed_out_count:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(1)
        return 1

    print("🎉 筛选完成！")
    if timed_out_count:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
