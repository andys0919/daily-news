# Investment Source Memo Integration (Phase 4) — Implementation Plan

> **For ralph-loop:** Process tasks 1 → 6 in order. Each task ends with a commit. When all tasks check, reply only with `<promise>PHASE_DONE</promise>`.

**Goal:** Surface the four new bundle fields (`latest_transcript`, `recent_insider_summary`, `latest_13f`, `short_interest`) in `stock_memo.py` (5 new memo sections) and `summarizer.py` (richer `format_financial_snapshot_bundle_context`). Macro context comes from a per-call `macro_data.aggregate_hyperscaler_capex()` call inside the memo renderer.

**Architecture:** All consumers read the bundle contract that Phase 3 already established. `format_financial_snapshot_bundle_context` becomes the single point that converts the new bundle fields into prompt-ready text — daily memo / weekly summarizer pipelines pick that up automatically. `stock_memo.render_stock_memo` adds five `##` markdown sections after the existing「官方財務快照」block and before「官方資料來源」.

**Tech Stack:** Pure Python, no new deps. `unittest` + in-memory SQLite fixtures.

**Spec:** [docs/superpowers/specs/2026-05-09-investment-source-expansion-design.md](../specs/2026-05-09-investment-source-expansion-design.md) (Phase 4 = section 7)

**Hard limits for this phase:**
- ❌ Do not add new RSS feeds (Phase 1 closed).
- ❌ Do not add new ingest fetchers (Phase 2 closed).
- ❌ Do not change SQLite schema (Phase 3 closed).
- ❌ Do not edit `crawler.py`, `news_enrichment.py`, the four Phase 2 ingest modules, or `financial_reports.py`'s schema / save / get / bundle definitions.
- ✅ Modify `financial_reports.py` `format_financial_snapshot_bundle_context` only (text formatting, NOT schema or query logic).
- ✅ Modify `stock_memo.py` (`render_stock_memo` + small private helpers).
- ✅ Modify `summarizer.py` if and only if needed to expose the new structured fields in the daily memo prompt — keep the change minimal.
- ✅ `html_generator.py` / `templates/report.html` may receive small additions if the existing weekly-category renderer needs a new section.

**Known baseline test failures (DO NOT try to fix):**

```
ERROR  test_news_enrichment.test_init_db_adds_enrichment_columns_and_hydrates_new_fields
FAIL   test_summarizer.test_ai_practice_uses_deterministic_hotlist_without_llm
```

Phase 4 success = no NEW failures beyond these two; new tests green.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `financial_reports.py` | modify | `format_financial_snapshot_bundle_context` appends transcript excerpt / insider summary / short-interest line when present |
| `stock_memo.py` | modify | `render_stock_memo` adds 5 new sections; uses `macro_data.aggregate_hyperscaler_capex` for the macro section |
| `summarizer.py` | modify if needed | Pass-through bundle context already invoked; only adjust if the new context lines need a new wrapper |
| `tests/test_stock_memo.py` | modify | Add tests for the 5 new sections (each driven by an in-memory bundle fixture) |
| `tests/test_financial_reports_bundle_context.py` | create | New test file proving `format_financial_snapshot_bundle_context` includes the structured-field lines |
| `openspec/changes/investment-source-memo-integration/*` | create | OpenSpec artefacts |

---

### Task 1: OpenSpec scaffold

**Files:**
- Create: `openspec/changes/investment-source-memo-integration/proposal.md`
- Create: `openspec/changes/investment-source-memo-integration/design.md`
- Create: `openspec/changes/investment-source-memo-integration/tasks.md`
- Create: `openspec/changes/investment-source-memo-integration/specs/investment-source-memo/spec.md`

- [ ] **Step 1: proposal.md**

