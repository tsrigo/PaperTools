# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PaperTools is an academic paper processing pipeline that automates: crawling papers from arXiv, filtering with LLMs, generating Chinese summaries, and creating interactive web pages.

## Common Commands

```bash
# Full pipeline (1000 papers)
python papertools.py run

# Quick test (10 papers)
python papertools.py run --mode quick

# Process specific date
python papertools.py run --date 2025-09-24

# Start web server only
python papertools.py serve

# Check environment/dependencies
python papertools.py check

# Clean cache
python papertools.py clean
```

### Individual Module Commands

```bash
# Crawl papers
python src/core/crawl_arxiv.py --categories cs.AI cs.CV --max-papers 100

# Filter papers
python src/core/paper_filter.py --input-file arxiv_paper/papers.json

# Generate summaries
python src/core/generate_summary.py --input-file domain_paper/filtered_papers.json

# Generate unified webpage
python src/core/generate_unified_index.py

# Start server
python src/core/serve_webpages.py --port 8080
```

## Architecture

### Pipeline Flow
`crawl -> filter -> summarize -> generate webpages -> serve`

- **Main entry**: `papertools.py` - CLI interface with dependency checking
- **Pipeline core**: `src/core/pipeline.py` - coordinates all steps, supports resume from any stage
- **Data flow**: Each stage reads JSON from previous stage, adds fields, outputs enhanced JSON

### Data Enhancement Through Stages
1. `crawl`: Base fields (title, summary, arxiv_id, link, date)
2. `filter`: Adds `filter_reason` field
3. `summary`: Adds `summary2` field (Chinese summary)
4. `webpage`: Converts to interactive HTML

### Directory Structure
- `arxiv_paper/` - Raw crawled papers (JSON)
- `domain_paper/` - Filtered papers with reasons
- `summary/` - Papers with summaries (files named `*_with_summary2.json`)
- `webpages/` - Generated HTML with interactive features
- `cache/` - Three-tier cache (papers/summaries/webpages)

### Key Configuration
- `.env` - API keys (OPENAI_API_KEY, OPENAI_BASE_URL, MODEL, JINA_API_TOKEN)
- `src/utils/config.py` - All parameters including `PAPER_FILTER_PROMPT` for customizing paper selection criteria

### Web Server API
`src/core/serve_webpages.py` extends Python HTTP server with:
- `/api/state` - Get user state
- `/api/toggle-read` - Mark paper as read
- `/api/delete` - Delete paper
- State persisted in `.user_state.json`

## Development Notes

### Concurrency
- `MAX_WORKERS` controls thread count (default 2, kept low to avoid API rate limits)
- Wrapper functions (`*_wrapper`) handle exceptions in concurrent operations
- Progress tracked with `tqdm` and `ProgressTracker` class

### Resume/Skip Features
- `--start-from {crawl,filter,summary,unified,serve}` to resume from specific stage
- `--skip-crawl`, `--skip-filter`, etc. for fine-grained control
- Pipeline auto-detects existing files to avoid reprocessing

### API Integration
- OpenAI-compatible interface via `openai` library with custom `base_url`
- Jina API for full-text reading with 20 RPM rate limit and exponential backoff
- Streaming responses used to avoid Cloudflare 524 timeout errors

### Testing
- Use `--mode quick` (10 papers) for rapid validation
- Check JSON file completeness after each stage
