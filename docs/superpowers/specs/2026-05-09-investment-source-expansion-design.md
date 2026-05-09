# Investment Source Expansion — Design Spec

**Date:** 2026-05-09
**Status:** approved (ready for writing-plans)
**Owner:** andy

## 1. 目的與範圍

擴充 `daily-news` 的投資相關資料來源到「全鏈整合」深度：
不只增加新 RSS feed，而是把新來源結構化進 SQLite、整合進 `stock_memo.py` 與
`summarizer.py`，讓每日 / 每週報告與單股 memo 可以直接看到法說會、機構持股、
內部人交易、融券資金流、宏觀脈絡等訊號。

**Out of scope（YAGNI）：**

- 付費 sell-side 資料（GS / MS / JPM 終端）
- 即時 webhook 推播
- 圖表化 dashboard
- LLM fine-tune
- 任一階段非必要的 refactor

## 2. 涵蓋的訊號類型

依使用者確認，五大類別全收，全部限制在「免費、可重複抓取、內容密度足夠」：

1. **`broker_research`** — 券商 / 獨立分析師免費公開研究
2. **`ir_materials`** — 法說會簡報、earnings transcript、IR newsroom
3. **`insider_holdings`** — SEC Form 4 / 13F、TW 董監持股變動
4. **`short_interest_flows`** — TW 信用交易、US short interest、ETF flows
5. **`macro_data`** — Fed staff papers、IMF / OECD、TW 主計處、sector tracker

## 3. 整體架構（4 phase）

```
Phase 1 │ 來源擴充（config.yaml + crawler 健康檢查 + tests）
Phase 2 │ 結構化 ingest 模組（4 個新 .py 模組）
Phase 3 │ 儲存模型擴充（4 張新 SQLite 表 + bundle 擴充）
Phase 4 │ Memo / Summarizer 整合（stock_memo + summarizer）
```

每 phase 一個 OpenSpec change，每 phase 一個 ralph-loop run，phase 之間嚴格隔離。

## 4. Phase 1：來源擴充

### 4.1 config.yaml 擴充

新增 5 個 `category_agents` 條目（persona / framework / key_metrics /
output_sections / anti_patterns）以及 5 個 `feeds:` 子節點。

預估 40–60 個新 feed 條目。每個條目沿用既有 schema：

```yaml
- name: "<source name>"
  url: "<rss or rsshub url>"
  fallback_url: "<optional>"
  source_key: "<unique key>"
  category: "<分類顯示名>"
  summary_prompt: "<broker_research|ir_materials|...>"
  priority: <int>
```

### 4.2 候選來源（最終由 ralph-loop 驗證可用性）

#### `broker_research`

- 凱基 / 元大 / 富邦 / 永豐投顧公開研究頁（HTML scrape；非原生 RSS 走
  `changedetection.io` 或 RSSHub `cssparser` route）
- Goldman Insights blog、JPM Research outlook 公開頁、Morgan Stanley Ideas
- Substack 免費分析師：Stratechery、Damodaran、Doomberg、Net Interest、
  Mostly Borrowed Ideas、Acquired
- Yardeni Research、Topdown Charts free、Morningstar Research、
  Seeking Alpha Top Ideas free

#### `ir_materials`

- TW：MOPS 法說會專區、TWSE 法說會行事曆 RSS、各上市公司 IR newsroom RSS
- US：SEC EDGAR `8-K` Item 7.01 / 2.02 atom feed、SEC investor presentation
  filings、各大廠 IR site transcript / webcast RSS
- 第三方：Motley Fool free transcripts、Seeking Alpha transcripts free 部分

#### `insider_holdings`

- SEC EDGAR `Form 4` atom feed
- SEC EDGAR `13F-HR` quarterly index
- TW：證交所董監持股月份變動 OpenAPI、櫃買持股轉讓申報
- WhaleWisdom free、Dataroma RSS、Insider Monkey free RSS

#### `short_interest_flows`

- TW：TWSE OpenAPI 信用交易日報、TPEX 信用交易日報、ETF 申購買回 OpenAPI
- US：FINRA short interest 雙月 CSV、FINRA Reg SHO daily files
- ETF：etf.com RSS、ETFGI free

