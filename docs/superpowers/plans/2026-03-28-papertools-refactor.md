# PaperTools Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor PaperTools to add LLM-driven paper clustering, API retry/fault tolerance with webhook notifications, a new clustered two-level UI with tag filtering, and a simplified README.

**Architecture:** Incremental changes on existing modular architecture. New `cluster_papers.py` stage inserted between filter and summarize. New `retry.py` and `notify.py` utilities. Frontend HTML regenerated with cluster-aware two-level collapsible layout + tag filter bar. Pipeline updated to wire everything together.

**Tech Stack:** Python 3.9+, OpenAI SDK, requests, BeautifulSoup, Tailwind CSS, Marked.js

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/utils/retry.py` | Generic retry decorator with exponential backoff |
| Create | `src/utils/notify.py` | Generic webhook notification utility |
| Create | `src/core/cluster_papers.py` | LLM-driven paper clustering stage |
| Modify | `src/utils/config.py` | Add WEBHOOK_URL config |
| Modify | `src/core/pipeline.py` | Insert cluster stage, wire retry/notify |
| Modify | `src/core/paper_filter.py` | Use retry, skip on failure |
| Modify | `src/core/crawl_arxiv.py` | Use retry |
| Modify | `src/core/generate_summary.py` | Use retry, skip on failure |
| Modify | `src/core/generate_unified_index.py` | Complete rewrite of HTML generation for cluster UI |
| Modify | `.env` | Update model + add webhook URL |
| Modify | `.env.example` | Add WEBHOOK_URL field |
| Rewrite | `README.md` | Minimal 5-minute quick start |
| Create | `docs/configuration.md` | Full configuration reference |
| Create | `docs/pipeline.md` | Pipeline stages explained |
| Create | `docs/deployment.md` | GitHub Pages + crontab setup |

---

### Task 1: Create `src/utils/retry.py` — Generic Retry Decorator

**Files:**
- Create: `src/utils/retry.py`

- [ ] **Step 1: Write retry.py**

```python
"""Generic retry utility with exponential backoff."""

import time
import logging
from functools import wraps
from typing import Tuple, Type

import requests
from openai import OpenAIError

logger = logging.getLogger(__name__)

# Default retryable exception types
RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError,
    ConnectionError,
    TimeoutError,
)

# Status codes worth retrying
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 524}

# Error substrings that indicate retryable OpenAI errors
RETRYABLE_ERROR_STRINGS = (
    'Connection error', 'timeout', 'Too Many Requests',
    'Rate limit', 'Service Unavailable', '503', '502', '500', '524',
)


def is_retryable(exc: Exception) -> bool:
    """Determine if an exception is retryable."""
    if isinstance(exc, requests.exceptions.HTTPError):
        if hasattr(exc, 'response') and exc.response is not None:
            return exc.response.status_code in RETRYABLE_STATUS_CODES
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True
    if isinstance(exc, OpenAIError):
        return any(s in str(exc) for s in RETRYABLE_ERROR_STRINGS)
    return False


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 2.0,
    multiplier: float = 2.0,
    max_delay: float = 60.0,
):
    """Decorator that retries a function with exponential backoff.

    Only retries on network/server errors. Auth errors (4xx except 429)
    are raised immediately.

    Args:
        max_retries: Maximum number of retry attempts.
        initial_delay: Initial delay in seconds before first retry.
        multiplier: Multiply delay by this factor after each retry.
        max_delay: Cap on the delay between retries.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc

                    if attempt == max_retries or not is_retryable(exc):
                        raise

                    logger.warning(
                        "Retry %d/%d for %s after error: %s — waiting %.1fs",
                        attempt + 1, max_retries, func.__name__, exc, delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * multiplier, max_delay)

            raise last_exception  # should not reach here

        return wrapper
    return decorator
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `cd /data/users/weikaihuang/projects/PaperTools && python -c "from src.utils.retry import retry_with_backoff; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/utils/retry.py
git commit -m "feat: add generic retry utility with exponential backoff"
```

---

### Task 2: Create `src/utils/notify.py` — Webhook Notification

**Files:**
- Create: `src/utils/notify.py`
- Modify: `src/utils/config.py`
- Modify: `.env`
- Modify: `.env.example`

- [ ] **Step 1: Add WEBHOOK_URL to config.py**

In `src/utils/config.py`, after the line `MODEL = os.getenv("MODEL")`, add:

```python
# Webhook notification (optional)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
```

- [ ] **Step 2: Write notify.py**

```python
"""Generic webhook notification utility.

