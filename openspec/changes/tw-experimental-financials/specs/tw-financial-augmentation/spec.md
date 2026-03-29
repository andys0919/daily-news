## ADDED Requirements

### Requirement: Taiwan financial facts augment relevant article context
The system SHALL augment Taiwan-related article and memo context with matching Taiwan financial snapshots when available.

#### Scenario: Taiwan issuer snapshot exists
- **WHEN** an article references a supported Taiwan issuer and a recent Taiwan financial snapshot exists
- **THEN** the prompt context SHALL include the normalized Taiwan financial facts summary for that issuer

#### Scenario: Taiwan issuer snapshot does not exist
- **WHEN** no matching Taiwan financial snapshot exists for an article
- **THEN** the prompt context SHALL continue without augmentation

### Requirement: Report runs refresh bounded Taiwan issuer sets
The main report pipeline SHALL refresh Taiwan issuer facts for a bounded set of candidate issuers during report generation.

#### Scenario: Candidate Taiwan issuers are present
- **WHEN** the report run detects Taiwan issuers from article entities or configured Taiwan symbols
- **THEN** it SHALL perform a bounded refresh of Taiwan financial facts before memo synthesis

#### Scenario: TWSE refresh partially fails
- **WHEN** one TWSE dataset fetch fails during refresh
- **THEN** the pipeline SHALL continue using any remaining successful datasets and existing stored snapshots
