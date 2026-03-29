## ADDED Requirements

### Requirement: Article storage preserves enrichment metadata
The system SHALL persist article source metadata, extraction metadata, and enriched body text in the primary article store without breaking existing rows.

#### Scenario: Existing database migrates additively
- **WHEN** the crawler initializes against a database created before this change
- **THEN** the system SHALL add the missing article columns without dropping existing data

#### Scenario: New article saves enriched fields
- **WHEN** the crawler saves an enriched article
- **THEN** the stored row SHALL include source metadata, extraction status, and enriched body text for later hydration

#### Scenario: Legacy article hydrates safely
- **WHEN** `get_recent_articles()` reads a row that predates enrichment
- **THEN** the returned article SHALL populate new fields with safe defaults instead of failing

### Requirement: High-signal articles receive selective page enrichment
The system SHALL fetch and parse article pages for selected high-signal items and keep RSS content as fallback when extraction fails.

#### Scenario: Source qualifies for enrichment
- **WHEN** an article comes from a qualifying source or matches a high-signal event heuristic
- **THEN** the crawler SHALL attempt to fetch the article page and extract canonical metadata and body text

#### Scenario: Extraction fails
- **WHEN** the article page cannot be fetched or parsed into a usable body
- **THEN** the crawler SHALL keep the RSS-derived summary, mark extraction as failed, and continue the run

## ADDED Requirements

### Requirement: Prompt assembly prefers enriched article bodies
The summarizer SHALL prefer enriched article body text over RSS summaries when building summary and memo prompts.

#### Scenario: Article has body text
- **WHEN** the prompt builder receives an article with enriched body text
- **THEN** it SHALL use that body text as the primary article content in the prompt

#### Scenario: Article lacks body text
- **WHEN** the prompt builder receives an article without enriched body text
- **THEN** it SHALL fall back to the RSS summary and existing title fallback behavior
