#!/usr/bin/env python3
"""
独立的统一HTML页面生成脚本
不依赖外部模板，直接生成完整的HTML页面
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def _atomic_save_text(filepath: str, content: str) -> bool:
    try:
        dir_path = os.path.dirname(filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        target_dir = dir_path or "."
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(filepath)}.",
            suffix=".tmp",
            dir=target_dir,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, filepath)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
        return True
    except OSError as e:
        print(f"❌ 保存文本失败 {filepath}: {e}")
        return False


def _atomic_save_json(filepath, data, indent=2, ensure_ascii=False):
    try:
        return _atomic_save_text(
            filepath,
            json.dumps(data, ensure_ascii=ensure_ascii, indent=indent),
        )
    except (TypeError, ValueError) as e:
        print(f"❌ JSON序列化失败 {filepath}: {e}")
        return False


# 导入配置
try:
    from src.utils.config import (
        SUMMARY_DIR,
        WEBPAGES_DIR,
        DOMAIN_PAPER_DIR,
        ARXIV_PAPER_DIR,
        PRESTIGE_COMPANY_WHITELIST,
        PRESTIGE_INSTITUTION_WHITELIST,
    )
except ImportError:
    SUMMARY_DIR = "summary"
    WEBPAGES_DIR = "webpages"
    DOMAIN_PAPER_DIR = "domain_paper"
    ARXIV_PAPER_DIR = "arxiv_paper"
    PRESTIGE_COMPANY_WHITELIST = {}
    PRESTIGE_INSTITUTION_WHITELIST = {}

try:
    from src.utils.io import save_json, save_text
except ImportError:

    def save_json(filepath, data, indent=2, ensure_ascii=False):  # type: ignore[no-redef]
        return _atomic_save_json(
            filepath, data, indent=indent, ensure_ascii=ensure_ascii
        )

    def save_text(filepath, content):  # type: ignore[no-redef]
        return _atomic_save_text(filepath, content)


from src.utils.published_data_version import build_published_data_version
from src.utils.published_webpage_data import project_embedded_clusters


try:
    from src.utils.publish_quality import (
        validate_date_data_payload,
        validate_publishable_papers,
    )
except ImportError as exc:
    _PUBLISH_QUALITY_IMPORT_ERROR = str(exc)

    def validate_publishable_papers(papers, *, context="papers"):  # type: ignore[no-redef]
        return False, [
            f"{context}: publication quality gate unavailable: "
            f"{_PUBLISH_QUALITY_IMPORT_ERROR}"
        ]

    def validate_date_data_payload(date_data, *, expected_date=""):  # type: ignore[no-redef]
        return False, [
            f"publication quality gate unavailable: {_PUBLISH_QUALITY_IMPORT_ERROR}"
        ]


# 分页配置
INITIAL_DAYS = 3  # 初始加载的天数（其余通过"加载更多"按需加载）
LOAD_MORE_DAYS = 7  # 每次"加载更多"加载的天数

RICHNESS_FIELDS = (
    "summary",
    "summary_translation",
    "intro_logic",
    "core_insight",
    "methodology",
    "additional_insights",
    "research_value",
)

REVIEWGROUNDER_METADATA_FIELDS = (
    "reviewgrounder_review",
    "research_value_source",
    "research_value_model",
    "research_value_reasoning_effort",
)

FAILED_GENERATION_MARKERS = (
    "翻译失败",
    "生成失败",
    "提取失败",
    "extraction failed",
    "generation failed",
    "translation failed",
)

SOURCE_METADATA_FIELDS = (
    "index",
    "title",
    "link",
    "arxiv_id",
    "authors",
    "summary",
    "abstract",
    "subjects",
    "date",
    "source_date",
    "category",
    "crawl_time",
)


def has_non_empty_text(value: Any) -> bool:
    """Check whether a JSON field contains meaningful text."""
    return isinstance(value, str) and bool(value.strip())


def is_failed_generated_text(value: Any) -> bool:
    """Return True for failure sentinels that should not be shown as content."""
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    return any(marker in lowered for marker in FAILED_GENERATION_MARKERS)


def has_valid_generated_text(value: Any) -> bool:
    """Check whether generated text is non-empty and not a failure placeholder."""
    return has_non_empty_text(value) and not is_failed_generated_text(value)


def derive_arxiv_tags(paper: Dict[str, Any]) -> List[str]:
    """Recover arXiv category tags even when the upstream file omitted `tags`."""
    tags = set(paper.get("tags", []) or [])

    category = (paper.get("category") or "").strip()
    if category:
        tags.add(category)

    subjects = paper.get("subjects") or ""
    for part in re.split(r"[,;]", subjects):
        part = part.strip()
        if re.match(r"^[a-z\-]+\.[A-Z]{2,}$", part):
            tags.add(part)

    return sorted(tags)


def normalize_match_text(text: str) -> str:
    """Normalize free text for whitelist matching."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_institution_names_from_affiliations(affiliations: Any) -> List[str]:
    """Parse affiliation JSON emitted by summary generation."""
    if not isinstance(affiliations, str) or not affiliations.strip():
        return []

    cleaned = affiliations.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        data = json.loads(cleaned)
    except Exception:
        return [cleaned]

    if not isinstance(data, dict):
        return [cleaned]

    names = []
    seen = set()
    for inst in data.get("institutions", []) or []:
        if not isinstance(inst, dict):
            continue
        name = (inst.get("name") or "").strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def find_whitelist_hits(
    values: List[str], whitelist: Dict[str, List[str]]
) -> List[str]:
    """Return canonical whitelist entries present in values."""
    hits = []
    seen = set()
    normalized_values = [
        f" {normalize_match_text(value)} " for value in values if value
    ]
    for canonical, aliases in whitelist.items():
        for alias in aliases:
            normalized_alias = normalize_match_text(alias)
            if not normalized_alias:
                continue
            if any(f" {normalized_alias} " in value for value in normalized_values):
                if canonical not in seen:
                    hits.append(canonical)
                    seen.add(canonical)
                break
    return hits


def repair_prestige_from_affiliations(paper: Dict[str, Any]) -> None:
    """Repair stale prestige status when later summary extraction found affiliations."""
    affiliations = paper.get("affiliations")
    if not has_valid_generated_text(affiliations):
        return

    current_source = paper.get("prestige_source")
    current_result = paper.get("prestige_result")
    if current_result is True and current_source != "missing_affiliations":
        return

    institution_names = extract_institution_names_from_affiliations(affiliations)
    institution_hits = find_whitelist_hits(
        institution_names, PRESTIGE_INSTITUTION_WHITELIST
    )
    company_hits = find_whitelist_hits(institution_names, PRESTIGE_COMPANY_WHITELIST)

    reasons = []
    if institution_hits:
        reasons.append("白名单命中顶级学术机构: " + ", ".join(institution_hits))
    if company_hits:
        reasons.append("白名单命中知名公司/研究机构: " + ", ".join(company_hits))

    if not reasons:
        return

    paper["prestige_result"] = True
    paper["prestige_reason"] = "；".join(reasons)
    if institution_hits and not company_hits:
        paper["prestige_source"] = "whitelist_institution"
    elif company_hits and not institution_hits:
        paper["prestige_source"] = "whitelist_company"
    else:
        paper["prestige_source"] = "whitelist"
    paper["prestige_status"] = "verified"
    paper["prestige_matches"] = {
        "authors": (paper.get("prestige_matches") or {}).get("authors", []),
        "institutions": institution_hits,
        "companies": company_hits,
        "institution_names": institution_names,
    }


