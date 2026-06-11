#!/usr/bin/env python3
"""批量提取所有日期论文的 affiliations（跳过已有的），高并发。"""

import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.generate_summary import (  # noqa: E402
    build_summary_providers,
    extract_affiliations,
)
from src.utils.cache_manager import CacheManager  # noqa: E402
from src.utils.config import (  # noqa: E402
    ENABLE_CACHE,
    SUMMARY_API_KEY,
    SUMMARY_BASE_URL,
    SUMMARY_MODEL_CHAIN,
    SUMMARY_PRISM_API_KEY,
    SUMMARY_PRISM_BASE_URL,
    SUMMARY_PRISM_REASONING_EFFORT,
    SUMMARY_PRISM_RPM,
    SUMMARY_SJTU_API_KEY,
    SUMMARY_SJTU_BASE_URL,
    TEMPERATURE,
)
from src.utils.io import load_json, save_json  # noqa: E402

MAX_WORKERS = 30
SUMMARY_FILE_GLOB = os.getenv(
    "PAPERTOOLS_AFFILIATION_SUMMARY_GLOB",
    "summary/clustered_papers_*_with_summary2.json",
)


def needs_affiliations(paper):
    affiliations = paper.get("affiliations", "")
    return not affiliations or "institutions" not in affiliations


def load_summary_papers(summary_file):
    papers = load_json(summary_file, default=None)
    if not isinstance(papers, list):
        raise ValueError(f"invalid summary payload, expected list: {summary_file}")
    return papers


def save_summary_papers(summary_file, papers):
    if not save_json(summary_file, papers, ensure_ascii=False, indent=2):
        raise OSError(f"failed to save summary payload: {summary_file}")


def write_affiliation_results(results):
    updated_files = {summary_file for summary_file, _idx in results}

    for summary_file in sorted(updated_files):
        papers = load_summary_papers(summary_file)
        changed = False
        for (file_path, idx), affiliations in results.items():
            if file_path != summary_file:
                continue
            if idx >= len(papers):
                raise IndexError(f"paper index {idx} out of range for {summary_file}")
            papers[idx]["affiliations"] = affiliations
            changed = True
        if changed:
            save_summary_papers(summary_file, papers)
            date = os.path.basename(summary_file).split("_")[2]
            print(f"💾 已更新: {summary_file} ({date})")

    return updated_files


def build_affiliation_providers():
    return build_summary_providers(
        SUMMARY_MODEL_CHAIN,
        SUMMARY_API_KEY,
        SUMMARY_BASE_URL,
        SUMMARY_SJTU_API_KEY,
        SUMMARY_SJTU_BASE_URL,
        SUMMARY_PRISM_API_KEY,
        SUMMARY_PRISM_BASE_URL,
        SUMMARY_PRISM_RPM,
        SUMMARY_PRISM_REASONING_EFFORT,
    )


def process_one(paper, paper_content, providers, cache_manager):
    title = paper.get("title", "")
    authors = paper.get("authors", "")
    try:
        result = extract_affiliations(
            paper_content,
            authors,
            providers,
            TEMPERATURE,
            paper_title=title,
            cache_manager=cache_manager,
        )
        return title, result
    except Exception as e:
        return title, f"ERROR: {e}"


def main() -> int:
    cache_manager = CacheManager("cache")

    # Collect all papers that need affiliations
    summary_files = sorted(glob.glob(SUMMARY_FILE_GLOB))

    tasks = []  # (summary_file, paper_index, paper, paper_content)

    for sf in summary_files:
        papers = load_summary_papers(sf)
        for i, paper in enumerate(papers):
            if not needs_affiliations(paper):
                continue
            # Get cached paper content
            link = paper.get("link", "")
            if cache_manager and ENABLE_CACHE:
                paper_cache = cache_manager.get_paper_cache(link)
                if paper_cache and paper_cache.get("data", {}).get("content"):
                    tasks.append((sf, i, paper, paper_cache["data"]["content"]))
                else:
                    print(f"⚠️ No cached content for: {paper.get('title', '')[:50]}")

    print(f"📋 需要处理 {len(tasks)} 篇论文的 affiliations")
    if not tasks:
        print("✅ 全部已有 affiliations，无需处理")
        return 0

    providers = build_affiliation_providers()
    if not providers:
        print("❌ 无可用总结 provider，无法提取 affiliations")
        return 1

    # Process in parallel
    results = {}  # (file, index) -> affiliation_str
    errors = []
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {}
        for sf, idx, paper, content in tasks:
            fut = executor.submit(process_one, paper, content, providers, cache_manager)
            future_map[fut] = (sf, idx)

        for fut in as_completed(future_map):
            sf, idx = future_map[fut]
            title, result = fut.result()
            done += 1
            if not isinstance(result, str) or result.startswith("ERROR"):
                errors.append((sf, idx, title, result))
                print(f"❌ [{done}/{len(tasks)}] {title[:40]}: {result}")
            else:
                results[(sf, idx)] = result
                print(f"✅ [{done}/{len(tasks)}] {title[:50]}")

    if errors:
        print(f"❌ affiliations 提取失败 {len(errors)} 篇，停止写回，避免部分更新")
        return 1

    try:
        write_affiliation_results(results)
    except (OSError, ValueError, IndexError) as e:
        print(f"❌ 写回 affiliations 失败: {e}")
        return 1

    print(f"\n🎉 完成！处理了 {len(results)} 篇论文")
    return 0


if __name__ == "__main__":
    sys.exit(main())