#### `macro_data`

- Fed staff working papers RSS、IMF WEO RSS、OECD STAT RSS、World Bank
- TW：行政院主計處 RSS、央行公告 RSS、財政部 OpenData
- Sector：SIA semi book-to-bill、SEMI WFE forecast、Counterpoint free、
  Canalys free
- Hyperscaler capex 彙整：MSFT / GOOG / AMZN / META 季報 capex（從現有
  `earnings_data.py` 衍生，不重新爬）

### 4.3 健康檢查與限制

- 全部沿用 `SourceHealthRegistry`（連續失敗達門檻 → cooldown）
- 政府網站（MOPS、TWSE、TPEX）沿用全域規範：`verify=False`、ASP.NET
  WebForms `__VIEWSTATE` / `__EVENTVALIDATION` 處理、增量儲存每 50 筆 commit
- SEC EDGAR 必帶 `SEC_API_USER_AGENT`，沿用 `earnings_data.py` session
- 每次新源請求間隔 `random.uniform(2, 4)` 秒

### 4.4 測試

- `tests/test_source_coverage.py` 擴充：5 個新分類各至少 1 feed 通過 schema
  驗證
- 新增 `tests/test_broker_research_feeds.py`：mock fetch 確認 parser 不爆
- `tests/test_news_enrichment.py` 擴充：新源觸發 issuer / ticker 抽取

### 4.5 不允許在本 phase 做

- 修改 `financial_reports.py`、`stock_memo.py`、`summarizer.py`
- 新增任何 `.py` ingest 模組
- 新增 SQLite schema

## 5. Phase 2：結構化 ingest 模組

### 5.1 4 個新模組

```python
# ir_materials.py
def refresh_ir_materials_for_articles(articles) -> list[IRMaterial]: ...
def fetch_us_transcripts(ticker: str) -> list[Transcript]: ...
def fetch_tw_law_call_slides(ticker: str) -> list[LawCallSlide]: ...

# insider_holdings.py
def refresh_insider_transactions(tickers: list[str]) -> list[InsiderTrade]: ...
def fetch_13f_holdings(reporter_cik: str) -> list[Holding]: ...
def fetch_tw_director_holding_changes(ticker: str) -> list[DirectorChange]: ...

# short_interest.py
def refresh_short_interest(market: str, tickers: list[str]) -> list[ShortInterestRow]: ...
def fetch_etf_flows(market: str) -> list[ETFFlow]: ...

# macro_data.py
def refresh_macro_releases() -> list[MacroRelease]: ...
def aggregate_hyperscaler_capex() -> CapexAggregate: ...
```

### 5.2 main.py 整合

`main.py` Step 2.5 從現有 4 條財報通道擴充為 8 條並行：

```
us_financials / tw_financials / tpex_financials / mops_financials
ir_materials / insider_holdings / short_interest / macro_data
```

每條獨立 `asyncio.to_thread`，個別 try / except，失敗只在
`financial_errors` 列表記錄，不阻塞其他通道。

### 5.3 測試

- `tests/test_ir_materials.py`：fixture HTML / 小型 PDF
- `tests/test_insider_holdings.py`：fixture Form 4 XML、fixture 13F XML
- `tests/test_short_interest.py`：fixture FINRA CSV、fixture TWSE 融券
- `tests/test_macro_data.py`：fixture Fed paper RSS

### 5.4 不允許在本 phase 做

- 動 SQLite schema（先寫進舊 `articles` 或暫存 dict，Phase 3 才搬到新表）
- 動 `stock_memo.py`、`summarizer.py`、`html_generator.py`

> **Phase 2 → Phase 3 的橋接：** Phase 2 的 ingest 函式回傳 dataclass list，
> 暫時不寫入新 SQLite 表（schema 還沒建立）。Phase 2 的 `main.py` 整合
> 只負責呼叫並 print 統計，不實際持久化。Phase 3 才把資料寫入新表。

## 6. Phase 3：儲存模型擴充

