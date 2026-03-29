## ADDED Requirements

### Requirement: OTC / ESB issuer financial facts are ingested from official TPEX endpoints
The system SHALL ingest official OTC / ESB company financial data from TPEX-hosted finance-report endpoints into normalized Taiwan financial snapshots.

#### Scenario: OTC issuer has finance-report payload
- **WHEN** the pipeline resolves an OTC issuer with a TPEX finance-report payload
- **THEN** it SHALL persist normalized quarterly and cash-flow-capable financial snapshots for that issuer

#### Scenario: Issuer has audit opinion details
- **WHEN** the TPEX finance-report payload contains auditor-opinion metadata
- **THEN** the persisted snapshot SHALL retain those details in its raw payload and summary fields

#### Scenario: TPEX payload is unavailable
- **WHEN** the TPEX company or finance-report payload cannot be fetched
- **THEN** the pipeline SHALL skip that issuer without failing the run
