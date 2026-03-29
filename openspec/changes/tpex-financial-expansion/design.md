## Context

The TPEX industry-value-chain platform exposes per-company financial report data through a JSONP endpoint that already contains cash flow, balance sheet, revenue, EPS, and auditor-opinion details for OTC / ESB issuers. This is a stronger free path than trying to infer OTC coverage from listed-company TWSE schemas.

## Goals / Non-Goals

**Goals:**
- Ingest official OTC / ESB company financial facts from TPEX-hosted endpoints.
- Normalize those facts into the shared financial report store.
- Reuse existing bundle and report-highlight logic for OTC / ESB issuers.

**Non-Goals:**
- Replace TWSE listed-company ingestion.
- Build perfect industry-chain metadata extraction from the broader TPEX site.
- Support every TPEX company-info page variant immediately.

## Decisions

### Decision: use the TPEX finance-report JSONP endpoint as the primary OTC source
The company page reveals a dedicated finance-report endpoint that already contains structured report objects. We will call that endpoint directly instead of scraping rendered HTML tables.

### Decision: persist OTC / ESB snapshots into the shared store with `market=tw`
The data still belongs to Taiwan issuers, so it should participate in the same Taiwan bundle path while remaining distinguishable through `source_type`.

## Risks / Trade-offs

- [Risk] TPEX JSONP schema may evolve. → Mitigation: keep parsing defensive and persist raw payload fragments for debugging.
- [Risk] Some tickers may not resolve through the company page path. → Mitigation: treat the TPEX path as additive coverage and skip unresolved issuers safely.
