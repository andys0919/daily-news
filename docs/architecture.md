# Architecture

## Pipeline

1. `crawler.py` 抓 RSS 並把文章存進 SQLite
2. `news_enrichment.py` 補正文、issuer/ticker、event key
3. 財報資料流並行刷新
   - `earnings_data.py` -> SEC
   - `tw_financials.py` -> TWSE OpenAPI
   - `tpex_financials.py` -> TPEX
   - `mops_financials.py` -> MOPS
4. `financial_reports.py` 將不同來源統一成 snapshot / bundle
5. `summarizer.py` 用 article + financial context 生成分類摘要與 daily memo
6. `html_generator.py` / `telegram_sender.py` 輸出報告

## Data Model

### Articles

文章會持久化：

- 原始 RSS 欄位
- enrichment 後 `body_text`
- `source_key / summary_prompt / priority / quality`
- `companies / tickers / event_type / event_key`

### Financial Snapshots

財報統一存成 `financial_reports`：

- `market`
- `ticker`
- `source_type`
- `form_type`
- `fiscal_year / fiscal_period`
- `revenue / EPS / OCF / capex / FCF`
- `guidance_summary / filing_excerpt`

### Bundles

下游讀的是 bundle，不是單一 row：

- 最新季度財報
- 最新月營收
- 根據市場與來源做 source preference

## Source Preference

- 美股季度：SEC
- 台股上市季度：MOPS 優先，TWSE OpenAPI 次之
- 台股上櫃 / 興櫃季度：TPEX
- 台股月營收：TWSE OpenAPI

## Output Philosophy

- Daily：單篇整體 memo 為主
- Weekly：保留分類摘要管線
- HTML / Telegram 都應直接看到財報 highlights，而不是只藏在 prompt 裡
