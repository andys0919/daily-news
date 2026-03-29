## ADDED Requirements

### Requirement: Taiwan listed-company facts are ingested from official open data
The system SHALL ingest Taiwan listed-company financial facts from TWSE OpenAPI datasets into normalized issuer snapshots.

#### Scenario: Listed-company monthly revenue is available
- **WHEN** the pipeline resolves a Taiwan listed-company code with monthly revenue data
- **THEN** it SHALL persist the latest monthly revenue snapshot for that issuer

#### Scenario: Listed-company quarterly statements are available
- **WHEN** the pipeline resolves a Taiwan listed-company code with supported income statement and balance sheet data
- **THEN** it SHALL persist a normalized quarterly financial report snapshot for that issuer

#### Scenario: Issuer is unsupported
- **WHEN** the resolved Taiwan issuer is missing from supported TWSE OpenAPI datasets
- **THEN** the pipeline SHALL skip snapshot creation for that issuer without failing the report run

### Requirement: Taiwan snapshots record provenance and confidence
The system SHALL persist Taiwan financial snapshots with explicit source provenance and confidence metadata.

#### Scenario: Snapshot is written
- **WHEN** a Taiwan financial snapshot is stored
- **THEN** it SHALL include market, source type, and confidence metadata that distinguish it from SEC structured facts