Sends POST requests with {"text": "..."} payload.
Compatible with Pumble, Slack, Feishu, Discord webhooks, etc.
"""

import logging
import requests
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from src.utils.config import WEBHOOK_URL
except ImportError:
    WEBHOOK_URL = ""


def send_notification(message: str, webhook_url: Optional[str] = None) -> bool:
    """Send a text notification via webhook.

    Args:
        message: The text message to send.
        webhook_url: Override webhook URL. Falls back to config WEBHOOK_URL.

    Returns:
        True if sent successfully, False otherwise.
    """
    url = webhook_url or WEBHOOK_URL
    if not url:
        return False

    try:
        resp = requests.post(url, json={"text": message}, timeout=10)
        resp.raise_for_status()
        logger.info("Webhook notification sent successfully")
        return True
    except Exception as exc:
        logger.warning("Failed to send webhook notification: %s", exc)
        return False


def notify_failures(stage: str, failures: List[str], webhook_url: Optional[str] = None) -> bool:
    """Send a batched failure notification for a pipeline stage.

    Args:
        stage: Pipeline stage name (e.g. "filter", "summarize").
        failures: List of failure description strings.
        webhook_url: Override webhook URL.

    Returns:
        True if sent successfully.
    """
    if not failures:
        return False

    header = f"⚠️ PaperTools [{stage}] — {len(failures)} failures"
    # Show up to 10 failures, truncate the rest
    details = "\n".join(f"  • {f}" for f in failures[:10])
    if len(failures) > 10:
        details += f"\n  ... and {len(failures) - 10} more"

    message = f"{header}\n{details}"
    return send_notification(message, webhook_url)


def notify_pipeline_complete(
    stats: dict,
    webhook_url: Optional[str] = None,
) -> bool:
    """Send a pipeline completion summary.

    Args:
        stats: Dict with keys like crawled, filtered, clustered, summarized, failures.
        webhook_url: Override webhook URL.

    Returns:
        True if sent successfully.
    """
    lines = ["✅ PaperTools pipeline complete"]
    for key, value in stats.items():
        lines.append(f"  • {key}: {value}")
    return send_notification("\n".join(lines), webhook_url)
```

- [ ] **Step 3: Update .env with model config and webhook**

Replace entire `.env` content with:
```
# API Configuration
OPENAI_API_KEY=sk-REPLACE_WITH_YOUR_KEY
OPENAI_BASE_URL=https://models.sjtu.edu.cn/api/v1/
MODEL=minimax-m2.5

# Webhook notification (optional)
WEBHOOK_URL=https://api.pumble.com/workspaces/<workspace-id>/incomingWebhooks/postMessage/<webhook-token>
```

- [ ] **Step 4: Update .env.example**

Replace entire `.env.example` content with:
```
# API Configuration (required)
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://your-api-url/v1/
MODEL=your_model_name

# Webhook notification (optional) — Pumble, Slack, Feishu, Discord etc.
WEBHOOK_URL=

# Optional: Jina API Token (for full paper content retrieval)
# JINA_API_TOKEN=your_jina_token_here
```

- [ ] **Step 5: Verify imports**

Run: `cd /data/users/weikaihuang/projects/PaperTools && python -c "from src.utils.notify import send_notification, notify_failures, notify_pipeline_complete; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/utils/notify.py src/utils/config.py .env.example
git commit -m "feat: add webhook notification utility and WEBHOOK_URL config"
```

Note: Do NOT `git add .env` — it contains secrets and should stay in `.gitignore`.

---

### Task 3: Create `src/core/cluster_papers.py` — LLM-Driven Clustering

**Files:**
- Create: `src/core/cluster_papers.py`

- [ ] **Step 1: Write cluster_papers.py**

```python
#!/usr/bin/env python3
"""
LLM-driven paper clustering.
Groups filtered papers into research clusters using an LLM.
"""

import json
import os
import sys
import argparse
import time
from typing import List, Dict, Optional

from openai import OpenAI

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.config import API_KEY, BASE_URL, MODEL, TEMPERATURE, DOMAIN_PAPER_DIR
from src.utils.retry import retry_with_backoff
from src.utils.notify import notify_failures

# Maximum number of papers to send in a single clustering request
# Adjust based on model context window
BATCH_SIZE = 60


CLUSTER_PROMPT = """你是一位学术论文分类专家。请根据以下论文列表，将它们分成若干研究聚类（cluster）。

要求：
1. 根据论文的研究主题和方法，识别出自然的研究聚类（通常3-8个）
2. 每个聚类起一个简洁、具有概括性的英文名称（如 "Multi-Agent Collaboration", "Tool Use & API Integration", "Self-Evolving Agents" 等）
3. 每篇论文只归入一个最相关的聚类
4. 如果某篇论文不太符合任何聚类，归入 "Other"

论文列表：
{papers_list}

请严格按以下JSON格式输出（不要输出其他内容）：
{{
  "clusters": [
    {{
      "name": "聚类名称",
      "paper_indices": [0, 1, 3]
    }},
    ...
  ]
}}

