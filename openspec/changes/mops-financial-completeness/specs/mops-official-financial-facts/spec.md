## ADDED Requirements

### Requirement: Listed-company quarterly facts are ingested from official MOPS APIs
The system SHALL ingest official listed-company income statement, balance sheet, and cash-flow data from the MOPS JSON APIs into normalized quarterly financial snapshots.

#### Scenario: Listed-company quarterly APIs return data
- **WHEN** the pipeline queries the MOPS quarterly APIs for a listed-company issuer
- **THEN** it SHALL persist a normalized quarterly financial snapshot including revenue, EPS, balance sheet values, operating cash flow, and capex when available

#### Scenario: Cash flow rows are available
- **WHEN** the MOPS cash-flow API returns operating, investing, and financing cash flow rows
- **THEN** the normalized snapshot SHALL retain operating cash flow and derive capex from property, plant, and equipment acquisition rows when present

#### Scenario: MOPS query fails
- **WHEN** one or more MOPS APIs fail for an issuer
- **THEN** the pipeline SHALL skip that issuer without failing the full report run
