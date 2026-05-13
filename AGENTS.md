# PaperTools Agent Rules

PaperTools is a user-facing daily reading system. Treat every generated webpage as production content that a user may read immediately.

## Publishing Principles

- Do not publish empty dates. If arXiv has no papers for a weekend or holiday, skip that date instead of uploading a zero-paper page.
- Do not publish partial content. A daily page is publishable only when every listed paper has the original abstract, Chinese abstract translation, intro logic, core insight, methodology, additional insights, research value review, cluster metadata, and a daily overview.
- Do not treat pipeline success as publication success. Validate the generated `webpages/data/YYYY-MM-DD.json` payload before committing or pushing it.
- Do not let filtered or clustered intermediate files appear as finished webpages. User-facing pages must be generated from complete summary outputs or already verified published data.
- Do not upload extraction failures. If document extraction fails or returns an error page, retry first; if it still fails, stop the run and keep the date unpublished.
- Do not upload filtering failures. If filtering has API/model errors, malformed output, or suspicious zero results, stop the run and alert instead of publishing.
- Do not fall back silently after clustering, summarization, overview generation, or webpage generation fails. These are publication blockers.
- Prefer failing closed over showing users incomplete papers. A missed day with a clear failure notification is better than a broken page that looks successful.
- Optional enrichment dependencies such as ReviewGrounder must have a real content-generating fallback. Dependency import failures must not create user-visible error placeholders.
- Filter model fallback must disable an invalid model ID after the first provider error and continue to the next configured model instead of retrying the same bad ID for every paper.

## Daily Automation Requirements

- Scheduled runs must start from the latest `origin/master` and a clean worktree.
- Scheduled runs must use a lock so two runs cannot publish concurrently.
- A skipped date should be recorded as skipped, not failed, when there are genuinely no source papers or no selected papers.
- A failed stage should return a non-zero exit code and must not be committed unless an operator explicitly opts into debug behavior.
- The publish step must validate that the target date exists in `webpages/data/index.json`, has at least one paper, has a non-empty daily overview, and every paper passes the publication quality gate.
- Regenerating the unified index should prune stale empty or partial date files.

## Robustness Expectations

- Add tests for every new gate or recovery behavior that protects publication quality.
- Keep retry counts configurable when a failure depends on network, API, or document extraction.
- Cache successful extraction and generation results, but never let invalid cached content count as complete.
- When broadening or tightening paper selection, verify both count and content completeness before pushing.
- When debugging production failures, check the live JSON payloads, not just local logs or commit status.