```markdown
## Why

Phase 3 added structured bundle fields (`latest_transcript`, `recent_insider_summary`, `latest_13f`, `short_interest`) but no consumer reads them yet. Phase 4 surfaces those fields in the per-stock memo and in the prompt context the summarizer feeds into the daily memo.

## What Changes

- `stock_memo.py` `render_stock_memo` adds five new markdown sections: 最新法說會 / 近 90 天內部人交易 / 13F 機構動向 / 融券與 ETF 資金流 / 宏觀脈絡.
- `financial_reports.py` `format_financial_snapshot_bundle_context` includes structured-field lines so the daily / weekly summarizer prompt sees them.
- `tests/test_stock_memo.py` covers the new sections with bundle fixtures.
- New `tests/test_financial_reports_bundle_context.py` covers context text shape.

## Capabilities

### Modified Capabilities
- `stock-memo`: Memo now includes transcript / insider / 13F / short-interest / macro sections.
- `financial-snapshot-bundle-context`: Context summary now includes the four new structured fields when present.

## Impact

- Affected code: `financial_reports.py` (text only, no schema), `stock_memo.py`, two test files.
- No new RSS feeds, no new ingest modules, no schema changes.
```

- [ ] **Step 2: design.md**

```markdown
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

Each new section gracefully degrades to a single「（暫無資料）」line when its bundle field is `None`, so memos for tickers without any structured ingest still render coherently.

## `format_financial_snapshot_bundle_context` extension

Append additional `parts` when present:

- `latest_transcript`: append `「{title}：{body_excerpt[:160]}」` (truncated)
- `recent_insider_summary`: append `近期內部人交易 {count} 筆 (買 {buys} / 賣 {sells})`
- `short_interest`: append `融券餘額 {short_interest:,.0f} (券資比 {short_interest_ratio:.1%})`
- `latest_13f`: append `機構持股 {issuer} {shares:,} 股` when present

Order matters — keep `quarterly`, `monthly_revenue`, `guidance_summary`, `filing_excerpt` first (existing), append new lines after.

## Macro section

`stock_memo.render_stock_memo` calls `macro_data.aggregate_hyperscaler_capex()` once per memo. The aggregator already handles missing data gracefully (returns empty `tickers_included`). When it returns a non-empty list, the section says e.g. `本季 MSFT/GOOG/AMZN/META capex 合計 $79B (FY26 Q1)`; otherwise it says `（無 hyperscaler capex 對照資料）`.

## summarizer.py touch

Existing `summarizer._article_financial_context` (or similar) already calls `format_financial_snapshot_bundle_context`. Phase 4 changes the *output* of that function, so summarizer changes only if the new context lines need explicit fenced labels in the prompt — verify via `tests/test_summarizer.py` that no existing summarizer test breaks.

## Out of scope

- Adding new bundle fields (Phase 3 closed).
- Adding new RSS sources or ingest modules (Phases 1 & 2 closed).
- Changing macro_data fetcher behaviour.
```

- [ ] **Step 3: tasks.md**

```markdown
# Tasks — investment-source-memo-integration

- [ ] Task 1 OpenSpec skeleton committed
- [ ] Task 2 format_financial_snapshot_bundle_context appends 4 new structured-field lines
- [ ] Task 3 stock_memo.render_stock_memo adds 5 new sections + tests
- [ ] Task 4 Smoke run: stock_memo CLI for one US ticker + one TW ticker
- [ ] Task 5 `openspec validate investment-source-memo-integration`
- [ ] Task 6 Final commit + PHASE_DONE
```

- [ ] **Step 4: spec delta**

`openspec/changes/investment-source-memo-integration/specs/investment-source-memo/spec.md`:

```markdown
## ADDED Requirements

### Requirement: render_stock_memo includes five new structured sections
The system SHALL render five new markdown sections in per-stock memos when corresponding bundle data is present, and a graceful「（暫無資料）」placeholder when not.

#### Scenario: transcript section appears when bundle.latest_transcript is set
- **WHEN** rendering a memo for a ticker whose bundle has `latest_transcript={"title":"X","body_text":"Blackwell ramp"}`
- **THEN** the rendered markdown SHALL contain `## 最新法說會重點` and SHALL include `Blackwell` somewhere in that section

#### Scenario: insider section summarises buys vs sells
- **WHEN** bundle.recent_insider_summary is `{"count":3,"buys":1,"sells":2,"latest":{...}}`
- **THEN** the section `## 近 90 天內部人交易` SHALL include `3 筆`, `買 1`, `賣 2`

