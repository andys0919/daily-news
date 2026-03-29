## MODIFIED Requirements

### Requirement: Taiwan financial facts augment relevant article context
The system SHALL augment Taiwan-related article and memo context with period-aware Taiwan financial snapshot bundles when available.

#### Scenario: Taiwan issuer bundle exists
- **WHEN** an article references a supported Taiwan issuer and recent quarterly and/or monthly revenue snapshots exist
- **THEN** the prompt context SHALL include the normalized Taiwan financial bundle summary for that issuer

#### Scenario: Taiwan issuer snapshot does not exist
- **WHEN** no matching Taiwan financial snapshot exists for an article
- **THEN** the prompt context SHALL continue without augmentation
