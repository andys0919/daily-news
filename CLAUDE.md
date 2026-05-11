# daily-news Agent Guide

This repository is a Taiwan/U.S. equity news and official-data pipeline.
Agents working in this repo should treat it as a data-collection and memo-generation system first, not just a news summarizer.

## What This Repo Supports

The repo currently supports five major query types:

1. Broad market / sector news search from RSS and article enrichment
2. Official financial snapshot lookup for TW and US issuers
3. Issuer-first stock memo generation for single names such as `2330` or `NVDA`
4. Daily / weekly HTML report generation
5. **Investment dashboard (web/)** — single-page Astro site at `https://invest.aihost.dev/` (cloudflared tunnel) showing: today takeaway · per-stock Scorecard · guidance feed · analyst views · revenue pulse · company internal data · SEC filing excerpts

When a user asks "can we get X?" or "what data do we have for this stock?", check the official data paths before assuming the answer depends on generic news.

## Investment Dashboard

The `web/` directory contains a static Astro site that consumes JSON exported by [`dashboard_export.py`](dashboard_export.py).

- Source: `web/src/pages/index.astro` is the single master page; `web/src/pages/stocks/[ticker].astro` generates per-ticker pages for all tickers with ≥3 articles or ≥1 financial report (currently 161 pages).
- Data: `web/src/data/{overview,guidance,fundamentals,tickers,coverage,events,news,decisions,watchlist}.json` + `web/src/data/stocks/{TICKER}.json`.
- Refresh:
  ```bash
  bash launchd/export-dashboard-data.sh    # re-export JSON
  cd web && npm run build                  # rebuild dist/
  ```
- Deployment: served by `com.dailynews.dashboard-server` (Python `http.server` on `127.0.0.1:8055`) proxied via `com.dailynews.cloudflared` tunnel to `invest.aihost.dev`. Config in `~/.cloudflared/dailynews-aihost.yml`.
- Tests: [`tests/test_dashboard_export.py`](tests/test_dashboard_export.py).

## Key Commands

Daily report:

```bash
uv run --with-requirements requirements.txt --python python3 python main.py --hours 24 --report-type daily
```

Weekly report:

```bash
uv run --with-requirements requirements.txt --python python3 python main.py --hours 168 --report-type weekly
```

Fetch / refresh without LLM:

```bash
uv run --with-requirements requirements.txt --python python3 python main.py --hours 24 --report-type daily --no-summary
```

Single-stock memo:

```bash
uv run --with-requirements requirements.txt --python python3 python stock_memo.py --ticker 2330 --market tw
uv run --with-requirements requirements.txt --python python3 python stock_memo.py --ticker NVDA --market us
```

Skip network refresh and use only existing SQLite snapshots:

```bash
uv run --with-requirements requirements.txt --python python3 python stock_memo.py --ticker NVDA --market us --no-refresh-official-data
```

## Where Data Lives

SQLite:

- `data/news.db`

Main tables:

- `articles`
- `financial_reports`
- `sec_issuer_cache`

Generated outputs:

- HTML reports: `data/reports/`
- Stock memos: `data/memos/`
- Launchd logs: `data/logs/`

## Supported Search / Lookup Paths

### 1. News Search

Primary module:

- [`crawler.py`](/Users/andy/Code/projects/telegram-bot/daily-news/crawler.py)

What it can search:

- `💰 財經與總經`
- `🌏 地緣政治與科技政策`
- `🔬 半導體與硬體`
- `🏢 科技廠動態`
- `🧠 AI 研究與突破`
- `🛠️ AI 工具與實戰`
- `🧭 深度觀點與分析`
- `🔥 X 社群熱議`

Configured sources live in:

- [`config.yaml`](/Users/andy/Code/projects/telegram-bot/daily-news/config.yaml)

Persisted article fields include:

- `title`
- `summary`
- `link`
- `source`
- `category`
- `published`
- `body_text`
- `publisher`
- `author`
- `companies`
- `tickers`
- `event_type`
- `event_key`

Important note:

- The repo does not only store RSS headlines. It also stores enriched article body text and issuer/event metadata.
- If a user asks for company-related news, prefer searching `tickers`, `companies`, and `event_type`, not just title keywords.

### 2. TW Official Financial Data

#### TWSE OpenAPI

Primary module:

- [`tw_financials.py`](/Users/andy/Code/projects/telegram-bot/daily-news/tw_financials.py)

Current official endpoints already wired in:

- Monthly revenue:
  - `https://openapi.twse.com.tw/v1/opendata/t187ap05_L`
