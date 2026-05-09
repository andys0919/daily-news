# Investment Source Ingest Modules (Phase 2) — Implementation Plan

> **For ralph-loop:** Process tasks 1 → 8 in order. Each task ends with a commit. Mark each `- [ ]` as `- [x]` when its tests pass and the commit lands. When all tasks are checked, reply only with `<promise>PHASE_DONE</promise>`.

**Goal:** Add four new structured ingest modules — `ir_materials.py`, `insider_holdings.py`, `short_interest.py`, `macro_data.py` — that fetch and parse free investment data from official endpoints, returning typed dataclass lists. Wire them into `main.py` Step 2.5 in parallel with the existing four financial channels.

**Architecture:** Each module is a sync Python file at the repo root that exposes refresh / fetch functions. `main.py` Step 2.5 calls them via `asyncio.to_thread`. **Phase 2 does NOT persist to SQLite** — Phase 3 wires the dataclass results to new tables. Tests use HTML / XML / CSV fixtures under `tests/fixtures/` and `unittest.mock.patch` to avoid network.

**Tech Stack:** Python `requests` + `BeautifulSoup` (HTML), built-in `xml.etree.ElementTree` (Atom / SEC XML), `csv` (FINRA), `dataclasses`, `unittest`.

**Spec:** [docs/superpowers/specs/2026-05-09-investment-source-expansion-design.md](../specs/2026-05-09-investment-source-expansion-design.md) (Phase 2 = section 5)

**Hard limits for this phase:**
- ❌ Do not change SQLite schema or persist new dataclasses to new tables (that is Phase 3).
- ❌ Do not edit `stock_memo.py`, `summarizer.py`, `html_generator.py`, `financial_reports.py`, `crawler.py`, `news_enrichment.py`.
- ❌ Do not add new RSS feeds in `config.yaml` (Phase 1 is closed).
- ❌ Do not run live network calls in tests — always mock via fixtures.
- ✅ Create new `.py` modules at repo root (`ir_materials.py`, `insider_holdings.py`, `short_interest.py`, `macro_data.py`).
- ✅ Modify `main.py` Step 2.5 to add 4 new background tasks (print-stats-only).
- ✅ Add fixture files under `tests/fixtures/`.

**Known baseline test failures (DO NOT try to fix these):**

```
ERROR  tests/test_news_enrichment.py
       NewsEnrichmentTests.test_init_db_adds_enrichment_columns_and_hydrates_new_fields
       (KeyError: '💰 財經與總經')

FAIL   tests/test_summarizer.py
       SummarizerTests.test_ai_practice_uses_deterministic_hotlist_without_llm
       (AssertionError: LLM should not be called for ai_practice)
```

Phase 2 success = no NEW failures beyond these two, plus all new tests green.

**Sandbox / network rule:** All four modules must be designed so their fetcher functions accept an injectable `_fetch_fn` (default = real network) so tests can substitute a fixture loader. No raw `requests.get` inside business logic without a seam.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `ir_materials.py` | create | Fetch Motley Fool transcripts + SEC 8-K text; return `IRMaterial` list |
| `insider_holdings.py` | create | Fetch SEC Form 4 + SEC 13F-HR + TWSE 董監持股; return `InsiderTrade` / `Holding` / `DirectorChange` lists |
| `short_interest.py` | create | Fetch TWSE 信用交易 + FINRA short interest + ETF flow snapshot; return `ShortInterestRow` / `ETFFlow` lists |
| `macro_data.py` | create | Aggregate hyperscaler capex from existing `financial_reports`; extract macro signals from `articles` |
| `main.py` | modify | Step 2.5 — add 4 background `asyncio.to_thread` tasks; print-stats-only |
| `tests/test_ir_materials.py` | create | Fixture-based parser tests |
| `tests/test_insider_holdings.py` | create | Fixture-based parser tests |
| `tests/test_short_interest.py` | create | Fixture-based parser tests |
| `tests/test_macro_data.py` | create | DB-mock + regex tests |
| `tests/fixtures/ir_materials/` | create | sample Motley Fool HTML, sample SEC 8-K text |
| `tests/fixtures/insider_holdings/` | create | sample Form 4 XML, sample 13F-HR XML |
| `tests/fixtures/short_interest/` | create | sample TWSE CSV-like, sample FINRA CSV |
| `openspec/changes/investment-source-ingest-modules/*` | create | OpenSpec proposal / design / tasks / spec deltas |

---

### Task 1: OpenSpec change skeleton

**Files:**
- Create: `openspec/changes/investment-source-ingest-modules/proposal.md`
- Create: `openspec/changes/investment-source-ingest-modules/design.md`
- Create: `openspec/changes/investment-source-ingest-modules/tasks.md`
- Create: `openspec/changes/investment-source-ingest-modules/specs/investment-source-ingest/spec.md`

- [ ] **Step 1: Create proposal.md**

```markdown
## Why

Phase 1 added RSS-layer coverage for five investment categories. The next step is to fetch structured data (transcripts, Form 4, 13F-HR, TWSE credit balance, FINRA short interest, hyperscaler capex aggregate) and return typed dataclasses that downstream phases can persist and consume.

## What Changes

- Add four new modules: `ir_materials.py`, `insider_holdings.py`, `short_interest.py`, `macro_data.py`.
- Each module exposes pure-Python fetcher / aggregator functions returning typed dataclass lists.
- Wire all four into `main.py` Step 2.5 as background tasks parallel to the existing four financial-data channels.
- This phase does NOT persist data to new SQLite tables — Phase 3 does.

## Capabilities

### New Capabilities
- `investment-source-ingest`: Pure-Python fetchers for transcripts, insider / 13F filings, short interest / ETF flow snapshots, and macro aggregates.

### Modified Capabilities
- `pipeline-orchestration`: `main.py` Step 2.5 now runs eight parallel background tasks instead of four.

## Impact

- Affected code: four new modules, `main.py`, four new test files, `tests/fixtures/` directory.
- No SQLite schema change.
- No edits to `stock_memo.py`, `summarizer.py`, `html_generator.py`, `financial_reports.py`, `crawler.py`, `news_enrichment.py`.
```

