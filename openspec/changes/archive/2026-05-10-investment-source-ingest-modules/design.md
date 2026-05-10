# Design — investment-source-ingest-modules (Phase 2 of 4)

This change is Phase 2 of the master spec at
`docs/superpowers/specs/2026-05-09-investment-source-expansion-design.md`.

Phase 2 introduces four pure-Python modules whose only job is to fetch
external data and return typed dataclass lists. They do not yet persist
results to SQLite — Phase 3 wires them to new tables.

## Module contracts

```python
# ir_materials.py
@dataclass
class IRMaterial:
    market: str
    ticker: str
    material_type: str  # 'transcript' | 'press_release' | '8-K-text'
    title: str
    body_text: str
    source_url: str
    fetched_at: datetime

def fetch_us_transcripts(ticker: str, *, _fetch_fn=...) -> list[IRMaterial]: ...
def fetch_us_8k_text(ticker: str, *, _fetch_fn=...) -> list[IRMaterial]: ...
def refresh_ir_materials_for_articles(articles: dict) -> list[IRMaterial]: ...

# insider_holdings.py
@dataclass
class InsiderTrade: ...
@dataclass
class Holding: ...
@dataclass
class DirectorChange: ...

def fetch_us_form4_recent(ticker: str, *, _fetch_fn=...) -> list[InsiderTrade]: ...
def fetch_us_13f_holdings(reporter_cik: str, *, _fetch_fn=...) -> list[Holding]: ...
def fetch_tw_director_changes(ticker: str, *, _fetch_fn=...) -> list[DirectorChange]: ...
def refresh_insider_transactions(tickers: list[str]) -> list[InsiderTrade]: ...

# short_interest.py
@dataclass
class ShortInterestRow: ...
@dataclass
class ETFFlow: ...

def fetch_tw_credit_balance(ticker: str, *, _fetch_fn=...) -> list[ShortInterestRow]: ...
def fetch_us_finra_short_interest(ticker: str, *, _fetch_fn=...) -> list[ShortInterestRow]: ...
def fetch_etf_flows_summary(*, _fetch_fn=...) -> list[ETFFlow]: ...
def refresh_short_interest(market: str, tickers: list[str]) -> list[ShortInterestRow]: ...

# macro_data.py
@dataclass
class MacroRelease: ...
@dataclass
class CapexAggregate: ...

def aggregate_hyperscaler_capex(*, _db_path=...) -> CapexAggregate: ...
def extract_macro_signals_from_articles(articles: dict) -> list[MacroRelease]: ...
def refresh_macro_releases() -> dict: ...
```

## Network seam

Every fetcher accepts an injectable `_fetch_fn` defaulting to a real-network
helper. Tests pass a fixture loader instead. No raw `requests.get` inside
business logic.

## main.py wiring

`_refresh_financials_in_background` extends from 4 channels to 8. The 4
new channels run via `asyncio.to_thread`, each with try / except. Failures
are recorded in `errors` list and printed; they do not abort the run.

## Out of scope

- New SQLite tables (Phase 3).
- `stock_memo.py` / `summarizer.py` integration (Phase 4).
- New RSS feeds (Phase 1 closed).