- Listed-company income statements by industry bucket:
  - `t187ap06_L_ci`
  - `t187ap06_L_basi`
  - `t187ap06_L_bd`
  - `t187ap06_L_fh`
  - `t187ap06_L_ins`
  - `t187ap06_L_mim`
- Listed-company balance sheets by industry bucket:
  - `t187ap07_L_ci`
  - `t187ap07_L_basi`
  - `t187ap07_L_bd`
  - `t187ap07_L_fh`
  - `t187ap07_L_ins`
  - `t187ap07_L_mim`

What this path can provide:

- Monthly revenue
- Quarterly revenue
- Gross profit
- Operating income
- Net income
- EPS
- Basic balance-sheet context depending on source bucket

This is best for:

- Listed TW names
- Fast structured pulls
- Monthly revenue and quarterly numbers

#### MOPS API

Primary module:

- [`mops_financials.py`](/Users/andy/Code/projects/telegram-bot/daily-news/mops_financials.py)

Current official endpoints already wired in:

- `https://mops.twse.com.tw/mops/api/t164sb03`
- `https://mops.twse.com.tw/mops/api/t164sb04`
- `https://mops.twse.com.tw/mops/api/t164sb05`

What this path can provide:

- Quarterly revenue
- Operating income
- Net income
- EPS
- Operating cash flow
- Capex proxy from cash flow statement
- Filing excerpt assembled from balance sheet / cash flow

This is best for:

- Listed TW names when you want richer quarterly context than TWSE OpenAPI alone
- Priority source for TW listed quarterly bundles

Important current behavior:

- Shared bundle logic prefers `mops-api` over TWSE OpenAPI for TW listed quarterly data.

#### TPEx / OTC / Emerging

Primary module:

- [`tpex_financials.py`](/Users/andy/Code/projects/telegram-bot/daily-news/tpex_financials.py)

Current official paths already wired in:

- Company page:
  - `https://ic.tpex.org.tw/company_basic.php?stk_code={ticker}`
- Parsed JSONP endpoints discovered from the company page:
  - `dsp.tpex.org.tw/storage/company_basic/company_basic.php?...`
  - `dsp.tpex.org.tw/storage/finance_report/company_finance_report.php?...`

What this path can provide:

- Company basic profile
- Quarterly revenue
- Net income / pretax income
- EPS
- Cash flow details
- Audit opinion summary

This is best for:

- OTC / TPEx / emerging-board issuers

### 3. US Official Financial Data

Primary module:

- [`earnings_data.py`](/Users/andy/Code/projects/telegram-bot/daily-news/earnings_data.py)

Current official endpoints already wired in:

- Ticker mapping:
  - `https://www.sec.gov/files/company_tickers.json`
- Filing history:
  - `https://data.sec.gov/submissions/CIK{cik}.json`
- XBRL company facts:
  - `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`

What this path can provide:

- Ticker to CIK resolution
- Recent primary filing selection
- Revenue
- Net income
- Operating income
- Gross profit
- EPS
- Operating cash flow
- Capex
- Free cash flow
- Guidance summary extracted from recent filing text
- Filing excerpt extracted from recent filing text

Forms currently prioritized:

- `10-Q`
- `10-K`
- `20-F`
- `40-F`
- `6-K`
- `8-K`

This is best for:

- Large-cap US earnings memo inputs
- Structured official financial numbers
- Filing-first company lookup

Important limitation:

- SEC gives excellent financial facts and filing text, but this repo does not yet have a generic issuer-IR transcript/slides crawler for all U.S. companies.

### 4. Issuer-First Stock Memo Search

Primary module:

- [`stock_memo.py`](/Users/andy/Code/projects/telegram-bot/daily-news/stock_memo.py)

What it does:

- Normalizes ticker and market
- Optionally refreshes official data
- Loads the latest `financial_reports` snapshot bundle
- Finds related recent articles from `articles`
- Builds a markdown memo with:
  - official financial snapshot
  - official source links
  - related recent news
  - analyst workbench notes

Use this first when the user asks:

- "幫我整理台積電 memo"
- "我想看 NVDA 的官方財報 / filing 重點"
- "這檔股票現在這個 repo 可以抓到什麼"

## Current Data Model

### Articles

The `articles` table includes:

- raw RSS metadata
- enriched article body
- issuer mapping
- event typing

Relevant issuer fields:

- `companies_json`
- `tickers_json`
- `event_type`
- `event_key`

Issuer extraction logic lives in:

- [`news_enrichment.py`](/Users/andy/Code/projects/telegram-bot/daily-news/news_enrichment.py)

Current event types include:

- `earnings`
- `capex`
- `policy`
- `filing`
- `news`

### Financial Reports

The `financial_reports` table stores normalized official snapshots with fields such as:

