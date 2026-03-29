## ADDED Requirements

### Requirement: Report output surfaces bundled financial highlights
The system SHALL build compact financial highlight entries from stored financial snapshots and render them in user-facing outputs.

#### Scenario: HTML report has bundled highlights
- **WHEN** the report includes articles tied to issuers with stored financial snapshot bundles
- **THEN** the HTML output SHALL render a financial highlights section showing the highest-signal issuers and their key metrics

#### Scenario: Telegram summary has bundled highlights
- **WHEN** the Telegram text summary includes issuers with stored financial snapshot bundles
- **THEN** the summary SHALL include a compact financial highlights section within length limits

#### Scenario: No financial bundles exist
- **WHEN** no issuer in the report has a stored financial snapshot bundle
- **THEN** the report and Telegram outputs SHALL omit the financial highlights section