def merge_paper_fields(
    base: Dict[str, Any], candidate: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge complementary records for the same paper instead of picking one whole file."""
    merged = dict(base)

    for field in RICHNESS_FIELDS:
        if not has_valid_generated_text(merged.get(field)) and has_valid_generated_text(
            candidate.get(field)
        ):
            merged[field] = candidate.get(field)

    for field in SOURCE_METADATA_FIELDS:
        if merged.get(field) in (None, "") and candidate.get(field) not in (None, ""):
            merged[field] = candidate.get(field)

    for field in (
        "filter_reason",
        "summary_generated_time",
        "summary_model",
        "link",
        *REVIEWGROUNDER_METADATA_FIELDS,
    ):
        if merged.get(field) in (None, "") and candidate.get(field) not in (None, ""):
            merged[field] = candidate.get(field)

    if not has_valid_generated_text(
        merged.get("affiliations")
    ) and has_valid_generated_text(candidate.get("affiliations")):
        merged["affiliations"] = candidate.get("affiliations")

    merged_cluster = merged.get("cluster") or ""
    candidate_cluster = candidate.get("cluster") or ""
    if (
        (not merged_cluster or merged_cluster == "Other")
        and candidate_cluster
        and candidate_cluster != "Other"
    ):
        merged["cluster"] = candidate_cluster

    merged_tags = list(merged.get("tags") or [])
    for tag in candidate.get("tags") or []:
        if tag not in merged_tags:
            merged_tags.append(tag)
    if merged_tags:
        merged["tags"] = merged_tags

    candidate_prestige_result = candidate.get("prestige_result")
    merged_prestige_result = merged.get("prestige_result")
    if candidate_prestige_result is True and merged_prestige_result is not True:
        for field in (
            "prestige_result",
            "prestige_reason",
            "prestige_source",
            "prestige_status",
            "prestige_matches",
        ):
            if field in candidate:
                merged[field] = candidate[field]

    repair_prestige_from_affiliations(merged)
    return merged


def normalize_papers_for_display(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize optional metadata so display logic is robust to partial files."""
    normalized = []
    for paper in papers:
        paper_copy = dict(paper)
        for field in RICHNESS_FIELDS:
            if is_failed_generated_text(paper_copy.get(field)):
                paper_copy[field] = ""
        paper_copy["cluster"] = paper_copy.get("cluster") or "Other"
        paper_copy["tags"] = derive_arxiv_tags(paper_copy)
        repair_prestige_from_affiliations(paper_copy)
        normalized.append(paper_copy)
    return normalized


def publishable_papers_or_none(
    papers: List[Dict[str, Any]],
    source_label: str,
) -> Optional[List[Dict[str, Any]]]:
    """Return normalized papers only when the whole source is ready to publish."""
    normalized = normalize_papers_for_display(papers)
    if not normalized:
        print(f"跳过空日期候选: {source_label}")
        return None

    ok, errors = validate_publishable_papers(normalized, context=source_label)
    if not ok:
        print(f"跳过未完成发布候选: {source_label}")
        for error in errors[:5]:
            print(f"  - {error}")
        if len(errors) > 5:
            print(f"  - ... 还有 {len(errors) - 5} 个未完成项")
        return None

    return normalized


def build_arxiv_source_index() -> Dict[str, Dict[str, Any]]:
    """Load crawl-stage metadata for backfilling partial downstream files."""
    source_by_id: Dict[str, Dict[str, Any]] = {}
    arxiv_dir = Path(ARXIV_PAPER_DIR)
    if not arxiv_dir.exists():
        return source_by_id

    for json_file in arxiv_dir.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                papers = json.load(f)
        except Exception as e:
            print(f"加载源文件 {json_file} 时出错: {e}")
            continue

        if not isinstance(papers, list):
            continue

        for paper in papers:
            if not isinstance(paper, dict):
                continue
            arxiv_id = (paper.get("arxiv_id") or "").strip()
            if arxiv_id:
                source_by_id[arxiv_id] = paper

    return source_by_id


def backfill_paper_metadata(
    papers: List[Dict[str, Any]],
    source_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Backfill fields that old filtered/clustered outputs may have dropped."""
    backfilled = []
    for paper in papers:
        paper_copy = dict(paper)
        source_paper = source_by_id.get((paper_copy.get("arxiv_id") or "").strip())
        if source_paper:
            for field in SOURCE_METADATA_FIELDS:
                source_value = source_paper.get(field)
                if source_value is None:
                    continue

                current_value = paper_copy.get(field)
                if field in {"summary", "abstract"}:
                    should_repair = has_non_empty_text(
                        source_value
                    ) and not has_non_empty_text(current_value)
                else:
                    should_repair = current_value in (
                        None,
                        "",
                    ) and source_value not in (None, "")

                if should_repair:
                    paper_copy[field] = source_value

        backfilled.append(paper_copy)
    return backfilled


def score_paper_file(json_file: Path, papers: List[Dict[str, Any]]) -> tuple:
    """Prefer clustered and fully enriched daily files over partial fallbacks."""
    normalized = normalize_papers_for_display(papers)
    in_summary_dir = json_file.parent.name == Path(SUMMARY_DIR).name
    with_summary_suffix = json_file.name.endswith("_with_summary2.json")
    is_clustered_file = json_file.stem.startswith("clustered_papers_")
    cluster_non_other = sum(
        1 for paper in normalized if paper.get("cluster") not in ("", "Other")
    )
    tags_present = sum(1 for paper in normalized if paper.get("tags"))
    rich_fields_present = sum(
        1
        for paper in normalized
        for field in RICHNESS_FIELDS
        if has_valid_generated_text(paper.get(field))
    )

    return (
        1 if in_summary_dir else 0,
        1 if with_summary_suffix else 0,
        1 if is_clustered_file else 0,
        cluster_non_other,
        tags_present,
        rich_fields_present,
        len(normalized),
        int(json_file.stat().st_mtime),
    )


def paper_identity(paper: Dict[str, Any]) -> str:
    """Return a stable key for merging rerun output with already published data."""
    return (
        str(paper.get("arxiv_id") or "").strip()
        or str(paper.get("link") or "").strip()
        or str(paper.get("title") or "").strip()
    )


def paper_display_score(paper: Dict[str, Any]) -> tuple:
    """Prefer records with generated analysis, non-Other clusters, and metadata."""
    rich_fields_present = sum(
        1 for field in RICHNESS_FIELDS if has_valid_generated_text(paper.get(field))
    )
    failed_fields_present = sum(
        1 for field in RICHNESS_FIELDS if is_failed_generated_text(paper.get(field))
    )
    source_fields_present = sum(
        1 for field in SOURCE_METADATA_FIELDS if paper.get(field) not in (None, "")
    )
    cluster = paper.get("cluster") or ""
    return (
        rich_fields_present,
        -failed_fields_present,
        1 if cluster and cluster != "Other" else 0,
        len(paper.get("tags", []) or []),
        source_fields_present,
    )


def merge_published_papers(
    current_papers: List[Dict[str, Any]],
    published_papers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge same-date rerun output with published data so reruns do not drop papers."""
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for paper in current_papers:
        key = paper_identity(paper)
        if not key:
            key = f"current-{len(order)}"
        if key not in merged:
            order.append(key)
        merged[key] = paper

    for paper in published_papers:
        key = paper_identity(paper)
        if not key:
            key = f"published-{len(order)}"
        if key not in merged:
            order.append(key)
            merged[key] = paper
        else:
            primary, secondary = (
                (paper, merged[key])
                if paper_display_score(paper) > paper_display_score(merged[key])
                else (merged[key], paper)
            )
            merged[key] = merge_paper_fields(primary, secondary)

    return normalize_papers_for_display([merged[key] for key in order])


def merge_candidate_papers(candidates: List[tuple]) -> tuple:
    """Merge same-date summary/cluster/filter candidates field-by-field."""
    sorted_candidates = sorted(candidates, key=lambda item: item[0], reverse=True)
    best_score, best_file, best_papers = sorted_candidates[0]
    merged_papers = normalize_papers_for_display(best_papers)

    for _score, _json_file, candidate_papers in sorted_candidates[1:]:
        merged_papers = merge_published_papers(
            merged_papers, normalize_papers_for_display(candidate_papers)
        )

    return best_score, best_file, merged_papers


def extract_yyyy_mm_dd(value: Any) -> str:
    """Extract a normalized YYYY-MM-DD date from a field value."""
    if value in (None, ""):
        return ""
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return match.group(0) if match else ""


def group_papers_by_source_date(
    papers: List[Dict[str, Any]],
    fallback_date: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """Group range-run papers by the upstream date page that produced them."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for paper in papers:
        date = (
            extract_yyyy_mm_dd(paper.get("source_date"))
            or extract_yyyy_mm_dd(paper.get("date"))
            or fallback_date
        )
        grouped.setdefault(date, []).append(paper)
    return grouped


def load_paper_data(
    replace_dates: Optional[Set[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """加载论文数据"""
    replace_dates = replace_dates or set()
    papers_by_date = {}
    summary_dir = Path(SUMMARY_DIR)
    domain_paper_dir = Path(DOMAIN_PAPER_DIR)
    candidates_by_date: Dict[str, List[tuple]] = {}
    source_by_id = build_arxiv_source_index()

    candidate_files = list(summary_dir.glob("*_with_summary2.json"))
    candidate_files.extend(domain_paper_dir.glob("clustered_papers_*.json"))
    candidate_files.extend(domain_paper_dir.glob("filtered_papers_*.json"))

    for json_file in candidate_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                papers = json.load(f)

            if not isinstance(papers, list):
                continue

            filename = json_file.stem
            range_match = re.search(
                r"(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})", filename
            )
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
            if date_match:
                backfilled_papers = backfill_paper_metadata(papers, source_by_id)
                normalized_papers = publishable_papers_or_none(
                    backfilled_papers,
                    f"{json_file.parent.name}/{json_file.name}",
                )
                if normalized_papers is None:
                    continue
                if range_match:
                    grouped_papers = group_papers_by_source_date(
                        normalized_papers,
                        range_match.group(1),
                    )
                    for date, date_papers in grouped_papers.items():
                        publishable_date_papers = publishable_papers_or_none(
                            date_papers,
                            f"{json_file.parent.name}/{json_file.name}:{date}",
                        )
                        if publishable_date_papers is None:
                            continue
                        candidates_by_date.setdefault(date, []).append(
                            (
                                score_paper_file(json_file, publishable_date_papers),
                                json_file,
                                publishable_date_papers,
                            )
                        )
                else:
                    date = date_match.group(1)
                    candidates_by_date.setdefault(date, []).append(
                        (
                            score_paper_file(json_file, normalized_papers),
                            json_file,
                            normalized_papers,
                        )
                    )
        except Exception as e:
            print(f"加载文件 {json_file} 时出错: {e}")

    for date, candidates in candidates_by_date.items():
        _, chosen_file, chosen_papers = merge_candidate_papers(candidates)
        papers_by_date[date] = chosen_papers
        print(
            f"加载了 {len(chosen_papers)} 篇论文，日期: {date}，来源: {chosen_file.parent.name}/{chosen_file.name}"
        )

    data_dir = Path(WEBPAGES_DIR) / "data"
    if data_dir.exists():
        for date_file in data_dir.glob("*.json"):
            if date_file.name == "index.json":
                continue

            date = date_file.stem
            try:
                with open(date_file, "r", encoding="utf-8") as f:
                    date_data = json.load(f)

                flattened_papers = []
                for cluster in date_data.get("clusters", []) or []:
                    cluster_name = cluster.get("name") or "Other"
                    for paper in cluster.get("papers", []) or []:
                        paper_copy = dict(paper)
                        paper_copy["cluster"] = (
                            paper_copy.get("cluster") or cluster_name
                        )
                        flattened_papers.append(paper_copy)

                if flattened_papers:
                    published_papers = publishable_papers_or_none(
                        flattened_papers,
                        f"{date_file}",
                    )
                    if published_papers is None:
                        continue
                    if date in replace_dates and date in papers_by_date:
                        print(f"跳过合并已发布数据 {date}: 当前运行显式重生成该日期")
                        continue
                    if date in papers_by_date:
                        before_count = len(papers_by_date[date])
                        merged_papers = merge_published_papers(
                            papers_by_date[date], published_papers
                        )
                        papers_by_date[date] = merged_papers
                        if len(merged_papers) > before_count:
                            print(
                                f"合并已发布数据 {date}: 当前 {before_count} 篇，"
                                f"发布 {len(published_papers)} 篇，合并后 {len(merged_papers)} 篇"
                            )
                    else:
                        papers_by_date[date] = published_papers
                        print(
                            f"保留已发布数据 {date}: {len(flattened_papers)} 篇，来源: {date_file}"
                        )
                elif date_data.get("date") == date:
                    print(f"跳过已发布空日期 {date}，来源: {date_file}")
            except Exception as e:
                print(f"加载已发布数据 {date_file} 时出错: {e}")

    return papers_by_date


def load_daily_overviews() -> Dict[str, str]:
    """加载每日AI论文速览"""
    overviews = {}
    summary_dir = Path(SUMMARY_DIR)

    # 查找所有的每日速览Markdown文件
    for md_file in summary_dir.glob("daily_overview_*.md"):
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()

            # 从文件名提取日期
            filename = md_file.stem
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
            if date_match:
                date = date_match.group(1)
                overviews[date] = content
                print(f"加载了每日速览，日期: {date}")
        except Exception as e:
            print(f"加载每日速览文件 {md_file} 时出错: {e}")

    data_dir = Path(WEBPAGES_DIR) / "data"
    if data_dir.exists():
        for date_file in data_dir.glob("*.json"):
            if date_file.name == "index.json" or date_file.stem in overviews:
                continue

            try:
                with open(date_file, "r", encoding="utf-8") as f:
                    date_data = json.load(f)
                overview = date_data.get("overview", "")
                if overview:
                    overviews[date_file.stem] = overview
                    print(f"保留已发布每日速览，日期: {date_file.stem}")
            except Exception as e:
                print(f"加载已发布每日速览 {date_file} 时出错: {e}")

    return overviews


def build_data_version(
    papers_by_date: Dict[str, List[Dict[str, Any]]], daily_overviews: Dict[str, str]
) -> str:
    """Return a deterministic cache-busting version for published JSON data."""
    all_dates = sorted(papers_by_date.keys(), reverse=True)
    index_data = {
        "dates": all_dates,
        "initial_days": INITIAL_DAYS,
        "load_more_days": LOAD_MORE_DAYS,
    }
    date_payloads = {
        date: {
            "date": date,
            "clusters": organize_papers_by_cluster(papers_by_date.get(date, [])),
            "tags": collect_all_tags(papers_by_date.get(date, [])),
            "overview": daily_overviews.get(date, ""),
        }
        for date in all_dates
    }
    return build_published_data_version(index_data, date_payloads)


def escape_script_json_chars(text: str) -> str:
    """Escape characters that can break out of an HTML script block."""
    return (
        text.replace("<", "\\u003C")
        .replace(">", "\\u003E")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def dumps_js(data: Any) -> str:
    """JSON dump safe for embedding inside a <script> tag."""
    return escape_script_json_chars(json.dumps(data, ensure_ascii=False))


def escape_js_string(text: str) -> str:
    """Escape one JavaScript double-quoted string inside a script block."""
    if text in (None, ""):
        return ""
    return escape_script_json_chars(
        str(text)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def organize_papers_by_cluster(papers: List[Dict]) -> List[Dict]:
    """将论文按聚类组织，按论文数量降序排列"""
    clusters = {}
    for paper in papers:
        cluster = paper.get("cluster", "Other")
        if cluster not in clusters:
            clusters[cluster] = []
        clusters[cluster].append(paper)
    result = []
    for cluster_name, cluster_papers in sorted(
        clusters.items(), key=lambda x: (-len(x[1]), x[0])
    ):
        result.append(
            {
                "name": cluster_name,
                "count": len(cluster_papers),
                "papers": cluster_papers,
            }
        )
    return result


def collect_all_tags(papers: List[Dict]) -> List[Dict]:
    """Collect all unique tags with counts for the tag filter bar.
    arXiv category tags (cs.XX) are listed first, then cluster tags."""
    arxiv_counts = {}
    cluster_counts = {}
    for paper in papers:
        tags = paper.get("tags", []) or []
        cluster = paper.get("cluster", "Other")
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


def prune_stale_date_files(data_dir: Path, valid_dates: List[str]) -> None:
    """Remove date JSON files that are empty, partial, or no longer publishable."""
    valid_date_set = set(valid_dates)
    if not data_dir.exists():
        return

    for date_file in data_dir.glob("*.json"):
        if date_file.name == "index.json":
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_file.stem):
            continue
        if date_file.stem not in valid_date_set:
            date_file.unlink()
            print(f"删除未发布日期数据文件: {date_file}")


def stage_date_data_files(
    data_dir: Path,
    date_payloads: Dict[str, Dict[str, Any]],
    index_data: Dict[str, Any],
) -> Path:
    """Write candidate published JSON into a staging directory before commit."""
    data_dir.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix=".publish-stage-", dir=str(data_dir)))
    try:
        for date, date_data in date_payloads.items():
            staged_date_file = stage_dir / f"{date}.json"
            if not save_json(
                str(staged_date_file), date_data, indent=None, ensure_ascii=False
            ):
                raise IOError(f"暂存数据文件失败: {staged_date_file}")

        staged_index_file = stage_dir / "index.json"
        if not save_json(
            str(staged_index_file), index_data, indent=2, ensure_ascii=False
        ):
            raise IOError(f"暂存索引文件失败: {staged_index_file}")

        return stage_dir
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise


def save_date_data_files(papers_by_date: Dict, daily_overviews: Dict) -> List[str]:
    """将每个日期的数据保存为独立的 JSON 文件"""
    all_dates = sorted(papers_by_date.keys(), reverse=True)
    if not all_dates:
        raise ValueError("没有可发布日期，拒绝写入空网页数据索引")

    date_payloads: Dict[str, Dict[str, Any]] = {}
    for date in all_dates:
        papers = papers_by_date[date]
        organized = organize_papers_by_cluster(papers)
        tags = collect_all_tags(papers)

        date_data = {
            "date": date,
            "clusters": organized,
            "tags": tags,
            "overview": daily_overviews.get(date, ""),
        }

        ok, errors = validate_date_data_payload(date_data, expected_date=date)
        if not ok:
            raise ValueError(f"{date} 未通过发布质量检查: {'; '.join(errors[:5])}")
        date_payloads[date] = date_data

    # 生成日期索引文件
    index_data = {
        "dates": all_dates,
        "initial_days": INITIAL_DAYS,
        "load_more_days": LOAD_MORE_DAYS,
    }
    data_dir = Path(WEBPAGES_DIR) / "data"
    data_snapshot = snapshot_directory(data_dir)
    stage_dir = stage_date_data_files(data_dir, date_payloads, index_data)
    try:
        try:
            for date in all_dates:
                date_file = data_dir / f"{date}.json"
                os.replace(stage_dir / f"{date}.json", date_file)
                print(f"保存数据文件: {date_file}")

            index_file = data_dir / "index.json"
            os.replace(stage_dir / "index.json", index_file)
            print(f"保存索引文件: {index_file}")

            prune_stale_date_files(data_dir, all_dates)
        except Exception:
            restore_directory_snapshot(data_dir, data_snapshot)
            raise
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)

    return all_dates


def generate_complete_html(replace_dates: Optional[Set[str]] = None) -> str:
    """生成完整的HTML页面"""
    papers_by_date = load_paper_data(replace_dates=replace_dates)
    daily_overviews = load_daily_overviews()

    for date in list(papers_by_date.keys()):
        if not has_valid_generated_text(daily_overviews.get(date, "")):
            print(f"跳过缺少每日速览的日期 {date}")
            del papers_by_date[date]

    # 保存所有日期的数据到独立文件
    all_dates = save_date_data_files(papers_by_date, daily_overviews)

    # 只取最近 INITIAL_DAYS 天的数据嵌入 HTML
    initial_dates = all_dates[:INITIAL_DAYS]
    data_version = build_data_version(papers_by_date, daily_overviews)

    # 生成JavaScript数据 - 只包含初始数据
    initial_papers = {}
    for date in initial_dates:
        papers = papers_by_date.get(date, [])
        organized = organize_papers_by_cluster(papers)
        date_payload = {"clusters": organized}
        initial_papers[date] = project_embedded_clusters(date_payload)

    js_data = f"const allPapers = {dumps_js(initial_papers)};\n\n"

    # 生成 allPaperTags 数据
    initial_tags = {
        date: collect_all_tags(papers_by_date.get(date, [])) for date in initial_dates
    }
    js_data += f"const allPaperTags = {dumps_js(initial_tags)};\n\n"

    # 添加所有可用日期列表（用于按需加载）
    js_data += f"const availableDates = {dumps_js(all_dates)};\n"
    js_data += f"const loadedDates = new Set({dumps_js(initial_dates)});\n"
    js_data += f"const LOAD_MORE_DAYS = {LOAD_MORE_DAYS};\n\n"
    js_data += f"const DATA_VERSION = {dumps_js(data_version)};\n\n"

    # 添加每日速览数据 - 只包含初始数据
    initial_overviews = {
        date: daily_overviews.get(date, "")
        for date in initial_dates
        if daily_overviews.get(date, "")
    }
    js_data += f"const dailyOverviewsRaw = {dumps_js(initial_overviews)};\n"
    # 在客户端，我们再将解析后的字符串赋值给 dailyOverviews
    js_data += "const dailyOverviews = {};\n"
    js_data += "for (const date in dailyOverviewsRaw) {\n"
    js_data += "    dailyOverviews[date] = dailyOverviewsRaw[date];\n"
    js_data += "}\n"

    # 完整的HTML模板
    html_template = f"""<!DOCTYPE html>
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

        /* 论文卡片展开/收起 */
        .paper-expand-hint {{
            padding: 4px 0;
            font-size: 0.75rem;
            cursor: pointer;
            transition: color 0.2s;
        }}
        .paper-expand-hint:hover {{
            color: #2563eb;
        }}
        .dark .paper-expand-hint:hover {{
            color: #60a5fa;
        }}
        .paper-expand-hint .expand-arrow {{
            display: inline-block;
            transition: transform 0.2s;
            font-size: 0.65rem;
            margin-right: 4px;
        }}
        .paper-detail {{
            border-top: 1px solid #e2e8f0;
            margin-top: 8px;
            padding-top: 8px;
        }}
        .dark .paper-detail {{
            border-top-color: #334155;
        }}
        .paper-detail.hidden {{
            display: none;
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
                    const response = await fetch(`data/${{date}}.json?v=${{DATA_VERSION}}`);
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
            const paperEl = document.querySelector(`[data-arxiv-id="${{cssEscape(arxivId)}}"]`);
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
                const starBtn = document.querySelector(`[data-arxiv-id="${{cssEscape(arxivId)}}"] .star-button`);
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
            const checkbox = document.querySelector(`[data-arxiv-id="${{cssEscape(arxivId)}}"] input[type="checkbox"]`);
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

        function escapeHtml(value) {{
            return String(value ?? '').replace(/[&<>"']/g, ch => ({{
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            }}[ch]));
        }}

        function escapeJsSingleQuotedAttr(value) {{
            return escapeHtml(String(value ?? '')
                .replace(/\\\\/g, '\\\\\\\\')
                .replace(/'/g, "\\\\'")
                .replace(/\\r/g, '\\\\r')
                .replace(/\\n/g, '\\\\n')
                .replace(/\\u2028/g, '\\\\u2028')
                .replace(/\\u2029/g, '\\\\u2029'));
        }}

        function safePathSegment(value) {{
            return encodeURIComponent(String(value ?? ''));
        }}

        function cssEscape(value) {{
            const text = String(value ?? '');
            if (window.CSS && typeof CSS.escape === 'function') return CSS.escape(text);
            return text.replace(/["\\\\]/g, '\\\\$&');
        }}

        function escapeMarkdownHtml(value) {{
            return String(value ?? '').replace(/[&<>]/g, ch => ({{
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;'
            }}[ch]));
        }}

        function sanitizeRenderedMarkdown(root) {{
            root.querySelectorAll('script, style, iframe, object, embed').forEach(el => el.remove());
            root.querySelectorAll('a[href]').forEach(link => {{
                const href = link.getAttribute('href') || '';
                if (!/^(https?:|mailto:|#|[/])/i.test(href)) {{
                    link.removeAttribute('href');
                }}
                link.setAttribute('target', '_blank');
                link.setAttribute('rel', 'noopener noreferrer');
            }});
        }}

        // Parse markdown for a single element by id
        function renderMarkdownEl(el) {{
            if (!el || el.getAttribute('data-rendered')) return;
            const raw = mdRawContent[el.id];
            if (raw) {{
                try {{
                    el.innerHTML = marked.parse(escapeMarkdownHtml(raw));
                    sanitizeRenderedMarkdown(el);
                }} catch (e) {{ el.textContent = raw; }}
                el.setAttribute('data-rendered', '1');
            }}
        }}

        // Parse markdown for all unrendered .markdown-content elements inside a container
        function lazyRenderMarkdown(container) {{
            if (typeof marked === 'undefined') return;
            container.querySelectorAll('.markdown-content:not([data-rendered])').forEach(renderMarkdownEl);
        }}

        function hasMeaningfulText(value) {{
            return typeof value === 'string' && value.trim().length > 0;
        }}

        // Render markdown only for currently visible (open) sections
        function renderVisibleMarkdown() {{
            if (typeof marked === 'undefined') return;
            marked.setOptions({{ breaks: true, gfm: true, headerIds: false, mangle: false }});
            // Render open collapsible sections
            document.querySelectorAll('.collapsible-content.open').forEach(c => lazyRenderMarkdown(c));
            // Render overview sections (top-level, not inside collapsible)
            document.querySelectorAll('.markdown-content:not([data-rendered])').forEach(el => {{
                if (!el.closest('.collapsible-content')) renderMarkdownEl(el);
            }});
        }}

        // 创建论文HTML
        function formatAuthorsWithAffiliations(authorsStr, affiliationsStr) {{
            if (!affiliationsStr) return escapeHtml(authorsStr);
            try {{
                // 解析 JSON（可能被包在 ```json ... ``` 中）
                let jsonStr = affiliationsStr;
                const match = jsonStr.match(/```json\\s*([\\s\\S]*?)\\s*```/);
                if (match) jsonStr = match[1];
                const objMatch = jsonStr.match(/\\{{[\\s\\S]*\\}}/);
                if (objMatch) jsonStr = objMatch[0];
                const data = JSON.parse(jsonStr);

                // 兼容旧格式（数组）
                if (Array.isArray(data)) {{
                    const authors = authorsStr.split(/,\\s*/);
                    const affMap = {{}};
                    data.forEach(a => {{ if (a.name && a.affiliation) affMap[a.name.trim().toLowerCase()] = a.affiliation; }});
                    return authors.map(a => {{
                        const aff = affMap[a.trim().toLowerCase()];
                        return aff
                            ? `${{escapeHtml(a.trim())}}<sup class="aff-sup" title="${{escapeHtml(aff)}}">${{escapeHtml(aff)}}</sup>`
                            : escapeHtml(a.trim());
                    }}).join(', ');
                }}

                if (!data.authors || !data.institutions) return escapeHtml(authorsStr);

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
                    const supValues = sups.map(escapeHtml).join(',');
                    const supStr = sups.length > 0
                        ? `<sup class="aff-sup">${{supValues}}</sup>`
                        : '';
                    return `${{escapeHtml(a.name)}}${{supStr}}`;
                }});

                // 渲染机构列表
                const instLine = data.institutions.map(inst =>
                    `<sup class="aff-sup">${{escapeHtml(inst.id)}}</sup>${{escapeHtml(inst.name)}}`
                ).join('&ensp;');

                // 渲染脚注
                let footLine = '';
                if (data.footnotes && data.footnotes.length > 0) {{
                    footLine = data.footnotes.map(fn =>
                        `<sup class="aff-sup">${{escapeHtml(fn.marker)}}</sup>${{escapeHtml(fn.text)}}`
                    ).join('&ensp;');
                }}

                let html = authorParts.join(', ');
                html += `<div class="text-xs text-slate-500 dark:text-slate-400 mt-1">${{instLine}}</div>`;
                if (footLine) {{
                    html += `<div class="text-xs text-slate-400 dark:text-slate-500 mt-0.5 italic">${{footLine}}</div>`;
                }}
                return html;
            }} catch (e) {{
                return escapeHtml(authorsStr);
            }}
        }}

        // Store paper data by arxiv_id for lazy detail building
        const paperDataMap = {{}};

        function createPaperHTML(paper, date) {{
            const aid = String(paper.arxiv_id ?? '');
            const aidHtml = escapeHtml(aid);
            const aidArg = escapeJsSingleQuotedAttr(aid);
            const titleHtml = escapeHtml(paper.title);
            const titleAttr = escapeHtml(paper.title);
            const dateHtml = escapeHtml(date);
            const isStarred = starredPapers.has(aid);
            const isRead = readPapers.has(aid);
            const isDeleted = deletedPapers.has(aid);

            if (isDeleted) return '';
            if (showOnlyStarred && !isStarred) return '';
            if (!paperMatchesFilters(paper, date)) return '';

            // Store paper data for lazy rendering
            paperDataMap[aid] = {{ paper, date }};

            const clusterBadge = paper.cluster ? `<span class="tag-badge">${{escapeHtml(paper.cluster)}}</span>` : '';
            const tagBadges = (paper.tags || []).map(tag => `<span class="tag-badge tag-arxiv">${{escapeHtml(tag)}}</span>`).join('');

            return `
                <div class="paper-item bg-white dark:bg-slate-800/50 rounded-lg shadow-sm p-4 sm:p-6" data-arxiv-id="${{aidHtml}}">
                    <!-- 论文标题和操作按钮 -->
                    <div class="flex items-start justify-between mb-1">
                        <div class="flex items-start space-x-2 sm:space-x-3 flex-1 min-w-0">
                            <button class="star-button ${{isStarred ? 'starred' : ''}} mt-1 flex-shrink-0" onclick="toggleStar('${{aidArg}}')" title="点击收藏">
                                <svg class="h-5 w-5 sm:h-6 sm:w-6" viewBox="0 0 20 20" fill="currentColor">
                                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                                </svg>
                            </button>
                            <h3 class="text-base sm:text-lg font-semibold text-black dark:text-white leading-tight break-words cursor-pointer hover:text-blue-600 dark:hover:text-blue-400 transition-colors" onclick="togglePaperDetail('${{aidArg}}')">${{titleHtml}}</h3>
                        </div>
                        <button class="delete-button text-slate-400 hover:text-red-500 ml-2 sm:ml-4 flex-shrink-0" onclick="deletePaperByButton(this)" data-arxiv-id="${{aidHtml}}" data-title="${{titleAttr}}" title="删除">
                            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>

                    <!-- 论文元信息（始终可见） -->
                    <div class="space-y-1 mb-2">
                        <div class="flex flex-wrap items-center gap-2 sm:gap-4 text-xs sm:text-sm text-slate-600 dark:text-slate-400">
                            <span class="break-all"><strong>ArXiv ID:</strong> ${{aidHtml}}</span>
                            ${{clusterBadge}}
                            ${{tagBadges}}
                            <span class="whitespace-nowrap">${{dateHtml}}</span>
                        </div>
                        <div class="text-xs sm:text-sm text-black dark:text-white break-words">
                            <strong>作者:</strong> ${{formatAuthorsWithAffiliations(paper.authors, paper.affiliations)}}
                        </div>
                    </div>

                    <!-- 展开/收起指示器 -->
                    <div class="paper-expand-hint text-xs text-slate-400 dark:text-slate-500 cursor-pointer select-none" onclick="togglePaperDetail('${{aidArg}}')" id="expand-hint-${{aidHtml}}">
                        <span class="expand-arrow">▶</span> 点击标题展开详情
                    </div>

                    <!-- 懒加载的详情容器 -->
                    <div class="paper-detail hidden" id="detail-${{aidHtml}}"></div>
                </div>
            `;
        }}

        // Build and inject paper detail DOM on first expand
        function buildPaperDetail(arxivId) {{
            const container = document.getElementById(`detail-${{arxivId}}`);
            if (!container || container.getAttribute('data-built')) return;
            container.setAttribute('data-built', '1');

            const {{ paper, date }} = paperDataMap[arxivId];
            if (!paper) return;

            const aid = String(paper.arxiv_id ?? '');
            const aidHtml = escapeHtml(aid);
            const aidArg = escapeJsSingleQuotedAttr(aid);
            const aidPath = safePathSegment(aid);
            const isRead = readPapers.has(aid);

            // Register all markdown content
            registerMarkdown(`filter-reason-${{aid}}`, paper.filter_reason);
            registerMarkdown(`intro-logic-${{aid}}`, paper.intro_logic);
            registerMarkdown(`core-insight-${{aid}}`, paper.core_insight);
            registerMarkdown(`methodology-${{aid}}`, paper.methodology);
            registerMarkdown(`additional-insights-${{aid}}`, paper.additional_insights);
            registerMarkdown(`research-value-${{aid}}`, paper.research_value);
            if (hasMeaningfulText(paper.summary)) registerMarkdown(`summary-en-${{aid}}`, paper.summary);
            if (hasMeaningfulText(paper.summary_translation)) registerMarkdown(`summary-zh-${{aid}}`, paper.summary_translation);

            let html = '';
            const hasSummaryEn = hasMeaningfulText(paper.summary);
            const hasSummaryZh = hasMeaningfulText(paper.summary_translation);

            // 已读复选框
            html += `
                <div class="mb-3 sm:mb-4 mt-3">
                    <label class="inline-flex items-center">
                        <input type="checkbox" ${{isRead ? 'checked' : ''}} onchange="toggleRead('${{aidArg}}')" class="rounded border-gray-300 text-blue-600 shadow-sm focus:border-blue-300 focus:ring focus:ring-blue-200 focus:ring-opacity-50 w-4 h-4">
                        <span class="ml-2 text-xs sm:text-sm text-slate-600 dark:text-slate-400">已阅读</span>
                    </label>
                </div>
            `;

            // 原始摘要
            html += `
                <div class="mb-3 sm:mb-4">
                    <div class="collapsible-header open text-sm sm:text-base" onclick="toggleCollapsible(this)">原始摘要</div>
                    <div class="collapsible-content open">
                        <div class="inner">
                            <div class="summary-section bg-green-50/70 dark:bg-green-950/20 border-l-3 border-green-300 p-3 sm:p-4 rounded-r-lg">
                                ${{hasSummaryEn ? `
                                <div class="english-summary text-xs sm:text-sm text-black dark:text-white leading-relaxed markdown-content break-words" id="summary-en-${{aidHtml}}" style="display: block;">
                                </div>` : ''}}
                                ${{hasSummaryZh ? `
                                <div class="chinese-summary text-xs sm:text-sm text-black dark:text-white leading-relaxed markdown-content break-words" id="summary-zh-${{aidHtml}}" style="display: ${{hasSummaryEn ? 'none' : 'block'}};">
                                </div>` : ''}}
                                ${{!hasSummaryEn && !hasSummaryZh ? `
                                <div class="text-xs sm:text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
                                    暂无原始摘要。上游抓取或解析可能失败。
                                </div>` : ''}}
                            </div>
                        </div>
                    </div>
                </div>
            `;

            // 各分析section的配置
            const sections = [
                {{ key: 'intro_logic', id: `intro-logic-${{aid}}`, title: 'Introduction 逻辑链', color: 'yellow' }},
                {{ key: 'core_insight', id: `core-insight-${{aid}}`, title: '核心切入点 / Pain Point', color: 'orange' }},
                {{ key: 'methodology', id: `methodology-${{aid}}`, title: '方法论解读', color: 'purple' }},
                {{ key: 'additional_insights', id: `additional-insights-${{aid}}`, title: '延伸洞察', color: 'red' }},
                {{ key: 'research_value', id: `research-value-${{aid}}`, title: paper.research_value_source === 'reviewgrounder' ? 'ReviewGrounder 审稿' : '研究价值', color: 'teal' }},
                {{ key: 'filter_reason', id: `filter-reason-${{aid}}`, title: '筛选原因', color: 'blue' }},
            ];

            let renderedSections = 0;
            sections.forEach(s => {{
                if (hasMeaningfulText(paper[s.key])) {{
                    renderedSections += 1;
                    html += `
                        <div class="mb-3 sm:mb-4">
                            <div class="collapsible-header text-sm sm:text-base" onclick="toggleCollapsible(this)">${{s.title}}</div>
                            <div class="collapsible-content">
                                <div class="inner">
                                    <div class="bg-${{s.color}}-50/70 dark:bg-${{s.color}}-950/20 border-l-3 border-${{s.color}}-300 p-3 sm:p-4 rounded-r-lg">
                                        <div class="text-xs sm:text-sm text-black dark:text-white leading-relaxed markdown-content break-words" id="${{escapeHtml(s.id)}}">
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                }}
            }});

            if (renderedSections === 0) {{
                html += `
                    <div class="mb-3 sm:mb-4">
                        <div class="bg-amber-50/80 dark:bg-amber-950/20 border-l-3 border-amber-300 p-3 sm:p-4 rounded-r-lg text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                            暂无扩展解析内容。通常是因为论文正文抓取失败、上游解析结果为空，或当天加载到了不完整的数据文件。
                        </div>
                    </div>
                `;
            }}

            // 论文链接
            html += `
                <div class="flex flex-wrap gap-2">
                    <a href="https://arxiv.org/abs/${{aidPath}}" target="_blank" rel="noopener noreferrer"
                       class="inline-flex items-center px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-md transition-colors whitespace-nowrap">
                        arXiv 原文
                    </a>
                    <a href="https://arxiv.org/pdf/${{aidPath}}.pdf" target="_blank" rel="noopener noreferrer"
                       class="inline-flex items-center px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-md transition-colors whitespace-nowrap">
                        PDF 下载
                    </a>
                    <a href="https://papers.cool/arxiv/${{aidPath}}" target="_blank" rel="noopener noreferrer"
                       class="inline-flex items-center px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors whitespace-nowrap">
                        Cool Paper
                    </a>
                </div>
            `;

            container.innerHTML = html;

            // Render the open summary section's markdown immediately
            container.querySelectorAll('.collapsible-content.open').forEach(c => lazyRenderMarkdown(c));

            // Apply summary language setting
            if (showChineseSummary) {{
                const ch = container.querySelector('.chinese-summary');
                const en = container.querySelector('.english-summary');
                if (ch) ch.style.display = 'block';
                if (en) en.style.display = 'none';
            }} else {{
                const ch = container.querySelector('.chinese-summary');
                const en = container.querySelector('.english-summary');
                if (ch) ch.style.display = 'none';
                if (en) en.style.display = 'block';
            }}
        }}

        // Toggle paper detail expansion
        function togglePaperDetail(arxivId) {{
            const container = document.getElementById(`detail-${{arxivId}}`);
            const hint = document.getElementById(`expand-hint-${{arxivId}}`);
            if (!container) return;

            const isHidden = container.classList.contains('hidden');
            if (isHidden) {{
                // First expand: build the DOM
                buildPaperDetail(arxivId);
                container.classList.remove('hidden');
                if (hint) {{
                    hint.querySelector('.expand-arrow').textContent = '▼';
                    hint.childNodes[hint.childNodes.length - 1].textContent = ' 点击标题收起';
                }}
            }} else {{
                container.classList.add('hidden');
                if (hint) {{
                    hint.querySelector('.expand-arrow').textContent = '▶';
                    hint.childNodes[hint.childNodes.length - 1].textContent = ' 点击标题展开详情';
                }}
            }}
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
            const dateArg = escapeJsSingleQuotedAttr(date);
            const filters = activeTagFilters[date] || new Set();
            const allActive = filters.size === 0;
            let html = '<div class="flex flex-wrap gap-1.5 mb-3">';
            html += `<button class="tag-btn ${{allActive ? 'active' : ''}}" onclick="toggleTagFilter('${{dateArg}}','All')">All</button>`;
            tags.forEach(tag => {{
                const isActive = filters.has(tag.name);
                const tagArg = escapeJsSingleQuotedAttr(tag.name);
                html += `<button class="tag-btn ${{isActive ? 'active' : ''}}" onclick="toggleTagFilter('${{dateArg}}','${{tagArg}}')">${{escapeHtml(tag.name)}} &times;${{escapeHtml(tag.count)}}</button>`;
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

            // Clear paper data map (rebuilt by createPaperHTML)
            Object.keys(paperDataMap).forEach(k => delete paperDataMap[k]);

            let html = '';
            let totalPapers = 0;

            for (const date in allPapers) {{
                const clusters = allPapers[date] || [];
                const {{ html: papersHTML, count: dateVisibleTotal }} = collectPapersForDate(clusters, date);
                const dateHtml = escapeHtml(date);

                totalPapers += dateVisibleTotal;

                html += `
                    <section class="mb-6 sm:mb-8" data-date-section="${{dateHtml}}">
                        <h2 class="text-base sm:text-lg font-medium text-slate-500 dark:text-slate-400 mb-3 sm:mb-4" data-date-heading="${{dateHtml}}">${{dateHtml}} (${{escapeHtml(dateVisibleTotal)}} 篇论文)</h2>
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

                if (dateVisibleTotal === 0) {{
                    html += `
                        <div class="bg-white dark:bg-slate-800/50 rounded-lg shadow-sm p-4 sm:p-5 lg:p-6">
                            <div class="text-sm sm:text-base text-slate-600 dark:text-slate-300 leading-relaxed">
                                今日数据已处理，但没有符合当前筛选条件的论文。
                            </div>
                        </div>
                    </section>
                    `;
                }} else {{
                    html += `
                        <div class="bg-white dark:bg-slate-800/50 rounded-lg shadow-sm p-3 sm:p-4 lg:p-6">
                            <ul class="space-y-3 sm:space-y-4">
                                ${{papersHTML}}
                            </ul>
                        </div>
                    </section>
                    `;
                }}
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
                const dateHtml = escapeHtml(date);
                const dateArg = escapeJsSingleQuotedAttr(date);

                html += `<div class="mb-1" data-toc-date="${{dateHtml}}">`;
                html += `<div class="toc-date${{dimClass}}" onclick="tocToggleDate(this, '${{dateArg}}')" data-toc-date-btn="${{dateHtml}}">`;
                html += `<span class="toc-date-arrow">▶</span>`;
                html += `<span>${{dateHtml}}</span>`;
                html += `<span class="text-xs text-slate-400 ml-auto">${{escapeHtml(countLabel)}}</span>`;
                html += `</div>`;
                html += `<div class="toc-papers" data-toc-papers="${{dateHtml}}">`;
                if (isLoaded) {{
                    papers.forEach(paper => {{
                        const title = paper.title.length > 50 ? paper.title.substring(0, 47) + '...' : paper.title;
                        const aidHtml = escapeHtml(paper.arxiv_id);
                        const aidArg = escapeJsSingleQuotedAttr(paper.arxiv_id);
                        html += `<div class="toc-paper" onclick="tocScrollToPaper('${{aidArg}}')" data-toc-paper="${{aidHtml}}" title="${{escapeHtml(paper.title)}}">${{escapeHtml(title)}}</div>`;
                    }});
                }} else {{
                    html += `<div class="toc-paper opacity-50" onclick="tocLoadAndScrollToDate('${{dateArg}}')">点击加载...</div>`;
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
                    const response = await fetch(`data/${{d}}.json?v=${{DATA_VERSION}}`);
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
            const papers = document.querySelector(`[data-toc-papers="${{cssEscape(date)}}"]`);
            if (papers) {{
                papers.classList.toggle('open');
                arrow.classList.toggle('open');
            }}
            // 同时滚动到对应日期
            tocScrollToDate(date);
        }}

        function tocScrollToPaper(arxivId) {{
            const el = document.querySelector(`[data-arxiv-id="${{cssEscape(arxivId)}}"]`);
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
            const section = document.querySelector(`[data-date-section="${{cssEscape(date)}}"]`);
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
                        const activeBtn = document.querySelector(`[data-toc-date-btn="${{cssEscape(currentDate)}}"]`);
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
</html>"""

    return html_template


def validate_required_date(require_date: str) -> None:
    """Ensure a requested date was generated and is ready for publication."""
    if not require_date:
        return

    date_file = Path(WEBPAGES_DIR) / "data" / f"{require_date}.json"
    if not date_file.exists():
        raise ValueError(f"{require_date} 没有可发布数据文件")

    with open(date_file, "r", encoding="utf-8") as handle:
        date_data = json.load(handle)

    ok, errors = validate_date_data_payload(date_data, expected_date=require_date)
    if not ok:
        raise ValueError(f"{require_date} 未通过发布质量检查: {'; '.join(errors[:5])}")


def validate_generated_webpages_for_publication() -> None:
    """Run the release validator before reporting successful page generation."""
    try:
        from scripts.validate_published_payloads import validate_webpages_data
    except Exception as exc:  # pragma: no cover - exercised via CLI environments
        raise RuntimeError(f"发布校验器不可用: {exc}") from exc

    errors = validate_webpages_data(Path(WEBPAGES_DIR))
    if errors:
        raise ValueError(f"生成网页未通过发布校验: {'; '.join(errors[:5])}")


def snapshot_file(path: Path) -> tuple[bool, bytes]:
    """Capture a file before replacement so failed generation can roll back."""
    if not path.exists():
        return False, b""
    return True, path.read_bytes()


def restore_file_snapshot(path: Path, snapshot: tuple[bool, bytes]) -> None:
    """Restore or remove a generated file after a failed publish validation."""
    existed, content = snapshot
    if not existed:
        if path.exists():
            path.unlink()
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{path.name}.rollback.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def snapshot_directory(path: Path) -> tuple[bool, Dict[str, bytes]]:
    """Capture all files below a directory before generation mutates them."""
    if not path.exists():
        return False, {}
    if not path.is_dir():
        return False, {}

    files: Dict[str, bytes] = {}
    for file_path in sorted(path.rglob("*")):
        if file_path.is_file():
            files[str(file_path.relative_to(path))] = file_path.read_bytes()
    return True, files


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{path.name}.rollback.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def restore_directory_snapshot(
    path: Path, snapshot: tuple[bool, Dict[str, bytes]]
) -> None:
    """Restore or remove a generated data directory after failed validation."""
    existed, files = snapshot
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

    if not existed:
        return

    path.mkdir(parents=True, exist_ok=True)
    for relative_path, content in files.items():
        _atomic_write_bytes(path / relative_path, content)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="生成统一 PaperTools 网页")
    parser.add_argument(
        "--require-date",
        default="",
        help="要求指定日期必须生成完整、可发布的数据，否则返回非零退出码",
    )
    args = parser.parse_args()
    webpages_dir = Path(WEBPAGES_DIR)
    output_path = webpages_dir / "index.html"
    output_snapshot = snapshot_file(output_path)
    data_dir = webpages_dir / "data"
    data_snapshot = snapshot_directory(data_dir)

    try:
        replace_dates = {args.require_date} if args.require_date else set()
        html_content = generate_complete_html(replace_dates=replace_dates)

        # 确保webpages目录存在
        webpages_dir.mkdir(exist_ok=True)

        # 写入输出文件到webpages目录
        if not save_text(str(output_path), html_content):
            raise IOError(f"写入统一HTML页面失败: {output_path}")

        validate_required_date(args.require_date)
        validate_generated_webpages_for_publication()

        print(f"成功生成统一HTML页面: {output_path}")

    except Exception as e:
        try:
            restore_directory_snapshot(data_dir, data_snapshot)
        except Exception as restore_error:
            print(f"恢复旧网页数据时出错: {restore_error}")
        try:
            restore_file_snapshot(output_path, output_snapshot)
        except Exception as restore_error:
            print(f"恢复旧HTML页面时出错: {restore_error}")
        print(f"生成HTML页面时出错: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
