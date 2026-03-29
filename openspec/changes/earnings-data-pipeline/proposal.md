## Why

The current report can mention earnings news only through media summaries, so it misses official filing facts and cannot ground memo output in primary financial data. We need a free, official U.S. earnings facts pipeline that can enrich article context with the latest filing-derived metrics.

## What Changes

- Add a U.S. official financial facts pipeline built on SEC ticker mappings, submissions feeds, and companyfacts XBRL data.
- Persist structured filing snapshots in a reusable financial reports store keyed by issuer and reporting period.
- Augment relevant article and memo context with filing-derived metrics such as revenue, EPS, net income, margins, operating cash flow, capex, and free cash flow when available.
- Orchestrate the new facts pipeline during report generation without blocking the existing market data and memo flow.

## Capabilities

### New Capabilities
- `us-official-financial-facts`: Resolve U.S. issuers and ingest official SEC filing facts into structured report snapshots.
- `article-financial-augmentation`: Join filing snapshots back into article and memo context when the news relates to earnings or filings.

### Modified Capabilities

## Impact

- Affected code: new SEC ingestion module, `main.py`, `summarizer.py`, tests, and SQLite schema.
- Affected data: new structured financial reports table plus issuer metadata caches.
- External systems: SEC `company_tickers.json`, submissions JSON, and companyfacts JSON endpoints.