其中 paper_indices 是论文在列表中的编号（从0开始）。确保所有论文都被分配到某个聚类中。"""


MERGE_PROMPT = """你是一位学术论文分类专家。以下是多个批次的论文聚类结果，请将语义相近的聚类名称统一合并。

聚类名称列表：
{cluster_names}

请输出合并映射（JSON格式，不要输出其他内容）：
{{
  "mapping": {{
    "原名称1": "统一名称",
    "原名称2": "统一名称",
    ...
  }}
}}

规则：
1. 语义相同或非常接近的聚类合并为同一个名称
2. 选择最具概括性和通用性的名称作为统一名称
3. 如果某个名称已经很好，mapping中原名和统一名相同即可
4. "Other" 类别保持不变"""


@retry_with_backoff(max_retries=3, initial_delay=2.0)
def call_llm_for_clustering(client: OpenAI, model: str, prompt: str, temperature: float) -> str:
    """Call LLM and collect streamed response."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一个学术论文分类专家，擅长将论文按研究主题进行聚类。请严格按要求的JSON格式输出。"},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        stream=True,
    )
    result = ""
    for chunk in response:
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                result += delta.content
    return result.strip()


def parse_json_response(text: str) -> dict:
    """Extract and parse JSON from LLM response, handling markdown code blocks."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        # Remove first line (```json or ```) and last line (```)
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


def cluster_batch(
    client: OpenAI,
    model: str,
    papers: List[Dict],
    temperature: float,
) -> Dict[str, List[int]]:
    """Cluster a single batch of papers. Returns {cluster_name: [paper_indices]}."""
    papers_list = ""
    for i, paper in enumerate(papers):
        title = paper.get("title", "").strip()
        summary = paper.get("summary", "") or paper.get("abstract", "")
        # Truncate summary to save tokens
        if len(summary) > 300:
            summary = summary[:300] + "..."
        papers_list += f"[{i}] {title}\n    {summary}\n\n"

    prompt = CLUSTER_PROMPT.format(papers_list=papers_list)
    response_text = call_llm_for_clustering(client, model, prompt, temperature)

    try:
        data = parse_json_response(response_text)
        clusters = {}
        for cluster in data.get("clusters", []):
            name = cluster.get("name", "Other")
            indices = cluster.get("paper_indices", [])
            clusters[name] = indices
        return clusters
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"⚠️ Failed to parse clustering response: {exc}")
        print(f"   Response: {response_text[:200]}...")
        # Fallback: all papers in "Other"
        return {"Other": list(range(len(papers)))}


def merge_cluster_names(
    client: OpenAI,
    model: str,
    cluster_names: List[str],
    temperature: float,
) -> Dict[str, str]:
    """Merge semantically similar cluster names across batches."""
    if len(cluster_names) <= 8:
        # No need to merge if few clusters
        return {name: name for name in cluster_names}

    prompt = MERGE_PROMPT.format(cluster_names=json.dumps(cluster_names, ensure_ascii=False))
    response_text = call_llm_for_clustering(client, model, prompt, temperature)

    try:
        data = parse_json_response(response_text)
        mapping = data.get("mapping", {})
        # Ensure all names are in the mapping
        for name in cluster_names:
            if name not in mapping:
                mapping[name] = name
        return mapping
    except (json.JSONDecodeError, KeyError):
        print("⚠️ Failed to parse merge response, keeping original names")
        return {name: name for name in cluster_names}


def cluster_papers(
    papers: List[Dict],
    client: OpenAI,
    model: str,
    temperature: float = 0.1,
) -> List[Dict]:
    """Main clustering function. Adds 'cluster' field to each paper.

    Args:
        papers: List of paper dicts from filter stage.
        client: OpenAI client.
        model: Model name.
        temperature: LLM temperature.

    Returns:
        Same papers list with 'cluster' field added to each paper.
    """
    if not papers:
        return papers

    print(f"🔬 Clustering {len(papers)} papers...")

    # Also preserve original arxiv categories as tags
    for paper in papers:
        category = paper.get("category", "")
        subjects = paper.get("subjects", "")
        tags = set()
        if category:
            tags.add(category)
        if subjects:
            for s in subjects.split(","):
                s = s.strip()
                if s:
                    tags.add(s)
        paper["tags"] = sorted(tags)

    # Split into batches if needed
    batches = []
    for i in range(0, len(papers), BATCH_SIZE):
        batches.append(papers[i:i + BATCH_SIZE])

    print(f"📦 Split into {len(batches)} batch(es)")

    # Cluster each batch
    all_cluster_assignments = []  # List of (batch_idx, cluster_name, global_paper_idx)
    all_cluster_names = set()

    for batch_idx, batch in enumerate(batches):
        print(f"  🔄 Processing batch {batch_idx + 1}/{len(batches)}...")
        global_offset = batch_idx * BATCH_SIZE

        clusters = cluster_batch(client, model, batch, temperature)

        for cluster_name, local_indices in clusters.items():
            all_cluster_names.add(cluster_name)
            for local_idx in local_indices:
                global_idx = global_offset + local_idx
                if global_idx < len(papers):
                    all_cluster_assignments.append((global_idx, cluster_name))

    # Merge cluster names if we had multiple batches
    name_mapping = {n: n for n in all_cluster_names}
    if len(batches) > 1 and len(all_cluster_names) > 8:
        print("  🔄 Merging cluster names across batches...")
        name_mapping = merge_cluster_names(
            client, model, sorted(all_cluster_names), temperature
        )

    # Assign clusters to papers
    assigned = set()
    for global_idx, cluster_name in all_cluster_assignments:
        unified_name = name_mapping.get(cluster_name, cluster_name)
        papers[global_idx]["cluster"] = unified_name
        assigned.add(global_idx)

    # Fallback: any unassigned paper gets "Other"
    for i in range(len(papers)):
        if i not in assigned:
            papers[i]["cluster"] = "Other"

    # Print summary
    cluster_counts = {}
    for paper in papers:
        c = paper.get("cluster", "Other")
        cluster_counts[c] = cluster_counts.get(c, 0) + 1

    print("📊 Clustering results:")
    for name, count in sorted(cluster_counts.items(), key=lambda x: -x[1]):
        print(f"    {name}: {count} papers")

    return papers


def main():
    """CLI entry point for standalone execution."""
    parser = argparse.ArgumentParser(description="LLM-driven paper clustering")
    parser.add_argument("--input-file", required=True, help="Input filtered papers JSON file")
    parser.add_argument("--output-dir", default=DOMAIN_PAPER_DIR, help="Output directory")
    parser.add_argument("--api-key", default=API_KEY, help="API key")
    parser.add_argument("--base-url", default=BASE_URL, help="API base URL")
    parser.add_argument("--model", default=MODEL, help="Model name")
    parser.add_argument("--temperature", type=float, default=TEMPERATURE, help="Temperature")

    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print(f"❌ Input file not found: {args.input_file}")
        return

    with open(args.input_file, "r", encoding="utf-8") as f:
        papers = json.load(f)

    print(f"📚 Loaded {len(papers)} papers from {args.input_file}")

    client = OpenAI(api_key=args.api_key, base_url=args.base_url, timeout=180.0)
    clustered = cluster_papers(papers, client, args.model, args.temperature)

    # Generate output filename
    input_basename = os.path.basename(args.input_file)
    name_without_ext = os.path.splitext(input_basename)[0]
    output_filename = f"clustered_{name_without_ext.replace('filtered_', '')}.json"
    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, output_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clustered, f, ensure_ascii=False, indent=2)

    print(f"💾 Saved clustered papers to: {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify imports**

Run: `cd /data/users/weikaihuang/projects/PaperTools && python -c "from src.core.cluster_papers import cluster_papers; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/core/cluster_papers.py
git commit -m "feat: add LLM-driven paper clustering stage"
```

---

### Task 4: Integrate Cluster Stage and Retry/Notify into Pipeline

**Files:**
- Modify: `src/core/pipeline.py`
- Modify: `src/core/paper_filter.py`

- [ ] **Step 1: Update pipeline.py — add cluster stage**

In `pipeline.py`, make the following changes:

1. Update imports at the top (after the existing imports from config):

```python
from src.utils.notify import notify_failures, notify_pipeline_complete
```

2. Update `ProgressTracker.__init__` to have 6 steps:

```python
def __init__(self, total_steps: int = 6):
    self.total_steps = total_steps
    self.current_step = 0
    self.step_names = [
        "爬取arXiv论文",
        "筛选相关论文",
        "论文聚类",
        "生成论文总结",
        "生成统一页面",
        "启动本地服务器"
    ]
    self.start_time = time.time()
```

3. Update `main()` argument parsing — add `'cluster'` to `stage_order` and `--start-from` choices:

```python
stage_order = ['crawl', 'filter', 'cluster', 'summary', 'unified', 'serve']
```

And update the `--start-from` choices:

```python
parser.add_argument('--start-from', choices=['crawl', 'filter', 'cluster', 'summary', 'unified', 'serve'], default=None,
                   help='从指定阶段开始执行，自动跳过之前的阶段')
```

Also add:
```python
parser.add_argument('--skip-cluster', action='store_true', help='跳过聚类步骤')
```

And update the skip logic for `--start-from`:

```python
if args.start_from:
    try:
        start_idx = stage_order.index(args.start_from)
        if start_idx > 0:
            args.skip_crawl = True
        if start_idx > 1:
            args.skip_filter = True
        if start_idx > 2:
            args.skip_cluster = True
        if start_idx > 3:
            args.skip_summary = True
        if start_idx > 4:
            args.skip_unified = True
    except ValueError:
        pass
```

4. Insert the cluster stage between step 2 (filter) and step 3 (summary). After the filter results check and before `# ============ 步骤3: 生成论文总结 ============`, insert:

```python
    # ============ 步骤3: 论文聚类 ============
    cluster_output_file = filter_output_file  # default fallback

    if not args.skip_cluster:
        progress.start_step("论文聚类")
        cmd = [
            sys.executable, "src/core/cluster_papers.py",
            "--input-file", filter_output_file,
            "--output-dir", DOMAIN_PAPER_DIR,
            "--api-key", args.api_key,
            "--base-url", args.base_url,
            "--model", args.model,
            "--temperature", str(args.temperature),
        ]
        if run_command(cmd, "论文聚类", progress):
            # Find the cluster output file
            if args.date:
                cluster_output_file = find_file_by_date(DOMAIN_PAPER_DIR, args.date, "clustered_*.json")
            if not cluster_output_file or not os.path.exists(cluster_output_file):
                # Try to find by pattern
                from glob import glob
                cluster_files = glob(os.path.join(DOMAIN_PAPER_DIR, "clustered_*.json"))
                if cluster_files:
                    cluster_output_file = max(cluster_files, key=os.path.getmtime)
                else:
                    cluster_output_file = filter_output_file
                    progress.log_with_timestamp("⚠️ 未找到聚类输出文件，使用筛选文件继续")
            progress.complete_step("论文聚类", True)
        else:
            progress.complete_step("论文聚类", False)
            progress.log_with_timestamp("⚠️ 聚类失败，使用筛选文件继续")
            cluster_output_file = filter_output_file
            notify_failures("cluster", ["Clustering stage failed, falling back to filtered papers"])
    else:
        progress.skip_step("论文聚类")
        # Try to find existing cluster file
        if args.date:
            candidate = find_file_by_date(DOMAIN_PAPER_DIR, args.date, "clustered_*.json")
            if candidate and os.path.exists(candidate):
                cluster_output_file = candidate
                progress.log_with_timestamp(f"📄 使用已有的聚类文件: {cluster_output_file}")

    progress.log_with_timestamp(f"📄 使用聚类文件: {cluster_output_file}")
```

5. Update step 3 (now step 4) — summary stage to use `cluster_output_file` instead of `filter_output_file`:

Change `summary_output_file = filter_output_file` to `summary_output_file = cluster_output_file`

Change the summary cmd's `"--input-file", filter_output_file` to `"--input-file", cluster_output_file`

6. Add pipeline completion notification at the end (before the final `print("\n✨ 流水线执行完成！")`):

```python
    # Send pipeline completion notification
    try:
        stats = {}
        if crawl_output_file and os.path.exists(crawl_output_file):
            with open(crawl_output_file, 'r', encoding='utf-8') as f:
                stats['crawled'] = len(json.load(f))
        if filter_output_file and os.path.exists(filter_output_file):
            with open(filter_output_file, 'r', encoding='utf-8') as f:
                stats['filtered'] = len(json.load(f))
        if cluster_output_file and os.path.exists(cluster_output_file):
            with open(cluster_output_file, 'r', encoding='utf-8') as f:
                stats['clustered'] = len(json.load(f))
        notify_pipeline_complete(stats)
    except Exception:
        pass  # notification is best-effort
```

- [ ] **Step 2: Update paper_filter.py — add retry import and failure isolation**

In `paper_filter.py`, update the `query_llm` function to use the retry decorator. Add at the top imports:

```python
from src.utils.retry import retry_with_backoff
```

Then decorate the `query_llm` function:

```python
@retry_with_backoff(max_retries=3, initial_delay=2.0)
def query_llm(title: str, summary: str, client: OpenAI, model: str, temperature: float = TEMPERATURE) -> Tuple[bool, str]:
```

The existing error handling in `filter_paper_wrapper` already catches exceptions and returns `'error'` status, so the skip-on-failure behavior is already implemented. The retry decorator will handle transient failures before giving up.

- [ ] **Step 3: Verify pipeline still runs basic argument parsing**

Run: `cd /data/users/weikaihuang/projects/PaperTools && python src/core/pipeline.py --help`
Expected: Should show updated help with `cluster` in `--start-from` choices

- [ ] **Step 4: Commit**

```bash
git add src/core/pipeline.py src/core/paper_filter.py
git commit -m "feat: integrate cluster stage and retry into pipeline"
```

---

### Task 5: Add Retry to crawl_arxiv.py and generate_summary.py

**Files:**
- Modify: `src/core/crawl_arxiv.py`
- Modify: `src/core/generate_summary.py`

- [ ] **Step 1: Update crawl_arxiv.py**

In `crawl_arxiv.py`, add import at top (after other imports):

```python
from src.utils.retry import retry_with_backoff
```

Wrap the `requests.get` call in `scrape_papers()` function. Replace the try/except block around `response = requests.get(url, timeout=30)` (lines 195-204) with a helper that uses retry:

```python
@retry_with_backoff(max_retries=3, initial_delay=2.0)
def _fetch_url(url: str) -> requests.Response:
    """Fetch URL with retry."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response