- [ ] **Step 2: Create design.md**

```markdown
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

Counts:
```python
return {
    "us": ..., "tw": ..., "tpex": ..., "mops": ...,
    "ir": ir_count, "insider": insider_count,
    "short": short_count, "macro": macro_count,
}, errors, elapsed
```

For Phase 2 the four new counts always print; persistence is a no-op.

## Out of scope

- New SQLite tables (Phase 3).
- `stock_memo.py` / `summarizer.py` integration (Phase 4).
- New RSS feeds (Phase 1 closed).
```

- [ ] **Step 3: Create tasks.md**

```markdown
# Tasks — investment-source-ingest-modules

- [ ] Task 1 OpenSpec skeleton committed
- [ ] Task 2 ir_materials.py module + fixture tests
- [ ] Task 3 insider_holdings.py module + fixture tests
- [ ] Task 4 short_interest.py module + fixture tests
- [ ] Task 5 macro_data.py module + DB-mock tests
- [ ] Task 6 main.py Step 2.5 wires 4 new background tasks
- [ ] Task 7 Smoke run: `main.py --no-summary` completes with 8 channels printed
- [ ] Task 8 `openspec validate investment-source-ingest-modules` + final commit
```

- [ ] **Step 4: Create spec delta**

Write `openspec/changes/investment-source-ingest-modules/specs/investment-source-ingest/spec.md`:

```markdown
## ADDED Requirements

### Requirement: Four new ingest modules expose pure-Python fetchers
The system SHALL expose four new modules — `ir_materials`, `insider_holdings`, `short_interest`, `macro_data` — at the repo root, each providing fetcher / aggregator functions that return typed dataclass lists.

#### Scenario: ir_materials returns IRMaterial dataclasses
- **WHEN** calling `ir_materials.fetch_us_transcripts("NVDA")` with an injected fixture HTML payload
- **THEN** the function SHALL return a list of `IRMaterial` whose `ticker == "NVDA"` and `body_text` is non-empty

#### Scenario: insider_holdings returns InsiderTrade dataclasses
- **WHEN** calling `insider_holdings.fetch_us_form4_recent("AAPL")` with an injected fixture XML payload
- **THEN** the function SHALL return a list of `InsiderTrade` with non-zero `shares` and a parsed `transaction_date`

#### Scenario: short_interest returns ShortInterestRow dataclasses
- **WHEN** calling `short_interest.fetch_us_finra_short_interest("TSLA")` with an injected fixture CSV payload
- **THEN** the function SHALL return a list of `ShortInterestRow` with `short_interest > 0`

#### Scenario: macro_data aggregates hyperscaler capex
- **WHEN** calling `macro_data.aggregate_hyperscaler_capex()` against a SQLite DB with capex rows for MSFT, GOOG, AMZN, META
- **THEN** the function SHALL return a `CapexAggregate` whose `total_usd` equals the sum across the four tickers and whose `tickers_included` lists those four

### Requirement: Phase 2 modules do not write new SQLite tables
The system SHALL keep new ingest results in-memory dataclasses only. Persistence to new tables is deferred to Phase 3.

#### Scenario: ingest functions do not touch new tables
- **WHEN** any Phase 2 fetcher / aggregator function returns
- **THEN** no `CREATE TABLE` or `INSERT INTO` statement targeting `issuer_materials`, `insider_transactions`, `holdings_snapshots`, or `short_interest_snapshots` SHALL have been executed

### Requirement: main.py runs eight parallel background channels
The system SHALL run the existing four financial-data channels and the four new ingest channels in parallel during Step 2.5 of the main pipeline.

#### Scenario: Step 2.5 prints stats for all eight channels
- **WHEN** running `python main.py --hours 24 --report-type daily --no-summary`
- **THEN** the smoke output SHALL include the count line "US ... / TW ... / TPEX ... / MOPS ... / IR ... / Insider ... / Short ... / Macro ..."
```

- [ ] **Step 5: Commit**

```bash
git add openspec/changes/investment-source-ingest-modules/
git commit -m "openspec: scaffold investment-source-ingest-modules change

Phase 2 of investment-source-expansion master spec. Adds proposal,
design, tasks, and spec delta. No code changes yet."
```

---

### Task 2: `ir_materials.py` module + fixture tests

**Files:**
- Create: `ir_materials.py`
- Create: `tests/test_ir_materials.py`
- Create: `tests/fixtures/ir_materials/motley_fool_sample.html`
- Create: `tests/fixtures/ir_materials/sec_8k_sample.txt`

- [ ] **Step 1: Add fixtures**

Create `tests/fixtures/ir_materials/motley_fool_sample.html`:

```html
<html><body>
<article>
<h1>NVIDIA (NVDA) Q1 2026 Earnings Call Transcript</h1>
<div class="article-body">
<p>Welcome to NVIDIA's first quarter fiscal 2026 earnings conference call.</p>
<p>Revenue grew 40% year over year to $30 billion driven by Blackwell ramp.</p>
<p>Gross margin expanded to 75%. Data center revenue was up 50%.</p>
</div>
</article>
</body></html>
```

Create `tests/fixtures/ir_materials/sec_8k_sample.txt`:

```
UNITED STATES
SECURITIES AND EXCHANGE COMMISSION
Washington, D.C. 20549

FORM 8-K
CURRENT REPORT

Date of Report: May 9, 2026
NVIDIA CORPORATION

Item 7.01 Regulation FD Disclosure
On May 9, 2026, NVIDIA announced that data center revenue
hit a record. Full text of the press release is attached
as Exhibit 99.1.

Item 9.01 Financial Statements and Exhibits
Exhibit 99.1: Press Release dated May 9, 2026
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_ir_materials.py`:

