# daily-news

`daily-news` 是一個以繁體中文輸出為主的每日 / 每週新聞摘要與市場 memo 產生器，目標是把台美股相關新聞、官方財報、宏觀資料與高訊號技術來源整理成一份可直接閱讀的報告。

## 目前能力

- 新聞抓取
  - 多分類 RSS 聚合：財經與總經、地緣政治與科技政策、半導體與硬體、科技廠動態、AI 研究與突破、AI 工具與實戰、深度觀點與分析、X 社群熱議
  - 來源健康檢查與暫停機制
  - 文章原文頁 enrichment、事件 key、issuer/ticker 抽取
- 財報與官方資料
  - 美股：SEC `company_tickers.json`、`submissions`、`companyfacts`、filling text highlights
  - 台股上市：TWSE OpenAPI + MOPS API
  - 台股上櫃 / 興櫃：TPEX 官方 company / finance-report 路徑
  - period-aware financial snapshot bundle：季度財報 + 月營收
- 輸出
  - HTML 報告
  - Telegram 文字摘要 + 附件報告
  - 單篇 daily memo 與 AI / GitHub digest

## 專案結構

- `main.py`: 主流程 orchestration
- `crawler.py`: RSS 抓取、文章 schema、SQLite 存取
- `news_enrichment.py`: 原文抽取、事件與 issuer intelligence
- `financial_reports.py`: 財報 snapshot store 與 bundle logic
- `earnings_data.py`: SEC 結構化數字 + filing text
- `tw_financials.py`: TWSE OpenAPI 台股財報
- `tpex_financials.py`: TPEX OTC / 興櫃財報
- `mops_financials.py`: MOPS listed-company 財報
- `summarizer.py`: prompt building、摘要、daily memo
- `html_generator.py`: HTML 報告
- `telegram_sender.py`: Telegram 推送
- `config.yaml`: 來源與市場設定
- `openspec/changes/`: 各次變更的 OpenSpec artifacts

## 快速開始

### 1. 安裝依賴

```bash
uv run --with-requirements requirements.txt --python python3 python -c "import aiohttp, bs4, yfinance"
```

### 2. 執行 daily 報告

```bash
uv run --with-requirements requirements.txt --python python3 python main.py --hours 24 --report-type daily
```

### 3. 執行 weekly 報告

```bash
uv run --with-requirements requirements.txt --python python3 python main.py --hours 168 --report-type weekly
```

### 4. 只做抓取與財務刷新，不跑 LLM

```bash
uv run --with-requirements requirements.txt --python python3 python main.py --hours 24 --report-type daily --no-summary
```

## 環境變數

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `AZURE_OPENAI_URL`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_MODEL`
- `SEC_API_USER_AGENT`

## 測試

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests -v
```

## 免費資料來源

- SEC
- TWSE OpenAPI
- MOPS
- TPEX
- Fed / BLS / FRED / BIS / ECB 等官方 feed
- 各公司 / 技術站官方 blog / newsroom

## OpenSpec

主要變更已用 OpenSpec 記錄在 `openspec/changes/`，包含：

- `news-enrichment`
- `earnings-data-pipeline`
- `tw-experimental-financials`
- `financial-snapshot-expansion`
- `us-filing-text-augmentation`
- `tpex-financial-expansion`
- `mops-financial-completeness`
- `source-coverage-expansion`