#### Scenario: short interest section appears with ratio
- **WHEN** bundle.short_interest is `{"short_interest":200000,"short_interest_ratio":0.05,...}`
- **THEN** the section `## 融券與 ETF 資金流` SHALL include `200,000` (or close formatting) and a percentage like `5.0%` or `0.05`

#### Scenario: macro section always present
- **WHEN** rendering any memo
- **THEN** the section `## 宏觀脈絡` SHALL be present in the output (even if its body says no hyperscaler comparison data)

### Requirement: format_financial_snapshot_bundle_context surfaces structured fields
The system SHALL extend `format_financial_snapshot_bundle_context` so daily / weekly summarizer prompts see the four new bundle fields when present.

#### Scenario: transcript excerpt appears in context
- **WHEN** `format_financial_snapshot_bundle_context(bundle)` is called with a bundle whose `latest_transcript = {"title":"NVDA Q1","body_text":"Blackwell ramp ...","material_type":"transcript"}`
- **THEN** the returned context string SHALL contain `Blackwell`

#### Scenario: short-interest one-liner appears in context
- **WHEN** the bundle has `short_interest = {"short_interest":200000,"short_interest_ratio":0.05,...}`
- **THEN** the returned context string SHALL contain at least `融券`
```

- [ ] **Step 5: commit**

```bash
git add openspec/changes/investment-source-memo-integration/
git commit -m "openspec: scaffold investment-source-memo-integration change"
```

---

### Task 2: `format_financial_snapshot_bundle_context` appends structured-field lines

**Files:**
- Modify: `financial_reports.py`
- Create: `tests/test_financial_reports_bundle_context.py`

- [ ] **Step 1: failing test**

Create `tests/test_financial_reports_bundle_context.py`:

```python
import unittest
from datetime import date, datetime, timezone

import financial_reports as fr


def _make_bundle(**overrides):
    base = dict(
        market="us",
        ticker="NVDA",
        company_name="NVIDIA",
        quarterly=fr.FinancialReport(
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
        ),
    )
    base.update(overrides)
    return fr.FinancialSnapshotBundle(**base)


class BundleContextTests(unittest.TestCase):
    def test_includes_transcript_excerpt_when_present(self):
        bundle = _make_bundle(
            latest_transcript={
                "title": "NVDA Q1 transcript",
                "body_text": "Blackwell ramp drives data center revenue.",
                "material_type": "transcript",
            }
        )
        context = fr.format_financial_snapshot_bundle_context(bundle)
        self.assertIn("Blackwell", context)

    def test_includes_short_interest_line_when_present(self):
        bundle = _make_bundle(
            short_interest={
                "short_interest": 200000.0,
                "days_to_cover": 1.5,
                "short_interest_ratio": 0.05,
                "source": "FINRA",
            }
        )
        context = fr.format_financial_snapshot_bundle_context(bundle)
        self.assertIn("融券", context)

    def test_includes_insider_summary_when_present(self):
        bundle = _make_bundle(
            recent_insider_summary={
                "count": 3,
                "buys": 1,
                "sells": 2,
                "latest": {"insider_name": "Cook", "transaction_type": "S"},
            }
        )
        context = fr.format_financial_snapshot_bundle_context(bundle)
        self.assertIn("3", context)
        self.assertIn("內部人", context)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: run test, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_financial_reports_bundle_context -v
