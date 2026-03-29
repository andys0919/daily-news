## Why

The project now has much better financial data, but article-to-issuer matching is still heuristic and misses many company mentions that do not carry an explicit ticker. We need a stronger issuer registry so more Taiwan and U.S. news can be matched back to the correct financial bundle.

## What Changes

- Add a reusable issuer registry with common aliases, multilingual names, and ticker mappings.
- Use the issuer registry during article event extraction so company and ticker inference is more reliable.
- Prefer financial bundles and caches as additional issuer-matching hints when available.

## Capabilities

### New Capabilities
- `issuer-registry-matching`: Resolve common U.S. and Taiwan issuer mentions from article text into normalized company/ticker pairs.

### Modified Capabilities
- `article-event-intelligence`: Use the issuer registry to improve entity extraction and event-key construction.

## Impact

- Affected code: new issuer registry module, `news_enrichment.py`, tests.