```

Add this function before `scrape_papers()`, then in `scrape_papers()` replace the try/except for the request with:

```python
    try:
        response = _fetch_url(url)
        time.sleep(delay)
    except Exception as e:
        print(f"❌ 获取 {category} 失败: {e}")
        return papers, paper_ids
```

- [ ] **Step 2: Update generate_summary.py — use shared retry**

The file already has its own `retry_on_failure` and `retry_on_openai_error` decorators that work well. We don't need to replace them since they already implement retry with backoff. The key change is adding failure notification.

Add at the top (with other imports):

```python
from src.utils.notify import notify_failures
```

In the `main()` function, after the processing loop completes (after the line `failed += 1` and `continue`), add failure notification:

```python
    # Notify about failures
    if failed > 0:
        failure_msgs = [f"{failed} papers failed during summary generation"]
        notify_failures("summarize", failure_msgs)
```

Insert this right before `# 保存更新后的JSON文件`.

- [ ] **Step 3: Commit**

```bash
git add src/core/crawl_arxiv.py src/core/generate_summary.py
git commit -m "feat: add retry to crawler, failure notifications to summary"
```

---

### Task 6: Rewrite `generate_unified_index.py` — Clustered Two-Level UI

**Files:**
- Modify: `src/core/generate_unified_index.py`

