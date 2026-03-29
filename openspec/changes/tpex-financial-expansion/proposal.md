## Why

Taiwan listed-company coverage is now decent, but OTC and emerging-company coverage is still missing, even though TPEX exposes free official company financial data through its industry-value-chain platform. We need to ingest those official OTC/ESB figures so Taiwan financial coverage is not limited to TWSE-listed issuers.

## What Changes

- Add a TPEX financial facts client that ingests official OTC / ESB company financial snapshots from TPEX-hosted finance-report endpoints.
- Capture OTC / ESB cash flow, balance sheet, revenue, EPS, and audit-opinion details where available.
- Extend financial bundles and report highlights so OTC / ESB issuers can participate in the same augmentation path as TWSE-listed issuers.

## Capabilities

### New Capabilities
- `tpex-official-financial-facts`: Ingest official OTC / ESB company financial data from TPEX-hosted finance-report endpoints.

### Modified Capabilities
- `tw-financial-augmentation`: Include TPEX OTC / ESB bundles in Taiwan financial augmentation.
- `financial-report-highlights`: Render OTC / ESB financial highlights when those issuers appear in report articles.

## Impact

- Affected code: new TPEX ingestion module, `financial_reports.py`, `summarizer.py`, report rendering, and tests.
- External systems: `ic.tpex.org.tw` and `dsp.tpex.org.tw` official TPEX financial data endpoints.