```python
import unittest
from datetime import datetime
from pathlib import Path

import ir_materials


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ir_materials"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class IRMaterialsTests(unittest.TestCase):
    def test_fetch_us_transcripts_parses_motley_fool_html(self):
        def fake_fetch(url):
            return _load_fixture("motley_fool_sample.html")

        results = ir_materials.fetch_us_transcripts(
            "NVDA", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item.ticker, "NVDA")
        self.assertEqual(item.market, "us")
        self.assertEqual(item.material_type, "transcript")
        self.assertIn("Blackwell", item.body_text)
        self.assertIsInstance(item.fetched_at, datetime)

    def test_fetch_us_8k_text_parses_filing_text(self):
        def fake_fetch(url):
            return _load_fixture("sec_8k_sample.txt")

        results = ir_materials.fetch_us_8k_text(
            "NVDA", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item.ticker, "NVDA")
        self.assertEqual(item.material_type, "8-K-text")
        self.assertIn("Item 7.01", item.body_text)

    def test_refresh_ir_materials_for_articles_collects_unique_tickers(self):
        articles = {
            "🏛️ 法說與 IR 材料": [
                _make_article(ticker="NVDA"),
                _make_article(ticker="AAPL"),
                _make_article(ticker="NVDA"),  # dup
            ]
        }
        seen = []

        def fake_transcripts(ticker, _fetch_fn=None):
            seen.append(ticker)
            return []

        original = ir_materials.fetch_us_transcripts
        ir_materials.fetch_us_transcripts = fake_transcripts  # type: ignore
        try:
            ir_materials.refresh_ir_materials_for_articles(articles)
        finally:
            ir_materials.fetch_us_transcripts = original  # type: ignore

        self.assertEqual(sorted(set(seen)), ["AAPL", "NVDA"])


def _make_article(ticker: str):
    class A:
        pass

    a = A()
    a.tickers = [ticker]
    a.companies = []
    a.title = f"{ticker} earnings"
    a.body_text = ""
    a.summary = ""
    return a


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_ir_materials -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ir_materials'`.

- [ ] **Step 4: Create `ir_materials.py`**

```python
"""IR materials ingest — earnings transcripts and SEC 8-K filing text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import quote

from bs4 import BeautifulSoup


@dataclass
class IRMaterial:
    market: str
    ticker: str
    material_type: str
    title: str
    body_text: str
    source_url: str
    fetched_at: datetime
    fiscal_year: int | None = None
    fiscal_period: str | None = None


FetchFn = Callable[[str], str | None]


def _real_fetch(url: str) -> str | None:
    import requests

    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "DailyNewsBot/1.0 ir_materials (andys0919@gmail.com)",
            },
            timeout=20,
        )
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception:
        return None


_TRANSCRIPT_TITLE_RE = re.compile(r"\(([A-Z]{1,6})\)\s*Q([1-4])\s*(\d{4})", re.IGNORECASE)


def fetch_us_transcripts(
    ticker: str,
    *,
    _fetch_fn: FetchFn | None = None,
) -> list[IRMaterial]:
    fetch = _fetch_fn or _real_fetch
    url = f"https://www.fool.com/quote/nasdaq/{quote(ticker.lower())}/earnings-call-transcripts/"
    html = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article")
    if not article:
        return []
    title_tag = article.find(["h1", "h2"])
    title = title_tag.get_text(" ", strip=True) if title_tag else f"{ticker} transcript"
    body = article.find("div", attrs={"class": lambda v: bool(v) and "body" in v}) or article
    paragraphs = [p.get_text(" ", strip=True) for p in body.find_all("p")]
    body_text = "\n".join(p for p in paragraphs if p)
    if not body_text:
        return []
    fiscal_year = None
    fiscal_period = None
    match = _TRANSCRIPT_TITLE_RE.search(title)
    if match:
        fiscal_period = f"q{match.group(2)}"
        fiscal_year = int(match.group(3))
    return [
        IRMaterial(
            market="us",
            ticker=ticker.upper(),
            material_type="transcript",
            title=title,
            body_text=body_text,
            source_url=url,
            fetched_at=datetime.now(timezone.utc),
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
        )
    ]


def fetch_us_8k_text(
    ticker: str,
    *,
    _fetch_fn: FetchFn | None = None,
) -> list[IRMaterial]:
    fetch = _fetch_fn or _real_fetch
    # Stub URL — Phase 3 will resolve CIK from earnings_data; for now the
    # fetcher accepts injected text and parses it generically.
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={quote(ticker)}&type=8-K&dateb=&owner=include&count=1&output=atom"
    text = fetch(url)
    if not text:
        return []
    if "FORM 8-K" not in text.upper() and "Item " not in text:
        return []
    return [
        IRMaterial(
            market="us",
            ticker=ticker.upper(),
            material_type="8-K-text",
            title=f"{ticker.upper()} latest 8-K",
            body_text=text.strip(),
            source_url=url,
            fetched_at=datetime.now(timezone.utc),
        )
    ]


def refresh_ir_materials_for_articles(
    articles: dict[str, Iterable[Any]],
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
    return results
```

- [ ] **Step 5: Run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_ir_materials -v
```

Expected: 3 PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only the two baseline failures; no new regressions.

- [ ] **Step 7: Commit**

```bash
git add ir_materials.py tests/test_ir_materials.py tests/fixtures/ir_materials/
git commit -m "feat(ingest): add ir_materials module