```

- [ ] **Step 3: extend `format_financial_snapshot_bundle_context`**

Replace the existing function in `financial_reports.py`:

```python
def format_financial_snapshot_bundle_context(bundle: FinancialSnapshotBundle) -> str:
    parts: list[str] = []
    if bundle.quarterly:
        quarterly = bundle.quarterly
        quarter_bits = ["官方財報" if bundle.market == "us" else "台股財務資料"]
        if quarterly.form_type:
            quarter_bits.append(quarterly.form_type)
        if quarterly.fiscal_year and quarterly.fiscal_period:
            quarter_bits.append(f"FY{quarterly.fiscal_year} {quarterly.fiscal_period}")
        if quarterly.revenue is not None:
            quarter_bits.append(f"營收 {_format_money(quarterly.revenue, bundle.market)}")
        if quarterly.eps_diluted is not None:
            quarter_bits.append(f"EPS {quarterly.eps_diluted:.2f}")
        if quarterly.free_cash_flow is not None:
            quarter_bits.append(f"FCF {_format_money(quarterly.free_cash_flow, bundle.market)}")
        parts.append(" | ".join(quarter_bits))
    if bundle.monthly_revenue and bundle.monthly_revenue.monthly_revenue is not None:
        monthly = bundle.monthly_revenue
        parts.append(
            f"{monthly.fiscal_period} 月營收 {_format_money(monthly.monthly_revenue, bundle.market)}"
        )
    if bundle.quarterly:
        if bundle.quarterly.guidance_summary:
            parts.append(bundle.quarterly.guidance_summary)
        if bundle.quarterly.filing_excerpt:
            parts.append(bundle.quarterly.filing_excerpt)

    if bundle.latest_transcript:
        title = (bundle.latest_transcript.get("title") or "").strip()
        body = (bundle.latest_transcript.get("body_text") or "").strip()
        excerpt = body[:160].replace("\n", " ").strip()
        if title or excerpt:
            parts.append(f"法說重點：{title} — {excerpt}".strip(" —"))

    if bundle.recent_insider_summary:
        s = bundle.recent_insider_summary
        parts.append(
            f"近期內部人交易 {s.get('count', 0)} 筆 (買 {s.get('buys', 0)} / 賣 {s.get('sells', 0)})"
        )

    if bundle.short_interest:
        si = bundle.short_interest
        ratio = si.get("short_interest_ratio") or 0
        parts.append(
            f"融券餘額 {si.get('short_interest', 0):,.0f} (券資比 {ratio:.1%})"
        )

    if bundle.latest_13f:
        h = bundle.latest_13f
        parts.append(
            f"機構持股 {h.get('issuer_name', '')} {h.get('shares', 0):,} 股"
        )

    return " ; ".join(parts)
```

- [ ] **Step 4: run test, expect pass + full sweep**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_financial_reports_bundle_context -v
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: 3 PASS for new tests; only baseline failures elsewhere.

- [ ] **Step 5: commit**

```bash
git add financial_reports.py tests/test_financial_reports_bundle_context.py
git commit -m "feat(memo): bundle context surfaces 4 new structured fields"
```

---

### Task 3: `stock_memo.render_stock_memo` adds 5 new sections + tests

**Files:**
- Modify: `stock_memo.py`
- Modify: `tests/test_stock_memo.py`

- [ ] **Step 1: read current `render_stock_memo` once**

```bash
sed -n '440,512p' stock_memo.py
```

- [ ] **Step 2: write failing tests**

Append to `tests/test_stock_memo.py`:

```python
class StockMemoNewSectionsTests(unittest.TestCase):
    def _packet(self, **bundle_overrides):
        from financial_reports import FinancialReport, FinancialSnapshotBundle
        from stock_memo import StockMemoPacket
        from datetime import datetime
        bundle = FinancialSnapshotBundle(
            market="us", ticker="NVDA", company_name="NVIDIA",
            quarterly=FinancialReport(
                market="us", ticker="NVDA", company_name="NVIDIA",
                source_type="sec", form_type="10-Q",
                fiscal_year=2026, fiscal_period="Q1",
                period_end="2026-03-31", filed_at="2026-04-25",
                source_url="https://example.com", report_kind="quarterly",
                revenue=30_000_000_000.0,
            ),
            **bundle_overrides,
        )
        return StockMemoPacket(
            ticker="NVDA", market="us", company_name="NVIDIA",
            generated_at=datetime(2026, 5, 9, 10, 0),
            bundle=bundle,
            official_materials=[],
            related_articles=[],
            warnings=[],
        )

    def test_section_macro_always_present(self):
        from stock_memo import render_stock_memo
        text = render_stock_memo(self._packet())
        self.assertIn("## 宏觀脈絡", text)

    def test_section_transcript_includes_body(self):
        from stock_memo import render_stock_memo
        packet = self._packet(latest_transcript={
            "title": "NVDA Q1 transcript",
            "body_text": "Blackwell ramp drives growth.",
            "material_type": "transcript",
        })
        text = render_stock_memo(packet)
        self.assertIn("## 最新法說會重點", text)
        self.assertIn("Blackwell", text)

    def test_section_insider_buy_sell_counts(self):
        from stock_memo import render_stock_memo
        packet = self._packet(recent_insider_summary={
            "count": 3, "buys": 1, "sells": 2,
            "latest": {"insider_name": "Cook", "transaction_type": "S"},
        })
        text = render_stock_memo(packet)
        self.assertIn("## 近 90 天內部人交易", text)
        self.assertIn("3", text)
        self.assertIn("買 1", text)
        self.assertIn("賣 2", text)

    def test_section_short_interest_includes_ratio(self):
        from stock_memo import render_stock_memo
        packet = self._packet(short_interest={
            "short_interest": 200000.0,
            "days_to_cover": 1.5,
            "short_interest_ratio": 0.05,
            "source": "FINRA",
        })
        text = render_stock_memo(packet)
        self.assertIn("## 融券與 ETF 資金流", text)
        self.assertIn("200,000", text)

    def test_section_13f_renders_placeholder_when_none(self):
        from stock_memo import render_stock_memo
        text = render_stock_memo(self._packet())
        self.assertIn("## 13F 機構動向", text)
        self.assertIn("暫無", text)
