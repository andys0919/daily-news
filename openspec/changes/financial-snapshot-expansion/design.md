## Context

The project now stores structured U.S. and Taiwan financial snapshots, but Taiwan quarterly coverage only uses one industry schema, `get_latest_financial_report()` only returns a single row, and the rendered report still hides most of the new financial facts behind prompt context. This change turns the stored data into broader coverage and visible output.

## Goals / Non-Goals

**Goals:**
- Cover the main listed-company Taiwan statement schemas exposed by TWSE OpenAPI.
- Provide a period-aware bundle that can return both the latest quarterly snapshot and the latest monthly revenue snapshot for an issuer.
- Expose the highest-signal financial facts directly in HTML and Telegram outputs.

**Non-Goals:**
- Build full cash-flow coverage for Taiwan through MOPS scraping in this iteration.
- Add paid consensus data or estimate-based beat/miss logic.
- Redesign the entire report layout.

## Decisions

### Decision: support multiple listed-company Taiwan statement endpoints with a first-match issuer lookup
TWSE OpenAPI splits quarterly statement schemas by industry. We will fetch the relevant listed-company endpoints and pick the first matching row set for each issuer. This improves coverage materially without introducing a separate schema per issuer in downstream code.

Alternative considered:
- Continue using only the general-industry endpoints. Rejected because it excludes major sectors such as financials and insurers.

### Decision: add a snapshot bundle helper instead of replacing the existing single-report lookup
Some callers still only need one snapshot. A new bundle helper can return `quarterly`, `monthly_revenue`, and a preformatted summary while preserving backwards-compatible single-report access.

Alternative considered:
- Change `get_latest_financial_report()` to return merged results. Rejected because it would silently break existing callers and tests.

### Decision: render a compact financial highlights section rather than a large statement table
The report should surface revenue, EPS, margins, and month-over-month / year-over-year revenue context in a small card so the user can scan it quickly. This is enough to prove the value of the facts pipeline without turning the report into a spreadsheet.

Alternative considered:
- Render full statement rows. Rejected because it would add noise and poor mobile readability.

## Risks / Trade-offs

- [Risk] Taiwan issuers may match more than one statement schema over time. → Mitigation: use a deterministic endpoint order and keep payload provenance in stored snapshots.
- [Risk] Financial cards can overwhelm the memo if too many issuers are shown. → Mitigation: cap highlights to the highest-signal issuers already present in the article set.
- [Risk] Monthly revenue and quarterly reports can point to different periods. → Mitigation: label each field with its period and keep the bundle explicit rather than pretending they are the same report.

## Migration Plan

1. Expand TWSE endpoint coverage and adjust refresh logic.
2. Add bundled snapshot selection helpers in `financial_reports.py`.
3. Update prompt builders to use bundled financial summaries.
4. Render bundled highlights in HTML and Telegram.

## Open Questions

- None blocking. Taiwan cash-flow coverage remains a separate follow-up because it requires a different source path than the current TWSE OpenAPI statement set.
