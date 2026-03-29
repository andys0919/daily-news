## Context

`daily-news` currently treats RSS feed descriptions as article bodies. The crawler stores a thin article record, then `get_recent_articles()` hydrates an even thinner legacy representation that loses `source_key` and `summary_prompt`. The summarizer has source ranking and filtering logic, but it operates on partial data and clusters events mostly by title fingerprints.

## Goals / Non-Goals

**Goals:**
- Preserve source metadata and enriched article content across crawl and reload boundaries.
- Fetch full article pages for high-signal items without turning every run into a full-site crawler.
- Produce stable entity and event metadata that improves de-duplication and memo context quality.
- Keep the migration additive so existing databases and tests continue to work.

**Non-Goals:**
- Build a generic NLP platform or perfect entity recognition for every company worldwide.
- Crawl every article body from every source regardless of signal quality.
- Replace the memo architecture that was recently introduced.

## Decisions

### Decision: widen the existing `articles` table instead of adding a second article shadow table
This keeps the current pipeline shape intact and minimizes query complexity in `get_recent_articles()`. The migration will use additive `ALTER TABLE` operations guarded by `PRAGMA table_info`, so existing databases remain readable.

Alternative considered:
- Separate `article_enrichments` table. Rejected because it adds join complexity to the hottest read path and forces more migration logic for every caller.

### Decision: perform selective enrichment during crawl for top-ranked source items
The crawler already has source priority and per-source limits. We will enrich only items that meet source-level thresholds or match high-signal event heuristics, using a smaller body-fetch concurrency limit. This improves article quality where it matters without making every run network-bound on full-text fetches.

Alternative considered:
- Run enrichment as a second offline job. Rejected because the summarizer would still see stale or partial data during the main report run.

### Decision: use heuristic event intelligence stored on the article record
Event typing and entity extraction will be heuristic, based on source metadata, title/body keywords, ticker patterns, and company aliases derived from tracked symbols. The result will be stored as normalized JSON plus a canonical `event_key`.

Alternative considered:
- Push all event inference to the LLM. Rejected because prompt-only inference is not reusable and makes de-duplication unstable across runs.

### Decision: prompt builders will emit structured context blocks
Summary and memo builders will prefer `body_text`, surface extracted entities, and include event metadata in the prompt context. This keeps the LLM grounded in explicit facts instead of reconstructing context from short feed descriptions.

Alternative considered:
- Only swap `summary` for `body_text`. Rejected because it improves detail but does not solve event grouping or downstream augmentation.

## Risks / Trade-offs

- [Risk] Some article pages will block crawlers or return noisy markup. → Mitigation: keep RSS summary as fallback, record extraction status, and only use enriched fields when extraction quality passes a minimum threshold.
- [Risk] Heuristic entity extraction will miss some companies or over-match tickers. → Mitigation: keep event-key fallback to title fingerprint and limit ticker inference with stopword lists and alias tables.
- [Risk] Wider article rows increase DB size. → Mitigation: cap stored body length and persist compact JSON instead of raw HTML.

## Migration Plan

1. Add additive article columns and ensure initialization migrates existing databases.
2. Update crawl/save/hydrate paths to populate the richer schema.
3. Add article-page enrichment and event intelligence helpers.
4. Switch prompt builders to prefer enriched article context.
5. Verify old rows still hydrate with safe defaults.

## Open Questions

- None blocking. Initial implementation will use heuristic extraction and leave model-based entity extraction for a later change if needed.