- `market`
- `ticker`
- `company_name`
- `source_type`
- `form_type`
- `fiscal_year`
- `fiscal_period`
- `period_end`
- `filed_at`
- `revenue`
- `monthly_revenue`
- `net_income`
- `operating_income`
- `gross_profit`
- `eps_diluted`
- `operating_cash_flow`
- `capex`
- `free_cash_flow`
- `guidance_summary`
- `filing_excerpt`
- `payload_json`

Bundle logic lives in:

- [`financial_reports.py`](/Users/andy/Code/projects/telegram-bot/daily-news/financial_reports.py)

The main downstream abstraction is:

- `FinancialSnapshotBundle`

Bundle contents:

- latest quarterly report
- latest monthly revenue report

### Source Preference Rules

Current bundle preference:

- US quarterly: SEC
- TW listed quarterly: MOPS first, then TWSE OpenAPI
- TW OTC / emerging quarterly: TPEx
- TW monthly revenue: TWSE OpenAPI

## What Claude / Agents Should Prefer

When a user asks for:

### "What official data do we have for this stock?"

Preferred order:

1. `stock_memo.py`
2. `financial_reports.py` bundle lookup
3. `articles` search for related event/news context

### "Can we get earnings / filing / guidance?"

Preferred order:

- US:
  1. SEC `companyfacts`
  2. SEC `submissions`
  3. filing text highlights
- TW:
  1. MOPS
  2. TWSE OpenAPI
  3. TPEx if non-listed

### "Can we get investor conference / law-call / presentation materials?"

Current repo support:

- TW:
  - yes, as lookup URLs / official entry points
  - not yet full automatic slide/video harvesting into SQLite
- US:
  - SEC filing links available
  - generic issuer IR transcript/slide harvesting is not yet implemented

So agents should answer precisely:

- "entry points exist" is true
- "full structured transcript/slides already ingested" is generally false

## Current Gaps

The repo does **not** yet provide these as first-class structured assets:

1. TW investor-conference slide files downloaded and stored locally
2. TW investor-conference video metadata stored in SQLite
3. US issuer-IR webcast / transcript / slide crawlers
4. A dedicated `issuer_materials` table
5. LLM-written single-stock investment analysis built on top of `stock_memo.py`

Do not claim those are implemented unless you add them.

## Practical Search Guidance

If you need to inspect stored stock-related data quickly:

Recent article search by ticker/company:

```bash
sqlite3 data/news.db "SELECT published, source, title, tickers_json, companies_json, event_type FROM articles WHERE tickers_json LIKE '%NVDA%' OR companies_json LIKE '%NVIDIA%' ORDER BY published DESC LIMIT 20;"
```

Latest official financial snapshots:

```bash
sqlite3 data/news.db "SELECT market, ticker, source_type, form_type, fiscal_year, fiscal_period, filed_at, revenue, monthly_revenue, eps_diluted, guidance_summary FROM financial_reports WHERE ticker='NVDA' ORDER BY filed_at DESC;"
```

Generate a memo:

```bash
uv run --with-requirements requirements.txt --python python3 python stock_memo.py --ticker NVDA --market us
```

## Files to Read First

If you are orienting yourself to this repo, read in this order:

1. [`README.md`](/Users/andy/Code/projects/telegram-bot/daily-news/README.md)
2. [`docs/architecture.md`](/Users/andy/Code/projects/telegram-bot/daily-news/docs/architecture.md)
3. [`stock_memo.py`](/Users/andy/Code/projects/telegram-bot/daily-news/stock_memo.py)
4. [`financial_reports.py`](/Users/andy/Code/projects/telegram-bot/daily-news/financial_reports.py)
5. [`earnings_data.py`](/Users/andy/Code/projects/telegram-bot/daily-news/earnings_data.py)
6. [`tw_financials.py`](/Users/andy/Code/projects/telegram-bot/daily-news/tw_financials.py)
7. [`tpex_financials.py`](/Users/andy/Code/projects/telegram-bot/daily-news/tpex_financials.py)
8. [`mops_financials.py`](/Users/andy/Code/projects/telegram-bot/daily-news/mops_financials.py)
9. [`news_enrichment.py`](/Users/andy/Code/projects/telegram-bot/daily-news/news_enrichment.py)

## If You Extend This Repo

If you add more issuer-search capability, keep these principles:

1. Prefer official sources before third-party summaries
2. Normalize into the existing `financial_reports` / bundle model where possible
3. Keep TW and US paths explicit instead of mixing them in one scraper
4. Be precise about whether a feature is:
   - fully ingested structured data
   - only a lookup URL
   - only recent news evidence

Do not blur those three states in user-facing answers.
