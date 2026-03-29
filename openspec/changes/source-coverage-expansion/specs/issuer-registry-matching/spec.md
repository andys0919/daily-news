## ADDED Requirements

### Requirement: Article issuer matching uses a reusable issuer registry
The system SHALL use a reusable issuer registry to map common company mentions to normalized company/ticker pairs.

#### Scenario: Taiwan alias resolves without explicit ticker
- **WHEN** article text mentions a supported Taiwan company name without a ticker
- **THEN** the system SHALL infer the matching Taiwan ticker from the issuer registry

#### Scenario: U.S. alias resolves without explicit ticker
- **WHEN** article text mentions a supported U.S. company name without a ticker
- **THEN** the system SHALL infer the matching U.S. ticker from the issuer registry