Pure-Python fetcher for IR transcripts (Motley Fool) and SEC 8-K text.
Returns IRMaterial dataclass list. No SQLite persistence yet (Phase 3).
Fixture-based tests cover transcript HTML parsing, 8-K text parsing,
and ticker dedup in refresh_ir_materials_for_articles."
```

---

### Task 3: `insider_holdings.py` module + fixture tests

**Files:**
- Create: `insider_holdings.py`
- Create: `tests/test_insider_holdings.py`
- Create: `tests/fixtures/insider_holdings/form4_sample.xml`
- Create: `tests/fixtures/insider_holdings/13f_sample.xml`

- [ ] **Step 1: Add fixtures**

Create `tests/fixtures/insider_holdings/form4_sample.xml`:

```xml
<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Cook Timothy D</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <officerTitle>CEO</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-04-15</value></transactionDate>
      <transactionCoding>
        <transactionCode>S</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>10000</value></transactionShares>
        <transactionPricePerShare><value>180.50</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
```

Create `tests/fixtures/insider_holdings/13f_sample.xml`:

```xml
<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>NVIDIA CORP</nameOfIssuer>
    <cusip>67066G104</cusip>
    <value>5000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>50000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>3000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>20000</sshPrnamtType>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
</informationTable>
```

(Note: the 13F fixture has a deliberate `</sshPrnamtType>` typo on the AAPL row — fix it to `</sshPrnamt>` before saving the file.)

Corrected `13f_sample.xml`:

```xml
<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>NVIDIA CORP</nameOfIssuer>
    <cusip>67066G104</cusip>
    <value>5000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>50000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>3000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>20000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
  </infoTable>
</informationTable>
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_insider_holdings.py`:

```python
import unittest
from datetime import date, datetime
from pathlib import Path