This is the largest task. The file generates a complete standalone HTML page. We need to:
1. Change the data structure from `categories` (arXiv subjects) to `clusters` (LLM-generated)
2. Add a tag filter bar at the top of each date section
3. Implement two-level collapsible: cluster level (collapsed by default) → paper level
4. Keep all existing features (star, read, delete, dark mode, load more, markdown rendering)

- [ ] **Step 1: Update `load_paper_data` and `save_date_data_files`**

Update `load_paper_data` to also look for `clustered_*_with_summary2.json` files (the summary stage output when input was a clustered file):

No change needed — the function already globs `filtered_papers_*_with_summary2.json`. The summary stage reads the clustered file but outputs with the same naming pattern based on input filename. Since the clustered file is named `clustered_papers_DATE.json` and the summary output is `clustered_papers_DATE_with_summary2.json`, we need to also match this pattern:

```python
def load_paper_data() -> Dict[str, List[Dict[str, Any]]]:
    """加载论文数据"""
    papers_by_date = {}
    summary_dir = Path(SUMMARY_DIR)

    # Match both filtered and clustered summary files
    for pattern in ["*_with_summary2.json"]:
        for json_file in summary_dir.glob(pattern):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    papers = json.load(f)

                filename = json_file.stem
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                if date_match:
                    date = date_match.group(1)
                    # If we already have data for this date, keep the one with more papers
                    if date in papers_by_date and len(papers_by_date[date]) >= len(papers):
                        continue
                    papers_by_date[date] = papers
                    print(f"加载了 {len(papers)} 篇论文，日期: {date}")
            except Exception as e:
                print(f"加载文件 {json_file} 时出错: {e}")

    return papers_by_date
```

