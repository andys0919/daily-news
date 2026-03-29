## Context

Existing article extraction recognizes only a small hard-coded alias set. That is enough for the biggest names but not for a wider Taiwan and U.S. universe, especially when company mentions appear without explicit tickers or in mixed Chinese/English forms.

## Goals / Non-Goals

**Goals:**
- Centralize issuer aliases in one registry.
- Improve article-to-ticker mapping for both Taiwan and U.S. names.
- Keep the solution deterministic and lightweight.

**Non-Goals:**
- Full NER or machine-learned entity linking.
- Universal company coverage across all markets.

## Decisions

### Decision: use a registry module instead of growing inline alias dicts
The current alias logic lives inside `news_enrichment.py`. Moving it to a registry module keeps matching focused and makes later coverage additions safer.

### Decision: merge static aliases with cached issuer data
Static aliases cover the high-signal names we care about, while cached SEC/TPEX/TW financial data can add more company names over time.

## Risks / Trade-offs

- [Risk] Alias collisions can map generic names incorrectly. → Mitigation: keep short ambiguous aliases out of the registry and prefer explicit ticker patterns when present.
