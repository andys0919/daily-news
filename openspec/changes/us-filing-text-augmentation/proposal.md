## Why

The current U.S. pipeline captures structured SEC facts but still misses the most useful free textual signal in filing packages: management outlook, guidance wording, and notable capital allocation language. We need a filing-text layer so official U.S. snapshots contain both numbers and the most relevant free-text clues.

## What Changes

- Fetch the primary SEC filing document for the selected report package and extract a compact filing excerpt.
- Derive a guidance / outlook summary from filing text using deterministic keyword-based extraction.
- Persist filing text highlights with the financial snapshot and surface them in prompt and report context.

## Capabilities

### New Capabilities
- `us-filing-text-highlights`: Extract filing excerpts and guidance summaries from free SEC filing documents.

### Modified Capabilities
- `us-official-financial-facts`: Extend stored U.S. snapshots to include filing-text highlights alongside structured metrics.
- `article-financial-augmentation`: Include filing-text highlights in article and memo financial context when available.
- `financial-report-highlights`: Show U.S. filing text highlights in user-facing financial highlight sections when present.

## Impact

- Affected code: `earnings_data.py`, `financial_reports.py`, `summarizer.py`, report rendering, and tests.
- External systems: SEC filing archive documents referenced from submissions metadata.
