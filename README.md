# daily-news

`daily-news` 是一個以繁體中文輸出為主的每日 / 每週新聞摘要與市場 memo 產生器，目標是把台美股相關新聞、官方財報、宏觀資料與高訊號技術來源整理成一份可直接閱讀的本地 HTML 報告。

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
  - 單篇 daily memo 與 AI / GitHub digest

## 投資 Dashboard (web/)

`web/` 是一個獨立的 Astro + Tailwind 靜態網站，把 daily-news pipeline 產生的資料以單頁形式呈現，方便每日做投資決策時參考。

- 部署：Cloudflare Tunnel（`com.dailynews.cloudflared` launchd service）+ 本機 `python3 -m http.server` 服務 `web/dist/`
- 自架 domain：`https://invest.aihost.dev/`（自家 subdomain，不覆蓋其他 service）
- 資料來源：[`dashboard_export.py`](dashboard_export.py) 讀 SQLite 寫 JSON 到 `web/src/data/`
- 部署細節：[`docs/dashboard-deployment.md`](docs/dashboard-deployment.md)

### 主要 sections（單頁）

| Section | 內容 |
|---|---|
| ① 今日研究隊列 | 以 idea-generation 思路排序：高優先研究 / 需要驗證 / 風險雷達 |
| ② Watchlist 決策表 | 一行一檔：為什麼現在、下一步查核、風險觸發、數字快照 |
| ③ 市場訊號 | 上修 / 下修 / 新聞熱度三欄，避免混成一張雜訊清單 |
| ④ 原文證據 | SEC filing excerpt 與公司內部 feed，用來驗證新聞與法人敘事 |

### 本機開發

```bash
cd web
npm install
npm run dev          # http://localhost:4321
npm run build        # 生成 web/dist/
```

### 每日資料刷新

```bash
bash launchd/export-dashboard-data.sh
```

會用 `data/news.db` 產出最新 JSON 寫到 `web/src/data/`，並接著執行 `cd web && npm run build` 重建 `web/dist/`。`com.dailynews.dashboard-server` 會從本機 `127.0.0.1:8055` 服務 `web/dist/`，再由 `com.dailynews.cloudflared` tunnel 對外提供 `https://invest.aihost.dev/`。

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
- `stock_memo.py`: 單一台股 / 美股個股 memo
- `dashboard_export.py`: 投資 dashboard JSON 匯出（讀 SQLite → 寫 `web/src/data/`）
- `config.yaml`: 來源與市場設定
- `launchd/`: macOS LaunchAgent 腳本與 template
- `web/`: 投資 dashboard 前端（Astro + Tailwind）
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

### 5. 產生單股 memo

```bash
uv run --with-requirements requirements.txt --python python3 python stock_memo.py --ticker 2330 --market tw
uv run --with-requirements requirements.txt --python python3 python stock_memo.py --ticker NVDA --market us
```

預設會先刷新該股票的官方財務資料，再輸出 markdown memo 到 `data/memos/`。
若只想用現有 SQLite 快照，不重新抓官方資料，可加 `--no-refresh-official-data`。

## 環境變數

- `AZURE_OPENAI_URL`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_MODEL`
- `SEC_API_USER_AGENT`
- `RSSHUB_URL`（選填；若設定為自架 RSSHub base URL，`x_trends` 會優先走 RSSHub 的 X user feeds，未設定時自動 fallback 到 Google News 的 `site:x.com` RSS 搜尋）
- `TWITTER_AUTH_TOKEN`（選填；自架 RSSHub 需要時可提供 X web `auth_token` cookie，但目前本機 RSSHub 的 `twitter/user` routes 已可正常返回主要 KOL feed）

## 自動執行（macOS launchd）

專案內建一份 LaunchAgent template，預設每天 `09:00` 執行 daily 報告。
`launchd/run-daily-news.sh` 現在會在正式跑 `main.py` 前先執行 `launchd/ensure-rsshub.sh`，若 `.env` 中的 `RSSHUB_URL` 指向本機 `127.0.0.1:1200`，會自動用 [`.infra/rsshub/docker-compose.yml`](/Users/andy/Code/projects/telegram-bot/daily-news/.infra/rsshub/docker-compose.yml) 確保 RSSHub/Redis 已啟動。

1. 建立 log 目錄

```bash
mkdir -p /Users/andy/Code/projects/telegram-bot/daily-news/data/logs
```

2. 複製 template 到 LaunchAgents

```bash
cp /Users/andy/Code/projects/telegram-bot/daily-news/launchd/com.andy.daily-news.plist.template \
  /Users/andy/Library/LaunchAgents/com.andy.daily-news.plist
```

3. 載入或重載排程

```bash
launchctl bootout "gui/$(id -u)" /Users/andy/Library/LaunchAgents/com.andy.daily-news.plist 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" /Users/andy/Library/LaunchAgents/com.andy.daily-news.plist
launchctl kickstart -k "gui/$(id -u)/com.andy.daily-news"
```

4. 查看狀態與 log

```bash
launchctl list | rg daily-news
tail -f /Users/andy/Code/projects/telegram-bot/daily-news/data/logs/daily-news-launchd.log
tail -f /Users/andy/Code/projects/telegram-bot/daily-news/data/logs/daily-news-launchd.err.log
```

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
- X 社群高訊號帳號：優先透過自架 RSSHub 轉 RSS，未設定時 fallback 到 Google News `site:x.com`

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
