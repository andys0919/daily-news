## ADDED Requirements

### Requirement: Articles expose normalized event intelligence
The system SHALL derive normalized event metadata for each article, including extracted entities, event type, and a reusable event key.

#### Scenario: Earnings-style article is classified
- **WHEN** an article title or body indicates an earnings or filing event
- **THEN** the system SHALL classify it with an event type that downstream pipelines can match

#### Scenario: Entity metadata is persisted
- **WHEN** the system extracts company names or tickers from an article
- **THEN** it SHALL persist them in normalized article metadata for later reuse

#### Scenario: Event key falls back safely
- **WHEN** entity extraction is insufficient to build a rich event key
- **THEN** the system SHALL fall back to a deterministic title-based key instead of leaving the event unclusterable

### Requirement: Daily memo clustering uses event metadata
The daily memo preparation flow SHALL use normalized event keys before falling back to title fingerprint clustering.

#### Scenario: Multiple sources reference the same event
- **WHEN** two or more articles share a normalized event key
- **THEN** the daily memo clustering step SHALL group them into one event cluster

#### Scenario: Event metadata is unavailable
- **WHEN** an article lacks normalized event metadata
- **THEN** the daily memo clustering step SHALL continue using the title fingerprint fallback
