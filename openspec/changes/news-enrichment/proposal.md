## Why

The current pipeline mostly summarizes RSS titles and short feed descriptions, which caps memo quality even when the source mix is strong. We need richer article bodies and structured event metadata so ranking, de-duplication, and synthesis operate on facts instead of blurbs.

## What Changes

- Add additive article schema migration to persist source metadata, extraction status, enriched body text, and event intelligence.
- Introduce selective article-page enrichment for high-value sources so the pipeline can capture canonical URL, publisher, author, published timestamp, and body text.
- Add event intelligence that extracts entities, classifies event type, and builds a stable event key for cross-source clustering.
- Upgrade summary and memo context assembly to prefer enriched body text and structured metadata over raw RSS snippets.

## Capabilities

### New Capabilities
- `enriched-article-ingestion`: Persist richer article records and selectively fetch article pages for high-signal content.
- `article-event-intelligence`: Derive entities and event keys from enriched article content and use them in downstream memo preparation.

### Modified Capabilities

## Impact

- Affected code: `crawler.py`, `summarizer.py`, `main.py`, tests, and new enrichment utilities.
- Affected data: SQLite article schema, persisted JSON metadata, and article hydration path.
- Affected dependencies: HTML parsing and structured metadata extraction library support.
