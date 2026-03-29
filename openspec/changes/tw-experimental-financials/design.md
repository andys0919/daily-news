## Context

TWSE now publishes several machine-readable financial datasets through OpenAPI, including listed-company income statements, balance sheets, and monthly revenue. This is sufficient for a first Taiwan facts pipeline, but coverage varies by company type and the schema differs across industry groups, so the integration must remain explicit about confidence and supported metrics.

## Goals / Non-Goals

**Goals:**
- Build a free Taiwan issuer facts path from official TWSE OpenAPI datasets.
- Normalize listed-company revenue and core statement metrics into the shared financial report store.
- Reuse the article and memo augmentation path introduced for U.S. official facts.
- Label Taiwan facts with clear provenance and confidence metadata.

**Non-Goals:**
- Cover every OTC, emerging, or non-listed issuer in the first version.
- Parse every Taiwan filing or PDF from MOPS.
- Guarantee a full cash-flow statement for every issuer and industry type.

## Decisions

### Decision: use TWSE OpenAPI as the primary Taiwan source
The OpenAPI provides stable JSON endpoints and avoids scraping HTML or PDFs for the initial implementation. We will use monthly revenue plus listed-company income statement and balance sheet datasets for supported industries.

Alternative considered:
- MOPS HTML/PDF scraping first. Rejected because it is noisier, harder to test, and unnecessary now that JSON endpoints are available.

### Decision: normalize Taiwan snapshots into the shared `financial_reports` table
Keeping U.S. and Taiwan snapshots in one normalized store allows a single augmentation path in the summarizer while still differentiating provenance with market and confidence fields.

Alternative considered:
- Separate Taiwan-only storage. Rejected because it would duplicate join and query logic.

### Decision: keep Taiwan confidence explicit
Taiwan data will be stored with `market=tw` and a source confidence marker such as `official-openapi` or `experimental-limited`. This lets prompts use the facts while preserving the distinction from SEC structured data.

Alternative considered:
- Treat Taiwan and U.S. facts identically. Rejected because coverage and schema consistency differ materially.

## Risks / Trade-offs

- [Risk] Different TWSE industry endpoints expose different field names. → Mitigation: begin with general-industry listed-company endpoints and leave unsupported schemas empty instead of guessing.
- [Risk] Some Taiwan articles mention OTC or non-listed issuers. → Mitigation: resolve only supported listed-company codes and skip others safely.
- [Risk] Monthly revenue and quarterly statements update on different cadences. → Mitigation: store them as separate snapshot types and surface the freshest compatible facts.

## Migration Plan

1. Add a TWSE OpenAPI client and normalize the listed-company datasets we can support reliably.
2. Extend the shared financial report helpers to accept Taiwan market snapshots.
3. Refresh Taiwan candidate issuers during the report run.
4. Reuse financial augmentation in summarizer context with provenance-aware summaries.

## Open Questions

- Broader Taiwan coverage through MOPS or OTC open data remains a follow-on enhancement after the listed-company JSON path is proven.
