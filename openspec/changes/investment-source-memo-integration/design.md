# Design — investment-source-memo-integration (Phase 4 of 4)

## Section ordering inside `render_stock_memo`

```
# {company} ({ticker}) 個股 Memo
## 官方財務快照            (existing)
## 最新法說會重點          (NEW — bundle.latest_transcript)
## 近 90 天內部人交易      (NEW — bundle.recent_insider_summary)
## 13F 機構動向            (NEW — bundle.latest_13f, gracefully empty when None)
## 融券與 ETF 資金流       (NEW — bundle.short_interest)
## 宏觀脈絡                (NEW — macro_data.aggregate_hyperscaler_capex())
## 官方資料來源            (existing)
## 近期相關新聞            (existing)
## 判讀底稿                (existing)
```

Each new section gracefully degrades to `（暫無資料）` when its bundle field is `None`.

## `format_financial_snapshot_bundle_context` extension

Append additional `parts` when present:

- `latest_transcript`: `法說重點：{title} — {body_excerpt[:160]}`
- `recent_insider_summary`: `近期內部人交易 {count} 筆 (買 {buys} / 賣 {sells})`
- `short_interest`: `融券餘額 {short_interest:,.0f} (券資比 {short_interest_ratio:.1%})`
- `latest_13f`: `機構持股 {issuer_name} {shares:,} 股`

## Macro section

`stock_memo.render_stock_memo` calls `macro_data.aggregate_hyperscaler_capex()` once per memo. When non-empty, prints the hyperscaler capex line; otherwise prints `（無 hyperscaler capex 對照資料）`.

## Out of scope

- New bundle fields (Phase 3 closed).
- New RSS sources or ingest modules (Phases 1 & 2 closed).
- Changing macro_data fetcher behaviour.
