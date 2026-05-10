## ADDED Requirements

### Requirement: Four new SQLite tables persist Phase 2 ingest results
The system SHALL define four new SQLite tables — `issuer_materials`, `insider_transactions`, `holdings_snapshots`, `short_interest_snapshots` — created via idempotent `CREATE TABLE IF NOT EXISTS`, and SHALL provide `save_*` functions for each.

#### Scenario: re-initialising the DB does not duplicate or drop rows
- **WHEN** `init_financial_report_store(db_path)` is called twice on the same DB
- **THEN** the four new tables SHALL exist exactly once with no row loss

#### Scenario: save_issuer_material round-trips
- **WHEN** writing an `IRMaterial` payload via `save_issuer_material(db_path, payload)` and then reading via `get_recent_issuer_materials`
- **THEN** the read row SHALL contain identical `ticker`, `material_type`, `title`, `body_text`, `source_url`, `fetched_at`

#### Scenario: save_insider_transaction round-trips
- **WHEN** writing an `InsiderTrade` payload and reading via `get_recent_insider_transactions`
- **THEN** the read row SHALL contain identical `ticker`, `insider_name`, `transaction_date`, `shares`, `price`

#### Scenario: save_holdings_snapshot round-trips
- **WHEN** writing a `Holding` payload and reading via `get_recent_holdings_snapshots`
- **THEN** the read row SHALL contain identical `reporter_cik`, `issuer_name`, `shares`, `value_usd`

#### Scenario: save_short_interest_snapshot round-trips
- **WHEN** writing a `ShortInterestRow` payload and reading via `get_recent_short_interest_snapshots`
- **THEN** the read row SHALL contain identical `ticker`, `period_end`, `short_interest`, `short_interest_ratio`

### Requirement: FinancialSnapshotBundle exposes four new optional structured fields
The system SHALL extend `FinancialSnapshotBundle` with `latest_transcript`, `recent_insider_summary`, `latest_13f`, `short_interest`, all defaulting to `None` so existing consumers stay compatible.

#### Scenario: existing bundle build path still returns
- **WHEN** calling `get_financial_snapshot_bundle` against a DB that has rows in `financial_reports` only
- **THEN** the returned bundle SHALL have `latest_transcript / recent_insider_summary / latest_13f / short_interest == None` and the existing `quarterly / monthly_revenue` populated as before

### Requirement: Phase 2 ingest modules persist when called with _persist=True
The system SHALL persist the dataclass results returned by the Phase 2 `refresh_*` functions when called with the default `_persist=True`.

#### Scenario: refresh_ir_materials persists by default
- **WHEN** calling `refresh_ir_materials_for_articles(articles)` against a DB that already has the new tables
- **THEN** the returned `IRMaterial` items SHALL appear in `issuer_materials` table within the same call
