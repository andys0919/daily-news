## Why

Financial facts now exist in the pipeline, but Taiwan coverage is still narrow, period selection is single-snapshot only, and the report output barely surfaces those facts to the user. We need broader Taiwan issuer coverage plus a better way to merge and display financial snapshots so the new data materially improves the report.

## What Changes

- Expand Taiwan financial ingestion beyond listed-company general industry to include financial, securities, holding-company, insurance, and diversified-industry statement endpoints.
- Add period-aware financial snapshot selection so prompt and report layers can combine the latest quarterly report with the latest monthly revenue snapshot when both exist.
- Render financial highlights in the HTML and Telegram outputs so users can see the official facts directly instead of only through memo prose.

## Capabilities

### New Capabilities
- `financial-report-highlights`: Build report-ready highlight bundles from stored financial snapshots and surface them in HTML and Telegram.

### Modified Capabilities
- `tw-official-financial-facts`: Expand Taiwan issuer coverage across additional listed-company industry schemas and preserve compatible quarterly snapshots.
- `article-financial-augmentation`: Use period-aware snapshot bundles instead of a single latest report when enriching article and memo context.
- `tw-financial-augmentation`: Use period-aware snapshot bundles instead of a single latest report when enriching article and memo context.

## Impact

- Affected code: `tw_financials.py`, `financial_reports.py`, `summarizer.py`, `html_generator.py`, report template, and tests.
- External systems: additional TWSE OpenAPI endpoints for listed-company sector financial statements.
- User-visible output: new financial highlight sections in daily reports.
