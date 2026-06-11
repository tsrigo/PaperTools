"""PaperTools adapter for the external ReviewGrounder pipeline."""

from collections import deque
import json
import os
import re
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.utils.openai_client import create_openai_client
from src.utils.config import (
    REVIEWGROUNDER_API_KEY,
    REVIEWGROUNDER_BASE_URL,
    REVIEWGROUNDER_ENABLE_WEB_FALLBACK,
    REVIEWGROUNDER_MAX_OUTPUT_TOKENS,
    REVIEWGROUNDER_MAX_PARALLEL_SUMMARIES,
    REVIEWGROUNDER_MAX_RELATED_PAPERS,
    REVIEWGROUNDER_MODEL,
    REVIEWGROUNDER_PATH,
    REVIEWGROUNDER_REASONING_EFFORT,
    REVIEWGROUNDER_REFINER_REVIEW_FORMAT,
    REVIEWGROUNDER_REVIEW_FORMAT,
    REVIEWGROUNDER_RPM,
    REVIEWGROUNDER_TIMEOUT_SECONDS,
    REVIEWGROUNDER_MAX_LLM_CALLS,
    REVIEWGROUNDER_JSON_TOOL_RETRIES,
    REVIEWGROUNDER_VERBOSE,
)


REVIEWGROUNDER_CACHE_VERSION = "reviewgrounder_v5"
_RATE_WINDOW_SECONDS = 60.0
_REVIEWGROUNDER_RATE_LOCK = threading.Lock()
_REVIEWGROUNDER_CALL_TIMESTAMPS: deque[float] = deque()


class ReviewGrounderDependencyError(RuntimeError):
    """Raised when the external ReviewGrounder checkout is unavailable."""


