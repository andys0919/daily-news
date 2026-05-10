## Why

Phase 1 added RSS-layer coverage for five investment categories. The next step is to fetch structured data (transcripts, Form 4, 13F-HR, TWSE credit balance, FINRA short interest, hyperscaler capex aggregate) and return typed dataclasses that downstream phases can persist and consume.

## What Changes

- Add four new modules: `ir_materials.py`, `insider_holdings.py`, `short_interest.py`, `macro_data.py`.
- Each module exposes pure-Python fetcher / aggregator functions returning typed dataclass lists.
- Wire all four into `main.py` Step 2.5 as background tasks parallel to the existing four financial-data channels.
- This phase does NOT persist data to new SQLite tables — Phase 3 does.

## Capabilities

### New Capabilities
- `investment-source-ingest`: Pure-Python fetchers for transcripts, insider / 13F filings, short interest / ETF flow snapshots, and macro aggregates.

### Modified Capabilities
- `pipeline-orchestration`: `main.py` Step 2.5 now runs eight parallel background tasks instead of four.

## Impact

- Affected code: four new modules, `main.py`, four new test files, `tests/fixtures/` directory.
- No SQLite schema change.
- No edits to `stock_memo.py`, `summarizer.py`, `html_generator.py`, `financial_reports.py`, `crawler.py`, `news_enrichment.py`.