```

- [ ] **Step 3: insert sections in `render_stock_memo`**

In `stock_memo.py`, after the existing「官方財務快照」block (right before `lines.extend(["", "## 官方資料來源"])`), insert:

```python
    bundle = packet.bundle

    lines.extend(["", "## 最新法說會重點"])
    if bundle.latest_transcript:
        title = (bundle.latest_transcript.get("title") or "").strip()
        body = (bundle.latest_transcript.get("body_text") or "").strip()
        excerpt = body[:600].replace("\n", " ")
        if title:
            lines.append(f"- {title}")
        if excerpt:
            lines.append(f"- 摘錄：{excerpt}")
    else:
        lines.append("- （暫無法說 / transcript 紀錄）")

    lines.extend(["", "## 近 90 天內部人交易"])
    if bundle.recent_insider_summary:
        s = bundle.recent_insider_summary
        lines.append(
            f"- 共 {s.get('count', 0)} 筆 (買 {s.get('buys', 0)} / 賣 {s.get('sells', 0)})"
        )
        latest = s.get("latest") or {}
        if latest:
            lines.append(
                f"- 最近一筆：{latest.get('insider_name', '')} "
                f"{latest.get('transaction_type', '')} "
                f"{latest.get('shares', 0):,} 股 @ {latest.get('price', 0):.2f}"
            )
    else:
        lines.append("- （暫無內部人交易紀錄）")

    lines.extend(["", "## 13F 機構動向"])
    if bundle.latest_13f:
        h = bundle.latest_13f
        lines.append(
            f"- {h.get('reporter_name', '')} 持有 {h.get('issuer_name', '')} "
            f"{h.get('shares', 0):,} 股 (期間 {h.get('period_end', '')})"
        )
    else:
        lines.append("- （暫無 13F 持股紀錄）")

    lines.extend(["", "## 融券與 ETF 資金流"])
    if bundle.short_interest:
        si = bundle.short_interest
        ratio = si.get("short_interest_ratio") or 0
        lines.append(
            f"- 融券餘額 {si.get('short_interest', 0):,.0f} (券資比 {ratio:.1%}, 來源 {si.get('source', '')})"
        )
    else:
        lines.append("- （暫無融券 / ETF 資金流紀錄）")

    lines.extend(["", "## 宏觀脈絡"])
    try:
        from macro_data import aggregate_hyperscaler_capex
        capex = aggregate_hyperscaler_capex()
        if capex.tickers_included:
            tickers_str = "/".join(capex.tickers_included)
            lines.append(
                f"- 本季 {tickers_str} capex 合計 ${capex.total_usd / 1_000_000_000:,.1f}B "
                f"(period {capex.period_end})"
            )
        else:
            lines.append("- （無 hyperscaler capex 對照資料）")
    except Exception:
        lines.append("- （無 hyperscaler capex 對照資料）")