class OpenAlexSearchAPI:
    """No-key online paper search fallback using OpenAlex."""

    base_url = "https://api.openalex.org/works"

    def __init__(
        self, paper_search_base_cls: Any = object, timeout: float = 20.0
    ) -> None:
        self.timeout = timeout
        self._paper_search_base_cls = paper_search_base_cls

    def search_by_query(
        self, query: str, limit: int = 50, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        params = {
            "search": query,
            "per-page": max(1, min(limit, 200)),
            "select": ",".join(
                [
                    "id",
                    "display_name",
                    "abstract_inverted_index",
                    "publication_year",
                    "authorships",
                    "cited_by_count",
                    "primary_location",
                    "doi",
                ]
            ),
        }
        data = self._get(params)
        results = data.get("results", []) if isinstance(data, dict) else []
        return [
            self._normalize_work(work) for work in results if work.get("display_name")
        ]

    def search_by_title(self, title: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        matches = self.search_by_query(title, limit=1, **kwargs)
        return matches[0] if matches else None

    def get_paper(self, paper_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if not paper_id:
            return None
        try:
            response = requests.get(paper_id, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("display_name"):
                return self._normalize_work(data)
        except Exception:
            return None
        return None

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.get(self.base_url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _normalize_work(self, work: Dict[str, Any]) -> Dict[str, Any]:
        primary_location = work.get("primary_location") or {}
        source = primary_location.get("source") or {}
        authors = []
        for authorship in work.get("authorships") or []:
            author = authorship.get("author") or {}
            if author.get("display_name"):
                authors.append(author["display_name"])

        abstract = _abstract_from_openalex_index(work.get("abstract_inverted_index"))
        url = (
            primary_location.get("landing_page_url")
            or work.get("doi")
            or work.get("id")
            or ""
        )
        return {
            "title": work.get("display_name", ""),
            "abstract": abstract,
            "text": abstract,
            "url": url,
            "citation_counts": work.get("cited_by_count") or 0,
            "year": work.get("publication_year"),
            "authors": authors,
            "paper_id": work.get("id", ""),
            "venue": source.get("display_name", ""),
            "search_source": "openalex",
        }


class FallbackPaperSearchAPI:
    """Try ReviewGrounder's configured search API first, then the online fallback."""

    def __init__(self, primary_api: Any, fallback_api: OpenAlexSearchAPI) -> None:
        self.primary_api = primary_api
        self.fallback_api = fallback_api
        self.last_source = "primary"

    def search_by_query(
        self, query: str, limit: int = 50, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        papers = self._try_primary("search_by_query", query, limit=limit, **kwargs)
        if papers:
            self.last_source = self._primary_source_name()
            return _tag_search_source(papers, self.last_source)
        self.last_source = "openalex"
        return self.fallback_api.search_by_query(query, limit=limit, **kwargs)

    def search_by_title(self, title: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        paper = self._try_primary("search_by_title", title, **kwargs)
        if paper:
            self.last_source = self._primary_source_name()
            paper["search_source"] = self.last_source
            return paper
        self.last_source = "openalex"
        return self.fallback_api.search_by_title(title, **kwargs)

    def get_paper(self, paper_id: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        paper = self._try_primary("get_paper", paper_id, **kwargs)
        if paper:
            self.last_source = self._primary_source_name()
            paper["search_source"] = self.last_source
            return paper
        self.last_source = "openalex"
        return self.fallback_api.get_paper(paper_id, **kwargs)

    def _try_primary(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        try:
            return getattr(self.primary_api, method_name)(*args, **kwargs)
        except Exception:
            return None

    def _primary_source_name(self) -> str:
        name = self.primary_api.__class__.__name__.lower()
        if "asta" in name:
            return "asta"
        if "semantic" in name:
            return "semantic_scholar"
        return name


def build_reviewgrounder_cache_payload(
    paper_title: str,
    arxiv_id: str,
    date: str,
    abstract: str,
    paper_content: str,
) -> str:
    """Build a deterministic cache fingerprint for ReviewGrounder outputs."""
    payload = {
        "version": REVIEWGROUNDER_CACHE_VERSION,
        "title": paper_title or "",
        "arxiv_id": arxiv_id or "",
        "date": date or "",
        "abstract": abstract or "",
        "content": paper_content or "",
        "model": REVIEWGROUNDER_MODEL,
        "reasoning_effort": REVIEWGROUNDER_REASONING_EFFORT,
        "max_output_tokens": REVIEWGROUNDER_MAX_OUTPUT_TOKENS,
        "max_related_papers": REVIEWGROUNDER_MAX_RELATED_PAPERS,
        "max_parallel_summaries": REVIEWGROUNDER_MAX_PARALLEL_SUMMARIES,
        "json_tool_retries": REVIEWGROUNDER_JSON_TOOL_RETRIES,
        "rpm": REVIEWGROUNDER_RPM,
        "web_fallback": REVIEWGROUNDER_ENABLE_WEB_FALLBACK,
        "review_format": REVIEWGROUNDER_REVIEW_FORMAT,
        "refiner_review_format": REVIEWGROUNDER_REFINER_REVIEW_FORMAT,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def generate_reviewgrounder_review(
    paper_content: str,
    *,
    paper_title: str,
    abstract: str,
    arxiv_id: str = "",
    date: str = "",
    keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run ReviewGrounder and return a JSON-serializable review result."""
    rg = _import_reviewgrounder()
    llm_service = _build_openai_compatible_llm(rg["LLMService"], rg["ChatMessage"])
    search_api, search_source = _build_search_api(rg)

    paper_retriever = rg["PaperRetriever"](
        search_api=search_api,
        reranker=None,
        top_n=max(1, REVIEWGROUNDER_MAX_RELATED_PAPERS),
        use_abstract=True,
    )
    prompts_file = str(_reviewgrounder_root() / "shared" / "configs" / "prompts.yaml")

    reviewer = rg["PaperReviewer"](
        reviewer_llm_service=llm_service,
        prompts_file=prompts_file,
    )
    reviewer.config = {
        "review_format": REVIEWGROUNDER_REVIEW_FORMAT,
        "max_tokens": REVIEWGROUNDER_MAX_OUTPUT_TOKENS,
    }

    refiner = rg["ReviewRefiner"](
        refiner_llm_service=llm_service,
        prompts_file=prompts_file,
    )
    refiner.config = {
        "review_format": REVIEWGROUNDER_REFINER_REVIEW_FORMAT,
        "max_tokens": REVIEWGROUNDER_MAX_OUTPUT_TOKENS,
    }

    related_work_searcher_cls = _build_related_work_searcher_cls(
        rg["RelatedWorkSearcher"]
    )
    related_work_searcher = related_work_searcher_cls(
        paper_retriever=paper_retriever,
        max_related_papers=REVIEWGROUNDER_MAX_RELATED_PAPERS,
        max_parallel_summaries=REVIEWGROUNDER_MAX_PARALLEL_SUMMARIES,
        prompts_file=prompts_file,
        keyword_llm_service=llm_service,
        summarizer_llm_service=llm_service,
        verbose=False,
    )

    results_analyzer = rg["PaperResultsAnalyzer"](
        prompts_file=prompts_file,
        llm_service=llm_service,
    )
    insight_miner = rg["PaperInsightMiner"](
        prompts_file=prompts_file,
        llm_service=llm_service,
    )

    paper_data = {
        "title": paper_title or "",
        "abstract": abstract or "",
        "content": paper_content or "",
        "keywords": keywords,
        "review_format": REVIEWGROUNDER_REVIEW_FORMAT,
        "refiner_review_format": REVIEWGROUNDER_REFINER_REVIEW_FORMAT,
    }

    review = rg["review_paper_with_refiner"](
        paper_data=paper_data,
        reviewer=reviewer,
        refiner=refiner,
        related_work_searcher=related_work_searcher,
        paper_results_analyzer=results_analyzer,
        paper_insight_miner=insight_miner,
        verbose=False,
    )

    result = _promote_initial_review_on_refiner_failure(_jsonable(review))
    result["reviewgrounder_metadata"] = {
        "source": "reviewgrounder",
        "model": REVIEWGROUNDER_MODEL,
        "reasoning_effort": REVIEWGROUNDER_REASONING_EFFORT,
        "base_url": REVIEWGROUNDER_BASE_URL,
        "review_format": REVIEWGROUNDER_REVIEW_FORMAT,
        "refiner_review_format": REVIEWGROUNDER_REFINER_REVIEW_FORMAT,
        "related_work_search": search_source,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "arxiv_id": arxiv_id,
        "date": date,
    }
    return result


def _build_related_work_searcher_cls(base_cls: Any) -> Any:
    class PaperToolsRelatedWorkSearcher(base_cls):
        def _summarize_paper_as_json(
            self,
            idx: int,
            paper: Dict[str, Any],
            reference_title: str,
            reference_abstract: str,
            reference_content: Optional[str],
            total_papers: int,
        ) -> Tuple[int, Dict[str, Any]]:
            idx, summary = super()._summarize_paper_as_json(
                idx,
                paper,
                reference_title,
                reference_abstract,
                reference_content,
                total_papers,
            )
            if isinstance(summary, dict):
                summary.setdefault("title", paper.get("title", ""))
                summary.setdefault("url", paper.get("url", ""))
                summary.setdefault("year", paper.get("year"))
                summary.setdefault("venue", paper.get("venue", ""))
                summary.setdefault("authors", paper.get("authors", []))
                summary.setdefault("search_source", paper.get("search_source", ""))
            return idx, summary

    return PaperToolsRelatedWorkSearcher


def reviewgrounder_error_result(
    exc: Exception, paper_title: str = ""
) -> Dict[str, Any]:
    return {
        "error": str(exc),
        "title": paper_title,
        "is_refined": False,
        "reviewgrounder_metadata": {
            "source": "reviewgrounder",
            "model": REVIEWGROUNDER_MODEL,
            "reasoning_effort": REVIEWGROUNDER_REASONING_EFFORT,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def reviewgrounder_markdown_from_result(review: Dict[str, Any]) -> str:
    """Extract a user-facing markdown review from ReviewGrounder output."""
    if not isinstance(review, dict):
        return str(review or "")

    if review.get("error"):
        return f"ReviewGrounder 审稿生成失败：{review.get('error')}"

    metadata = review.get("reviewgrounder_metadata") or {}
    header_parts = [
        "ReviewGrounder",
        f"model={metadata.get('model', REVIEWGROUNDER_MODEL)}",
        f"reasoning_effort={metadata.get('reasoning_effort', REVIEWGROUNDER_REASONING_EFFORT)}",
    ]
    if metadata.get("related_work_search"):
        header_parts.append(f"related_work_search={metadata['related_work_search']}")

    body = review.get("review_markdown") or review.get("review")
    if not isinstance(body, str) or not body.strip():
        body = _format_review_json(review.get("review_json") or review)

    parts = [f"> {'; '.join(header_parts)}"]
    if body:
        parts.append(body.strip())
    if review.get("search_keywords"):
        parts.append(
            "## Search Keywords\n\n" + ", ".join(map(str, review["search_keywords"]))
        )
    if review.get("refiner_error"):
        parts.append(
            f"## Refiner Status\n\nRefiner fallback used: {review['refiner_error']}"
        )
    return "\n\n".join(parts).strip()


def _promote_initial_review_on_refiner_failure(
    review: Dict[str, Any],
) -> Dict[str, Any]:
    """Use ReviewGrounder's initial review when the optional refiner step fails."""
    if not isinstance(review, dict) or not review.get("error"):
        return review

    initial_review = review.get("initial_review")
    if not isinstance(initial_review, dict):
        return review

    markdown, review_json = _initial_review_markdown(initial_review)
    if not markdown:
        return review

    review["refiner_error"] = review.pop("error")
    review["review"] = markdown
    review["review_markdown"] = markdown
    review["review_json"] = review_json or {
        field: initial_review[field]
        for field in (
            "summary",
            "soundness",
            "presentation",
            "contribution",
            "strengths",
            "weaknesses",
            "suggestions",
            "questions",
            "rating",
            "confidence",
            "decision",
        )
        if field in initial_review
    }
    review["is_refined"] = False
    review["used_initial_review_fallback"] = True
    return review


def _initial_review_markdown(
    initial_review: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    raw_review = initial_review.get("review")
    if isinstance(raw_review, str) and raw_review.strip():
        parsed = _parse_json_object(raw_review)
        if parsed:
            return _format_review_json(parsed), parsed
        return raw_review.strip(), {}
    return _format_review_json(initial_review), {}


def _build_openai_compatible_llm(llm_base_cls: Any, chat_message_cls: Any) -> Any:
    class OpenAICompatibleReviewGrounderLLM(llm_base_cls):
        def __init__(self) -> None:
            if not REVIEWGROUNDER_API_KEY:
                raise ValueError(
                    "REVIEWGROUNDER_API_KEY, SUMMARY_PRISM_OPENAI_API_KEY, or OPENAI_API_KEY "
                    "is required for ReviewGrounder"
                )
            self.model_name = REVIEWGROUNDER_MODEL
            self.reasoning_effort = REVIEWGROUNDER_REASONING_EFFORT
            self.base_url = REVIEWGROUNDER_BASE_URL
            self.call_count = 0
            self.client = create_openai_client(
                api_key=REVIEWGROUNDER_API_KEY,
                base_url=REVIEWGROUNDER_BASE_URL,
                timeout=float(REVIEWGROUNDER_TIMEOUT_SECONDS),
            )

        def generate(
            self,
            messages: List[Any],
            temperature: float = 0.7,
            top_p: float = 0.8,
            top_k: int = 20,
            max_tokens: int = 16384,
            presence_penalty: float = 0.0,
            **kwargs: Any,
        ) -> str:
            self.call_count += 1
            if (
                REVIEWGROUNDER_MAX_LLM_CALLS
                and self.call_count > REVIEWGROUNDER_MAX_LLM_CALLS
            ):
                raise RuntimeError(
                    f"ReviewGrounder LLM call limit exceeded: {REVIEWGROUNDER_MAX_LLM_CALLS}"
                )
            if REVIEWGROUNDER_VERBOSE:
                print(
                    "ReviewGrounder LLM call "
                    f"{self.call_count}: model={self.model_name}, "
                    f"effort={self.reasoning_effort}, max_tokens={max_tokens}, rpm={REVIEWGROUNDER_RPM}",
                    flush=True,
                )
            wait_seconds = _wait_for_reviewgrounder_rate_slot()
            if REVIEWGROUNDER_VERBOSE and wait_seconds > 0:
                print(
                    f"ReviewGrounder LLM call {self.call_count}: waited {wait_seconds:.1f}s for RPM limiter",
                    flush=True,
                )
            request_kwargs = {
                "model": self.model_name,
                "messages": _format_reviewgrounder_messages(messages, chat_message_cls),
                "temperature": temperature,
                "top_p": top_p,
                "presence_penalty": presence_penalty,
            }
            output_tokens = max(16, min(max_tokens, REVIEWGROUNDER_MAX_OUTPUT_TOKENS))
            if self.model_name.lower().startswith("gpt"):
                request_kwargs["reasoning_effort"] = self.reasoning_effort
                request_kwargs["max_completion_tokens"] = output_tokens
            else:
                request_kwargs["max_tokens"] = output_tokens

            try:
                response = self.client.chat.completions.create(**request_kwargs)
            except Exception as exc:
                if REVIEWGROUNDER_VERBOSE:
                    print(
                        f"ReviewGrounder LLM call {self.call_count}: request failed "
                        f"({exc.__class__.__name__}: {str(exc)[:300]})",
                        flush=True,
                    )
                raise
            choice = response.choices[0]
            text = (choice.message.content or "").strip()
            if not text:
                finish_reason = getattr(choice, "finish_reason", "")
                if REVIEWGROUNDER_VERBOSE:
                    print(
                        f"ReviewGrounder LLM call {self.call_count}: empty output "
                        f"(finish_reason={finish_reason})",
                        flush=True,
                    )
                raise ValueError(
                    f"ReviewGrounder LLM call returned empty output (finish_reason={finish_reason})"
                )
            if REVIEWGROUNDER_VERBOSE:
                print(
                    f"ReviewGrounder LLM call {self.call_count}: received {len(text)} chars",
                    flush=True,
                )
            return strip_think_tags(text)

        def stream_generate(
            self,
            messages: List[Any],
            temperature: float = 0.7,
            top_p: float = 0.8,
            top_k: int = 20,
            max_tokens: int = 16384,
            presence_penalty: float = 0.0,
            **kwargs: Any,
        ) -> Any:
            yield self.generate(
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                max_tokens=max_tokens,
                presence_penalty=presence_penalty,
                **kwargs,
            )

    return OpenAICompatibleReviewGrounderLLM()


def _wait_for_reviewgrounder_rate_slot() -> float:
    """Reserve one request slot in a process-wide rolling RPM window."""
    if REVIEWGROUNDER_RPM <= 0:
        return 0.0

    waited = 0.0
    while True:
        with _REVIEWGROUNDER_RATE_LOCK:
            now = time.monotonic()
            while (
                _REVIEWGROUNDER_CALL_TIMESTAMPS
                and now - _REVIEWGROUNDER_CALL_TIMESTAMPS[0] >= _RATE_WINDOW_SECONDS
            ):
                _REVIEWGROUNDER_CALL_TIMESTAMPS.popleft()

            if len(_REVIEWGROUNDER_CALL_TIMESTAMPS) < REVIEWGROUNDER_RPM:
                _REVIEWGROUNDER_CALL_TIMESTAMPS.append(now)
                return waited

            sleep_for = (
                _RATE_WINDOW_SECONDS - (now - _REVIEWGROUNDER_CALL_TIMESTAMPS[0]) + 0.05
            )

        sleep_for = max(0.05, sleep_for)
        if REVIEWGROUNDER_VERBOSE:
            print(f"ReviewGrounder RPM limiter sleeping {sleep_for:.1f}s", flush=True)
        time.sleep(sleep_for)
        waited += sleep_for


def _build_search_api(rg: Dict[str, Any]) -> Tuple[Any, str]:
    fallback_api = OpenAlexSearchAPI()
    primary_api = None
    primary_source = ""

    asta_key = os.environ.get("ASTA_API_KEY")
    s2_key = os.environ.get("S2_API_KEY")

    if asta_key:
        try:
            primary_api = rg["AstaAPI"](api_key=asta_key)
            primary_source = "asta"
        except Exception:
            primary_api = None
    if primary_api is None and s2_key:
        try:
            primary_api = rg["SemanticScholarAPI"](api_key=s2_key)
            primary_source = "semantic_scholar"
        except Exception:
            primary_api = None

    if primary_api is not None and REVIEWGROUNDER_ENABLE_WEB_FALLBACK:
        return FallbackPaperSearchAPI(
            primary_api, fallback_api
        ), f"{primary_source}+openalex_fallback"
    if primary_api is not None:
        return primary_api, primary_source
    if REVIEWGROUNDER_ENABLE_WEB_FALLBACK:
        return fallback_api, "openalex"
    raise ValueError(
        "ReviewGrounder related-work search needs ASTA_API_KEY, S2_API_KEY, or REVIEWGROUNDER_ENABLE_WEB_FALLBACK=true"
    )


def _import_reviewgrounder() -> Dict[str, Any]:
    root = _reviewgrounder_root()
    if not root.exists():
        raise ReviewGrounderDependencyError(
            f"ReviewGrounder checkout not found at {root}. Run: git submodule update --init vendor/ReviewGrounder"
        )
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    try:
        _ensure_namespace_package("reviewgrounder_src", root / "src")
        from shared.utils.llm_service import ChatMessage, LLMService
        from reviewgrounder_src.reviewer_agent.main_pipeline import (
            review_paper_with_refiner,
        )
        from reviewgrounder_src.reviewer_agent import (
            paper_insight_miner as paper_insight_miner_module,
        )
        from reviewgrounder_src.reviewer_agent import (
            paper_results_analyzer as paper_results_analyzer_module,
        )
        from reviewgrounder_src.reviewer_agent.paper_reviewer import PaperReviewer
        from reviewgrounder_src.reviewer_agent.paper_search.asta_api import AstaAPI
        from reviewgrounder_src.reviewer_agent.paper_search.paper_retriever import (
            PaperRetriever,
        )
        from reviewgrounder_src.reviewer_agent.paper_search.semantic_scholar_api import (
            SemanticScholarAPI,
        )
        from reviewgrounder_src.reviewer_agent.related_work_searcher import (
            RelatedWorkSearcher,
        )
        from reviewgrounder_src.reviewer_agent.review_refiner import ReviewRefiner
    except Exception as exc:
        raise ReviewGrounderDependencyError(
            f"Unable to import ReviewGrounder from {root}: {exc}"
        ) from exc

    paper_insight_miner_module.MAX_JSON_RETRIES = REVIEWGROUNDER_JSON_TOOL_RETRIES
    paper_results_analyzer_module.MAX_JSON_RETRIES = REVIEWGROUNDER_JSON_TOOL_RETRIES

    return {
        "AstaAPI": AstaAPI,
        "ChatMessage": ChatMessage,
        "LLMService": LLMService,
        "PaperInsightMiner": paper_insight_miner_module.PaperInsightMiner,
        "PaperResultsAnalyzer": paper_results_analyzer_module.PaperResultsAnalyzer,
        "PaperRetriever": PaperRetriever,
        "PaperReviewer": PaperReviewer,
        "RelatedWorkSearcher": RelatedWorkSearcher,
        "ReviewRefiner": ReviewRefiner,
        "SemanticScholarAPI": SemanticScholarAPI,
        "review_paper_with_refiner": review_paper_with_refiner,
    }


def _reviewgrounder_root() -> Path:
    path = Path(REVIEWGROUNDER_PATH)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path


def _ensure_namespace_package(name: str, path: Path) -> None:
    package = sys.modules.get(name)
    if package is None:
        package = types.ModuleType(name)
        package.__path__ = [str(path)]
        package.__package__ = name
        sys.modules[name] = package
    else:
        package.__path__ = [str(path)]


def _format_reviewgrounder_messages(
    messages: List[Any], chat_message_cls: Any
) -> List[Dict[str, str]]:
    formatted = []
    for message in messages:
        if isinstance(message, dict):
            role = str(message.get("role", "user"))
            content = str(message.get("content", ""))
        else:
            role = str(getattr(message, "role", "user"))
            content = str(getattr(message, "content", ""))
        formatted.append({"role": role, "content": content})
    return formatted


def _responses_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text
    text_parts = []
    for item in getattr(response, "output", []) or []:
        for block in getattr(item, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                text_parts.append(text)
    return "\n".join(text_parts)


def _abstract_from_openalex_index(index: Any) -> str:
    if not isinstance(index, dict) or not index:
        return ""
    positions = []
    for word, word_positions in index.items():
        if isinstance(word_positions, list):
            for position in word_positions:
                if isinstance(position, int):
                    positions.append((position, word))
    if not positions:
        return ""
    words = [word for _, word in sorted(positions)]
    return " ".join(words)


def _tag_search_source(
    papers: List[Dict[str, Any]], source: str
) -> List[Dict[str, Any]]:
    for paper in papers:
        if isinstance(paper, dict):
            paper.setdefault("search_source", source)
    return papers


def _format_review_json(review: Dict[str, Any]) -> str:
    sections = []
    field_titles = [
        ("summary", "Summary"),
        ("strengths", "Strengths"),
        ("weaknesses", "Weaknesses"),
        ("suggestions", "Suggestions"),
        ("questions", "Questions"),
        ("soundness", "Soundness"),
        ("presentation", "Presentation"),
        ("contribution", "Contribution"),
        ("rating", "Rating"),
        ("confidence", "Confidence"),
        ("decision", "Decision"),
    ]
    for field, title in field_titles:
        value = review.get(field)
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            content = "\n".join(f"- {item}" for item in value)
        else:
            content = str(value)
        sections.append(f"## {title}\n\n{content}")
    return "\n\n".join(sections)


def _parse_json_object(text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_jsonable(v) for v in value]
        if isinstance(value, tuple):
            return [_jsonable(v) for v in value]
        return str(value)


def strip_think_tags(text: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>\s*", "", text or "").strip()
