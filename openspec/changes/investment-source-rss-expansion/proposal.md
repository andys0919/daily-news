## Why

The project tracks earnings via SEC / TWSE / TPEX / MOPS, but the RSS layer has gaps in five investment-relevant areas: broker / independent analyst research, issuer relations materials, insider and institutional holdings, short interest and ETF flows, and macro / sector data. These signals belong in the daily / weekly memo and per-stock memo workflows.

## What Changes

- Add five new feed categories to `config.yaml`: `broker_research`, `ir_materials`, `insider_holdings`, `short_interest_flows`, `macro_data`.
- Add matching `category_agents` entries (initial persona; later phases refine prompts).
- Extend `tests/test_source_coverage.py` to assert key feeds exist in each new category.
- Extend `tests/test_news_enrichment.py` to confirm articles from new categories still trigger issuer / ticker / event extraction.
- Add `tests/test_broker_research_feeds.py` with a mock-fetch parser smoke test.

## Capabilities

### New Capabilities
- `investment-source-coverage`: RSS-layer coverage for broker research, IR materials, insider / 13F holdings, short interest / ETF flows, and macro / sector data.

### Modified Capabilities
- `news-pipeline-coverage`: Crawl five new feed categories with the existing aiohttp / feedparser path.

## Impact

- Affected code: `config.yaml`, three test files.
- No code changes in `crawler.py`, `news_enrichment.py`, `financial_reports.py`, `summarizer.py`, `stock_memo.py`, `html_generator.py`.
- No SQLite schema change.
