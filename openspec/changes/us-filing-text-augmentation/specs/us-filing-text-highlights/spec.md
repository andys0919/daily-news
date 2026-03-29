## ADDED Requirements

### Requirement: U.S. filing snapshots include textual highlights when available
The system SHALL extract and persist compact filing text highlights from free SEC filing documents.

#### Scenario: Filing contains guidance language
- **WHEN** the primary filing document includes outlook or guidance wording
- **THEN** the stored financial snapshot SHALL include a normalized guidance summary

#### Scenario: Filing contains no useful highlight
- **WHEN** the filing text does not contain a usable highlight sentence
- **THEN** the financial snapshot SHALL keep text-highlight fields empty without failing the ingestion

### Requirement: Prompt and report context surfaces filing text highlights
The system SHALL include filing text highlights in financial context when a snapshot contains them.

#### Scenario: Filing highlight exists
- **WHEN** a matched financial snapshot contains a filing excerpt or guidance summary
- **THEN** the prompt and report financial context SHALL include that text