### 6.1 新 SQLite 表

```sql
CREATE TABLE IF NOT EXISTS issuer_materials (
    id INTEGER PRIMARY KEY,
    market TEXT NOT NULL, ticker TEXT NOT NULL, company_name TEXT,
    material_type TEXT NOT NULL,  -- 'transcript' | 'ir_slide' | 'broker_note' | 'press_release'
    source TEXT, source_url TEXT, fetched_at TEXT,
    fiscal_year INTEGER, fiscal_period TEXT, event_date TEXT,
    title TEXT, body_text TEXT, body_excerpt TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS insider_transactions (
    id INTEGER PRIMARY KEY,
    market TEXT NOT NULL, ticker TEXT NOT NULL,
    insider_name TEXT, insider_role TEXT,
    transaction_date TEXT, transaction_type TEXT,
    shares INTEGER, price REAL, value_usd REAL,
    filing_url TEXT, fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS holdings_snapshots (
    id INTEGER PRIMARY KEY,
    reporter_cik TEXT, reporter_name TEXT,
    period_end TEXT NOT NULL, ticker TEXT NOT NULL,
    shares INTEGER, value_usd REAL, change_pct REAL,
    filing_url TEXT, fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS short_interest_snapshots (
    id INTEGER PRIMARY KEY,
    market TEXT NOT NULL, ticker TEXT NOT NULL, period_end TEXT NOT NULL,
    short_interest REAL, days_to_cover REAL, short_interest_ratio REAL,
    source TEXT, fetched_at TEXT
);
```

全部用 `CREATE TABLE IF NOT EXISTS` + `_ensure_columns` 模式，可重複執行
idempotent（沿用 `crawler.py` `_ensure_article_columns` pattern）。

### 6.2 Bundle 擴充

`FinancialSnapshotBundle` 新增四個欄位：

- `latest_transcript: IRMaterial | None`
- `recent_insider_summary: InsiderSummary | None`
- `latest_13f: HoldingsSnapshot | None`
- `short_interest: ShortInterestRow | None`

`build_bundle(market, ticker)` 一次查 8 個來源（既有 4 + 新 4），合併回傳。

### 6.3 Phase 2 ingest 結果接線

把 Phase 2 模組的回傳 dataclass 真正寫入新表。`main.py` Step 2.5 不變，
只是底層 ingest 函式現在會 commit 到 SQLite。

### 6.4 測試

- `tests/test_financial_reports_bundle.py` 擴充：bundle 帶新四欄位的 round-trip
- `tests/test_db_migrations.py`：新表 IF NOT EXISTS + 重複呼叫 idempotent

### 6.5 不允許在本 phase 做

- 動 `stock_memo.py`、`summarizer.py`、`html_generator.py`
- 加新來源 / 動 `config.yaml`

## 7. Phase 4：Memo / Summarizer 整合

### 7.1 stock_memo.py

新 5 個區塊（在現有「官方財報快照」之後）：

1. 最新法說會重點（從 `latest_transcript` 抽 body_excerpt）
2. 近 90 天內部人交易摘要（從 `insider_transactions` 聚合）
3. 13F 機構持股動向（從 `holdings_snapshots` 列重要持股變動）
4. 融券與 ETF 資金流（從 `short_interest_snapshots`）
5. 宏觀脈絡（從 `macro_data` 抓相關 release，依 ticker 產業 tag 過濾）

### 7.2 summarizer.py

- 為 5 個新分類各寫 `category_agents` prompt（persona / framework /
  key_metrics / output_sections / anti_patterns）
- daily memo prompt 引用結構化欄位 `{{insider_summary}}`、
  `{{short_interest_change}}`、`{{transcript_quote}}`，不再只塞文字
- weekly 分類摘要管線沿用既有迴圈，自動吃到新分類

### 7.3 測試

- `tests/test_stock_memo.py`：新 5 區塊渲染
- `tests/test_summarizer.py`：新 5 分類 prompt 構築 + structured field
  interpolation
- `tests/test_daily_memo_report.py`：含 transcript / insider 的整合 case

### 7.4 不允許在本 phase 做