import insider_holdings


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "insider_holdings"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class InsiderHoldingsTests(unittest.TestCase):
    def test_form4_parser_returns_insider_trade(self):
        def fake_fetch(url):
            return _load("form4_sample.xml")

        trades = insider_holdings.fetch_us_form4_recent(
            "AAPL", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade.ticker, "AAPL")
        self.assertEqual(trade.insider_name, "Cook Timothy D")
        self.assertEqual(trade.insider_role, "CEO")
        self.assertEqual(trade.transaction_type, "S")
        self.assertEqual(trade.shares, 10000)
        self.assertAlmostEqual(trade.price, 180.50)
        self.assertEqual(trade.transaction_date, date(2026, 4, 15))

    def test_13f_parser_returns_two_holdings(self):
        def fake_fetch(url):
            return _load("13f_sample.xml")

        holdings = insider_holdings.fetch_us_13f_holdings(
            "0001067983", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(holdings), 2)
        names = {h.issuer_name for h in holdings}
        self.assertIn("NVIDIA CORP", names)
        self.assertIn("APPLE INC", names)
        nvda = next(h for h in holdings if h.issuer_name == "NVIDIA CORP")
        self.assertEqual(nvda.shares, 50000)
        self.assertEqual(nvda.value_usd, 5000000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_insider_holdings -v
```

- [ ] **Step 4: Create `insider_holdings.py`**

```python
"""Insider transactions and 13F holdings ingest."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

FetchFn = Callable[[str], str | None]


@dataclass
class InsiderTrade:
    market: str
    ticker: str
    insider_name: str
    insider_role: str
    transaction_date: date
    transaction_type: str
    shares: int
    price: float
    value_usd: float
    filing_url: str
    fetched_at: datetime


@dataclass
class Holding:
    reporter_cik: str
    issuer_name: str
    cusip: str
    shares: int
    value_usd: float
    period_end: str | None
    filing_url: str
    fetched_at: datetime


@dataclass
class DirectorChange:
    market: str
    ticker: str
    director_name: str
    period_end: str
    shares_before: int
    shares_after: int
    filing_url: str
    fetched_at: datetime


def _real_fetch(url: str) -> str | None:
    import requests

    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "DailyNewsBot/1.0 insider_holdings (andys0919@gmail.com)",
            },
            timeout=20,
        )
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception:
        return None


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _findtext(root: ET.Element, path: list[str]) -> str | None:
    cursor: ET.Element | None = root
    for part in path:
        if cursor is None:
            return None
        next_cursor = None
        for child in cursor:
            if _strip_ns(child.tag) == part:
                next_cursor = child
                break
        cursor = next_cursor
    if cursor is None:
        return None
    return (cursor.text or "").strip() or None


def fetch_us_form4_recent(
    ticker: str,
    *,
    _fetch_fn: FetchFn | None = None,
) -> list[InsiderTrade]:
    fetch = _fetch_fn or _real_fetch
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        f"action=getcompany&CIK={ticker}&type=4&dateb=&owner=include&count=10&output=atom"
    )
    payload = fetch(url)
    if not payload:
        return []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    name = _findtext(root, ["reportingOwner", "reportingOwnerId", "rptOwnerName"]) or ""
    role = _findtext(root, ["reportingOwner", "reportingOwnerRelationship", "officerTitle"]) or ""
    trades: list[InsiderTrade] = []
    table = None
    for child in root:
        if _strip_ns(child.tag) == "nonDerivativeTable":
            table = child
            break
    if table is None:
        return []
    for tx in table:
        if _strip_ns(tx.tag) != "nonDerivativeTransaction":
            continue
        date_str = _findtext(tx, ["transactionDate", "value"])
        code = _findtext(tx, ["transactionCoding", "transactionCode"]) or ""
        shares_str = _findtext(tx, ["transactionAmounts", "transactionShares", "value"]) or "0"
        price_str = _findtext(tx, ["transactionAmounts", "transactionPricePerShare", "value"]) or "0"
        try:
            tx_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
        except ValueError:
            tx_date = date.today()
        try:
            shares = int(float(shares_str))
        except ValueError:
            shares = 0
        try:
            price = float(price_str)
        except ValueError:
            price = 0.0
        trades.append(
            InsiderTrade(
                market="us",
                ticker=ticker.upper(),
                insider_name=name,
                insider_role=role,
                transaction_date=tx_date,
                transaction_type=code,
                shares=shares,
                price=price,
                value_usd=shares * price,
                filing_url=url,
                fetched_at=datetime.now(timezone.utc),
            )
        )
    return trades


def fetch_us_13f_holdings(
    reporter_cik: str,
    *,
    _fetch_fn: FetchFn | None = None,
) -> list[Holding]:
    fetch = _fetch_fn or _real_fetch
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar?"
        f"action=getcompany&CIK={reporter_cik}&type=13F-HR&owner=include&count=1&output=atom"
    )
    payload = fetch(url)
    if not payload:
        return []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    holdings: list[Holding] = []
    for table in root.iter():
        if _strip_ns(table.tag) != "infoTable":
            continue
        issuer = _findtext(table, ["nameOfIssuer"]) or ""
        cusip = _findtext(table, ["cusip"]) or ""
        value = _findtext(table, ["value"]) or "0"
        shares = _findtext(table, ["shrsOrPrnAmt", "sshPrnamt"]) or "0"
        try:
            value_usd = float(value)
        except ValueError:
            value_usd = 0.0
        try:
            shares_int = int(float(shares))
        except ValueError:
            shares_int = 0
        if not issuer:
            continue
        holdings.append(
            Holding(
                reporter_cik=reporter_cik,
                issuer_name=issuer,
                cusip=cusip,
                shares=shares_int,
                value_usd=value_usd,
                period_end=None,
                filing_url=url,
                fetched_at=datetime.now(timezone.utc),
            )
        )
    return holdings


def fetch_tw_director_changes(
    ticker: str,
    *,
    _fetch_fn: FetchFn | None = None,
) -> list[DirectorChange]:
    # Phase 2 stub: returns empty list when no fetch payload provided.
    fetch = _fetch_fn or _real_fetch
    url = (
        "https://openapi.twse.com.tw/v1/opendata/t100sb04?"
        f"company={ticker}"
    )
    payload = fetch(url)
    if not payload:
        return []
    return []


def refresh_insider_transactions(tickers: list[str]) -> list[InsiderTrade]:
    out: list[InsiderTrade] = []
    for ticker in tickers:
        try:
            out.extend(fetch_us_form4_recent(ticker))
        except Exception:
            continue
    return out
```

- [ ] **Step 5: Run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_insider_holdings -v
```

Expected: 2 PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only the two baseline failures; no new regressions.

- [ ] **Step 7: Commit**

```bash
git add insider_holdings.py tests/test_insider_holdings.py tests/fixtures/insider_holdings/
git commit -m "feat(ingest): add insider_holdings module

SEC Form 4 XML parser and 13F-HR holdings parser, returning
InsiderTrade and Holding dataclasses. TW director-change stub
in place. No SQLite persistence yet (Phase 3). Fixture-based
tests cover Form 4 single-transaction parse and 13F multi-row
parse."
```

---

### Task 4: `short_interest.py` module + fixture tests

**Files:**
- Create: `short_interest.py`
- Create: `tests/test_short_interest.py`
- Create: `tests/fixtures/short_interest/finra_sample.txt`
- Create: `tests/fixtures/short_interest/twse_credit_sample.json`

- [ ] **Step 1: Add fixtures**

Create `tests/fixtures/short_interest/finra_sample.txt`:

```
Date|Symbol|Market|ShortVolume|TotalVolume
20260509|TSLA|N|1500000|3500000
20260509|NVDA|N|2200000|5200000
20260509|AAPL|Q|800000|2400000
```

Create `tests/fixtures/short_interest/twse_credit_sample.json`:

```json
[
  {
    "Date": "2026-05-08",
    "Code": "2330",
    "Name": "台積電",
    "MarginPurchase": 1200,
    "MarginSale": 800,
    "MarginBalance": 50000,
    "ShortPurchase": 100,
    "ShortSale": 250,
    "ShortBalance": 1500
  }
]
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_short_interest.py`:

```python
import unittest
from datetime import date
from pathlib import Path

import short_interest


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "short_interest"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ShortInterestTests(unittest.TestCase):
    def test_finra_parser_returns_rows_for_target_ticker(self):
        def fake_fetch(url):
            return _load("finra_sample.txt")

        rows = short_interest.fetch_us_finra_short_interest(
            "TSLA", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.ticker, "TSLA")
        self.assertEqual(row.market, "us")
        self.assertEqual(row.short_interest, 1500000)
        self.assertGreater(row.short_interest_ratio, 0)
        self.assertEqual(row.period_end, date(2026, 5, 9))

    def test_twse_credit_parser_returns_rows(self):
        def fake_fetch(url):
            return _load("twse_credit_sample.json")

        rows = short_interest.fetch_tw_credit_balance(
            "2330", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.ticker, "2330")
        self.assertEqual(row.market, "tw")
        self.assertEqual(row.short_interest, 1500)
        self.assertEqual(row.period_end, date(2026, 5, 8))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_short_interest -v
```

- [ ] **Step 4: Create `short_interest.py`**

```python
"""Short interest and ETF flow ingest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

FetchFn = Callable[[str], str | None]


@dataclass
class ShortInterestRow:
    market: str
    ticker: str
    period_end: date
    short_interest: float
    days_to_cover: float
    short_interest_ratio: float
    source: str
    fetched_at: datetime


@dataclass
class ETFFlow:
    market: str
    etf_ticker: str
    period_end: date
    flow_usd: float
    aum_usd: float
    source: str
    fetched_at: datetime


def _real_fetch(url: str) -> str | None:
    import requests

    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "DailyNewsBot/1.0 short_interest (andys0919@gmail.com)",
            },
            timeout=20,
        )
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception:
        return None


def _parse_yyyymmdd(value: str) -> date:
    return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))


