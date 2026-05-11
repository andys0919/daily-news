## ADDED Requirements

### Requirement: dashboard_export.py produces JSON snapshots
The system SHALL expose `dashboard_export.py` that reads `data/news.db` + `financial_reports` bundles and writes JSON files under `web/src/data/`.

#### Scenario: overview.json contains today's top signals
- **WHEN** running `python dashboard_export.py --output web/src/data/`
- **THEN** `web/src/data/overview.json` SHALL exist with `top_transcripts`, `top_insider_trades`, `top_holdings_changes`, `market_indices`, `watchlist` keys

#### Scenario: stocks/<ticker>.json contains per-stock bundle
- **WHEN** exporting for a ticker present in `financial_reports`
- **THEN** `web/src/data/stocks/<ticker>.json` SHALL contain `bundle`, `recent_news`, `transcripts`, `insider`, `holdings`, `short_interest` keys

### Requirement: Astro project builds locally
The system SHALL provide an Astro project under `web/` that builds via `npm install && npm run build` without errors.

#### Scenario: dist directory contains 5 pages
- **WHEN** running `npm run build` in `web/`
- **THEN** `web/dist/` SHALL contain `index.html`, `news/index.html`, `calendar/index.html`, `decisions/index.html`, plus `stocks/<ticker>/index.html` for each example ticker

### Requirement: Deployment artefacts are templated only
The system SHALL provide `wrangler.toml.template` and `.env.example` with placeholder values, and SHALL NOT contain any real secret.

#### Scenario: no real secrets committed
- **WHEN** searching tracked files for typical secret patterns (real CF token, real account ID, real domain)
- **THEN** only placeholder patterns like `${CF_API_TOKEN}` or `your-domain.com` SHALL appear
