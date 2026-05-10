## Why

Phase 3 added structured bundle fields (`latest_transcript`, `recent_insider_summary`, `latest_13f`, `short_interest`) but no consumer reads them yet. Phase 4 surfaces those fields in the per-stock memo and in the prompt context the summarizer feeds into the daily memo.

## What Changes

- `stock_memo.py` `render_stock_memo` adds five new markdown sections: 最新法說會 / 近 90 天內部人交易 / 13F 機構動向 / 融券與 ETF 資金流 / 宏觀脈絡.
- `financial_reports.py` `format_financial_snapshot_bundle_context` includes structured-field lines so the daily / weekly summarizer prompt sees them.
- `tests/test_stock_memo.py` covers the new sections with bundle fixtures.
- New `tests/test_financial_reports_bundle_context.py` covers context text shape.

## Capabilities

### Modified Capabilities
- `stock-memo`: Memo now includes transcript / insider / 13F / short-interest / macro sections.
- `financial-snapshot-bundle-context`: Context summary now includes the four new structured fields when present.

## Impact

- Affected code: `financial_reports.py` (text only, no schema), `stock_memo.py`, two test files.
- No new RSS feeds, no new ingest modules, no schema changes.
