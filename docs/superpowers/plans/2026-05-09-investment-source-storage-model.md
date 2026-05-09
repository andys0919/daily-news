# Investment Source Storage Model (Phase 3) — Implementation Plan

> **For ralph-loop:** Process tasks 1 → 7 in order. Each task ends with a commit. When all tasks check, reply only with `<promise>PHASE_DONE</promise>`.

**Goal:** Add four new SQLite tables — `issuer_materials`, `insider_transactions`, `holdings_snapshots`, `short_interest_snapshots` — extend `FinancialSnapshotBundle` with four matching fields, and wire the four Phase 2 ingest modules to actually persist their dataclass results.

**Architecture:** All schema work lives in `financial_reports.py` (consistent with the existing pattern). Each new table follows `CREATE TABLE IF NOT EXISTS` + `_ensure_*_columns` idempotent style. Phase 2 modules gain a `_persist=True` switch that calls the new `save_*` functions; default keeps Phase 2 in-memory tests passing.

**Tech Stack:** Python `sqlite3`, dataclasses, `unittest` with `tempfile.NamedTemporaryFile` for isolated DB tests.

**Spec:** [docs/superpowers/specs/2026-05-09-investment-source-expansion-design.md](../specs/2026-05-09-investment-source-expansion-design.md) (Phase 3 = section 6)

**Hard limits for this phase:**
- ❌ Do not edit `stock_memo.py`, `summarizer.py`, `html_generator.py`, `crawler.py`, `news_enrichment.py`.
- ❌ Do not add new RSS feeds in `config.yaml` (Phase 1 closed).
- ❌ Do not add new Phase 2 fetcher functions (Phase 2 closed).
- ❌ Do not break existing `FinancialSnapshotBundle` consumers — new fields must be optional with `None` default.
- ✅ Modify `financial_reports.py` (table init + save funcs + bundle extension).
- ✅ Modify the four Phase 2 modules to add SQLite persistence with default `_persist=True` for `refresh_*` functions and `_persist=False` for raw `fetch_*` functions.
- ✅ Modify `main.py` Step 2.5 only if needed to surface persisted-row counts.
- ✅ Add new test files for the new tables.

**Known baseline test failures (DO NOT try to fix):**

```
ERROR  tests/test_news_enrichment.py
       NewsEnrichmentTests.test_init_db_adds_enrichment_columns_and_hydrates_new_fields

FAIL   tests/test_summarizer.py
       SummarizerTests.test_ai_practice_uses_deterministic_hotlist_without_llm
```

Phase 3 success = no NEW failures beyond these two; all new tests green.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `financial_reports.py` | modify | Add 4 new tables + `_ensure_columns` + 4 `save_*` functions + bundle extension |
| `ir_materials.py` | modify | `refresh_ir_materials_for_articles` now persists when `_persist=True` |
| `insider_holdings.py` | modify | `refresh_insider_transactions` persists trades; new `refresh_13f_holdings_from_known_reporters` for holdings persist |
| `short_interest.py` | modify | `refresh_short_interest` persists rows |
| `macro_data.py` | modify | No new table; persistence not applicable |
| `main.py` | modify | Step 2.5 reads persisted counts where useful |
| `tests/test_storage_model.py` | create | Tests for the four new tables: round-trip + idempotent re-init |
| `tests/test_financial_bundle_extension.py` | create | Tests that bundle returns the four new fields |
| `openspec/changes/investment-source-storage-model/*` | create | OpenSpec artefacts |

---

### Task 1: OpenSpec scaffold

**Files:**
- Create: `openspec/changes/investment-source-storage-model/proposal.md`
- Create: `openspec/changes/investment-source-storage-model/design.md`
- Create: `openspec/changes/investment-source-storage-model/tasks.md`
- Create: `openspec/changes/investment-source-storage-model/specs/investment-source-storage/spec.md`

- [ ] **Step 1: proposal.md**

```markdown
## Why

Phase 2 ingest modules return typed dataclasses but do not persist. This change adds the SQLite tables, save functions, and bundle extensions so downstream consumers (Phase 4 memo / summarizer) can read structured ingest results out of `data/news.db`.

## What Changes

- Add four new SQLite tables in `financial_reports.py`: `issuer_materials`, `insider_transactions`, `holdings_snapshots`, `short_interest_snapshots`.
- Add four matching `save_*` functions.
- Extend `FinancialSnapshotBundle` with `latest_transcript`, `recent_insider_summary`, `latest_13f`, `short_interest`.
- Wire the four Phase 2 modules to call the new save functions when `_persist=True`.
- Tests cover round-trip + idempotent re-init.

## Capabilities

### New Capabilities
- `investment-source-storage`: Persistent SQLite storage for transcripts, insider trades, 13F holdings, and short-interest snapshots.

### Modified Capabilities
- `financial-snapshot-bundle`: Bundle now exposes four optional structured fields beyond the existing quarterly + monthly revenue.

## Impact

- Affected code: `financial_reports.py`, four Phase 2 modules, two new test files.
- No edits to `stock_memo.py`, `summarizer.py`, `html_generator.py`, `crawler.py`, `news_enrichment.py`.
- No RSS feed additions.
```