- 加新來源 / 動 ingest 模組 / 動 schema

## 8. Error Handling 總則

| 場景 | 處理 |
|---|---|
| 新分類 RSS 抓不到 | `SourceHealthRegistry` cooldown |
| SEC EDGAR 429 | 既有 retry + UA header |
| TW 政府網站 SSL / WebForms | `verify=False` + `__VIEWSTATE` + ASP.NET session |
| transcript / IR PDF 解析失敗 | `body_text=""`、`extraction_status='failed'`，不丟 main pipeline 異常 |
| schema 衝突 | `CREATE TABLE IF NOT EXISTS` + `_ensure_columns` 模式，idempotent |
| 長跑 timeout | 每 50 筆 commit 一次（沿用全域規範） |
| Rate limit 禮貌 | `time.sleep(random.uniform(2, 4))` + 識別性 user-agent |

## 9. Ralph-loop 啟動配置

每 phase 一個 ralph-loop run：

| Run | Phase | max_iterations | completion_promise |
|---|---|---|---|
| 1 | RSS 擴充 | 10 | `PHASE_DONE` |
| 2 | Ingest 模組 | 15 | `PHASE_DONE` |
| 3 | Storage 擴充 | 12 | `PHASE_DONE` |
| 4 | Memo 整合 | 12 | `PHASE_DONE` |

每 run prompt 結尾自動帶退出指示：

```
完成本 phase 所有任務後，最後一次回覆「只」輸出 <promise>PHASE_DONE</promise>，
不要附加其他文字。如果尚未完成，繼續工作不要輸出該 tag。
```

每 phase ralph-loop prompt 第一段會明確列出嚴格範圍與不允許動的檔案 / 功能。

Phase 之間在主 session 由人工確認 commit + 全測試通過後才啟動下一 phase。

## 10. OpenSpec change 結構

```
openspec/changes/
├── investment-source-rss-expansion/        # Phase 1
├── investment-source-ingest-modules/       # Phase 2
├── investment-source-storage-model/        # Phase 3
└── investment-source-memo-integration/     # Phase 4
```

每個 change 目錄含 `proposal.md` / `design.md` / `tasks.md` / `specs/`。
ralph-loop 每 phase 結束跑 `openspec validate <change-id>`。

## 11. 驗收條件

- 5 個新 RSS 分類進入 `config.yaml` 並可被 crawler 正常抓取
- 4 個新 ingest 模組對應 fixture 測試全綠
- 4 張新 SQLite 表存在於 `data/news.db`，bundle round-trip OK
- `python stock_memo.py --ticker NVDA --market us` 與
  `python stock_memo.py --ticker 2330 --market tw` 兩個 CLI 都能在輸出 memo
  看到 5 個新區塊（沒資料則顯示「尚無紀錄」）
- daily 與 weekly HTML 報告含新分類 summary
- `python -m unittest discover -s tests -v` 全綠
- 4 個 OpenSpec change 通過 `openspec validate` 且 archive

## 12. 風險與緩解

| 風險 | 緩解 |
|---|---|
| 部分券商研究頁變動頻繁，parser 失效 | 走 `changedetection.io` / RSSHub bridge；個別失效進 `SourceHealthRegistry` cooldown |
| 13F filing 量大、解析慢 | 限制 reporter list 到知名機構（Berkshire、Bridgewater、Renaissance、Tiger 等 ~30 名單），不全 universe |
| 透過 RSSHub 抓 X 已不太穩 | 與本 spec 無關（X 走既有 `x_trends`） |
| ralph-loop 在 phase 內偏離範圍 | prompt 明確列出不允許動的檔案；phase-end commit message 必含 `[phase-N done]` |
| Schema migration 撞 production data | 全部 `CREATE TABLE IF NOT EXISTS`，新表絕不刪舊表 |

## 13. 完成後狀態

- `data/news.db` 多 4 張結構化表
- `data/memos/<ticker>.md` 內容增厚 5 個區塊
- `data/reports/*.html` 新增 5 個分類段落
- 4 個 OpenSpec change archived
- 全測試綠
