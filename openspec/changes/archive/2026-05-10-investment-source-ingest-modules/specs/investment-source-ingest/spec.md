## ADDED Requirements

### Requirement: Four new ingest modules expose pure-Python fetchers
The system SHALL expose four new modules — `ir_materials`, `insider_holdings`, `short_interest`, `macro_data` — at the repo root, each providing fetcher / aggregator functions that return typed dataclass lists.

#### Scenario: ir_materials returns IRMaterial dataclasses
- **WHEN** calling `ir_materials.fetch_us_transcripts("NVDA")` with an injected fixture HTML payload
- **THEN** the function SHALL return a list of `IRMaterial` whose `ticker == "NVDA"` and `body_text` is non-empty

#### Scenario: insider_holdings returns InsiderTrade dataclasses
- **WHEN** calling `insider_holdings.fetch_us_form4_recent("AAPL")` with an injected fixture XML payload
- **THEN** the function SHALL return a list of `InsiderTrade` with non-zero `shares` and a parsed `transaction_date`

#### Scenario: short_interest returns ShortInterestRow dataclasses
- **WHEN** calling `short_interest.fetch_us_finra_short_interest("TSLA")` with an injected fixture CSV payload
- **THEN** the function SHALL return a list of `ShortInterestRow` with `short_interest > 0`

#### Scenario: macro_data aggregates hyperscaler capex
- **WHEN** calling `macro_data.aggregate_hyperscaler_capex()` against a SQLite DB with capex rows for MSFT, GOOG, AMZN, META
- **THEN** the function SHALL return a `CapexAggregate` whose `total_usd` equals the sum across the four tickers and whose `tickers_included` lists those four

### Requirement: Phase 2 modules do not write new SQLite tables
The system SHALL keep new ingest results in-memory dataclasses only. Persistence to new tables is deferred to Phase 3.

#### Scenario: ingest functions do not touch new tables
- **WHEN** any Phase 2 fetcher / aggregator function returns
- **THEN** no `CREATE TABLE` or `INSERT INTO` statement targeting `issuer_materials`, `insider_transactions`, `holdings_snapshots`, or `short_interest_snapshots` SHALL have been executed

### Requirement: main.py runs eight parallel background channels
The system SHALL run the existing four financial-data channels and the four new ingest channels in parallel during Step 2.5 of the main pipeline.

#### Scenario: Step 2.5 prints stats for all eight channels
- **WHEN** running `python main.py --hours 24 --report-type daily --no-summary`
- **THEN** the smoke output SHALL include the count line "US ... / TW ... / TPEX ... / MOPS ... / IR ... / Insider ... / Short ... / Macro ..."
