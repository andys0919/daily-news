## Why

Taiwan coverage now includes TWSE listed-company schemas and TPEX OTC data, but listed-company cash flow and deeper quarterly fields are still incomplete. The new MOPS API already exposes full income statement, balance sheet, and cash flow JSON, so we should use it to upgrade the completeness of Taiwan listed-company financial bundles.

## What Changes

- Add a MOPS financial client that queries the official `t164sb03/04/05` APIs for listed-company quarterly statements.
- Normalize MOPS income statement, balance sheet, and cash flow data into the shared financial report store.
- Prefer richer MOPS quarterly snapshots over thinner Taiwan quarterly snapshots when both exist for the same issuer and period.

## Capabilities

### New Capabilities
- `mops-official-financial-facts`: Ingest official listed-company quarterly statements from the MOPS JSON APIs.

### Modified Capabilities
- `tw-financial-augmentation`: Prefer richer MOPS-backed Taiwan quarterly bundles when available.
- `financial-report-highlights`: Use the richer Taiwan quarterly bundle fields when rendering report highlights.

## Impact

- Affected code: new `mops_financials.py`, `financial_reports.py`, `main.py`, and tests.
- External systems: `https://mops.twse.com.tw/mops/api/t164sb03`, `t164sb04`, `t164sb05`.