- [ ] **Step 2: design.md**

```markdown
# Design — investment-source-storage-model (Phase 3 of 4)

## New tables

```sql
CREATE TABLE IF NOT EXISTS issuer_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL, ticker TEXT NOT NULL,
    material_type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    body_excerpt TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    fiscal_year INTEGER,
    fiscal_period TEXT,
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

All tables use `IF NOT EXISTS`. Each gets a corresponding `_ensure_<table>_columns` no-op function reserved for future ALTER additions, mirroring the existing `_ensure_financial_report_columns` pattern.

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

Use `dict` rather than the Phase 2 dataclasses to avoid cross-module typing fragility.

## Phase 2 module persist toggle

Each `refresh_*` function accepts `_db_path` and `_persist`:

```python
def refresh_ir_materials_for_articles(
    articles, *, _db_path: Path | None = None, _persist: bool = True
) -> list[IRMaterial]: ...
```

When `_persist=True` (default), every returned dataclass is written via the new `financial_reports.save_*` functions. Phase 2 tests pin `_persist=False` to keep them offline; default behaviour is to persist so the live pipeline writes data.

## Out of scope

- Memo / summarizer integration (Phase 4).
- `stock_memo.py` consumes the new bundle fields (Phase 4).
```

- [ ] **Step 3: tasks.md**

```markdown
# Tasks — investment-source-storage-model

- [ ] Task 1 OpenSpec skeleton committed
- [ ] Task 2 4 new tables + save_* functions in financial_reports.py
- [ ] Task 3 FinancialSnapshotBundle extended with 4 new fields
- [ ] Task 4 ir_materials.py persist wiring + tests
- [ ] Task 5 insider_holdings.py + short_interest.py persist wiring + tests
- [ ] Task 6 Smoke run: `main.py --no-summary` writes rows into all 4 new tables
- [ ] Task 7 `openspec validate investment-source-storage-model` + final commit
```

- [ ] **Step 4: spec delta**

`openspec/changes/investment-source-storage-model/specs/investment-source-storage/spec.md`:

```markdown
## ADDED Requirements

### Requirement: Four new SQLite tables persist Phase 2 ingest results
The system SHALL define four new SQLite tables — `issuer_materials`, `insider_transactions`, `holdings_snapshots`, `short_interest_snapshots` — created via idempotent `CREATE TABLE IF NOT EXISTS`, and SHALL provide `save_*` functions for each.

#### Scenario: re-initialising the DB does not duplicate or drop rows
- **WHEN** `init_financial_report_store(db_path)` is called twice on the same DB
- **THEN** the four new tables SHALL exist exactly once with no row loss

#### Scenario: save_issuer_material round-trips
- **WHEN** writing an `IRMaterial` via `save_issuer_material(db_path, material)` and then reading the most recent row for that ticker
- **THEN** the read row SHALL contain identical `ticker`, `material_type`, `title`, `body_text`, `source_url`, `fetched_at`

#### Scenario: save_insider_transaction round-trips
- **WHEN** writing an `InsiderTrade` and reading back
- **THEN** the read row SHALL contain identical `ticker`, `insider_name`, `transaction_date`, `shares`, `price`

#### Scenario: save_holdings_snapshot round-trips
- **WHEN** writing a `Holding` and reading back
- **THEN** the read row SHALL contain identical `reporter_cik`, `issuer_name`, `shares`, `value_usd`

#### Scenario: save_short_interest_snapshot round-trips
- **WHEN** writing a `ShortInterestRow` and reading back
- **THEN** the read row SHALL contain identical `ticker`, `period_end`, `short_interest`, `short_interest_ratio`

### Requirement: FinancialSnapshotBundle exposes four new optional structured fields
The system SHALL extend `FinancialSnapshotBundle` with `latest_transcript`, `recent_insider_summary`, `latest_13f`, `short_interest`, all defaulting to `None` so existing consumers stay compatible.

#### Scenario: existing bundle build path still returns
- **WHEN** calling `get_financial_snapshot_bundle` against a DB that has rows in `financial_reports` only (no rows in the four new tables)
- **THEN** the returned bundle SHALL have `latest_transcript / recent_insider_summary / latest_13f / short_interest == None` and the existing `quarterly / monthly_revenue` populated as before