- [ ] **Step 2: Replace `organize_papers_by_category` with `organize_papers_by_cluster`**

```python
def organize_papers_by_cluster(papers: List[Dict]) -> List[Dict]:
    """将论文按聚类组织"""
    clusters = {}
    for paper in papers:
        cluster = paper.get('cluster', 'Other')
        if cluster not in clusters:
            clusters[cluster] = []
        clusters[cluster].append(paper)

    result = []
    for cluster_name, cluster_papers in sorted(clusters.items(), key=lambda x: (-len(x[1]), x[0])):
        result.append({
            "name": cluster_name,
            "count": len(cluster_papers),
            "papers": cluster_papers
        })
    return result


def collect_all_tags(papers: List[Dict]) -> List[Dict]:
    """Collect all unique tags with counts for the tag filter bar."""
    tag_counts = {}
    for paper in papers:
        tags = paper.get('tags', [])
        cluster = paper.get('cluster', 'Other')
        # Add cluster as a tag too
        tag_counts[cluster] = tag_counts.get(cluster, 0) + 1
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    # Sort: clusters first (non cs.XX), then arxiv categories
    result = []
    for tag, count in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])):
        result.append({"name": tag, "count": count})
    return result
```

- [ ] **Step 3: Update `save_date_data_files` to use clusters instead of categories**

