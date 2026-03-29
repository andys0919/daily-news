## Why

The project tracks Taiwan market news heavily, but it has no structured Taiwan financial facts path to complement that coverage. We need a free TW pipeline that can ingest official TWSE open data into the same report augmentation flow while explicitly handling coverage and schema limitations.

## What Changes

- Add a Taiwan financial facts client built on TWSE OpenAPI financial statement and monthly revenue datasets.
- Normalize Taiwan issuer snapshots into the shared financial reports store with explicit source confidence and coverage metadata.
- Refresh Taiwan financial facts for issuers mentioned in news and configured Taiwan watchlist symbols.
- Surface Taiwan financial facts in article and memo context using the same augmentation path as U.S. official facts.

## Capabilities

### New Capabilities
- `tw-official-financial-facts`: Ingest TWSE official open financial datasets into normalized issuer snapshots.
- `tw-financial-augmentation`: Join Taiwan issuer snapshots back into article and memo context with explicit confidence labeling.

### Modified Capabilities

## Impact

- Affected code: new TWSE ingestion module, `main.py`, `summarizer.py`, tests, and shared financial report helpers.
- External systems: TWSE OpenAPI financial statement and monthly revenue endpoints.
- Operational note: coverage is strongest for listed companies and varies by dataset and industry schema.