def fetch_us_finra_short_interest(
    ticker: str,
    *,
    _fetch_fn: FetchFn | None = None,
) -> list[ShortInterestRow]:
    fetch = _fetch_fn or _real_fetch
    url = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol.txt"
    payload = fetch(url)
    if not payload:
        return []
    rows: list[ShortInterestRow] = []
    target = ticker.upper()
    for line in payload.splitlines():
        line = line.strip()
        if not line or line.startswith("Date|") or line.startswith("Header"):
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        if parts[1].upper() != target:
            continue
        try:
            period_end = _parse_yyyymmdd(parts[0])
            short_vol = float(parts[3])
            total_vol = float(parts[4])
        except (ValueError, IndexError):
            continue
        ratio = (short_vol / total_vol) if total_vol > 0 else 0.0
        rows.append(
            ShortInterestRow(
                market="us",
                ticker=target,
                period_end=period_end,
                short_interest=short_vol,
                days_to_cover=0.0,
                short_interest_ratio=ratio,
                source="FINRA Reg SHO",
                fetched_at=datetime.now(timezone.utc),
            )
        )
    return rows


def fetch_tw_credit_balance(
    ticker: str,
    *,
    _fetch_fn: FetchFn | None = None,
) -> list[ShortInterestRow]:
    fetch = _fetch_fn or _real_fetch
    url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"
    payload = fetch(url)
    if not payload:
        return []
    try:
        records = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(records, list):
        return []
    target = ticker.strip()
    rows: list[ShortInterestRow] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("Code", "")).strip() != target:
            continue
        try:
            period_end = datetime.strptime(record["Date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        try:
            short_balance = float(record.get("ShortBalance", 0) or 0)
            margin_balance = float(record.get("MarginBalance", 0) or 0)
        except (TypeError, ValueError):
            continue
        ratio = (short_balance / margin_balance) if margin_balance > 0 else 0.0
        rows.append(
            ShortInterestRow(
                market="tw",
                ticker=target,
                period_end=period_end,
                short_interest=short_balance,
                days_to_cover=0.0,
                short_interest_ratio=ratio,
                source="TWSE OpenAPI MI_MARGN",
                fetched_at=datetime.now(timezone.utc),
            )
        )
    return rows


def fetch_etf_flows_summary(
    *,
    _fetch_fn: FetchFn | None = None,
) -> list[ETFFlow]:
    # Phase 2 stub: returns empty unless fetch returns parseable JSON.
    fetch = _fetch_fn or _real_fetch
    url = "https://www.etf.com/api/news/v1/flows"
    payload = fetch(url)
    if not payload:
        return []
    return []


def refresh_short_interest(market: str, tickers: list[str]) -> list[ShortInterestRow]:
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
    return out
```

- [ ] **Step 5: Run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_short_interest -v
```

Expected: 2 PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only baseline failures.

- [ ] **Step 7: Commit**

```bash
git add short_interest.py tests/test_short_interest.py tests/fixtures/short_interest/
git commit -m "feat(ingest): add short_interest module

FINRA Reg SHO daily short volume parser and TWSE OpenAPI
MI_MARGN credit-balance parser, returning ShortInterestRow
dataclass list. ETF flow stub in place. No SQLite persistence
yet (Phase 3). Fixture tests cover both US and TW paths."
```

---

### Task 5: `macro_data.py` module + DB-mock tests

**Files:**
- Create: `macro_data.py`
- Create: `tests/test_macro_data.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_macro_data.py`:

```python
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import macro_data


class MacroDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE financial_reports (
                ticker TEXT,
                market TEXT,
                period_end TEXT,
                capex REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO financial_reports VALUES (?, ?, ?, ?)",
            [
                ("MSFT", "us", "2026-03-31", 22000.0),
                ("GOOG", "us", "2026-03-31", 18000.0),
                ("AMZN", "us", "2026-03-31", 25000.0),
                ("META", "us", "2026-03-31", 14000.0),
                ("NVDA", "us", "2026-03-31", 5000.0),
            ],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)

    def test_aggregate_hyperscaler_capex_sums_four_tickers(self):
        agg = macro_data.aggregate_hyperscaler_capex(_db_path=self.db_path)
        self.assertEqual(agg.total_usd, 22000.0 + 18000.0 + 25000.0 + 14000.0)
        self.assertEqual(sorted(agg.tickers_included), ["AMZN", "GOOG", "META", "MSFT"])
        self.assertEqual(agg.period_end, "2026-03-31")

    def test_extract_macro_signals_picks_cpi_number(self):
        articles = {
            "🌐 宏觀與產業數據": [
                _make_article(
                    title="US CPI rose to 3.2% in April",
                    body_text="The April CPI print came in at 3.2 percent, above 3.1% consensus.",
                ),
                _make_article(title="ECB holds rate", body_text="No data quoted."),
            ]
        }
        signals = macro_data.extract_macro_signals_from_articles(articles)
        cpi_signals = [s for s in signals if s.metric == "CPI"]
        self.assertGreaterEqual(len(cpi_signals), 1)
        self.assertAlmostEqual(cpi_signals[0].value, 3.2)


def _make_article(title: str, body_text: str):
    class A:
        pass

    a = A()
    a.title = title
    a.body_text = body_text
    a.summary = ""
    a.tickers = []
    a.published = datetime.now(timezone.utc)
    return a


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_macro_data -v
```

- [ ] **Step 3: Create `macro_data.py`**

```python
"""Macro-level aggregations: hyperscaler capex, macro release signals."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


HYPERSCALERS = ("MSFT", "GOOG", "AMZN", "META")


@dataclass
class CapexAggregate:
    period_end: str
    tickers_included: list[str]
    total_usd: float
    fetched_at: datetime


@dataclass
class MacroRelease:
    metric: str
    value: float
    unit: str
    article_title: str
    fetched_at: datetime


_DEFAULT_DB = Path(__file__).resolve().parent / "data" / "news.db"


def aggregate_hyperscaler_capex(
    *,
    _db_path: Path | None = None,
) -> CapexAggregate:
    path = Path(_db_path) if _db_path is not None else _DEFAULT_DB
    if not path.exists():
        return CapexAggregate(
            period_end="",
            tickers_included=[],
            total_usd=0.0,
            fetched_at=datetime.now(timezone.utc),
        )
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            f"""
            SELECT ticker, period_end, capex
            FROM financial_reports
            WHERE ticker IN ({",".join("?" for _ in HYPERSCALERS)})
              AND capex IS NOT NULL
            ORDER BY period_end DESC
            """,
            HYPERSCALERS,
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return CapexAggregate(
            period_end="",
            tickers_included=[],
            total_usd=0.0,
            fetched_at=datetime.now(timezone.utc),
        )
    latest_period = rows[0][1]
    tickers: list[str] = []
    total = 0.0
    for ticker, period_end, capex in rows:
        if period_end != latest_period:
            continue
        if ticker in tickers:
            continue
        tickers.append(ticker)
        try:
            total += float(capex or 0)
        except (TypeError, ValueError):
            continue
    return CapexAggregate(
        period_end=latest_period,
        tickers_included=tickers,
        total_usd=total,
        fetched_at=datetime.now(timezone.utc),
    )


_MACRO_PATTERNS = [
    ("CPI", re.compile(r"\bCPI[^\d]{0,40}?(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)),
    ("PPI", re.compile(r"\bPPI[^\d]{0,40}?(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)),
    ("PCE", re.compile(r"\bPCE[^\d]{0,40}?(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)),
    (
        "unemployment",
        re.compile(r"\bunemployment[^\d]{0,40}?(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE),
    ),
]


def extract_macro_signals_from_articles(
    articles: dict[str, Iterable[Any]],
) -> list[MacroRelease]:
    releases: list[MacroRelease] = []
    for items in articles.values():
        for item in items:
            text = "{} {}".format(
                getattr(item, "title", "") or "",
                getattr(item, "body_text", "") or "",
            )
            for metric, pattern in _MACRO_PATTERNS:
                match = pattern.search(text)
                if not match:
                    continue
                try:
                    value = float(match.group(1))
                except ValueError:
                    continue
                releases.append(
                    MacroRelease(
                        metric=metric,
                        value=value,
                        unit="%",
                        article_title=getattr(item, "title", "") or "",
                        fetched_at=datetime.now(timezone.utc),
                    )
                )
    return releases


def refresh_macro_releases() -> dict[str, Any]:
    return {"capex": aggregate_hyperscaler_capex(), "signals": []}
```

- [ ] **Step 4: Run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_macro_data -v
```

Expected: 2 PASS.

- [ ] **Step 5: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only baseline failures.

- [ ] **Step 6: Commit**

```bash
git add macro_data.py tests/test_macro_data.py
git commit -m "feat(ingest): add macro_data module

Hyperscaler capex aggregator (MSFT/GOOG/AMZN/META) reading
financial_reports.capex column, plus regex extractor for
CPI/PPI/PCE/unemployment percentage signals from macro_data
articles. Returns CapexAggregate and MacroRelease dataclasses.
No SQLite write (Phase 3). Tests cover capex aggregation and
CPI signal extraction."
```

---

### Task 6: `main.py` Step 2.5 wires four new background tasks

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Read current `main.py` Step 2.5 block**

```bash
sed -n '60,140p' main.py
```

- [ ] **Step 2: Locate `_refresh_financials_in_background` definition and add four parallel channels**

Replace the `_refresh_financials_in_background` function body so it runs eight channels instead of four. Specifically, after the existing four `try` blocks (`us_reports`, `tw_reports`, `tpex_reports`, `mops_reports`), add four more `try` blocks that call:

- `ir_materials.refresh_ir_materials_for_articles(articles)` → `ir_count`
- `insider_holdings.refresh_insider_transactions(<dedup tickers from articles>)` → `insider_count`
- `short_interest.refresh_short_interest("us", <us tickers>)` plus `refresh_short_interest("tw", <tw tickers>)` aggregated → `short_count`
- `macro_data.refresh_macro_releases()` (returns dict) → `macro_count = len(<signals>)`

Imports added at the top of `main.py` (next to existing financial imports, inside the function body where the other imports live):

```python
    from ir_materials import refresh_ir_materials_for_articles
    from insider_holdings import refresh_insider_transactions
    from short_interest import refresh_short_interest
    from macro_data import refresh_macro_releases
```

Add helper above `_refresh_financials_in_background`:

```python
def _collect_tickers(articles: dict, market: str) -> list[str]:
    tickers: set[str] = set()
    for items in articles.values():
        for item in items:
            for ticker in getattr(item, "tickers", []) or []:
                if not ticker:
                    continue
                ticker = ticker.upper()
                if market == "tw" and ticker.isdigit():
                    tickers.add(ticker)
                elif market == "us" and ticker.isalpha():
                    tickers.add(ticker)
    return sorted(tickers)
```

Inside `_refresh_financials_in_background`, after the existing four blocks:

```python
        ir_count = insider_count = short_count = macro_count = 0
        try:
            ir_results = await asyncio.to_thread(
                refresh_ir_materials_for_articles, articles
            )
            ir_count = len(ir_results)
        except Exception as e:
            errors.append(f"IR: {e}")
        try:
            us_tickers = _collect_tickers(articles, "us")
            insider_results = await asyncio.to_thread(
                refresh_insider_transactions, us_tickers
            )
            insider_count = len(insider_results)
        except Exception as e:
            errors.append(f"Insider: {e}")
        try:
            tw_tickers = _collect_tickers(articles, "tw")
            us_short = await asyncio.to_thread(
                refresh_short_interest, "us", us_tickers
            )
            tw_short = await asyncio.to_thread(
                refresh_short_interest, "tw", tw_tickers
            )
            short_count = len(us_short) + len(tw_short)
        except Exception as e:
            errors.append(f"Short: {e}")
        try:
            macro_payload = await asyncio.to_thread(refresh_macro_releases)
            macro_count = len(macro_payload.get("signals", []) or [])
        except Exception as e:
            errors.append(f"Macro: {e}")
```

Then update the return value of `_refresh_financials_in_background` from:

```python
return {"us": us_count, "tw": tw_count, "tpex": tpex_count, "mops": mops_count}, errors, time.time() - started
```

To:

```python
return (
    {
        "us": us_count, "tw": tw_count, "tpex": tpex_count, "mops": mops_count,
        "ir": ir_count, "insider": insider_count,
        "short": short_count, "macro": macro_count,
    },
    errors,
    time.time() - started,
)
```

And update the success-print block from:

```python
print(
    "✅ 財務資料刷新完成: "
    f"US {financial_counts['us']} 筆 / TW {financial_counts['tw']} 筆 / TPEX {financial_counts['tpex']} 筆 / MOPS {financial_counts['mops']} 筆",
    flush=True,
)
```

To:

```python
print(
    "✅ 財務資料刷新完成: "
    f"US {financial_counts['us']} / TW {financial_counts['tw']} / TPEX {financial_counts['tpex']} / MOPS {financial_counts['mops']} / "
    f"IR {financial_counts['ir']} / Insider {financial_counts['insider']} / "
    f"Short {financial_counts['short']} / Macro {financial_counts['macro']}",
    flush=True,
)
```

- [ ] **Step 3: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only baseline failures (main.py change does not affect existing tests).

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(pipeline): wire four new ingest channels into Step 2.5

main.py background financial refresh now runs eight channels
in parallel: existing four (US/TW/TPEX/MOPS) plus IR materials,
insider transactions, short interest, and macro releases. Each
channel has its own try/except so partial failures do not abort
the run. Counts are printed; persistence to new tables is
deferred to Phase 3."
```

---

### Task 7: Smoke run — `main.py --no-summary`

**Files:** none modified.

- [ ] **Step 1: Run smoke**

```bash
uv run --with-requirements requirements.txt --python python3 python main.py --hours 24 --report-type daily --no-summary 2>&1 | tee /tmp/phase2-smoke.log
```

Expected: process exits 0; log contains the eight-channel count line including `IR ...`, `Insider ...`, `Short ...`, `Macro ...`.

- [ ] **Step 2: Verify the eight-channel count line**

```bash
grep -E "✅ 財務資料刷新完成" /tmp/phase2-smoke.log | tail -1
```

Expected output contains all of: `US`, `TW`, `TPEX`, `MOPS`, `IR`, `Insider`, `Short`, `Macro`.

- [ ] **Step 3: Verify no Python tracebacks**

```bash
grep -cE "Traceback|YAMLError|KeyError" /tmp/phase2-smoke.log
```

Expected: `0`.

- [ ] **Step 4: Commit log artifact**

```bash
mkdir -p docs/superpowers/runs
grep -E "(✅|⚠️|📂|本次新增)" /tmp/phase2-smoke.log | head -200 > docs/superpowers/runs/2026-05-09-phase2-smoke.txt
git add docs/superpowers/runs/2026-05-09-phase2-smoke.txt
git commit -m "test(smoke): capture phase 2 ingest-modules smoke run"
```

---

### Task 8: OpenSpec validate + final commit

**Files:**
- Modify: `openspec/changes/investment-source-ingest-modules/tasks.md`

- [ ] **Step 1: Mark all tasks completed**

Replace each `- [ ]` in `openspec/changes/investment-source-ingest-modules/tasks.md` with `- [x]`.

- [ ] **Step 2: Run `openspec validate`**

```bash
command -v openspec >/dev/null && openspec validate investment-source-ingest-modules 2>&1 | tail -5 || echo "openspec CLI not installed locally — skip"
```

Expected: validate passes, or skip with the exact message above.

- [ ] **Step 3: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only baseline failures, all new tests green.

- [ ] **Step 4: Final commit**

```bash
git add openspec/changes/investment-source-ingest-modules/tasks.md
git commit -m "openspec: phase 2 done — investment-source-ingest-modules

[phase-2 done]

Four new ingest modules (ir_materials, insider_holdings,
short_interest, macro_data) with fixture-based tests.
main.py Step 2.5 now runs eight parallel channels. No
SQLite persistence yet — Phase 3 wires dataclasses to
new tables. openspec validate passes."
```

- [ ] **Step 5: Reply with promise tag**

When all checkboxes above are checked and the commit lands, reply with **only**:

```
<promise>PHASE_DONE</promise>
```

No other text.

---

## Self-review notes (already applied)

- Spec coverage: Phase 2 master spec section 5.1–5.4 maps to Tasks 2–6. Task 7 covers the eight-channel smoke. Task 1 + Task 8 form the OpenSpec lifecycle.
- Phase isolation: explicit "Hard limits" at top + reminder before each task. No edits to `crawler.py`, `news_enrichment.py`, `summarizer.py`, `stock_memo.py`, `financial_reports.py`, `html_generator.py`. No SQLite schema. No new RSS feeds.
- Network seam: every fetcher accepts `_fetch_fn` so tests stay offline.
- Whitelisted baseline failures: Tasks 6 and 8 reuse the same diff helper interpretation as Phase 1.
- Type / signature consistency: dataclass fields are declared once in Task 4 / Task 5 / Task 6 and reused unchanged in subsequent tasks. Function names (`refresh_ir_materials_for_articles`, `refresh_insider_transactions`, `refresh_short_interest`, `refresh_macro_releases`) match between the modules and the `main.py` wiring task.
- No placeholders: every YAML, every Python block contains real code; every URL contains a real endpoint or stub explained inline.
