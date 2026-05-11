# Investment Decision Dashboard — Design Spec

**Date:** 2026-05-10
**Status:** approved-direct-execution (user said「直接做到好」, skipping Q&A)
**Owner:** andy

## 1. 目的

把 daily-news 累積的資料（新聞、官方財報、transcripts、insider、13F、short interest、macro）做成一個專給投資決策用的 web dashboard，部署在 Cloudflare Pages，使用使用者自己的 domain（子網域），**不能覆蓋任何既有的 Cloudflare 服務**。

## 2. 投資決策用例（驅動 UI 設計）

每天早上開盤前 / 下班後使用者打開 dashboard 想看到：

1. **總覽（首頁）**：昨日重點訊號、市場指數變動、追蹤名單 alerts
2. **個股深度頁**：以 ticker 為主鍵，整合官方財報快照、最新 transcript、insider 動作、13F 機構動向、融券 / ETF 資金流、宏觀對照、相關新聞
3. **新聞時間軸**：依分類 / 標籤 / 公司過濾 daily-news 抓到的 articles
4. **事件月曆**：法說會、財報、總體數據發布、上市櫃事件（從 articles + macro 推算）
5. **決策日誌**：使用者自己加 thesis / decision notes（簡易，先靠 markdown 文件）

## 3. 不會做（YAGNI）

- 即時行情串接（不是日常用例的痛點，且 free tier 取不到穩定即時）
- 多使用者 / 公開 SaaS（只給 owner 用）
- 動態回測 / 模型訓練
- 行動 App native UI

## 4. Stack 決策

| 層 | 選擇 | 理由 |
|---|---|---|
| 框架 | **Astro 5+** | 靜態優先、islands 支援、Cloudflare 原生支援 |
| Styling | **Tailwind CSS 4** | 與 Astro 整合佳、shadcn 生態 |
| Component patterns | shadcn-style（手抄而非 npm 套件）| 不引入大型 dependency 樹 |
| Charts | **uPlot** 或 **lightweight-charts**（TradingView 開源版）| 投資數據常見、bundle 小 |
| Icons | Lucide icons | 與 shadcn 風格一致 |
| Hosting | **Cloudflare Pages** | 免費 tier、auto-build on git push、與 Workers 整合 |
| Auth | **Cloudflare Access**（zero-trust）| 不需要在 app 內寫 auth code |
| Data 層 | 靜態 JSON（build-time generated）| 沒有伺服端 query 成本、CDN 全快取 |
| Optional Worker | `worker/api/` 給 on-demand search / memo | 不一定本期做 |

## 5. 隔離 / 不覆蓋既有服務的硬性規則

1. **CF Pages 專案名**: `daily-news-dashboard`（明確 namespace、跟使用者既有 services 不衝突）
2. **域名策略**: 只用子網域，例：`invest.{user-domain}` 或 `dashboard.{user-domain}` —— 絕不 deploy 到 root domain
3. **配置參數化**: 域名、CF account ID、API token、Access policy 都透過 env / `.env.example` / `wrangler.toml` 範本，ralph **絕對不** 寫死 user 的真實值
4. **ralph 不執行 deploy**: 只產生 `wrangler.toml`、deploy script、README；實際 `wrangler deploy` / git push 由使用者手動執行
5. **不動既有檔案**: `web/` 目錄是新增的，所有既有 Python 模組、launchd、config 不修改
6. **launchd 整合分離**: 新增的 daily export step 寫在 `launchd/export-dashboard-data.sh` 獨立檔，user 自行 chain 進現有 plist

## 6. 整體架構

```
┌──────────────────────────────────────────────────────┐
│  Python pipeline (既有，每天 09:00 跑 main.py)          │
│  → data/news.db (SQLite)                              │
└──────────────────────────────────────────────────────┘
                       ↓ (新增)
┌──────────────────────────────────────────────────────┐
│  dashboard_export.py                                  │
│  Query SQLite + financial_reports bundle             │
│  Output → web/src/data/*.json                         │
└──────────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────┐
│  Astro build (web/)                                  │
│  Reads JSON at build time → static dist/             │
└──────────────────────────────────────────────────────┘
                       ↓ (使用者 push 後)
┌──────────────────────────────────────────────────────┐
│  Cloudflare Pages auto-build                         │
│  Project: daily-news-dashboard                       │
│  Domain: invest.{user-domain}                        │
│  Auth: Cloudflare Access (email allowlist)           │
└──────────────────────────────────────────────────────┘
```

