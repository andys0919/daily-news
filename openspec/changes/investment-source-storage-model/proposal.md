## Why

Phase 2 ingest modules return typed dataclasses but do not persist. This change adds the SQLite tables, save functions, and bundle extensions so downstream consumers (Phase 4 memo / summarizer) can read structured ingest results out of `data/news.db`.

## What Changes

- Add four new SQLite tables in `financial_reports.py`: `issuer_materials`, `insider_transactions`, `holdings_snapshots`, `short_interest_snapshots`.
- Add four matching `save_*` functions.
- Extend `FinancialSnapshotBundle` with `latest_transcript`, `recent_insider_summary`, `latest_13f`, `short_interest`.
- Wire the four Phase 2 modules to call the new save functions when `_persist=True`.
- Tests cover round-trip + idempotent re-init.

## Capabilities

### New Capabilities
- `investment-source-storage`: Persistent SQLite storage for transcripts, insider trades, 13F holdings, and short-interest snapshots.

### Modified Capabilities
- `financial-snapshot-bundle`: Bundle now exposes four optional structured fields beyond the existing quarterly + monthly revenue.

## Impact

- Affected code: `financial_reports.py`, four Phase 2 modules, two new test files.
- No edits to `stock_memo.py`, `summarizer.py`, `html_generator.py`, `crawler.py`, `news_enrichment.py`.
- No RSS feed additions.