```python
def save_date_data_files(papers_by_date: Dict, daily_overviews: Dict) -> List[str]:
    """将每个日期的数据保存为独立的 JSON 文件"""
    data_dir = Path(WEBPAGES_DIR) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    all_dates = sorted(papers_by_date.keys(), reverse=True)

    for date in all_dates:
        papers = papers_by_date[date]
        organized = organize_papers_by_cluster(papers)
        tags = collect_all_tags(papers)

        date_data = {
            "date": date,
            "clusters": organized,
            "tags": tags,
            "overview": daily_overviews.get(date, "")
        }

        date_file = data_dir / f"{date}.json"
        with open(date_file, 'w', encoding='utf-8') as f:
            json.dump(date_data, f, ensure_ascii=False)
        print(f"保存数据文件: {date_file}")

    # 生成日期索引文件
    index_data = {
        "dates": all_dates,
        "initial_days": INITIAL_DAYS,
        "load_more_days": LOAD_MORE_DAYS
    }
    index_file = data_dir / "index.json"
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    print(f"保存索引文件: {index_file}")

    return all_dates
```

- [ ] **Step 4: Rewrite `generate_complete_html` with new cluster-based UI**

This is the core change. The new HTML/JS/CSS must:
- Use `clusters` instead of `categories` in the data structure
- Add a tag filter bar per date section
- Implement two-level collapsible (cluster → papers, clusters collapsed by default)
- Keep all existing features

The full rewrite of `generate_complete_html` is too large to include inline in the plan. The implementation should:

1. Update the JS data generation to use `clusters` and `tags` fields
2. Replace `createCategoryHTML` with `createClusterHTML` — same structure but uses cluster name
3. Add a `createTagFilterHTML(tags, date)` function that renders clickable tag buttons
4. Add JS filter logic: clicking a tag filters papers across all clusters for that date
5. Update `renderPapers()` to render tag filter bar + cluster groups
6. Add CSS for tag filter buttons (pill-shaped, toggleable active state)

Key JS additions for tag filtering:
```javascript
// Track active tag filters per date
let activeTagFilters = {}; // {date: Set of active tag names}

function toggleTagFilter(date, tagName) {
    if (!activeTagFilters[date]) activeTagFilters[date] = new Set();
    const filters = activeTagFilters[date];

    if (tagName === 'All') {
        filters.clear();
    } else if (filters.has(tagName)) {
        filters.delete(tagName);
    } else {
        filters.add(tagName);
    }

    renderDateSection(date);
}

function paperMatchesFilters(paper, date) {
    const filters = activeTagFilters[date];
    if (!filters || filters.size === 0) return true;
    // Check if paper's cluster or any tag matches active filters
    if (filters.has(paper.cluster)) return true;
    return (paper.tags || []).some(tag => filters.has(tag));
}
```

The full HTML template structure per date section:
```html
<section data-date-section="DATE">
  <h2>DATE (N papers)</h2>
  <!-- Tag filter bar -->
  <div class="tag-filter-bar">
    <button class="tag-btn active" onclick="toggleTagFilter('DATE','All')">All</button>
    <button class="tag-btn" onclick="toggleTagFilter('DATE','Multi-Agent')">Multi-Agent ×12</button>
    ...
  </div>
  <!-- Daily overview (if exists) -->
  <!-- Cluster groups -->
  <div class="cluster-group">
    <div class="cluster-header" onclick="toggleCluster(this)">
      ▸ Multi-Agent Collaboration (12)
    </div>
    <div class="cluster-content hidden">
      <!-- Paper items (same as current createPaperHTML, with tag badges added) -->
    </div>
  </div>
</section>
```

Tag badge CSS addition for paper items:
```css
.tag-badge {
    display: inline-block;
    padding: 1px 6px;
    font-size: 0.7rem;
    border-radius: 9999px;
    background: #e0f2fe;
    color: #0369a1;
    margin-right: 4px;
}
.dark .tag-badge {
    background: #1e3a5f;
    color: #7dd3fc;
}
```

- [ ] **Step 5: Update the `main()` function call**

```python
def main():
    try:
        html_content = generate_complete_html()
        webpages_dir = Path(WEBPAGES_DIR)
        webpages_dir.mkdir(exist_ok=True)
        output_path = webpages_dir / "index.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"成功生成统一HTML页面: {output_path}")
    except Exception as e:
        print(f"生成HTML页面时出错: {e}")
        return 1
    return 0
```

