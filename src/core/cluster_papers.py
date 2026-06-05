#!/usr/bin/env python3
"""
LLM-driven paper clustering module.
Groups filtered papers into research topic clusters using an LLM.
Runs after filter stage, before summarize stage.
"""

import json
import os
import re
import sys
import argparse
from typing import Any, Dict, List

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from openai import OpenAI

from src.utils.config import (
    CLUSTER_API_KEY,
    CLUSTER_BASE_URL,
    CLUSTER_MODEL,
    TEMPERATURE,
    DOMAIN_PAPER_DIR,
)
from src.utils.io import save_json
from src.utils.openai_client import create_openai_client
from src.utils.retry import retry_with_backoff

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_SIZE = 60  # Maximum papers per clustering request
CLUSTER_MODEL_CHAIN_ENV = (
    os.getenv("PAPERTOOLS_CLUSTER_MODEL_CHAIN")
    or os.getenv("CLUSTER_MODEL_CHAIN")
    or ""
)
_DISABLED_CLUSTER_MODELS = set()

CLUSTER_PROMPT = """You are an expert researcher helping to organise a set of academic papers into meaningful research clusters.

Below is a list of papers (index, title, and a short abstract excerpt). Your task is to:
1. Identify 3 to 8 natural research clusters that best describe the topics covered.
2. Assign every paper to exactly one cluster.
3. Choose short, descriptive cluster names (e.g. "Multi-Agent Collaboration", "Tool Use & Planning", "Self-Evolving Agents").

Return ONLY a valid JSON object in this exact format (no markdown fences, no extra text):
{{
  "clusters": [
    {{"name": "Cluster Name", "paper_indices": [0, 2, 5]}},
    ...
  ]
}}

Papers:
{papers_text}
"""

MERGE_PROMPT = """You are an expert researcher. The following cluster names come from separately processed batches of papers and may contain duplicates or semantically similar groups.

Merge semantically similar cluster names into a single canonical name so that there are at most 8 distinct clusters in total. Keep names concise and descriptive.

Return ONLY a valid JSON object mapping each original name to its canonical merged name (no markdown fences, no extra text):
{{
  "mapping": {{
    "Original Name A": "Canonical Name",
    "Original Name B": "Canonical Name",
    ...
  }}
}}

Cluster names to merge:
{names_text}
"""


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------


def split_csv(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def is_openrouter_base_url(base_url: str) -> bool:
    return "openrouter.ai" in (base_url or "").lower()


def normalize_cluster_model(model: str, base_url: str = "") -> str:
    """Translate stale local aliases to model ids accepted by the active router."""
    model = (model or "").strip()
    if not model:
        return model

    key = model.lower().replace("（", "(").replace("）", ")").replace("_", "-").strip()
    key = " ".join(key.split())

    if is_openrouter_base_url(base_url):
        aliases = {
            "qwen": "qwen/qwen3-30b-a3b",
            "qwen3-30b-a3b": "qwen/qwen3-30b-a3b",
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
        return aliases.get(key, model)

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
    return aliases.get(key, model)


def build_cluster_model_chain(primary_model: str, base_url: str = "") -> List[str]:
    """Build a de-duplicated clustering model fallback chain."""
    configured = split_csv(CLUSTER_MODEL_CHAIN_ENV)
    raw_models = [primary_model]
    if configured:
        raw_models.extend(configured)
    elif is_openrouter_base_url(base_url):
        raw_models.extend(
            [
                "qwen/qwen3-30b-a3b",
                "deepseek/deepseek-chat-v3-0324",
            ]
        )
    else:
        raw_models.extend(
            [
                "qwen",
                "deepseek-chat",
                "minimax",
            ]
        )

    chain = []
    seen = set()
    for raw_model in raw_models:
        model = normalize_cluster_model(raw_model, base_url)
        if not model or model in seen:
            continue
        seen.add(model)
        chain.append(model)
    return chain


def coerce_cluster_model_chain(models: Any) -> List[str]:
    if isinstance(models, (list, tuple)):
        raw_models = [str(model) for model in models]
    else:
        raw_models = [str(models)]

    chain = []
    seen = set()
    for raw_model in raw_models:
        model = raw_model.strip()
        if model and model not in seen:
            seen.add(model)
            chain.append(model)
    return chain


def is_invalid_cluster_model_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "invalid model",
            "invalid model name",
            "not a valid model id",
            "model not found",
            "does not exist",
        )
    )


