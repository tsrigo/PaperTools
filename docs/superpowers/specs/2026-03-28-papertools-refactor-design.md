# PaperTools Refactoring Design Spec

**Date:** 2026-03-28
**Status:** Approved

## Goals

1. Improve usability: simplify README, 5-minute onboarding
2. Improve robustness: API retry, single-paper failure isolation, webhook notifications
3. Restructure paper display: LLM-driven clustering with two-level collapsible UI + tag filtering
4. Switch model to minimax-m2.5 via models.sjtu.edu.cn

## Non-Goals

- Changing filter prompt or summary prompt content/structure
- Rewriting crawl logic
- Microservice architecture or major architectural overhaul

---

## 1. Pipeline: New Cluster Stage

### Data Flow

```
crawl → filter → cluster (NEW) → summarize → generate_unified_index → serve
```

### New Module: `src/core/cluster_papers.py`

**Input:** `filtered_papers_DATE.json`
**Output:** `clustered_papers_DATE.json` (each paper gains a `cluster` field)

**Logic:**
1. Read all filtered papers for a given date
2. Compose a list of (title, abstract) pairs
3. Send to LLM (minimax-m2.5) in one request, asking it to:
   - Analyze all papers and identify natural research clusters
   - Assign each paper to exactly one cluster
   - Return cluster name + paper-to-cluster mapping as JSON
4. If paper count exceeds context window limits, split into batches:
   - Process each batch independently
   - After all batches, do a final LLM call to merge semantically similar cluster names
5. Write output with `cluster` field added to each paper

**Original arXiv categories** (cs.AI, cs.CL, cs.LG, cs.MA) are preserved as `tags` on each paper, no longer used for grouping.

### Pipeline Integration

- New stage inserted between filter and summarize in `pipeline.py`
- Summarize stage reads `clustered_papers_DATE.json` instead of `filtered_papers_DATE.json`
- `generate_unified_index.py` reads `cluster` field for grouping

---

## 2. API Retry & Fault Tolerance

### New Module: `src/utils/retry.py`

**`retry_with_backoff` decorator/function:**
- Initial delay: 2s
- Multiplier: 2x
- Max delay: 60s
- Max retries: 3 (configurable)
- Retryable: network timeout, 5xx, 429 Rate Limit, connection errors
- Non-retryable: 4xx (except 429), authentication failures

### Application

| Module | Behavior on failure |
|--------|-------------------|
| `crawl_arxiv.py` | Retry request; skip paper on exhaustion |
| `paper_filter.py` | Retry API call; skip paper on exhaustion, log warning, continue |
| `cluster_papers.py` | Retry API call; on exhaustion, assign "Uncategorized" cluster |
| `generate_summary.py` | Retry API call; skip summary on exhaustion, paper still included |

### Pipeline-Level Tolerance

- Filter stage: continues as long as >=1 paper passes
- Cluster stage: continues even if some papers are "Uncategorized"
- Summarize stage: papers without summaries are still included in output (displayed without summary in UI)

---

## 3. Webhook Notifications

### New Module: `src/utils/notify.py`

**Generic webhook notifier:**
- Accepts any webhook URL that takes POST with `{"text": "..."}` payload
- Compatible with Pumble, Slack, Feishu, Discord, etc.

**Configuration (`.env`, optional):**
```
WEBHOOK_URL=https://...
```

**Trigger points:**
- Pipeline stage failure (after retries exhausted): batched summary of all failures in that stage, sent as one message
- Pipeline completion: summary message (X papers crawled, Y filtered, Z clustered, W summarized, N failures)

**Local config:** Pumble webhook URL configured in `.env` (not committed to git).

---

## 4. Frontend: Clustered Two-Level Collapsible UI + Tag Filter

### Layout Per Date