## 7. 頁面結構

```
/                     首頁 dashboard（bento grid）
  - 昨日重點訊號（top 5-10 transcripts / insider trades / 大額 13F 變動）
  - 市場指數卡片（從 market_overview_cache.json）
  - Watchlist 卡片（從 user-defined watchlist.yaml）
  - 即將事件（events.json 月曆 widget）

/stocks/[ticker]      個股深度頁
  - Header: ticker + company + market + 連結到 SEC / MOPS / TPEx
  - Tab 1 官方財報: 最新季報 / 月營收圖、guidance、filing excerpt
  - Tab 2 法說會: 最新 transcript 全文、IR materials 列表
  - Tab 3 內部人 / 機構: Form 4 表格、13F holdings 表格
  - Tab 4 資金流: 融券 / 券資比、ETF 流向
  - Tab 5 新聞: 相關 articles 時間軸
  - Tab 6 宏觀對照: hyperscaler capex、CPI / PCE 重要 release

/news                 新聞時間軸 + 過濾
  - 左欄: 分類 / region / event_type 多選
  - 主欄: 卡片式 article list（headline + source + ticker chips + body excerpt）

/calendar             事件月曆
  - 月曆 grid，事件來源: macro release + earnings_data filing 日期 + Google News 推算

/decisions            決策日誌（簡易版）
  - 讀取 web/src/data/decisions.md
  - 每個 entry 一個 card（日期 / ticker / thesis / size / 結果待補）
```

## 8. UI / UX 風格（用 ui-ux-pro-max 設計）

- **整體風格**: **Bento grid** + 深色為主（投資 dashboard 常見）+ 局部 glassmorphism
- **色彩**: 中性灰階為底、語意色（漲跌綠紅、event_type chip 各色）
- **字體**: SF Pro / Inter for body、JetBrains Mono for 數字 / ticker
- **資訊密度**: 高（dashboard 用例）、但允許 hover 展開細節
- **互動**: 鍵盤快捷鍵（`/` 搜尋、`g s` 跳 stocks）、動畫只用 framer-motion 局部
- **Responsive**: desktop 為主（>1024px 體驗最好）、tablet 可用、mobile 給「閱讀模式」

## 9. 資料流（build-time vs run-time）

### Build time（每天）
1. Python pipeline 跑完 daily（既有）
2. `dashboard_export.py` 從 `data/news.db` + financial bundle export：
   - `web/src/data/overview.json`（首頁卡片）
   - `web/src/data/stocks/<ticker>.json`（每個追蹤 ticker 一個）
   - `web/src/data/news.json`（過去 30 天 articles，trimmed）
   - `web/src/data/events.json`（月曆事件）
   - `web/src/data/decisions.json`（從 `data/decisions/` markdown 解析）
   - `web/src/data/watchlist.json`（從 `data/watchlist.yaml`）
3. `cd web && npm run build` 產生 `web/dist/`
4. （可選）`wrangler pages deploy web/dist --project-name daily-news-dashboard`

### Run time（瀏覽器）
- 所有頁面 SSG，初次載入即 final HTML
- 互動部分用 islands（搜尋 / tab 切換 / chart 渲染）
- 客戶端 zero API call（全靜態）

## 10. 認證

Cloudflare Access：
- 在 CF dashboard → Zero Trust → Access → Applications 設一個 app
- Hostname: `invest.{user-domain}`
- Policy: include email == `<user-email>`（or specific list）
- Identity provider: Google / One-time PIN（user 選）

ralph **不會** 自動建立 Access policy（需要 user 手動操作 CF dashboard 一次）。README 提供截圖步驟。

## 11. 部署流程（README 會詳述）

