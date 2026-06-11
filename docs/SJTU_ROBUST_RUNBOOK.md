# SJTU Daily Runbook

This runbook documents the SJTU-oriented daily automation profile. The
publishing invariant is the same as the rest of PaperTools: only validated
`webpages/` artifacts are publishable.

## Runtime Defaults

The daily wrappers apply conservative OpenAI-compatible gateway defaults:

- `OPENAI_BASE_URL=https://models.sjtu.edu.cn/api/v1/`
- `FILTER_MODEL=qwen`
- `PAPERTOOLS_FILTER_MODEL_CHAIN=qwen,deepseek-chat,minimax`
- `CLUSTER_MODEL=glm`
- `PAPERTOOLS_CLUSTER_MODEL_CHAIN=qwen,deepseek-chat,minimax`
- `SUMMARY_MODEL=qwen`
- `SUMMARY_MODEL_CHAIN=sjtu:qwen,sjtu:deepseek-chat,sjtu:minimax,sjtu:glm,sjtu:deepseek-reasoner`
- `FILTER_MAX_WORKERS=1`
- `SUMMARY_MAX_WORKERS=1`
- `PAPERTOOLS_FILTER_RPM=4`
- `PAPERTOOLS_FILTER_LLM_TIMEOUT=60`
- `PAPERTOOLS_FILTER_LLM_MAX_RETRIES=1`
- `PAPERTOOLS_TOPIC_HEURISTIC_BYPASS_PRESTIGE=0`
- `DOCUMENT_EXTRACTOR_CHAIN=jina,pymupdf4llm`

Use `PAPERTOOLS_DAILY_*` variables for explicit cron-time overrides. Secrets
still belong in `.env` or a secret manager.

Daily publishing wrappers run the remote `/models` preflight by default. The
check validates configured primary plus fallback filter, cluster, and summary
models against their actual provider endpoint, so a separate cluster or Prism
summary provider is not checked against the main `OPENAI_BASE_URL`. Set
`PAPERTOOLS_DAILY_PREFLIGHT_OFFLINE_OK=1` only for an intentional offline run
where the gateway cannot be reached but local validation should still run.

## Recommended Cron

Use the hardened publisher for normal daily publishing:

```cron
0 8 * * * cd /path/to/PaperTools && ./daily_update.sh >> logs/cron.log 2>&1
```

For the legacy SJTU wrapper with retry/window defaults:

```cron
0 8 * * * cd /path/to/PaperTools && bash scripts/robust_daily_update.sh >> logs/cron.log 2>&1
```

Both paths must run the full publication validator before committing. They
stage only `webpages/`; `arxiv_paper/`, `domain_paper/`, `summary/`, and `logs/`
remain local runtime state.

## Validation

Before pushing or deploying, run:

```bash
make ci
python scripts/validate_published_payloads.py --webpages-dir webpages
```

The validator checks the static entrypoint, index integrity, stale date files,
daily overviews, cluster metadata, and every user-facing generated field.

## Failure Policy

- Pipeline or validator failure is publication-blocking.
- Empty source days and zero selected papers are skipped, not published.
- Commit and push failures must be visible non-zero failures.
- When debugging production failures, inspect `webpages/data/*.json`; logs are
  supporting evidence, not proof that a page is publishable.