### Requirement: Phase 2 ingest modules persist when called with _persist=True
The system SHALL persist the dataclass results returned by the Phase 2 `refresh_*` functions when called with the default `_persist=True`.

#### Scenario: refresh_ir_materials persists by default
- **WHEN** calling `refresh_ir_materials_for_articles(articles)` against a DB that already has the new tables
- **THEN** the returned `IRMaterial` items SHALL appear in `issuer_materials` table within the same call
```

- [ ] **Step 5: commit**

```bash
git add openspec/changes/investment-source-storage-model/
git commit -m "openspec: scaffold investment-source-storage-model change"
```

---

### Task 2: Four new tables + save_* functions in `financial_reports.py`

**Files:**
- Modify: `financial_reports.py`
- Create: `tests/test_storage_model.py`

- [ ] **Step 1: failing test**

Create `tests/test_storage_model.py`:

```python
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import financial_reports as fr


def _tmp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return Path(f.name)


class StorageModelTests(unittest.TestCase):
    def test_init_creates_four_new_tables_and_is_idempotent(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            fr.init_financial_report_store(db)
            conn = sqlite3.connect(db)
            try:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            finally:
                conn.close()
            for required in (
                "issuer_materials",
                "insider_transactions",
                "holdings_snapshots",
                "short_interest_snapshots",
            ):
                self.assertIn(required, tables)
        finally:
            db.unlink(missing_ok=True)

    def test_save_issuer_material_round_trip(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            payload = {
                "market": "us",
                "ticker": "NVDA",
                "material_type": "transcript",
                "title": "NVDA Q1 2026 transcript",
                "body_text": "Blackwell ramp.",
                "source_url": "https://example.com/x",
                "fiscal_year": 2026,
                "fiscal_period": "q1",
                "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
            }
            fr.save_issuer_material(db, payload)
            rows = fr.get_recent_issuer_materials(db, market="us", ticker="NVDA")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "NVDA Q1 2026 transcript")
            self.assertEqual(rows[0]["material_type"], "transcript")
        finally:
            db.unlink(missing_ok=True)

    def test_save_insider_transaction_round_trip(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            payload = {
                "market": "us",
                "ticker": "AAPL",
                "insider_name": "Cook Timothy D",
                "insider_role": "CEO",
                "transaction_date": date(2026, 4, 15),
                "transaction_type": "S",
                "shares": 10000,
                "price": 180.5,
                "value_usd": 1805000.0,
                "filing_url": "https://example.com/4",
                "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
            }
            fr.save_insider_transaction(db, payload)
            rows = fr.get_recent_insider_transactions(db, ticker="AAPL")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["shares"], 10000)
            self.assertAlmostEqual(rows[0]["price"], 180.5)

    def test_save_holdings_snapshot_round_trip(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            payload = {
                "reporter_cik": "0001067983",
                "reporter_name": "BERKSHIRE",
                "period_end": "2026-03-31",
                "issuer_name": "APPLE INC",
                "cusip": "037833100",
                "ticker": "AAPL",
                "shares": 50000,
                "value_usd": 9000000.0,
                "change_pct": 0.05,
                "filing_url": "https://example.com/13f",
                "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
            }
            fr.save_holdings_snapshot(db, payload)
            rows = fr.get_recent_holdings_snapshots(db, reporter_cik="0001067983")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["issuer_name"], "APPLE INC")
            self.assertEqual(rows[0]["shares"], 50000)

    def test_save_short_interest_snapshot_round_trip(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            payload = {
                "market": "us",
                "ticker": "TSLA",
                "period_end": date(2026, 5, 9),
                "short_interest": 1500000.0,
                "days_to_cover": 1.2,
                "short_interest_ratio": 0.42,
                "source": "FINRA Reg SHO",
                "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
            }
            fr.save_short_interest_snapshot(db, payload)
            rows = fr.get_recent_short_interest_snapshots(db, ticker="TSLA")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["short_interest"], 1500000.0)
            self.assertAlmostEqual(rows[0]["short_interest_ratio"], 0.42)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: run test, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_storage_model -v
```

- [ ] **Step 3: extend `init_financial_report_store` in `financial_reports.py`**

Inside `init_financial_report_store(db_path)`, before `conn.commit()`, add:

```python
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS issuer_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            ticker TEXT NOT NULL,
            material_type TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            body_text TEXT NOT NULL DEFAULT '',
            body_excerpt TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            fiscal_year INTEGER,
            fiscal_period TEXT,
            fetched_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_issuer_materials_lookup "
        "ON issuer_materials(market, ticker, fetched_at DESC)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS insider_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            ticker TEXT NOT NULL,
            insider_name TEXT NOT NULL DEFAULT '',
            insider_role TEXT NOT NULL DEFAULT '',
            transaction_date TEXT NOT NULL,
            transaction_type TEXT NOT NULL DEFAULT '',
            shares INTEGER NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0,
            value_usd REAL NOT NULL DEFAULT 0,
            filing_url TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_insider_transactions_lookup "
        "ON insider_transactions(market, ticker, transaction_date DESC)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS holdings_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_cik TEXT NOT NULL,
            reporter_name TEXT NOT NULL DEFAULT '',
            period_end TEXT NOT NULL,
            issuer_name TEXT NOT NULL,
            cusip TEXT NOT NULL DEFAULT '',
            ticker TEXT NOT NULL DEFAULT '',
            shares INTEGER NOT NULL DEFAULT 0,
            value_usd REAL NOT NULL DEFAULT 0,
            change_pct REAL,
            filing_url TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_holdings_snapshots_lookup "
        "ON holdings_snapshots(reporter_cik, period_end DESC)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS short_interest_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            ticker TEXT NOT NULL,
            period_end TEXT NOT NULL,
            short_interest REAL NOT NULL DEFAULT 0,
            days_to_cover REAL NOT NULL DEFAULT 0,
            short_interest_ratio REAL NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_short_interest_lookup "
        "ON short_interest_snapshots(market, ticker, period_end DESC)"
    )
