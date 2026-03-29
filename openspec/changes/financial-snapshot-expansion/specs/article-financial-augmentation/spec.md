## MODIFIED Requirements

### Requirement: Earnings-related article context includes official facts when available
The system SHALL attach period-aware financial context to relevant article and memo inputs when matching official snapshots exist.

#### Scenario: Earnings article has matching quarterly snapshot
- **WHEN** an article is classified as an earnings or filing event and its issuer matches a stored quarterly financial report snapshot
- **THEN** the prompt context SHALL include the official quarterly financial facts summary for that issuer-period

#### Scenario: Issuer has quarterly and monthly revenue snapshots
- **WHEN** an article matches an issuer with both a quarterly snapshot and a newer monthly revenue snapshot
- **THEN** the prompt context SHALL include both periods in a merged financial summary instead of dropping the monthly revenue update

#### Scenario: No official snapshot exists
- **WHEN** an article has no matching stored financial report snapshot
- **THEN** the prompt context SHALL omit the augmentation and continue with article evidence only