```
┌─────────────────────────────────────────────┐
│  2026-03-28  (32 papers)                    │
│  [All] [Multi-Agent x12] [Tool Use x8] ... │  ← tag filter bar
│                                              │
│  ▸ Multi-Agent Collaboration (12)            │  ← collapsed cluster
│  ▸ Tool Use & API Integration (8)            │
│  ▾ Self-Evolution (7)                        │  ← expanded
│     ├─ Paper Title A  [cs.AI] [cs.MA]        │
│     │  authors... | summary preview...       │
│     ├─ Paper Title B  [cs.CL]                │
│     └─ ...                                   │
│  ▸ Planning & Reasoning (5)                  │
└─────────────────────────────────────────────┘
```

### Behavior

- **First level:** Cluster names, collapsed by default, showing paper count
- **Second level:** Paper list within each cluster, each paper expandable for details
- **Tag filter bar:** Shows all cluster tags + arXiv category tags with counts. Click to filter. Multi-select supported. "All" resets filter.
- **Tags on papers:** Each paper displays its cluster tag + arXiv category tags as small badges
- **Each paper belongs to exactly one cluster** (primary, determined by LLM), but can have multiple arXiv category tags

### Data Format Change

`webpages/data/DATE.json` — each paper object gains:
```json
{
  "cluster": "Multi-Agent Collaboration",
  "tags": ["cs.AI", "cs.MA"]
}
```

### Preserved Features

- Bookmark, read, delete interactions
- Load More pagination
- Local serve API endpoints unchanged
- Markdown rendering for summaries

---

## 5. README Rewrite

### New Structure

```
# PaperTools
One-line description.

## Quick Start (3 steps)
1. pip install -e .
2. cp .env.example .env → fill in API config
3. papertools run

## Configuration
| Variable | Description | Required |
|----------|-------------|----------|
| OPENAI_BASE_URL | API endpoint | Yes |
| OPENAI_API_KEY | API key | Yes |
| MODEL | Model name | Yes |
| WEBHOOK_URL | Notification webhook | No |

## Commands
papertools run / serve / clean / check — one line each

## Scheduled Runs
crontab example: 0 8 * * * cd /path/to/PaperTools && papertools run >> logs/cron.log 2>&1

## Documentation
→ docs/
```

### Detailed Docs (new `docs/` directory)

- `docs/configuration.md` — full config reference
- `docs/pipeline.md` — pipeline stages explained
- `docs/deployment.md` — GitHub Pages + crontab setup
- `docs/advanced.md` — advanced usage

---

## 6. Model Configuration

### Local `.env`

```
OPENAI_BASE_URL=https://models.sjtu.edu.cn/api/v1/
OPENAI_API_KEY=sk-Oc9HS3jAJ9EY6HTjGycknw
MODEL=minimax-m2.5
WEBHOOK_URL=https://api.pumble.com/workspaces/67a0346a240b8a36fd63b2fa/incomingWebhooks/postMessage/AGzEVNKPaL1aHDu1TJ1GlGLY
```

### `.env.example` (committed to git)

```
OPENAI_BASE_URL=https://your-api-url/v1/
OPENAI_API_KEY=your_key_here
MODEL=your_model_name
WEBHOOK_URL=
JINA_API_TOKEN=
```

---

## File Changes Summary

| Action | File |
|--------|------|
| **New** | `src/core/cluster_papers.py` |
| **New** | `src/utils/retry.py` |
| **New** | `src/utils/notify.py` |
| **Modify** | `src/core/pipeline.py` — insert cluster stage |
| **Modify** | `src/core/paper_filter.py` — add retry, skip on failure |
| **Modify** | `src/core/generate_summary.py` — add retry, skip on failure |
| **Modify** | `src/core/crawl_arxiv.py` — add retry |
| **Modify** | `src/core/generate_unified_index.py` — clustered UI + tag filter |
| **Modify** | `src/utils/config.py` — add WEBHOOK_URL config |
| **Modify** | `.env` — update model config + webhook |
| **Modify** | `.env.example` — add WEBHOOK_URL field |
| **Rewrite** | `README.md` |
| **New** | `docs/configuration.md` |
| **New** | `docs/pipeline.md` |
| **New** | `docs/deployment.md` |
| **New** | `docs/advanced.md` |