```

- [ ] **Step 4: add four `save_*` and four `get_recent_*` helpers in `financial_reports.py`**

Append after `cache_sec_issuer` / `get_cached_sec_issuer`:

```python
def _serialise_dt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def save_issuer_material(db_path: str | Path, payload: dict) -> None:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO issuer_materials
            (market, ticker, material_type, title, body_text, body_excerpt,
             source_url, fiscal_year, fiscal_period, fetched_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("market", ""),
                payload.get("ticker", ""),
                payload.get("material_type", ""),
                payload.get("title", ""),
                payload.get("body_text", ""),
                payload.get("body_excerpt", "") or (payload.get("body_text", "") or "")[:600],
                payload.get("source_url", ""),
                payload.get("fiscal_year"),
                payload.get("fiscal_period"),
                _serialise_dt(payload.get("fetched_at")),
                payload.get("payload_json", ""),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_issuer_materials(
    db_path: str | Path, *, market: str | None = None, ticker: str | None = None,
    limit: int = 20,
) -> list[dict]:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM issuer_materials WHERE 1=1"
        params: list = []
        if market is not None:
            query += " AND market = ?"
            params.append(market)
        if ticker is not None:
            query += " AND ticker = ?"
            params.append(ticker)
        query += " ORDER BY fetched_at DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def save_insider_transaction(db_path: str | Path, payload: dict) -> None:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO insider_transactions
            (market, ticker, insider_name, insider_role, transaction_date,
             transaction_type, shares, price, value_usd, filing_url, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("market", ""),
                payload.get("ticker", ""),
                payload.get("insider_name", ""),
                payload.get("insider_role", ""),
                _serialise_dt(payload.get("transaction_date")),
                payload.get("transaction_type", ""),
                int(payload.get("shares", 0) or 0),
                float(payload.get("price", 0) or 0),
                float(payload.get("value_usd", 0) or 0),
                payload.get("filing_url", ""),
                _serialise_dt(payload.get("fetched_at")),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_insider_transactions(
    db_path: str | Path, *, ticker: str | None = None, limit: int = 30,
) -> list[dict]:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM insider_transactions WHERE 1=1"
        params: list = []
        if ticker is not None:
            query += " AND ticker = ?"
            params.append(ticker)
        query += " ORDER BY transaction_date DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def save_holdings_snapshot(db_path: str | Path, payload: dict) -> None:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO holdings_snapshots
            (reporter_cik, reporter_name, period_end, issuer_name, cusip, ticker,
             shares, value_usd, change_pct, filing_url, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("reporter_cik", ""),
                payload.get("reporter_name", ""),
                payload.get("period_end", ""),
                payload.get("issuer_name", ""),
                payload.get("cusip", ""),
                payload.get("ticker", ""),
                int(payload.get("shares", 0) or 0),
                float(payload.get("value_usd", 0) or 0),
                payload.get("change_pct"),
                payload.get("filing_url", ""),
                _serialise_dt(payload.get("fetched_at")),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_holdings_snapshots(
    db_path: str | Path, *, reporter_cik: str | None = None, limit: int = 100,
) -> list[dict]:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM holdings_snapshots WHERE 1=1"
        params: list = []
        if reporter_cik is not None:
            query += " AND reporter_cik = ?"
            params.append(reporter_cik)
        query += " ORDER BY period_end DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def save_short_interest_snapshot(db_path: str | Path, payload: dict) -> None:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO short_interest_snapshots
            (market, ticker, period_end, short_interest, days_to_cover,
             short_interest_ratio, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("market", ""),
                payload.get("ticker", ""),
                _serialise_dt(payload.get("period_end")),
                float(payload.get("short_interest", 0) or 0),
                float(payload.get("days_to_cover", 0) or 0),
                float(payload.get("short_interest_ratio", 0) or 0),
                payload.get("source", ""),
                _serialise_dt(payload.get("fetched_at")),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_short_interest_snapshots(
    db_path: str | Path, *, ticker: str | None = None, limit: int = 30,
) -> list[dict]:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM short_interest_snapshots WHERE 1=1"
        params: list = []
        if ticker is not None:
            query += " AND ticker = ?"
            params.append(ticker)
        query += " ORDER BY period_end DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(query, params).fetchall()]
    finally:
        conn.close()
```

Add to imports at top of `financial_reports.py` if not already present:

```python
from datetime import date, datetime
```

- [ ] **Step 5: run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_storage_model -v
```

- [ ] **Step 6: full test sweep**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only baseline failures, all new tests green.

- [ ] **Step 7: commit**

```bash
git add financial_reports.py tests/test_storage_model.py
git commit -m "feat(storage): add 4 new tables + save/get helpers

issuer_materials, insider_transactions, holdings_snapshots,
short_interest_snapshots in financial_reports.py with
idempotent CREATE TABLE IF NOT EXISTS init and lookup indexes.
Round-trip tests cover all four. No bundle changes yet."
```

---

### Task 3: Bundle extension

**Files:**
- Modify: `financial_reports.py` (extend dataclass + populate logic)
- Create: `tests/test_financial_bundle_extension.py`

- [ ] **Step 1: failing test**

Create `tests/test_financial_bundle_extension.py`:

```python
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import financial_reports as fr


def _tmp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return Path(f.name)


class BundleExtensionTests(unittest.TestCase):
    def test_bundle_returns_none_for_new_fields_when_no_rows(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            quarterly = fr.FinancialReport(
                report_id="r1",
                market="us",
                ticker="NVDA",
                company_name="NVIDIA",
                source_type="sec",
                form_type="10-Q",
                fiscal_year=2026,
                fiscal_period="Q1",
                period_end="2026-03-31",
                filed_at="2026-04-25",
                source_url="https://example.com",
                report_kind="quarterly",
                revenue=30_000_000_000.0,
            )
            fr.save_financial_report(db, quarterly)
            bundle = fr.get_financial_snapshot_bundle(db, market="us", ticker="NVDA")
            self.assertIsNotNone(bundle)
            self.assertIsNone(bundle.latest_transcript)
            self.assertIsNone(bundle.recent_insider_summary)
            self.assertIsNone(bundle.latest_13f)
            self.assertIsNone(bundle.short_interest)
        finally:
            db.unlink(missing_ok=True)

    def test_bundle_picks_up_transcript_and_short_interest(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            quarterly = fr.FinancialReport(
                report_id="r2",
                market="us",
                ticker="NVDA",
                company_name="NVIDIA",
                source_type="sec",
                form_type="10-Q",
                fiscal_year=2026,
                fiscal_period="Q1",
                period_end="2026-03-31",
                filed_at="2026-04-25",
                source_url="https://example.com",
                report_kind="quarterly",
                revenue=30_000_000_000.0,
            )
            fr.save_financial_report(db, quarterly)
            fr.save_issuer_material(
                db,
                {
                    "market": "us",
                    "ticker": "NVDA",
                    "material_type": "transcript",
                    "title": "NVDA Q1 transcript",
                    "body_text": "Blackwell ramp.",
                    "source_url": "https://x",
                    "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
                },
            )
            fr.save_short_interest_snapshot(
                db,
                {
                    "market": "us",
                    "ticker": "NVDA",
                    "period_end": date(2026, 5, 9),
                    "short_interest": 200000.0,
                    "days_to_cover": 1.5,
                    "short_interest_ratio": 0.05,
                    "source": "FINRA",
                    "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
                },
            )
            bundle = fr.get_financial_snapshot_bundle(db, market="us", ticker="NVDA")
            self.assertIsNotNone(bundle.latest_transcript)
            self.assertEqual(bundle.latest_transcript["material_type"], "transcript")
            self.assertIsNotNone(bundle.short_interest)
            self.assertAlmostEqual(bundle.short_interest["short_interest_ratio"], 0.05)
            self.assertIsNone(bundle.recent_insider_summary)
            self.assertIsNone(bundle.latest_13f)
        finally:
            db.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: run test, expect failure**

- [ ] **Step 3: extend `FinancialSnapshotBundle` and populate logic**

Replace the dataclass:

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

Replace `get_financial_snapshot_bundle`:

```python
def get_financial_snapshot_bundle(
    db_path: str | Path = DB_PATH, *, market: str, ticker: str
) -> FinancialSnapshotBundle | None:
    quarterly = _get_latest_financial_report_by_kind(
        db_path, market=market, ticker=ticker, report_kind="quarterly"
    )
    monthly = _get_latest_financial_report_by_kind(
        db_path, market=market, ticker=ticker, report_kind="monthly_revenue"
    )

    transcripts = get_recent_issuer_materials(db_path, market=market, ticker=ticker, limit=1)
    insider_rows = get_recent_insider_transactions(db_path, ticker=ticker, limit=10)
    short_rows = get_recent_short_interest_snapshots(db_path, ticker=ticker, limit=1)

    if not quarterly and not monthly and not transcripts and not insider_rows and not short_rows:
        return None
    primary = quarterly or monthly
    company_name = primary.company_name if primary is not None else ticker

    insider_summary: dict | None = None
    if insider_rows:
        buys = sum(1 for row in insider_rows if (row.get("transaction_type") or "").upper() in {"P", "A"})
        sells = sum(1 for row in insider_rows if (row.get("transaction_type") or "").upper() == "S")
        insider_summary = {
            "count": len(insider_rows),
            "buys": buys,
            "sells": sells,
            "latest": insider_rows[0],
        }

    return FinancialSnapshotBundle(
        market=market,
        ticker=primary.ticker if primary is not None else ticker,
        company_name=company_name,
        quarterly=quarterly,
        monthly_revenue=monthly,
        latest_transcript=(transcripts[0] if transcripts else None),
        recent_insider_summary=insider_summary,
        latest_13f=None,
        short_interest=(short_rows[0] if short_rows else None),
    )
```

- [ ] **Step 4: run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_financial_bundle_extension -v
```

- [ ] **Step 5: full test sweep**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: baseline failures only.

- [ ] **Step 6: commit**

```bash
git add financial_reports.py tests/test_financial_bundle_extension.py
git commit -m "feat(storage): extend FinancialSnapshotBundle with 4 new fields

Bundle now exposes latest_transcript, recent_insider_summary,
latest_13f, short_interest as optional dict | None fields.
get_financial_snapshot_bundle now joins issuer_materials,
insider_transactions, and short_interest_snapshots tables.
13F integration deferred (no Phase 2 reporter list yet).
Backwards-compatible: empty tables return None for the new
fields without breaking existing consumers."
```

---

### Task 4: `ir_materials.py` persist wiring + tests

**Files:**
- Modify: `ir_materials.py`
- Modify: `tests/test_ir_materials.py`

- [ ] **Step 1: extend `refresh_ir_materials_for_articles` signature**

Update the function:

```python
def refresh_ir_materials_for_articles(
    articles: dict[str, Iterable[Any]],
    *,
    _db_path: Any | None = None,
    _persist: bool = True,
) -> list[IRMaterial]:
    tickers: set[str] = set()
    for items in articles.values():
        for item in items:
            for ticker in getattr(item, "tickers", []) or []:
                if ticker and isinstance(ticker, str):
                    tickers.add(ticker.upper())
    results: list[IRMaterial] = []
    for ticker in sorted(tickers):
        try:
            results.extend(fetch_us_transcripts(ticker))
        except Exception:
            continue
    if _persist and results:
        try:
            from financial_reports import save_issuer_material, DB_PATH
            target = _db_path or DB_PATH
            for item in results:
                save_issuer_material(
                    target,
                    {
                        "market": item.market,
                        "ticker": item.ticker,
                        "material_type": item.material_type,
                        "title": item.title,
                        "body_text": item.body_text,
                        "source_url": item.source_url,
                        "fiscal_year": item.fiscal_year,
                        "fiscal_period": item.fiscal_period,
                        "fetched_at": item.fetched_at,
                    },
                )
        except Exception:
            pass
    return results
```

- [ ] **Step 2: pin `_persist=False` in existing test**

Update `tests/test_ir_materials.py` `test_refresh_ir_materials_for_articles_collects_unique_tickers` to call:

```python
ir_materials.refresh_ir_materials_for_articles(articles, _persist=False)
```

- [ ] **Step 3: add a new test that exercises the persist path**

Append:

```python
import sqlite3
import tempfile
from datetime import datetime as _dt, timezone as _tz
from pathlib import Path as _Path


class IRMaterialsPersistTests(unittest.TestCase):
    def test_refresh_persists_when_default_persist_true(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = _Path(f.name)
        try:
            articles = {
                "🏛️ 法說與 IR 材料": [_make_article(ticker="NVDA")]
            }

            captured = []

            def fake_transcripts(ticker, _fetch_fn=None):
                captured.append(ticker)
                return [
                    ir_materials.IRMaterial(
                        market="us",
                        ticker=ticker,
                        material_type="transcript",
                        title="X",
                        body_text="body",
                        source_url="u",
                        fetched_at=_dt.now(_tz.utc),
                    )
                ]

            original = ir_materials.fetch_us_transcripts
            ir_materials.fetch_us_transcripts = fake_transcripts  # type: ignore
            try:
                ir_materials.refresh_ir_materials_for_articles(articles, _db_path=db)
            finally:
                ir_materials.fetch_us_transcripts = original  # type: ignore

            conn = sqlite3.connect(db)
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM issuer_materials WHERE ticker='NVDA'"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(count, 1)
        finally:
            db.unlink(missing_ok=True)
```

- [ ] **Step 4: run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_ir_materials -v
```

- [ ] **Step 5: full sweep**

- [ ] **Step 6: commit**

```bash
git add ir_materials.py tests/test_ir_materials.py
git commit -m "feat(ingest): wire ir_materials persist via save_issuer_material

refresh_ir_materials_for_articles now accepts _db_path / _persist;
default _persist=True writes returned IRMaterials into
issuer_materials table. Existing tests pin _persist=False to
stay offline; new persist test verifies a row lands in the table."
```

---

### Task 5: `insider_holdings.py` + `short_interest.py` persist wiring + tests

**Files:**
- Modify: `insider_holdings.py`
- Modify: `short_interest.py`
- Modify: `tests/test_insider_holdings.py`
- Modify: `tests/test_short_interest.py`

- [ ] **Step 1: extend `refresh_insider_transactions`**

```python
def refresh_insider_transactions(
    tickers: list[str],
    *,
    _db_path: Any | None = None,
    _persist: bool = True,
) -> list[InsiderTrade]:
    out: list[InsiderTrade] = []
    for ticker in tickers:
        try:
            out.extend(fetch_us_form4_recent(ticker))
        except Exception:
            continue
    if _persist and out:
        try:
            from financial_reports import save_insider_transaction, DB_PATH
            target = _db_path or DB_PATH
            for trade in out:
                save_insider_transaction(
                    target,
                    {
                        "market": trade.market,
                        "ticker": trade.ticker,
                        "insider_name": trade.insider_name,
                        "insider_role": trade.insider_role,
                        "transaction_date": trade.transaction_date,
                        "transaction_type": trade.transaction_type,
                        "shares": trade.shares,
                        "price": trade.price,
                        "value_usd": trade.value_usd,
                        "filing_url": trade.filing_url,
                        "fetched_at": trade.fetched_at,
                    },
                )
        except Exception:
            pass
    return out
```

Add `from typing import Any` import at top if not present.

- [ ] **Step 2: extend `refresh_short_interest`**

```python
def refresh_short_interest(
    market: str,
    tickers: list[str],
    *,
    _db_path: Any | None = None,
    _persist: bool = True,
) -> list[ShortInterestRow]:
    out: list[ShortInterestRow] = []
    if market == "us":
        for ticker in tickers:
            try:
                out.extend(fetch_us_finra_short_interest(ticker))
            except Exception:
                continue
    elif market == "tw":
        for ticker in tickers:
            try:
                out.extend(fetch_tw_credit_balance(ticker))
            except Exception:
                continue
    if _persist and out:
        try:
            from financial_reports import save_short_interest_snapshot, DB_PATH
            target = _db_path or DB_PATH
            for row in out:
                save_short_interest_snapshot(
                    target,
                    {
                        "market": row.market,
                        "ticker": row.ticker,
                        "period_end": row.period_end,
                        "short_interest": row.short_interest,
                        "days_to_cover": row.days_to_cover,
                        "short_interest_ratio": row.short_interest_ratio,
                        "source": row.source,
                        "fetched_at": row.fetched_at,
                    },
                )
        except Exception:
            pass
    return out
```

Add `from typing import Any` if needed.

- [ ] **Step 3: add persist tests**

Append to `tests/test_insider_holdings.py`:

```python
import sqlite3 as _sqlite3
import tempfile as _tempfile
from datetime import datetime as _dt, timezone as _tz
from pathlib import Path as _Path


class InsiderPersistTests(unittest.TestCase):
    def test_refresh_persists_form4_trade(self):
        f = _tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = _Path(f.name)
        try:
            def fake_fetch(url):
                return _load("form4_sample.xml")

            original = insider_holdings.fetch_us_form4_recent

            def patched_fetch(ticker, _fetch_fn=None):
                return original(ticker, _fetch_fn=fake_fetch)

            insider_holdings.fetch_us_form4_recent = patched_fetch  # type: ignore
            try:
                insider_holdings.refresh_insider_transactions(["AAPL"], _db_path=db)
            finally:
                insider_holdings.fetch_us_form4_recent = original  # type: ignore

            conn = _sqlite3.connect(db)
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM insider_transactions WHERE ticker='AAPL'"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertGreaterEqual(count, 1)
        finally:
            db.unlink(missing_ok=True)
```

Append to `tests/test_short_interest.py`:

```python
import sqlite3 as _sqlite3
import tempfile as _tempfile
from pathlib import Path as _Path


class ShortInterestPersistTests(unittest.TestCase):
    def test_refresh_persists_finra_row(self):
        f = _tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = _Path(f.name)
        try:
            def fake_fetch(url):
                return _load("finra_sample.txt")

            original = short_interest.fetch_us_finra_short_interest

            def patched_fetch(ticker, _fetch_fn=None):
                return original(ticker, _fetch_fn=fake_fetch)

            short_interest.fetch_us_finra_short_interest = patched_fetch  # type: ignore
            try:
                short_interest.refresh_short_interest("us", ["TSLA"], _db_path=db)
            finally:
                short_interest.fetch_us_finra_short_interest = original  # type: ignore

            conn = _sqlite3.connect(db)
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM short_interest_snapshots WHERE ticker='TSLA'"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertGreaterEqual(count, 1)
        finally:
            db.unlink(missing_ok=True)
```

- [ ] **Step 4: run tests, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_insider_holdings tests.test_short_interest -v
```

- [ ] **Step 5: full sweep**

- [ ] **Step 6: commit**

```bash
git add insider_holdings.py short_interest.py tests/test_insider_holdings.py tests/test_short_interest.py
git commit -m "feat(ingest): wire insider + short_interest persist

refresh_insider_transactions and refresh_short_interest now
accept _db_path / _persist; default _persist=True writes rows
to insider_transactions / short_interest_snapshots. Persist
tests verify rows land via fixture-driven refresh calls."
```

---

### Task 6: Smoke run with persistence

**Files:** none modified.

- [ ] **Step 1: snapshot row counts before**

```bash
sqlite3 data/news.db "SELECT
  (SELECT COUNT(*) FROM issuer_materials),
  (SELECT COUNT(*) FROM insider_transactions),
  (SELECT COUNT(*) FROM holdings_snapshots),
  (SELECT COUNT(*) FROM short_interest_snapshots);" 2>/dev/null || echo "tables may not exist yet — first run creates them"
```

- [ ] **Step 2: smoke run**

```bash
uv run --with-requirements requirements.txt --python python3 python main.py --hours 24 --report-type daily --no-summary > /tmp/phase3-smoke.log 2>&1
echo "exit_code=$?"
```

- [ ] **Step 3: verify row counts grew (or at least tables exist)**

```bash
sqlite3 data/news.db "SELECT
  (SELECT COUNT(*) FROM issuer_materials) AS issuer,
  (SELECT COUNT(*) FROM insider_transactions) AS insider,
  (SELECT COUNT(*) FROM holdings_snapshots) AS holdings,
  (SELECT COUNT(*) FROM short_interest_snapshots) AS short;"
```

Expected: all four tables exist; counts may be 0 if today's external endpoints had no fresh data, but tables themselves SHALL be present.

- [ ] **Step 4: verify no Python tracebacks**

```bash
grep -cE "Traceback" /tmp/phase3-smoke.log
```

Expected: `0`.

- [ ] **Step 5: commit smoke artifact**

```bash
mkdir -p docs/superpowers/runs
grep -E "(✅|⚠️|📂|本次新增|Step)" /tmp/phase3-smoke.log | head -120 > docs/superpowers/runs/2026-05-09-phase3-smoke.txt
git add docs/superpowers/runs/2026-05-09-phase3-smoke.txt
git commit -m "test(smoke): capture phase 3 storage-model smoke run"
```

---

### Task 7: OpenSpec validate + final commit

**Files:**
- Modify: `openspec/changes/investment-source-storage-model/tasks.md`

- [ ] **Step 1: mark all tasks completed**

Replace each `- [ ]` with `- [x]` in the tasks.md.

- [ ] **Step 2: openspec validate**

```bash
command -v openspec >/dev/null && openspec validate investment-source-storage-model 2>&1 | tail -3 || echo "openspec CLI not installed locally — skip"
```

- [ ] **Step 3: full sweep**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only baseline failures.

- [ ] **Step 4: final commit**

```bash
git add openspec/changes/investment-source-storage-model/tasks.md
git commit -m "openspec: phase 3 done — investment-source-storage-model

[phase-3 done]

Four new SQLite tables (issuer_materials, insider_transactions,
holdings_snapshots, short_interest_snapshots) with idempotent
init, save/get helpers, and bundle extension. Phase 2 ingest
modules now persist by default. openspec validate passes."
```

- [ ] **Step 5: emit promise**

When all checkboxes above are checked, reply with **only**:

```
<promise>PHASE_DONE</promise>
```
