## Context

The MOPS SPA now exposes JSON APIs for listed-company income statements, balance sheets, and cash-flow statements. This is a cleaner and more complete official source than the current TWSE OpenAPI path for listed-company quarterly data, especially for operating cash flow and capex.

## Goals / Non-Goals

**Goals:**
- Ingest MOPS quarterly financial JSON for listed-company issuers.
- Capture cash flow, balance sheet, and income statement data in one normalized quarterly snapshot.
- Prefer MOPS quarterly snapshots in downstream Taiwan bundles.

**Non-Goals:**
- Replace TWSE monthly revenue data.
- Support every MOPS feature page beyond the quarterly statement APIs.
- Add OTC / ESB coverage through MOPS in this iteration.

## Decisions

### Decision: treat MOPS as the preferred listed-company quarterly source
TWSE OpenAPI still covers a broad set of quarterly fields, but MOPS adds direct cash flow and fuller official statement data. We will persist both when useful, but downstream bundle selection will prefer MOPS for quarterly Taiwan snapshots.

### Decision: map the MOPS JSON tables by row label
The MOPS APIs return row-oriented tables, not stable field IDs. The parser will normalize known row labels to the fields we need and keep the raw table JSON in `payload_json`.

## Risks / Trade-offs

- [Risk] MOPS row labels may vary slightly across company types. → Mitigation: use multiple alias labels per normalized metric and keep parsing defensive.
- [Risk] The SPA API may evolve. → Mitigation: isolate it in `mops_financials.py` and keep tests around real row-label examples.
