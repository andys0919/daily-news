## ADDED Requirements

### Requirement: SEC issuer resolution is cached and reusable
The system SHALL resolve U.S. tickers to SEC issuer identifiers using the official SEC ticker mapping and cache the results for later runs.

#### Scenario: Ticker resolves through official mapping
- **WHEN** the pipeline receives a supported U.S. ticker
- **THEN** it SHALL resolve and cache the issuer CIK and company title from SEC mapping data

#### Scenario: Ticker cannot be resolved
- **WHEN** the pipeline receives a ticker that is absent from SEC mapping data
- **THEN** it SHALL skip issuer refresh for that ticker without failing the report run

### Requirement: Official filing snapshots are persisted
The system SHALL ingest recent SEC filing metadata and structured facts into normalized financial report snapshots.

#### Scenario: Latest 10-Q or 10-K snapshot is available
- **WHEN** submissions and companyfacts data exist for an issuer
- **THEN** the system SHALL persist a financial report snapshot with filing metadata and normalized metrics for the latest supported reporting period

#### Scenario: Free cash flow can be derived
- **WHEN** operating cash flow and capex are both available for a snapshot
- **THEN** the system SHALL persist a derived free cash flow value alongside the raw metrics

#### Scenario: Structured fact is missing
- **WHEN** a target metric is absent from companyfacts
- **THEN** the system SHALL leave that metric empty and continue building the snapshot
