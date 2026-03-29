## ADDED Requirements

### Requirement: Earnings-related article context includes official facts when available
The system SHALL attach filing-derived financial context to relevant article and memo inputs when a matching official snapshot exists.

#### Scenario: Earnings article has matching financial snapshot
- **WHEN** an article is classified as an earnings or filing event and its issuer matches a stored financial report snapshot
- **THEN** the prompt context SHALL include the official financial facts summary for that issuer-period

#### Scenario: No official snapshot exists
- **WHEN** an article has no matching stored financial report snapshot
- **THEN** the prompt context SHALL omit the augmentation and continue with article evidence only

### Requirement: Report runs refresh candidate issuer facts
The main report pipeline SHALL refresh official U.S. financial snapshots for candidate issuers before final memo generation.

#### Scenario: Candidate issuers are discovered
- **WHEN** the report run detects U.S. issuers from article entities or configured symbols
- **THEN** it SHALL attempt a bounded refresh of official financial snapshots for those issuers

#### Scenario: SEC refresh errors
- **WHEN** the SEC refresh encounters network or parsing failures for one issuer
- **THEN** the report run SHALL record the failure and continue refreshing the remaining issuers
