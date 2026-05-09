# Design — investment-source-storage-model (Phase 3 of 4)

## New tables

All tables use `IF NOT EXISTS`. Each gets a corresponding lookup index. `_ensure_*_columns` mirrors the existing `_ensure_financial_report_columns` no-op-then-ALTER pattern for future schema additions.

```sql
CREATE TABLE IF NOT EXISTS issuer_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL, ticker TEXT NOT NULL,
    material_type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    body_excerpt TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    fiscal_year INTEGER, fiscal_period TEXT,
    fetched_at TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS insider_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL, ticker TEXT NOT NULL,
    insider_name TEXT NOT NULL DEFAULT '',
    insider_role TEXT NOT NULL DEFAULT '',
    transaction_date TEXT NOT NULL,
    transaction_type TEXT NOT NULL DEFAULT '',
    shares INTEGER NOT NULL DEFAULT 0,
    price REAL NOT NULL DEFAULT 0,
    value_usd REAL NOT NULL DEFAULT 0,
    filing_url TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holdings_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_cik TEXT NOT NULL, reporter_name TEXT NOT NULL DEFAULT '',
    period_end TEXT NOT NULL,
    issuer_name TEXT NOT NULL,
    cusip TEXT NOT NULL DEFAULT '',
    ticker TEXT NOT NULL DEFAULT '',
    shares INTEGER NOT NULL DEFAULT 0,
    value_usd REAL NOT NULL DEFAULT 0,
    change_pct REAL,
    filing_url TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS short_interest_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL, ticker TEXT NOT NULL,
    period_end TEXT NOT NULL,
    short_interest REAL NOT NULL DEFAULT 0,
    days_to_cover REAL NOT NULL DEFAULT 0,
    short_interest_ratio REAL NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL
);
```

## Bundle extension

```python
@dataclass
class FinancialSnapshotBundle:
    market: str
    ticker: str
    company_name: str
    quarterly: FinancialReport | None = None
    monthly_revenue: FinancialReport | None = None
    latest_transcript: dict | None = None
    recent_insider_summary: dict | None = None
    latest_13f: dict | None = None
    short_interest: dict | None = None
```

`dict` rather than the Phase 2 dataclasses to avoid cross-module typing fragility.

## Phase 2 module persist toggle

```python
def refresh_ir_materials_for_articles(
    articles, *, _db_path=None, _persist=True
) -> list[IRMaterial]: ...
```

Default `_persist=True` → live pipeline writes data. Phase 2 tests pin `_persist=False` to stay offline; new persist tests pin `_db_path=tmpfile`.

## Out of scope

- Memo / summarizer integration (Phase 4).
- `stock_memo.py` consuming the new bundle fields (Phase 4).