@retry_with_backoff(max_retries=3)
def call_llm_for_clustering(
    client: OpenAI, model: str, prompt: str, temperature: float
) -> str:
    """Call the LLM and return the full response text. Decorated with retry."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise academic research assistant. "
                    "Always respond with valid JSON only, no markdown fences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        stream=True,
    )
    text = ""
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            text += chunk.choices[0].delta.content
    return text.strip()


def call_llm_for_clustering_with_fallback(
    client: OpenAI, models: Any, prompt: str, temperature: float
) -> str:
    """Call clustering LLM, disabling invalid model ids after the first provider error."""
    last_exception = None
    attempted = []
    for model in coerce_cluster_model_chain(models):
        if model in _DISABLED_CLUSTER_MODELS:
            continue
        attempted.append(model)
        try:
            return call_llm_for_clustering(client, model, prompt, temperature)
        except Exception as exc:
            last_exception = exc
            if is_invalid_cluster_model_error(exc):
                _DISABLED_CLUSTER_MODELS.add(model)
                print(f"⚠️ 聚类模型不可用，跳过: {model}: {str(exc)[:240]}")
                continue
            raise

    if last_exception:
        raise last_exception
    raise RuntimeError(
        f"没有可用的聚类模型，已尝试: {', '.join(attempted) or '<none>'}"
    )


def parse_json_response(text: str) -> dict:
    """Extract and parse a JSON object from an LLM response.

    Handles optional markdown code fences (```json ... ```) and leading/trailing
    whitespace.
    """
    # Strip markdown fences if present
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        text = fence_match.group(1).strip()

    # Find the first '{' and last '}' to isolate the JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response: {text[:200]}")

    return json.loads(text[start : end + 1])


# ---------------------------------------------------------------------------
# Core clustering logic
# ---------------------------------------------------------------------------


def _build_papers_text(papers: list, offset: int = 0) -> str:
    """Build a compact text representation of papers for the prompt."""
    lines = []
    for i, paper in enumerate(papers):
        title = paper.get("title", "").strip()
        abstract = paper.get("summary", "") or paper.get("abstract", "") or ""
        abstract_snippet = abstract[:300].replace("\n", " ")
        lines.append(f"[{offset + i}] {title} — {abstract_snippet}")
    return "\n".join(lines)


def _validate_cluster_assignments(
    assignments: Dict[str, List[int]],
    paper_count: int,
) -> None:
    """Require the LLM clustering response to assign every paper exactly once."""
    if paper_count == 0:
        return
    if not assignments:
        raise ValueError("clustering output did not contain any clusters")

    errors: List[str] = []
    seen: Dict[int, str] = {}

    for cluster_name, indices in assignments.items():
        if not isinstance(cluster_name, str) or not cluster_name.strip():
            errors.append("cluster name must be non-empty text")
        if not isinstance(indices, list):
            errors.append(f"cluster {cluster_name!r} paper_indices must be a list")
            continue
        if not indices:
            errors.append(f"cluster {cluster_name!r} has no paper indices")
            continue

        for raw_index in indices:
            if isinstance(raw_index, bool) or not isinstance(raw_index, int):
                errors.append(
                    f"cluster {cluster_name!r} has non-integer paper index {raw_index!r}"
                )
                continue
            if raw_index < 0 or raw_index >= paper_count:
                errors.append(
                    f"cluster {cluster_name!r} has out-of-range paper index {raw_index}"
                )
                continue
            if raw_index in seen:
                # Paper assigned to multiple clusters - use first assignment
                continue
            seen[raw_index] = cluster_name

    missing = sorted(set(range(paper_count)) - set(seen))
    if missing:
        # Assign missing papers to a default cluster instead of failing
        default_cluster = "Other"
        if default_cluster not in result:
            result[default_cluster] = []
        result[default_cluster].extend(missing)
        print(f"⚠️ {len(missing)} papers missing cluster assignments, assigned to '{default_cluster}'")


def cluster_batch(
    client: OpenAI, model: Any, papers: list, temperature: float
) -> Dict[str, List[int]]:
    """Cluster one batch of papers. Returns a dict mapping cluster name -> list of indices."""
    papers_text = _build_papers_text(papers)
    prompt = CLUSTER_PROMPT.format(papers_text=papers_text)

    try:
        raw = call_llm_for_clustering_with_fallback(client, model, prompt, temperature)
        data = parse_json_response(raw)
        result: Dict[str, List[int]] = {}
        clusters = data.get("clusters")
        if not isinstance(clusters, list):
            raise ValueError("clustering output must contain a clusters list")
        for cluster_index, cluster in enumerate(clusters, 1):
            if not isinstance(cluster, dict):
                raise ValueError(f"cluster#{cluster_index} must be an object")
            name = cluster.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"cluster#{cluster_index} name must be non-empty text")
            indices = cluster.get("paper_indices")
            if not isinstance(indices, list):
                raise ValueError(
                    f"cluster#{cluster_index} paper_indices must be a list"
                )
            name = name.strip()
            result[name] = result.get(name, []) + indices
        _validate_cluster_assignments(result, len(papers))
        return result
    except Exception as exc:
        raise RuntimeError(f"clustering batch failed: {exc}") from exc


def merge_cluster_names(
    client: OpenAI, model: Any, cluster_names: List[str], temperature: float
) -> Dict[str, str]:
    """Ask the LLM to merge semantically similar cluster names.

    Returns a mapping from original name -> canonical name.
    If <= 8 unique names, returns identity mapping (no merge needed).
    """
    unique_names = list(dict.fromkeys(cluster_names))  # preserve order, deduplicate
    if len(unique_names) <= 8:
        return {n: n for n in unique_names}

    names_text = "\n".join(f"- {n}" for n in unique_names)
    prompt = MERGE_PROMPT.format(names_text=names_text)

    try:
        raw = call_llm_for_clustering_with_fallback(client, model, prompt, temperature)
        data = parse_json_response(raw)
        mapping = data.get("mapping", {})
        # Ensure every known name is covered (fall back to original if missing)
        return {n: mapping.get(n, n) for n in unique_names}
    except Exception as exc:
        raise RuntimeError(f"cluster merge failed: {exc}") from exc


def cluster_papers(
    papers: list,
    client: OpenAI,
    model: Any,
    temperature: float,
) -> list:
    """Main clustering function.

    Adds ``cluster`` and ``tags`` fields to each paper dict (in-place copy).
    Returns the enriched list.
    """
    enriched = [dict(p) for p in papers]  # shallow copy each paper

    # Add tags field: sorted unique arXiv categories from 'category' and 'subjects'
    for paper in enriched:
        cats: set = set()
        cat = paper.get("category", "")
        if cat:
            cats.add(cat.strip())
        subjects = paper.get("subjects", "") or ""
        # subjects may be a comma/semicolon-separated string like "cs.AI; cs.LG"
        for part in re.split(r"[,;]", subjects):
            part = part.strip()
            # Keep only arXiv category codes (e.g. cs.AI, cs.LG, stat.ML)
            if re.match(r"^[a-z\-]+\.[A-Z]{2,}$", part):
                cats.add(part)
        paper["tags"] = sorted(cats)

    # Default cluster assignment
    for paper in enriched:
        paper["cluster"] = "Other"

    if not enriched:
        return enriched

    # Split into batches of BATCH_SIZE
    batches = [
        enriched[i : i + BATCH_SIZE] for i in range(0, len(enriched), BATCH_SIZE)
    ]

    # cluster_name -> list of global indices
    global_clusters: Dict[str, List[int]] = {}
    offset = 0

    for batch in batches:
        batch_result = cluster_batch(client, model, batch, temperature)
        for name, local_indices in batch_result.items():
            global_indices = [offset + idx for idx in local_indices if idx < len(batch)]
            if name not in global_clusters:
                global_clusters[name] = []
            global_clusters[name].extend(global_indices)
        offset += len(batch)

    # Merge cluster names if there are too many unique ones (from multiple batches)
    if len(batches) > 1:
        all_names = list(global_clusters.keys())
        name_mapping = merge_cluster_names(client, model, all_names, temperature)
        merged: Dict[str, List[int]] = {}
        for old_name, indices in global_clusters.items():
            canonical = name_mapping.get(old_name, old_name)
            merged.setdefault(canonical, [])
            merged[canonical].extend(indices)
        global_clusters = merged

    # Assign cluster field to each paper
    for cluster_name, indices in global_clusters.items():
        for idx in indices:
            if 0 <= idx < len(enriched):
                enriched[idx]["cluster"] = cluster_name

    return enriched


def save_clustered_papers_output(output_filepath: str, clustered: List[dict]) -> None:
    """Atomically save clustered papers or raise so the stage fails closed."""
    if not save_json(output_filepath, clustered, indent=4, ensure_ascii=False):
        raise IOError(f"failed to save clustered papers: {output_filepath}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Cluster filtered papers into research topic groups using an LLM."
    )
    parser.add_argument(
        "--input-file", required=True, help="Path to filtered_papers_DATE.json"
    )
    parser.add_argument(
        "--output-dir",
        default=DOMAIN_PAPER_DIR,
        help=f"Output directory (default: {DOMAIN_PAPER_DIR})",
    )
    parser.add_argument("--api-key", default=CLUSTER_API_KEY, help="API key")
    parser.add_argument("--base-url", default=CLUSTER_BASE_URL, help="API base URL")
    parser.add_argument("--model", default=CLUSTER_MODEL, help="Model to use")
    parser.add_argument(
        "--temperature", type=float, default=TEMPERATURE, help="Sampling temperature"
    )
    args = parser.parse_args()

    # Validate input file
    if not os.path.exists(args.input_file):
        print(f"Error: input file not found: {args.input_file}")
        sys.exit(1)

    # Extract DATE from filename  e.g. filtered_papers_2026-03-28.json -> 2026-03-28
    input_basename = os.path.basename(args.input_file)
    match = re.search(r"filtered_papers_(.+?)\.json$", input_basename)
    if match:
        date_part = match.group(1)
    else:
        # Fallback: use last underscore-separated segment before .json
        date_part = input_basename.rsplit("_", 1)[-1].replace(".json", "")

    output_filename = f"clustered_papers_{date_part}.json"
    os.makedirs(args.output_dir, exist_ok=True)
    output_filepath = os.path.join(args.output_dir, output_filename)

    # Load papers
    try:
        with open(args.input_file, "r", encoding="utf-8") as f:
            papers = json.load(f)
        print(f"Loaded {len(papers)} papers from {args.input_file}")
    except Exception as exc:
        print(f"Error reading input file: {exc}")
        sys.exit(1)

    if not papers:
        print("No papers to cluster.")
        sys.exit(0)

    # Initialise OpenAI client
    client = create_openai_client(
        api_key=args.api_key,
        base_url=args.base_url,
        timeout=180.0,
    )

    model_chain = build_cluster_model_chain(args.model, args.base_url)
    if not model_chain:
        print("Error: no clustering model configured")
        sys.exit(1)

    print(
        f"Clustering {len(papers)} papers using model chain: {', '.join(model_chain)}"
    )
    print(
        f"Batch size: {BATCH_SIZE}, batches: {(len(papers) + BATCH_SIZE - 1) // BATCH_SIZE}"
    )

    clustered = cluster_papers(papers, client, model_chain, args.temperature)

    # Show cluster summary
    from collections import Counter

    cluster_counts = Counter(p["cluster"] for p in clustered)
    print("\nCluster summary:")
    for name, count in sorted(cluster_counts.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count} papers")

    # Save output
    try:
        save_clustered_papers_output(output_filepath, clustered)
        print(f"\nClustered papers saved to: {output_filepath}")
    except Exception as exc:
        print(f"Error saving output file: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
