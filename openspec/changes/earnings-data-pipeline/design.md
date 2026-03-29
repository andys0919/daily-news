## Context

The repo already tracks market prices and article summaries, but it has no primary-source financial facts store. For U.S. issuers, SEC provides free machine-readable ticker mappings, filing history, and XBRL company facts that are suitable for building a lightweight official earnings pipeline.

## Goals / Non-Goals

**Goals:**
- Build a free U.S. issuer pipeline using SEC data only.
- Persist normalized filing snapshots that the summarizer can query quickly.
- Derive a compact, memo-friendly financial fact summary from official filings.
- Limit run-time cost through caching and issuer caps.

**Non-Goals:**
- Provide analyst consensus, beat/miss versus street estimates, or paid transcript feeds.
- Cover every SEC filing type in the first iteration.
- Replace media reporting with raw filing text in the final user output.

## Decisions

### Decision: store filing snapshots in a dedicated `financial_reports` table
Financial facts have a different lifecycle from articles and need issuer- and period-based lookups. A dedicated table keeps the schema explicit and avoids stuffing unrelated financial metrics into article rows.

Alternative considered:
- Store filing data inside article metadata JSON. Rejected because a single filing should be reusable across multiple articles and report runs.

### Decision: derive a normalized report snapshot from SEC companyfacts and submissions
`submissions` provides filing recency and form metadata, while `companyfacts` provides structured XBRL metrics. We will combine them into one report snapshot per issuer-period using a fixed metric mapping and derive free cash flow where enough inputs exist.

Alternative considered:
- Parse filing HTML exhibits directly. Rejected for the initial implementation because companyfacts already provides the core metrics more reliably.

### Decision: trigger the U.S. pipeline from article entities and curated symbols
The report should refresh facts for issuers that matter to the current run. Candidate issuers will come from extracted article entities plus configured watchlist symbols, capped per run to keep SEC traffic reasonable.

Alternative considered:
- Pull facts for all SEC issuers each run. Rejected as wasteful and unnecessary.

### Decision: financial augmentation remains additive
If no filing snapshot exists, article and memo generation must continue using article evidence only. The facts pipeline enriches report quality but does not become a hard dependency for report generation.

Alternative considered:
- Require filing facts for all earnings articles. Rejected because some companies or forms will not resolve cleanly in every run.

## Risks / Trade-offs

- [Risk] SEC metric taxonomies differ across issuers. → Mitigation: use ordered fallback metric maps and keep raw payload JSON for debugging.
- [Risk] Filing dates and companyfacts frames do not line up perfectly. → Mitigation: choose the latest fact set consistent with the selected filing period and persist provenance.
- [Risk] SEC rate limits can slow runs. → Mitigation: use caching, caps, and a dedicated user agent with bounded retry logic.

## Migration Plan

1. Add the structured financial reports table and issuer mapping cache support.
2. Implement SEC issuer resolution, submissions fetch, and companyfacts mapping.
3. Integrate background refresh into the main report run.
4. Update summary and memo context assembly to surface official facts when present.

## Open Questions

- Guidance extraction from official filings remains best-effort and will stay outside the first metric set unless clearly available from structured or nearby article evidence.
