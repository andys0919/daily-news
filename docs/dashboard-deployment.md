# Investment Dashboard — Cloudflare Pages 部署指南

> ⚠️ **不會覆蓋你既有的 Cloudflare 服務**：本 dashboard 使用獨立的 Pages 專案名 `daily-news-dashboard`，只 deploy 到你自選的 **subdomain**（例如 `invest.your-domain.com`），絕不動 root domain 或現有專案。

## 前置條件

- Node.js ≥ 22（建議：`nvm install 22 && nvm use 22`）
- Cloudflare 帳號（免費 tier 已足夠）
- 一個你已擁有、已加到 Cloudflare 的 domain
- `wrangler` CLI（可選）：`npm install -g wrangler`

## 第一次設定（手動）

### 1. 本地建置確認

```bash
cd web
npm install
npm run build        # 產生 web/dist/
npm run preview      # http://localhost:4321 確認 5 頁亮著
```

### 2. 建立 Cloudflare Pages 專案

在 Cloudflare dashboard → **Pages → Create application → Connect to Git**。

| 欄位 | 值 |
|---|---|
| Repository | `andys0919/daily-news`（或你自己的 fork） |
| Production branch | `main` |
| Project name | **`daily-news-dashboard`**（請務必用這個名稱，不要覆蓋既有專案） |
| Build command | `cd web && npm install && npm run build` |
| Build output directory | `web/dist` |
| Environment variables | `PUBLIC_SITE_URL=https://invest.your-domain.com` |

### 3. 綁定 custom domain（subdomain only）

Pages → 你的專案 → **Custom domains → Set up a custom domain** → 輸入 `invest.your-domain.com`（自選 subdomain，例如 `invest`、`dashboard`、`hub`…）。

> ⚠️ **請務必使用 subdomain**，避免 deploy 到 root domain 影響你現有的服務。

CF 會自動產生 CNAME。等 DNS 生效後就可以從子網域訪問。

### 4. 啟用 Cloudflare Access（私人化）

**Zero Trust → Access → Applications → Add an application**:

- Type：**Self-hosted**
- Application domain：`invest.your-domain.com`
- Identity providers：**Google**（或 One-time PIN email）
- Policy：**Include → Emails → 你的 email**（或 `Emails ending in @your-domain.com`）

存檔後，未通過驗證的訪客會看到 CF Access login 畫面。

### 5. 本地 wrangler 設定（可選，用於手動 deploy）

```bash
cp web/wrangler.toml.template web/wrangler.toml
cp web/.env.example web/.env.local
# 編輯 .env.local 填入 CF_API_TOKEN / CF_ACCOUNT_ID / CF_DEPLOYMENT_DOMAIN
```

兩個檔都已加進 `.gitignore`，不會被提交。

## 日常 deploy 流程

### A. 自動（建議）：daily-news 跑完 → git push → CF Pages 自動 build

```bash
# 通常由 launchd 每天 09:00 跑完 main.py 後接著跑
bash launchd/export-dashboard-data.sh    # 刷新 web/src/data/*.json
git add web/src/data/
git commit -m "data: daily snapshot $(date +%F)"
git push                                  # CF Pages 偵測到 push、自動 rebuild
```

### B. 手動：用 wrangler 直接 deploy

```bash
cd web
npm run build
wrangler pages deploy dist --project-name daily-news-dashboard
```

## 不會覆蓋既有服務的硬性保證

1. Pages 專案名是 `daily-news-dashboard`，與你既有專案隔離
2. 只 deploy 到 subdomain（`invest.*` 或 `dashboard.*`），不動 root
3. `wrangler.toml.template` 只放 placeholder，git 看不到真實值
4. ralph 自動化腳本不會執行 `wrangler deploy`、不會 `git push`
5. launchd export script 只寫本地 JSON、不接觸 CF

## Troubleshooting

| 症狀 | 原因 | 解法 |
|---|---|---|
| `npm install` 失敗 | Node < 22 | `nvm install 22 && nvm use 22` |
| `astro check` 報錯 | 修改了 .astro 檔但 type 不對 | 看 error 訊息修對應 type |
| CF Pages build 失敗 | Build command 不正確 | dashboard → Settings 確認 `cd web && npm install && npm run build` |
| Subdomain 連不上 | DNS 還沒生效或 CF 還沒 issue cert | 等 5-10 分鐘；確認 CF dashboard DNS 有 CNAME |
| 訪客看不到 login 畫面 | Access policy 沒綁好 | Zero Trust → Access → Policies 確認 domain 對 |

## 完整檔案地圖

```
web/                          ← 整個 Astro 專案，獨立於 Python pipeline
├── package.json
├── astro.config.mjs
├── tailwind.config.mjs
├── tsconfig.json
├── wrangler.toml.template    ← 範本，user 自己 copy → wrangler.toml
├── .env.example              ← 範本，user 自己 copy → .env.local
├── .gitignore
├── README.md
├── public/
└── src/
    ├── layouts/Base.astro
    ├── components/
    │   ├── BentoCard.astro
    │   ├── TickerChip.astro
    │   └── StatLine.astro
    ├── pages/
    │   ├── index.astro
    │   ├── stocks/[ticker].astro
    │   ├── news.astro
    │   ├── calendar.astro
    │   └── decisions.astro
    ├── data/                  ← daily refresh 寫入處（dashboard_export.py 產生）
    └── styles/global.css

dashboard_export.py            ← Python 端：SQLite → web/src/data/*.json
launchd/export-dashboard-data.sh ← shell wrapper
```