### 第一次 setup（user 手動）
1. CF dashboard 建立新 Pages 專案 `daily-news-dashboard`
2. Build command: `cd web && npm install && npm run build`
3. Build output: `web/dist`
4. 設定 production branch: `main`
5. 加 custom domain: `invest.{user-domain}`（user 自己決定 subdomain）
6. CF Access 加 policy 鎖網域
7. local `.env`: `CF_API_TOKEN=...`、`CF_ACCOUNT_ID=...`、`CF_DEPLOYMENT_DOMAIN=invest.<...>`

### 日常 deploy
- 每次 Python pipeline 跑完 → `dashboard_export.py` 寫 JSON → git commit `web/src/data/` → push → CF Pages 自動 rebuild

或：
- `cd web && npm run deploy`（呼叫 wrangler，用 `.env` 的 token）

## 12. Repo 變更總覽（ralph 會做的）

新增：
```
web/
├── package.json
├── astro.config.mjs
├── tailwind.config.mjs
├── tsconfig.json
├── wrangler.toml.template       ← 範本，user 複製成 wrangler.toml 填值
├── .env.example                 ← env vars 範本
├── README.md                    ← deployment guide
├── src/
│   ├── layouts/Base.astro
│   ├── components/...           ← BentoCard / TickerChip / FilingTable / TranscriptViewer
│   ├── pages/
│   │   ├── index.astro
│   │   ├── stocks/[ticker].astro
│   │   ├── news.astro
│   │   ├── calendar.astro
│   │   └── decisions.astro
│   ├── data/                    ← JSON 由 Python export，ralph commit 空 schema 範例
│   └── styles/global.css
└── public/

dashboard_export.py              ← 新模組，由 ralph 寫，含測試
tests/test_dashboard_export.py
launchd/export-dashboard-data.sh ← 獨立 script，user 自行 chain 進 plist
docs/dashboard-deployment.md     ← Cloudflare 設定步驟
```

**不動：** 所有既有 Python 模組（除了 `dashboard_export.py` 是新檔）、`config.yaml`、所有 ingest 模組、`financial_reports.py`、launchd 既有 scripts、原本的 HTML report（保留共存）

## 13. Phase 切分（給 ralph-loop）

只一個 ralph-loop run（max_iter = 20）：

1. OpenSpec scaffold (`investment-dashboard`)
2. `dashboard_export.py` + JSON schema + tests
3. `web/` Astro project scaffold + Tailwind + base layout
4. 首頁 `/` bento grid + 4 個 dashboard 卡片
5. `/stocks/[ticker]` 動態頁 + 6 tabs（mock interactive 也可）
6. `/news` 過濾頁 + island search
7. `/calendar` 月曆 widget
8. `/decisions` 日誌頁
9. UI 樣式 polish（呼叫 ui-ux-pro-max 心法）
10. `wrangler.toml.template` + `.env.example` + deploy script
11. `launchd/export-dashboard-data.sh`
12. `docs/dashboard-deployment.md`
13. 本地 build smoke (`cd web && npm install && npm run build`)
14. 最終 commit + PHASE_DONE

## 14. 驗收

- `cd web && npm install && npm run build` 在 worktree 成功產生 `web/dist/`
- `python dashboard_export.py` 跑通、寫出 JSON
- `npm run preview` 本機 `http://localhost:4321` 可看到 5 頁全亮
- 所有既有 Python 測試仍綠（包含 baseline 2 個 whitelist）
- `web/README.md` 含完整 CF Pages setup 步驟、不含任何使用者真實 secret
- `wrangler.toml.template` 用 `${CF_ACCOUNT_ID}` 等 placeholder

## 15. 風險與緩解

| 風險 | 緩解 |
|---|---|
| 跟 user 既有 CF service 衝突 | Project 名稱獨立 (`daily-news-dashboard`)、只 deploy 到 subdomain、ralph 不執行 deploy |
| user secret 外漏到 repo | `.env` 加 `.gitignore`；ralph 只寫 `.env.example` |
| Astro 版本不穩 | 鎖 minor version、提交 `package-lock.json` |
| 第一次 build 失敗 | 提供 fallback「pure HTML」分支說明 |
| user 沒有 Node.js 環境 | README 寫 `nvm install 22` 步驟 |
