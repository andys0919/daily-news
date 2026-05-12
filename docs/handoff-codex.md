# 投資 Dashboard 專案狀態摘要（給 Codex 接手用）

## 部署現況

- **Live**：`https://invest.aihost.dev/`
- **部署方式**：cloudflared 隧道 + 本機 http.server，**不是** Cloudflare Pages / wrangler
  - Tunnel: `~/.cloudflared/dailynews-aihost.yml` → tunnel UUID `77f7a85b-1715-419e-8720-556130a8d1b2`
  - launchd: `~/Library/LaunchAgents/com.dailynews.cloudflared.plist` + `com.dailynews.dashboard-server.plist`
  - 靜態檔: `127.0.0.1:8055` 服務 main repo 的 `web/dist/`
- **repo path**：`/Users/andy/Code/projects/telegram-bot/daily-news`（dashboard 已 merge 回 main）

## 程式結構

```
dashboard_export.py    Python → JSON (讀 SQLite，寫 web/src/data/)
web/                   Astro + Tailwind 4 靜態網站
  src/pages/
    index.astro        ← 單頁主視角（idea-generation 研究隊列）
    stocks/[ticker].astro  ← 171 檔個股深度頁
  src/layouts/Base.astro    ← 共用 layout，含搜尋框 + 搜尋 index
  src/styles/global.css     ← 全套 design tokens
  src/data/*.json           ← 10 個頂層資料檔 + stocks/*.json（每日 export 刷新）
launchd/export-dashboard-data.sh    ← 每日刷新腳本
docs/dashboard-deployment.md        ← 部署指南
tests/test_dashboard_export.py      ← dashboard export 測試
tests/test_dashboard_homepage_contract.py ← 首頁資訊架構合約測試
```

## 單頁結構（index.astro）

1. **今日研究隊列 hero**：顯示產出日期、上修/下修 breadth、可搜尋標的數、財報樣本數、首要追蹤標的
2. **Sticky section index**：研究隊列 / Watchlist / 市場訊號 / 原文證據
3. **研究隊列**：高優先研究 / 需要驗證 / 風險雷達；每張卡回答「為什麼現在 / 下一步查核 / 風險觸發」
4. **Watchlist 決策表**：用同一套 researchQueue 排序，集中顯示狀態、證據信心、風險與數字快照
5. **市場訊號**：上修、下修、新聞熱度三欄
6. **原文證據**：SEC filing excerpt + 公司內部 feed

## 資料來源

- 56,703 篇新聞 + 327 份財報（TWSE / MOPS / TPEx / SEC）
- 5 份 SEC 10-Q filing_excerpt
- 60 條法人 / 30 條公司內部（經 alias 補正 ticker mapping）

## 已知問題 / TODO

| 項目 | 狀態 |
|---|---|
| Yahoo Finance 即時股價 | 被 IP rate-limit，`dashboard_prices.py` 已刪 |
| Insider / 13F / short interest 表 | 空（Phase 2-4 schema 有，ingest 沒跑） |
| Consensus estimates | 需付費資料源（Finnhub / Refinitiv） |
| YoY 在 Scorecard 顯示「—」 | TW data 重複 row 已 dedupe 但缺去年同期可比資料 |
| Watchlist hardcode | 已補 `data/watchlist.yaml`；`dashboard_export.py` 預設讀 yaml，沒有檔案才 fallback |
| 主 branch 未 merge | 已 fast-forward merge 到 main |
| 首頁舊 Scorecard/guide 很難讀 | 已改成投資研究隊列：高優先研究 / 需要驗證 / 風險雷達 / Watchlist 決策表 |

## 最近 commits（main）

```
ui(dashboard): research-queue homepage redesign
data(dashboard): refresh latest snapshot
fix(dashboard): finalize local tunnel refresh
ui(dashboard): strip filler + fix currency + populate Scorecard
ui(dashboard): consolidate guidance + next-steps + sticky table
chore(dashboard): project cleanup (archive openspec + README)
ui(dashboard): strip top-nav anchor links
ui(dashboard): professional layout — unified scorecard + tabbed pulse
ui(dashboard): single-page master view with 6 unified sections
```

## 重要背景

- ralph-loop 已結束，**完成承諾**：`<promise>PHASE_DONE</promise>` 已於 plan 階段送出
- **嚴格範圍曾經**：禁止 wrangler deploy、禁止 git push、禁止修改既有 Python pipeline 模組——這些限制已隨 ralph-loop 結束失效，但 Python pipeline 模組（crawler / summarizer / news_enrichment 等）仍保持未動
- 設計參考 `ui-ux-pro-max` skill 的 dark / bento / glass 風格

## 給 Codex 的接手建議

1. 想跑 export：`bash launchd/export-dashboard-data.sh`
2. 想 build：`cd web && npm run build`
3. 想看資料庫：`sqlite3 data/news.db`
4. 想看 live：`https://invest.aihost.dev/`
5. Tests：`uv run --with-requirements requirements.txt --with pytest --python python3 python -m pytest tests/test_dashboard_export.py -q`