- [ ] **Step 6: Test by running the generate script**

Run: `cd /data/users/weikaihuang/projects/PaperTools && python -c "from src.core.generate_unified_index import generate_complete_html; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 7: Commit**

```bash
git add src/core/generate_unified_index.py
git commit -m "feat: rewrite HTML generation with cluster-based two-level UI and tag filtering"
```

---

### Task 7: Rewrite README.md

**Files:**
- Rewrite: `README.md`
- Create: `docs/configuration.md`
- Create: `docs/pipeline.md`
- Create: `docs/deployment.md`

- [ ] **Step 1: Write new README.md**

```markdown
# PaperTools

自动追踪、筛选、聚类、总结 arXiv 论文。每天帮你从海量论文中找到真正相关的研究。

## 快速开始

```bash
# 1. 安装
pip install -e .

# 2. 配置
cp .env.example .env
# 编辑 .env，填入 API 地址、密钥和模型名

# 3. 运行
papertools run
```

## 配置

| 变量 | 说明 | 必填 |
|------|------|------|
| `OPENAI_BASE_URL` | API 地址 | 是 |
| `OPENAI_API_KEY` | API 密钥 | 是 |
| `MODEL` | 模型名 | 是 |
| `WEBHOOK_URL` | 失败/完成通知 webhook | 否 |
| `JINA_API_TOKEN` | Jina Reader API（全文获取）| 否 |

筛选规则在 `src/utils/config.py` 的 `PAPER_FILTER_PROMPT` 中定义。

## 命令

```bash
papertools run                        # 运行完整流水线
papertools run --mode quick           # 快速测试（10篇）
papertools run --date 2026-03-28      # 指定日期
papertools serve                      # 启动本地服务器
papertools clean                      # 清理缓存
papertools check                      # 检查环境
```

## 定时运行

```bash
crontab -e
# 每天早上 8 点自动运行
0 8 * * * cd /path/to/PaperTools && papertools run --skip-serve >> logs/cron.log 2>&1
```

## 流水线

```
爬取 arXiv → LLM 筛选 → LLM 聚类 → 摘要/总结生成 → 网页生成
```

每个阶段产出独立的 JSON 文件，可以从任意阶段恢复：`papertools run --start-from cluster`

## 更多文档

- [完整配置参考](docs/configuration.md)
- [流水线详解](docs/pipeline.md)
- [部署指南](docs/deployment.md)（GitHub Pages、crontab）
```

- [ ] **Step 2: Write docs/configuration.md**

Move the detailed configuration docs from the old README (env vars, config.py params, filter prompt explanation, etc.) into this file.

- [ ] **Step 3: Write docs/pipeline.md**

Document the 6 pipeline stages (crawl, filter, cluster, summarize, generate, serve) with input/output file patterns and options.

- [ ] **Step 4: Write docs/deployment.md**

Move the GitHub Pages deployment section from old README here. Add crontab setup instructions with troubleshooting tips (PATH issues, log rotation, error handling).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/configuration.md docs/pipeline.md docs/deployment.md
git commit -m "docs: rewrite README as 5-minute quick start, move details to docs/"
```

---

### Task 8: End-to-End Smoke Test

**Files:** None (testing only)

- [ ] **Step 1: Test full pipeline with quick mode**

Run: `cd /data/users/weikaihuang/projects/PaperTools && python papertools.py run --mode quick --skip-serve --date 2026-03-28`

Verify:
- Crawl stage completes
- Filter stage completes
- Cluster stage produces `clustered_*.json` with `cluster` and `tags` fields on each paper
- Summary stage completes (or partially completes)
- HTML generation produces `webpages/index.html` with cluster-based UI

- [ ] **Step 2: Verify HTML output structure**

Run: `python -c "
import json
from pathlib import Path
# Check that date JSON files have clusters instead of categories
data_dir = Path('webpages/data')
for f in sorted(data_dir.glob('*.json'))[:1]:
    if f.name == 'index.json': continue
    data = json.loads(f.read_text())
    print(f'File: {f.name}')
    print(f'Has clusters: {\"clusters\" in data}')
    print(f'Has tags: {\"tags\" in data}')
    if 'clusters' in data:
        for c in data['clusters']:
            print(f'  Cluster: {c[\"name\"]} ({c[\"count\"]} papers)')
"`

Expected: Output shows clusters and tags in the date JSON files.

- [ ] **Step 3: Verify webhook notification**

Run: `python -c "from src.utils.notify import send_notification; send_notification('🧪 PaperTools test notification')"`

Expected: Message appears in your Pumble channel.

- [ ] **Step 4: Commit any fixes**

If smoke test revealed issues, fix them and commit.

```bash
git add -A
git commit -m "fix: address issues found in smoke test"
```
