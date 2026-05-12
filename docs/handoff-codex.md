# 投資 Dashboard 專案狀態摘要（給 Codex 接手用）

## 部署現況

- **Live**：`https://invest.aihost.dev/`
- **部署方式**：cloudflared 隧道 + 本機 http.server，**不是** Cloudflare Pages / wrangler
  - Tunnel: `~/.cloudflared/dailynews-aihost.yml` → tunnel UUID `77f7a85b-1715-419e-8720-556130a8d1b2`
  - launchd: `~/Library/LaunchAgents/com.dailynews.cloudflared.plist` + `com.dailynews.dashboard-server.plist`
  - 靜態檔: `127.0.0.1:8055` 服務 worktree 的 `web/dist/`
- **worktree path**：`/Users/andy/Code/projects/telegram-bot/daily-news/.claude/worktrees/investment-dashboard`（main 分支尚未 merge）

## 程式結構

```
dashboard_export.py    Python → JSON (讀 SQLite，寫 web/src/data/)
web/                   Astro + Tailwind 4 靜態網站
  src/pages/
    index.astro        ← 單頁主視角（5 sections）
    stocks/[ticker].astro  ← 161 檔個股深度頁
  src/layouts/Base.astro    ← 共用 layout，含搜尋框 + 搜尋 index
  src/styles/global.css     ← 全套 design tokens
  src/data/*.json           ← 11 個資料檔（每日 export 刷新）
launchd/export-dashboard-data.sh    ← 每日刷新腳本
docs/dashboard-deployment.md        ← 部署指南
tests/test_dashboard_export.py      ← 3 個測試（全過）
```

## 單頁結構（index.astro）

1. **Date stamp**（極簡 hero）
2. **Sticky section index**：今日重點 / 個股 Scorecard / 訊號流 / 公司原文
3. **本頁如何使用**（可摺疊 guide）
4. **今日重點**：3 句 takeaway
5. **個股 Scorecard**（centerpiece）：一行一檔 × 8 欄（健康度/季營收/EPS/YoY/月營收/分析師/最近事件）
6. **訊號流**：tabbed（指引 / 法人 / 公司內部）
7. **公司原文**：SEC 10-Q forward-looking 摘錄
8. **下一步**：3 張 action cards

## 資料來源

- 55,879 篇新聞 + 316 份財報（TWSE / MOPS / TPEx / SEC）
- 5 份 SEC 10-Q filing_excerpt
- 60 條法人 / 30 條公司內部（經 alias 補正 ticker mapping）

## 已知問題 / TODO

| 項目 | 狀態 |
|---|---|
| Yahoo Finance 即時股價 | 被 IP rate-limit，`dashboard_prices.py` 已刪 |
| Insider / 13F / short interest 表 | 空（Phase 2-4 schema 有，ingest 沒跑） |
| Consensus estimates | 需付費資料源（Finnhub / Refinitiv） |
| YoY 在 Scorecard 顯示「—」 | TW data 重複 row 已 dedupe 但缺去年同期可比資料 |
| Watchlist hardcode | 在 `dashboard_export.py:DEFAULT_WATCHLIST`，沒讀 yaml |
| 主 branch 未 merge | 整個 dashboard 在 `worktree-investment-dashboard` 分支 |

## 最近 commits（worktree-investment-dashboard）

```
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
