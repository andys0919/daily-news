# Design — investment-source-rss-expansion (Phase 1 of 4)

This change is Phase 1 of the investment-source-expansion master spec at
`docs/superpowers/specs/2026-05-09-investment-source-expansion-design.md`.

Phase 1 only adds RSS / Atom entries that the existing `crawler.py` can
ingest with no code changes. Five new feed categories are introduced. Their
`category_agents` entries are added so YAML stays internally consistent;
prompt polish happens in Phase 4.

Non-RSS endpoints (FINRA short-interest CSV, MOPS HTML, TWSE OpenAPI direct
calls) belong to Phase 2 ingest modules and are deliberately **not** added
here.

## Source Health

All new feeds use the existing `SourceHealthRegistry` cooldown mechanism.
Feeds that turn out to be 404 / paywalled / unstable get marked
`active: false` rather than retried forever.

## Tests

- `tests/test_source_coverage.py` — structural assertions (feed exists,
  required keys present).
- `tests/test_broker_research_feeds.py` — mock-fetch parser smoke.
- `tests/test_news_enrichment.py` — issuer / ticker extraction still works
  on representative new-source samples.

## Out of scope

- New `.py` ingest modules (Phase 2).
- SQLite schema (Phase 3).
- `stock_memo.py` / `summarizer.py` integration (Phase 4).