```

- [ ] **Step 4: run tests, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_stock_memo -v
```

- [ ] **Step 5: full sweep**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only baseline failures.

- [ ] **Step 6: commit**

```bash
git add stock_memo.py tests/test_stock_memo.py
git commit -m "feat(memo): render 5 new sections in stock_memo

Memo now renders 最新法說會 / 近 90 天內部人交易 / 13F 機構動向
/ 融券與 ETF 資金流 / 宏觀脈絡, gracefully degrading to
'(暫無資料)' when the corresponding bundle field is None.
Macro section calls macro_data.aggregate_hyperscaler_capex
once per render."
```

---

### Task 4: Smoke run — `stock_memo` CLI for one US + one TW ticker

**Files:** none modified.

- [ ] **Step 1: NVDA memo**

```bash
uv run --with-requirements requirements.txt --python python3 python stock_memo.py --ticker NVDA --market us --no-refresh-official-data 2>&1 | tee /tmp/phase4-memo-nvda.log | tail -30
```

- [ ] **Step 2: 2330 memo**

```bash
uv run --with-requirements requirements.txt --python python3 python stock_memo.py --ticker 2330 --market tw --no-refresh-official-data 2>&1 | tee /tmp/phase4-memo-2330.log | tail -30
```

- [ ] **Step 3: confirm both memos contain all 5 new section headers**

```bash
for f in /tmp/phase4-memo-nvda.log /tmp/phase4-memo-2330.log; do
  echo "=== $f ==="
  for h in "## 最新法說會重點" "## 近 90 天內部人交易" "## 13F 機構動向" "## 融券與 ETF 資金流" "## 宏觀脈絡"; do
    grep -F "$h" "$f" >/dev/null && echo "  ✓ $h" || echo "  ✗ $h"
  done
done
```

Or read the actual output file under `data/memos/<ticker>.md` (the CLI writes there).

- [ ] **Step 4: commit smoke artifact**

```bash
mkdir -p docs/superpowers/runs
{
  echo "=== NVDA memo tail ==="
  tail -60 /tmp/phase4-memo-nvda.log
  echo ""
  echo "=== 2330 memo tail ==="
  tail -60 /tmp/phase4-memo-2330.log
} > docs/superpowers/runs/2026-05-09-phase4-memo-smoke.txt
git add docs/superpowers/runs/2026-05-09-phase4-memo-smoke.txt
git commit -m "test(smoke): capture phase 4 memo integration smoke run"
```

---

### Task 5: `openspec validate`

- [ ] **Step 1: mark all tasks completed**

Replace `- [ ]` with `- [x]` in `openspec/changes/investment-source-memo-integration/tasks.md`.

- [ ] **Step 2: validate**

```bash
command -v openspec >/dev/null && openspec validate investment-source-memo-integration 2>&1 | tail -3 || echo "openspec CLI not installed locally — skip"
```

Expected: validate passes.

---

### Task 6: Final commit + PHASE_DONE

- [ ] **Step 1: full sweep**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only baseline failures.

- [ ] **Step 2: final commit**

```bash
git add openspec/changes/investment-source-memo-integration/tasks.md
git commit -m "openspec: phase 4 done — investment-source-memo-integration

[phase-4 done]

stock_memo.py renders 5 new sections from bundle's structured
fields and macro_data hyperscaler capex aggregate.
format_financial_snapshot_bundle_context surfaces the same
fields into summarizer prompts. openspec validate passes.
All four phases of investment-source-expansion complete."
```

- [ ] **Step 3: emit promise**

When all checkboxes above are checked, reply with **only**:

```
<promise>PHASE_DONE</promise>
```
