# Investment Decision Dashboard — Implementation Plan

> **For ralph-loop:** Process tasks 1 → 14 in order. Each task ends with a commit. When all tasks check, reply only with `<promise>PHASE_DONE</promise>`.

**Goal:** Build a Cloudflare-Pages-deployable Astro dashboard that surfaces daily-news data for daily investment-decision use. New `web/` directory, new `dashboard_export.py` Python module, isolated CF Pages project `daily-news-dashboard`, deploys only to a subdomain via user-supplied env vars. **DO NOT execute `wrangler deploy`. DO NOT push to origin.** ralph only prepares artefacts.

**Architecture:** Build-time SSG. Python pipeline exports JSON snapshots to `web/src/data/`. Astro reads JSON at build time and produces `web/dist/` static site. CF Pages auto-builds on git push (user-controlled).

**Tech Stack:** Astro 5 + Tailwind 4 + TypeScript + shadcn-style components + uPlot for charts + Lucide icons. Python (existing repo). Node 22+ (assumed available; if not, README guides install).

**Spec:** [docs/superpowers/specs/2026-05-10-investment-dashboard-design.md](../specs/2026-05-10-investment-dashboard-design.md)

**Hard limits for this phase:**
- ❌ Do NOT execute `wrangler deploy` or any deployment command that hits a real CF endpoint
- ❌ Do NOT push to origin (`git push` forbidden)
- ❌ Do NOT modify existing Python pipeline modules (`crawler.py`, `summarizer.py`, `stock_memo.py`, `financial_reports.py`, `main.py`, `news_enrichment.py`, the 4 Phase-2 ingest modules)
- ❌ Do NOT modify `config.yaml`
- ❌ Do NOT touch `templates/report.html`, `html_generator.py` (existing daily HTML coexists)
- ❌ Do NOT write any real secret (API tokens, account IDs, domain names) anywhere except `.env.example` placeholders
- ✅ Create `web/` directory tree (Astro project)
- ✅ Create `dashboard_export.py` + `tests/test_dashboard_export.py`
- ✅ Create `launchd/export-dashboard-data.sh` (independent script)
- ✅ Create `docs/dashboard-deployment.md`
- ✅ Create new OpenSpec change under `openspec/changes/investment-dashboard/`

**Known baseline test failures (do not fix):**

```
ERROR  test_news_enrichment.test_init_db_adds_enrichment_columns_and_hydrates_new_fields
FAIL   test_summarizer.test_ai_practice_uses_deterministic_hotlist_without_llm
```

Phase success = no NEW Python test regressions + `cd web && npm install && npm run build` succeeds locally.

**Node.js prerequisite:** assume `node --version` ≥ 22. If `node` is missing, the build smoke task documents the gap in `web/README.md` and skips actual build (still commits Astro source files). Plan does not block on Node availability.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `dashboard_export.py` | create | Read SQLite + bundle → write JSON to `web/src/data/` |
| `tests/test_dashboard_export.py` | create | Round-trip tests against tmp SQLite |
| `web/package.json` | create | Astro 5 + Tailwind 4 deps, scripts |
| `web/astro.config.mjs` | create | Astro config (Cloudflare adapter optional) |
| `web/tailwind.config.mjs` | create | Theme tokens (dark / glassmorphism) |
| `web/tsconfig.json` | create | TypeScript strict |
| `web/src/layouts/Base.astro` | create | HTML shell, nav, dark theme |
| `web/src/components/BentoCard.astro` | create | Reusable card |
| `web/src/components/TickerChip.astro` | create | Coloured ticker tag |
| `web/src/components/StatLine.astro` | create | Label / value with delta |
| `web/src/components/EventCalendar.tsx` | create | Calendar island (interactive) |
| `web/src/components/NewsFilter.tsx` | create | News filter island |
| `web/src/components/TranscriptViewer.astro` | create | Transcript section render |
| `web/src/pages/index.astro` | create | Dashboard home (bento grid) |
| `web/src/pages/stocks/[ticker].astro` | create | Per-stock dynamic page with 6 tabs |
| `web/src/pages/news.astro` | create | News timeline + filter island |
| `web/src/pages/calendar.astro` | create | Calendar widget |
| `web/src/pages/decisions.astro` | create | Decisions journal |
| `web/src/data/overview.json` | create (example) | Schema example committed |
| `web/src/data/stocks/NVDA.json` | create (example) | Schema example |
| `web/src/data/news.json` | create (example) | Schema example |
| `web/src/data/events.json` | create (example) | Schema example |
| `web/src/data/decisions.json` | create (example) | Schema example |
| `web/src/data/watchlist.json` | create (example) | Schema example |
| `web/src/styles/global.css` | create | Tailwind base + custom |
| `web/wrangler.toml.template` | create | CF Pages config template |
| `web/.env.example` | create | Env var placeholders |
| `web/.gitignore` | create | `node_modules/`, `dist/`, `.env`, `wrangler.toml` |
| `web/README.md` | create | Stack overview + dev commands |
| `launchd/export-dashboard-data.sh` | create | Optional daily export script |
| `docs/dashboard-deployment.md` | create | CF Pages setup walkthrough |
| `openspec/changes/investment-dashboard/*` | create | OpenSpec artefacts |

---

### Task 1: OpenSpec scaffold

- [x] **Step 1: `openspec/changes/investment-dashboard/proposal.md`**

```markdown
## Why

daily-news produces rich data (news, financials, transcripts, insider, 13F, short-interest, macro) but consumption is via shell-rendered markdown or daily HTML report. An interactive web dashboard makes the data usable for daily investment decisions.

## What Changes

- Add `dashboard_export.py` Python module that reads SQLite + bundle and writes JSON snapshots.
- Add `web/` Astro project (Tailwind, shadcn-style components, uPlot charts) with 5 pages: home, per-stock, news, calendar, decisions.
- Add Cloudflare Pages config (template only, no real secrets).
- Add deployment guide under `docs/dashboard-deployment.md`.

## Capabilities

### New Capabilities
- `investment-dashboard-export`: Export daily-news SQLite data to JSON for static-site consumption.
- `investment-dashboard-web`: Astro-based static site with 5 dashboard pages.

## Impact

- New files only. No edits to existing Python pipeline modules, `config.yaml`, or existing templates.
- New CF Pages project `daily-news-dashboard` — isolated, deploys to subdomain only.
- No deployment executed by ralph. User runs `wrangler deploy` manually.
```

- [x] **Step 2: `openspec/changes/investment-dashboard/design.md`**

```markdown
# Design — investment-dashboard

See master spec at `docs/superpowers/specs/2026-05-10-investment-dashboard-design.md`.

## Highlights

- New `web/` directory uses Astro 5 SSG.
- Python `dashboard_export.py` writes JSON to `web/src/data/` at build time (daily cron).
- All deploy secrets parameterised via `.env.example` + `wrangler.toml.template`.
- ralph does NOT execute `wrangler deploy` or `git push`.

## Out of scope

- Real-time data feeds.
- Multi-tenant SaaS.
- Mobile-native app.
```

- [x] **Step 3: `openspec/changes/investment-dashboard/tasks.md`**

```markdown
# Tasks — investment-dashboard

- [x] Task 1 OpenSpec skeleton committed
- [x] Task 2 dashboard_export.py + tests
- [x] Task 3 web/ Astro scaffold + Tailwind + Base layout
- [x] Task 4 Home page bento grid
- [x] Task 5 Per-stock dynamic page with tabs
- [x] Task 6 News timeline + filter island
- [x] Task 7 Calendar widget
- [x] Task 8 Decisions journal
- [x] Task 9 UI polish (apply ui-ux-pro-max heuristics)
- [x] Task 10 wrangler.toml.template + .env.example
- [x] Task 11 launchd/export-dashboard-data.sh
- [x] Task 12 docs/dashboard-deployment.md
- [x] Task 13 Local build smoke + commit
- [x] Task 14 Final commit + PHASE_DONE
```

- [x] **Step 4: `openspec/changes/investment-dashboard/specs/investment-dashboard/spec.md`**

```markdown
## ADDED Requirements

### Requirement: dashboard_export.py produces JSON snapshots
The system SHALL expose `dashboard_export.py` that reads `data/news.db` + `financial_reports` bundles and writes JSON files under `web/src/data/`.

#### Scenario: overview.json contains today's top signals
- **WHEN** running `python dashboard_export.py --output web/src/data/`
- **THEN** `web/src/data/overview.json` SHALL exist with `top_transcripts`, `top_insider_trades`, `top_holdings_changes`, `market_indices`, `watchlist` keys

#### Scenario: stocks/<ticker>.json contains per-stock bundle
- **WHEN** exporting for a ticker present in `financial_reports`
- **THEN** `web/src/data/stocks/<ticker>.json` SHALL contain `bundle`, `recent_news`, `transcripts`, `insider`, `holdings`, `short_interest` keys

### Requirement: Astro project builds locally
The system SHALL provide an Astro project under `web/` that builds via `npm install && npm run build` without errors.

#### Scenario: dist directory contains 5 pages
- **WHEN** running `npm run build` in `web/`
- **THEN** `web/dist/` SHALL contain `index.html`, `news/index.html`, `calendar/index.html`, `decisions/index.html`, plus `stocks/<ticker>/index.html` for each example ticker

### Requirement: Deployment artefacts are templated only
The system SHALL provide `wrangler.toml.template` and `.env.example` with placeholder values, and SHALL NOT contain any real secret.

#### Scenario: no real secrets committed
- **WHEN** searching tracked files for typical secret patterns (real CF token, real account ID, real domain)
- **THEN** only placeholder patterns like `${CF_API_TOKEN}` or `your-domain.com` SHALL appear
```

- [x] **Step 5: Commit**

```bash
git add openspec/changes/investment-dashboard/
git commit -m "openspec: scaffold investment-dashboard change"
```

---

### Task 2: `dashboard_export.py` + tests

**Files:**
- Create: `dashboard_export.py`
- Create: `tests/test_dashboard_export.py`

- [x] **Step 1: Write failing test**

`tests/test_dashboard_export.py`:

```python
import json
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import dashboard_export
import financial_reports as fr


def _tmp_dir() -> Path:
    return Path(tempfile.mkdtemp())


class DashboardExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_dir()
        self.db = self.tmp / "news.db"
        self.out = self.tmp / "out"
        self.out.mkdir(parents=True, exist_ok=True)

        fr.init_financial_report_store(self.db)
        fr.save_financial_report(
            self.db,
            fr.FinancialReport(
                market="us", ticker="NVDA", company_name="NVIDIA",
                source_type="sec", form_type="10-Q",
                fiscal_year=2026, fiscal_period="Q1",
                period_end="2026-03-31", filed_at="2026-04-25",
                source_url="https://example.com", report_kind="quarterly",
                revenue=30_000_000_000.0,
            ),
        )
        fr.save_issuer_material(
            self.db,
            {
                "market": "us", "ticker": "NVDA",
                "material_type": "transcript",
                "title": "NVDA Q1 transcript",
                "body_text": "Blackwell ramp drives growth.",
                "source_url": "https://x",
                "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
            },
        )

    def test_export_overview_writes_json(self):
        dashboard_export.export_all(
            db_path=self.db, output_dir=self.out, tickers=["NVDA"]
        )
        overview = json.loads((self.out / "overview.json").read_text())
        self.assertIn("top_transcripts", overview)
        self.assertIn("watchlist", overview)
        self.assertIsInstance(overview["top_transcripts"], list)

    def test_export_per_stock_json(self):
        dashboard_export.export_all(
            db_path=self.db, output_dir=self.out, tickers=["NVDA"]
        )
        path = self.out / "stocks" / "NVDA.json"
        self.assertTrue(path.exists())
        payload = json.loads(path.read_text())
        self.assertEqual(payload["ticker"], "NVDA")
        self.assertIn("bundle", payload)
        self.assertIn("transcripts", payload)

    def test_export_news_json_with_empty_db(self):
        dashboard_export.export_all(
            db_path=self.db, output_dir=self.out, tickers=["NVDA"]
        )
        news = json.loads((self.out / "news.json").read_text())
        self.assertIn("articles", news)
        self.assertIsInstance(news["articles"], list)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_dashboard_export
```

- [x] **Step 3: Create `dashboard_export.py`**

```python
"""Export daily-news SQLite + bundle data to JSON for the dashboard."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import financial_reports as fr


DEFAULT_DB = Path(__file__).resolve().parent / "data" / "news.db"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "web" / "src" / "data"


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Not JSON serialisable: {type(value)!r}")


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _load_watchlist(repo_root: Path) -> list[str]:
    candidate = repo_root / "data" / "watchlist.yaml"
    if not candidate.exists():
        return ["NVDA", "TSM", "2330", "AAPL", "MSFT"]
    try:
        import yaml

        loaded = yaml.safe_load(candidate.read_text(encoding="utf-8")) or []
        if isinstance(loaded, list):
            return [str(t).strip() for t in loaded if t]
        if isinstance(loaded, dict) and "tickers" in loaded:
            return [str(t).strip() for t in loaded["tickers"] if t]
    except Exception:
        pass
    return ["NVDA", "TSM", "2330", "AAPL", "MSFT"]


def _recent_news(db_path: Path, limit: int = 200) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT title, link, source, category, published, summary,
                   tickers_json, companies_json, event_type
            FROM articles
            ORDER BY published DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    out: list[dict] = []
    for row in rows:
        record = dict(row)
        for key in ("tickers_json", "companies_json"):
            raw = record.pop(key, "[]")
            try:
                record[key.replace("_json", "")] = json.loads(raw or "[]")
            except Exception:
                record[key.replace("_json", "")] = []
        out.append(record)
    return out


def _market_overview_cache(repo_root: Path) -> dict:
    cache = repo_root / "data" / "market_overview_cache.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _bundle_to_dict(bundle: fr.FinancialSnapshotBundle | None) -> dict | None:
    if bundle is None:
        return None
    return {
        "market": bundle.market,
        "ticker": bundle.ticker,
        "company_name": bundle.company_name,
        "quarterly": asdict(bundle.quarterly) if bundle.quarterly else None,
        "monthly_revenue": asdict(bundle.monthly_revenue) if bundle.monthly_revenue else None,
        "latest_transcript": bundle.latest_transcript,
        "recent_insider_summary": bundle.recent_insider_summary,
        "latest_13f": bundle.latest_13f,
        "short_interest": bundle.short_interest,
    }


def _per_stock(db_path: Path, market: str, ticker: str) -> dict:
    bundle = fr.get_financial_snapshot_bundle(db_path, market=market, ticker=ticker)
    transcripts = fr.get_recent_issuer_materials(db_path, market=market, ticker=ticker, limit=5)
    insiders = fr.get_recent_insider_transactions(db_path, ticker=ticker, limit=20)
    shorts = fr.get_recent_short_interest_snapshots(db_path, ticker=ticker, limit=20)
    recent_news = [n for n in _recent_news(db_path, limit=1000) if ticker.upper() in (n.get("tickers") or [])][:25]
    return {
        "ticker": ticker.upper(),
        "market": market,
        "bundle": _bundle_to_dict(bundle),
        "transcripts": transcripts,
        "insider": insiders,
        "short_interest": shorts,
        "holdings": [],
        "recent_news": recent_news,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def _infer_market(ticker: str) -> str:
    return "tw" if ticker.strip().isdigit() else "us"


def export_all(
    *,
    db_path: Path | str = DEFAULT_DB,
    output_dir: Path | str = DEFAULT_OUTPUT,
    tickers: list[str] | None = None,
) -> dict[str, Path]:
    db_path = Path(db_path)
    output_dir = Path(output_dir)
    repo_root = Path(__file__).resolve().parent
    if tickers is None:
        tickers = _load_watchlist(repo_root)

    artefacts: dict[str, Path] = {}

    # overview
    overview_path = output_dir / "overview.json"
    top_transcripts: list[dict] = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM issuer_materials WHERE material_type='transcript' "
                "ORDER BY fetched_at DESC LIMIT 5"
            ).fetchall()
            top_transcripts = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            top_transcripts = []
        finally:
            conn.close()
    except Exception:
        top_transcripts = []
    overview = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "top_transcripts": top_transcripts,
        "top_insider_trades": [],
        "top_holdings_changes": [],
        "market_indices": _market_overview_cache(repo_root),
        "watchlist": tickers,
    }
    _write(overview_path, overview)
    artefacts["overview"] = overview_path

    # news
    news_path = output_dir / "news.json"
    _write(news_path, {"articles": _recent_news(db_path, limit=300)})
    artefacts["news"] = news_path

    # events
    events_path = output_dir / "events.json"
    _write(events_path, {"events": []})
    artefacts["events"] = events_path

    # decisions
    decisions_path = output_dir / "decisions.json"
    _write(decisions_path, {"decisions": []})
    artefacts["decisions"] = decisions_path

    # watchlist
    watchlist_path = output_dir / "watchlist.json"
    _write(watchlist_path, {"tickers": tickers})
    artefacts["watchlist"] = watchlist_path

    # per-stock
    for ticker in tickers:
        market = _infer_market(ticker)
        path = output_dir / "stocks" / f"{ticker.upper()}.json"
        _write(path, _per_stock(db_path, market, ticker))
        artefacts[f"stock:{ticker}"] = path

    return artefacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--ticker", action="append", default=None)
    args = parser.parse_args(argv)
    export_all(
        db_path=Path(args.db),
        output_dir=Path(args.output),
        tickers=args.ticker,
    )
    print("✅ dashboard export complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Run tests, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_dashboard_export -v
```

- [x] **Step 5: Run full Python suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only baseline failures.

- [x] **Step 6: Commit**

```bash
git add dashboard_export.py tests/test_dashboard_export.py
git commit -m "feat(dashboard): add dashboard_export.py + tests"
```

---

### Task 3: Astro scaffold + Tailwind + Base layout

**Files:** create everything under `web/`.

- [x] **Step 1: `web/package.json`**

```json
{
  "name": "daily-news-dashboard",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "astro dev",
    "build": "astro check && astro build",
    "preview": "astro preview",
    "astro": "astro"
  },
  "dependencies": {
    "@astrojs/check": "^0.9.4",
    "@astrojs/tailwind": "^6.0.2",
    "@tailwindcss/vite": "^4.1.16",
    "astro": "^5.10.2",
    "lucide-astro": "^0.475.0",
    "tailwindcss": "^4.1.16",
    "typescript": "^5.7.2",
    "uplot": "^1.6.32"
  }
}
```

- [x] **Step 2: `web/astro.config.mjs`**

```js
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  output: "static",
  site: process.env.PUBLIC_SITE_URL ?? "https://invest.example.com",
  vite: {
    plugins: [tailwindcss()],
  },
});
```

- [x] **Step 3: `web/tsconfig.json`**

```json
{
  "extends": "astro/tsconfigs/strict",
  "include": ["src/**/*.ts", "src/**/*.tsx", "src/**/*.astro"]
}
```

- [x] **Step 4: `web/tailwind.config.mjs`** (kept for clarity even with Vite plugin)

```js
export default {
  content: ["./src/**/*.{astro,html,ts,tsx,jsx,js,md}"],
  theme: {
    extend: {
      colors: {
        bg: { 950: "#0a0c10", 900: "#0f1218", 800: "#161b24" },
        accent: { 500: "#7aa2ff", 400: "#a5c0ff" },
        ok: { 500: "#3ddc97" },
        warn: { 500: "#ffae5c" },
        bad: { 500: "#ff6b81" },
      },
      fontFamily: {
        sans: ["Inter", "SF Pro Text", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
};
```

- [x] **Step 5: `web/src/styles/global.css`**

```css
@import "tailwindcss";

:root {
  color-scheme: dark;
  --bg-950: #0a0c10;
  --bg-900: #0f1218;
}

html,
body {
  background-color: var(--bg-950);
  color: #e8ecf3;
  font-family: "Inter", "SF Pro Text", system-ui, sans-serif;
}

.glass {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.01));
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.mono { font-family: "JetBrains Mono", ui-monospace, monospace; }

.delta-up { color: #3ddc97; }
.delta-down { color: #ff6b81; }
```

- [x] **Step 6: `web/src/layouts/Base.astro`**

```astro
---
import "../styles/global.css";

interface Props {
  title?: string;
}
const { title = "投資決策 Dashboard" } = Astro.props;
---
<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width" />
    <title>{title}</title>
  </head>
  <body class="min-h-screen">
    <nav class="glass sticky top-0 z-50 px-6 py-3 flex gap-6 items-center">
      <a href="/" class="font-semibold tracking-tight">📈 Daily-News</a>
      <a href="/" class="opacity-80 hover:opacity-100">總覽</a>
      <a href="/news" class="opacity-80 hover:opacity-100">新聞</a>
      <a href="/calendar" class="opacity-80 hover:opacity-100">月曆</a>
      <a href="/decisions" class="opacity-80 hover:opacity-100">日誌</a>
      <span class="ml-auto text-xs opacity-60 mono">v0.1</span>
    </nav>
    <main class="max-w-7xl mx-auto px-6 py-8">
      <slot />
    </main>
    <footer class="text-center text-xs opacity-50 py-8 mono">
      build: <span id="build-ts">{new Date().toISOString().slice(0, 16)}Z</span>
    </footer>
  </body>
</html>
```

- [x] **Step 7: `web/src/components/BentoCard.astro`**

```astro
---
interface Props {
  title: string;
  href?: string;
  span?: "1" | "2" | "3";
}
const { title, href, span = "1" } = Astro.props;
const colSpan = { "1": "md:col-span-1", "2": "md:col-span-2", "3": "md:col-span-3" }[span];
---
<div class={`glass rounded-2xl p-5 ${colSpan}`}>
  <header class="flex items-center justify-between mb-3">
    <h3 class="text-sm uppercase tracking-wider opacity-70">{title}</h3>
    {href ? <a href={href} class="text-xs opacity-60 hover:opacity-100">→</a> : null}
  </header>
  <div class="space-y-2">
    <slot />
  </div>
</div>
```

- [x] **Step 8: `web/src/components/TickerChip.astro`**

```astro
---
interface Props { ticker: string; market?: "tw" | "us" | null }
const { ticker, market = null } = Astro.props;
const marketStr = (market ?? (ticker.match(/^\d+$/) ? "tw" : "us"));
const cls = marketStr === "tw" ? "bg-bg-800 text-accent-400 border-accent-500/40" : "bg-bg-800 text-amber-300 border-amber-500/40";
---
<span class={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs mono ${cls}`}>
  <a href={`/stocks/${ticker.toUpperCase()}`}>{ticker.toUpperCase()}</a>
</span>
```

- [x] **Step 9: `web/.gitignore`**

```
node_modules/
dist/
.astro/
.env
.env.local
wrangler.toml
.DS_Store
```

- [x] **Step 10: Commit**

```bash
git add web/package.json web/astro.config.mjs web/tsconfig.json web/tailwind.config.mjs \
        web/src/styles/global.css web/src/layouts/Base.astro \
        web/src/components/BentoCard.astro web/src/components/TickerChip.astro \
        web/.gitignore
git commit -m "feat(dashboard): scaffold astro+tailwind shell + base layout"
```

---

### Task 4: Home page bento grid

- [x] **Step 1: Sample `web/src/data/overview.json`**

```json
{
  "generated_at": "2026-05-10T00:00:00Z",
  "watchlist": ["NVDA", "TSM", "2330", "AAPL", "MSFT"],
  "top_transcripts": [
    { "ticker": "NVDA", "title": "NVDA Q1 transcript", "body_excerpt": "Blackwell ramp drives data center revenue.", "fetched_at": "2026-05-09T00:00:00Z" }
  ],
  "top_insider_trades": [
    { "ticker": "AAPL", "insider_name": "Cook Timothy D", "transaction_type": "S", "shares": 10000, "price": 180.5, "transaction_date": "2026-04-15" }
  ],
  "top_holdings_changes": [],
  "market_indices": { "indices": [{ "symbol": "SPY", "price": 580.4, "change_pct": 0.42 }, { "symbol": "QQQ", "price": 510.1, "change_pct": 0.68 }, { "symbol": "^TWII", "price": 22130.5, "change_pct": -0.15 }] }
}
```

- [x] **Step 2: `web/src/pages/index.astro`**

```astro
---
import Base from "../layouts/Base.astro";
import BentoCard from "../components/BentoCard.astro";
import TickerChip from "../components/TickerChip.astro";
import overview from "../data/overview.json";

const indices = (overview.market_indices?.indices ?? []) as Array<{ symbol: string; price: number; change_pct: number }>;
const transcripts = overview.top_transcripts ?? [];
const insiders = overview.top_insider_trades ?? [];
const watchlist = overview.watchlist ?? [];
---
<Base title="總覽 — 投資決策 Dashboard">
  <header class="mb-6 flex items-baseline justify-between">
    <h1 class="text-3xl font-semibold tracking-tight">總覽</h1>
    <span class="text-xs opacity-60 mono">data @ {overview.generated_at}</span>
  </header>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <BentoCard title="指數" span="1">
      <ul class="space-y-1">
        {indices.map(ix => (
          <li class="flex justify-between mono text-sm">
            <span>{ix.symbol}</span>
            <span>{ix.price.toLocaleString()}</span>
            <span class={ix.change_pct >= 0 ? "delta-up" : "delta-down"}>
              {ix.change_pct >= 0 ? "+" : ""}{ix.change_pct.toFixed(2)}%
            </span>
          </li>
        ))}
      </ul>
    </BentoCard>

    <BentoCard title="Watchlist" span="1">
      <div class="flex flex-wrap gap-2">
        {watchlist.map(t => <TickerChip ticker={t} />)}
      </div>
    </BentoCard>

    <BentoCard title="今日重點訊號" span="1" href="/news">
      <p class="text-xs opacity-70">最近 transcript / 內部人 / 大額機構變動 5 條</p>
    </BentoCard>

    <BentoCard title="最新法說會 transcripts" span="2" href="/news">
      <ul class="space-y-2">
        {transcripts.map(t => (
          <li class="text-sm">
            <TickerChip ticker={t.ticker} /> <span class="opacity-80">{t.title}</span>
            <p class="text-xs opacity-60 mt-1 line-clamp-2">{t.body_excerpt}</p>
          </li>
        ))}
      </ul>
    </BentoCard>

    <BentoCard title="近期內部人交易" span="1">
      <ul class="space-y-2 text-sm">
        {insiders.map(i => (
          <li>
            <TickerChip ticker={i.ticker} />
            <span class="opacity-80">{i.insider_name}</span>
            <span class={i.transaction_type === "S" ? "delta-down" : "delta-up"}>
              {i.transaction_type === "S" ? "賣" : "買"}
            </span>
            <span class="mono opacity-70">{i.shares.toLocaleString()} @ ${i.price.toFixed(2)}</span>
          </li>
        ))}
      </ul>
    </BentoCard>
  </div>
</Base>
```

- [x] **Step 3: Commit**

```bash
git add web/src/data/overview.json web/src/pages/index.astro
git commit -m "feat(dashboard): home bento grid with indices/watchlist/transcripts"
```

---

### Task 5: Per-stock dynamic page with tabs

- [x] **Step 1: Sample `web/src/data/stocks/NVDA.json`**

```json
{
  "ticker": "NVDA",
  "market": "us",
  "generated_at": "2026-05-10T00:00:00Z",
  "bundle": {
    "market": "us", "ticker": "NVDA", "company_name": "NVIDIA",
    "quarterly": { "form_type": "10-Q", "fiscal_year": 2026, "fiscal_period": "Q1", "revenue": 30000000000.0, "eps_diluted": 3.14, "free_cash_flow": 13500000000.0, "guidance_summary": "FY26 Q2 guide $32B revenue", "filing_excerpt": "" },
    "monthly_revenue": null,
    "latest_transcript": { "title": "NVDA Q1 transcript", "body_text": "Blackwell ramp drives data center revenue.", "material_type": "transcript" },
    "recent_insider_summary": null,
    "latest_13f": null,
    "short_interest": null
  },
  "transcripts": [],
  "insider": [],
  "short_interest": [],
  "holdings": [],
  "recent_news": [
    { "title": "NVIDIA sets new AI compute record", "link": "https://example.com/n1", "source": "CNBC", "published": "2026-05-09T00:00:00Z" }
  ]
}
```

- [x] **Step 2: `web/src/pages/stocks/[ticker].astro`**

```astro
---
import Base from "../../layouts/Base.astro";
import BentoCard from "../../components/BentoCard.astro";
import TickerChip from "../../components/TickerChip.astro";

export async function getStaticPaths() {
  const modules = import.meta.glob("../../data/stocks/*.json", { eager: true });
  return Object.entries(modules).map(([file, mod]) => {
    const m = mod as { default: any };
    const ticker = file.split("/").pop()!.replace(".json", "");
    return { params: { ticker }, props: { data: m.default } };
  });
}

const { data } = Astro.props;
const bundle = data.bundle ?? null;
const quarterly = bundle?.quarterly ?? null;
---
<Base title={`${data.ticker} 個股深度`}>
  <header class="mb-6 flex items-baseline gap-3">
    <h1 class="text-3xl font-semibold mono">{data.ticker}</h1>
    <span class="text-sm opacity-70">{bundle?.company_name ?? ""}</span>
    <span class="text-xs opacity-60 mono ml-auto">data @ {data.generated_at}</span>
  </header>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <BentoCard title="官方財報" span="2">
      {quarterly ? (
        <ul class="space-y-1 text-sm">
          <li>FY{quarterly.fiscal_year} {quarterly.fiscal_period} | {quarterly.form_type}</li>
          {quarterly.revenue && <li>營收 <span class="mono">${(quarterly.revenue / 1e9).toFixed(1)}B</span></li>}
          {quarterly.eps_diluted && <li>EPS <span class="mono">{quarterly.eps_diluted.toFixed(2)}</span></li>}
          {quarterly.free_cash_flow && <li>FCF <span class="mono">${(quarterly.free_cash_flow / 1e9).toFixed(1)}B</span></li>}
          {quarterly.guidance_summary && <li class="opacity-80">Guidance：{quarterly.guidance_summary}</li>}
        </ul>
      ) : <p class="opacity-60 text-sm">（暫無官方財報資料）</p>}
    </BentoCard>

    <BentoCard title="最新法說會">
      {bundle?.latest_transcript ? (
        <div class="text-sm space-y-1">
          <p class="font-medium">{bundle.latest_transcript.title}</p>
          <p class="opacity-80 line-clamp-4">{bundle.latest_transcript.body_text}</p>
        </div>
      ) : <p class="opacity-60 text-sm">（暫無）</p>}
    </BentoCard>

    <BentoCard title="近期內部人交易" span="1">
      {(data.insider ?? []).length === 0
        ? <p class="opacity-60 text-sm">（暫無）</p>
        : <ul class="space-y-1 text-sm">
            {(data.insider ?? []).slice(0, 5).map((i: any) => (
              <li class="mono"><span class={i.transaction_type === "S" ? "delta-down" : "delta-up"}>{i.transaction_type}</span> {i.shares.toLocaleString()} @ ${i.price.toFixed(2)}</li>
            ))}
          </ul>}
    </BentoCard>

    <BentoCard title="融券 / ETF 流向" span="1">
      {bundle?.short_interest
        ? <p class="text-sm mono">融券餘額 {bundle.short_interest.short_interest.toLocaleString()} | 券資比 {(bundle.short_interest.short_interest_ratio * 100).toFixed(1)}%</p>
        : <p class="opacity-60 text-sm">（暫無）</p>}
    </BentoCard>

    <BentoCard title="相關新聞" span="3" href="/news">
      <ul class="space-y-1 text-sm">
        {(data.recent_news ?? []).slice(0, 10).map((n: any) => (
          <li class="flex gap-3">
            <span class="opacity-60 mono text-xs shrink-0">{(n.published ?? "").slice(0, 10)}</span>
            <a href={n.link} class="opacity-90 hover:opacity-100 truncate">{n.title}</a>
            <span class="ml-auto text-xs opacity-50">{n.source}</span>
          </li>
        ))}
      </ul>
    </BentoCard>
  </div>
</Base>
```

- [x] **Step 3: Commit**

```bash
git add web/src/data/stocks/NVDA.json web/src/pages/stocks/[ticker].astro
git commit -m "feat(dashboard): per-stock dynamic page with 5 bento sections"
```

---

### Task 6: News timeline + filter

- [x] **Step 1: Sample `web/src/data/news.json`**

```json
{
  "articles": [
    { "title": "NVIDIA sets new AI compute record", "link": "https://example.com/n1", "source": "CNBC", "category": "🔬 半導體與硬體", "published": "2026-05-09T08:00:00Z", "summary": "NVIDIA announced…", "tickers": ["NVDA"], "companies": ["NVIDIA"], "event_type": "news" },
    { "title": "Berkshire 13F shows reduced AAPL stake", "link": "https://example.com/n2", "source": "Insider Monkey", "category": "👁️ 內部人與機構持股", "published": "2026-05-09T11:00:00Z", "summary": "Berkshire reduced…", "tickers": ["AAPL"], "companies": ["Apple"], "event_type": "filing" }
  ]
}
```

- [x] **Step 2: `web/src/pages/news.astro`**

```astro
---
import Base from "../layouts/Base.astro";
import TickerChip from "../components/TickerChip.astro";
import news from "../data/news.json";

const articles = (news.articles ?? []) as Array<any>;
const categories = Array.from(new Set(articles.map(a => a.category))).filter(Boolean) as string[];
---
<Base title="新聞 — 投資決策 Dashboard">
  <header class="mb-6 flex items-baseline justify-between">
    <h1 class="text-3xl font-semibold tracking-tight">新聞</h1>
    <span class="text-xs opacity-60 mono">{articles.length} 篇</span>
  </header>

  <details class="glass rounded-xl px-4 py-3 mb-4 text-sm">
    <summary class="cursor-pointer opacity-80">分類過濾</summary>
    <div class="flex flex-wrap gap-2 mt-3">
      {categories.map(c => (
        <a href={`#${encodeURIComponent(c)}`} class="px-2 py-1 rounded-md border border-white/10 text-xs opacity-80 hover:opacity-100">{c}</a>
      ))}
    </div>
  </details>

  <ul class="space-y-2">
    {articles.map(a => (
      <li class="glass rounded-xl p-4">
        <div class="flex flex-wrap items-baseline gap-2">
          <a href={a.link} class="font-medium hover:underline">{a.title}</a>
          {(a.tickers ?? []).map((t: string) => <TickerChip ticker={t} />)}
          <span class="ml-auto text-xs opacity-60 mono">{(a.published ?? "").slice(0, 16).replace("T", " ")} | {a.source}</span>
        </div>
        {a.summary && <p class="opacity-70 text-sm mt-2 line-clamp-2">{a.summary}</p>}
        <div class="text-xs opacity-50 mt-2">{a.category}{a.event_type ? ` · ${a.event_type}` : ""}</div>
      </li>
    ))}
  </ul>
</Base>
```

- [x] **Step 3: Commit**

```bash
git add web/src/data/news.json web/src/pages/news.astro
git commit -m "feat(dashboard): news timeline with category filter"
```

---

### Task 7: Calendar widget

- [x] **Step 1: Sample `web/src/data/events.json`**

```json
{
  "events": [
    { "date": "2026-05-15", "ticker": "NVDA", "type": "earnings", "title": "NVDA Q1 法說會" },
    { "date": "2026-05-18", "ticker": "", "type": "macro", "title": "US CPI release" }
  ]
}
```

- [x] **Step 2: `web/src/pages/calendar.astro`**

```astro
---
import Base from "../layouts/Base.astro";
import TickerChip from "../components/TickerChip.astro";
import events from "../data/events.json";

const list = (events.events ?? []) as Array<any>;
const byDate = list.reduce((acc: Record<string, any[]>, e) => {
  (acc[e.date] = acc[e.date] || []).push(e);
  return acc;
}, {});
const dates = Object.keys(byDate).sort();
---
<Base title="月曆 — 投資決策 Dashboard">
  <header class="mb-6"><h1 class="text-3xl font-semibold">事件月曆</h1></header>
  {dates.length === 0
    ? <p class="opacity-60">尚無事件資料（Python 端 events export 待補）</p>
    : <ul class="space-y-3">
        {dates.map(d => (
          <li class="glass rounded-xl p-4">
            <div class="mono text-sm opacity-70 mb-2">{d}</div>
            <ul class="space-y-1">
              {byDate[d].map((e: any) => (
                <li class="flex gap-2 items-baseline text-sm">
                  {e.ticker && <TickerChip ticker={e.ticker} />}
                  <span class="opacity-90">{e.title}</span>
                  <span class="ml-auto text-xs opacity-60">{e.type}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>}
</Base>
```

- [x] **Step 3: Commit**

```bash
git add web/src/data/events.json web/src/pages/calendar.astro
git commit -m "feat(dashboard): event calendar page"
```

---

### Task 8: Decisions journal

- [x] **Step 1: Sample `web/src/data/decisions.json`**

```json
{
  "decisions": [
    { "date": "2026-04-20", "ticker": "NVDA", "action": "加碼", "size_pct": 2, "thesis": "Blackwell ramp + sovereign AI demand", "follow_up": "Q1 earnings check guidance" }
  ]
}
```

- [x] **Step 2: `web/src/pages/decisions.astro`**

```astro
---
import Base from "../layouts/Base.astro";
import TickerChip from "../components/TickerChip.astro";
import data from "../data/decisions.json";

const decisions = (data.decisions ?? []) as Array<any>;
---
<Base title="決策日誌 — 投資決策 Dashboard">
  <header class="mb-6"><h1 class="text-3xl font-semibold">決策日誌</h1></header>
  {decisions.length === 0
    ? <p class="opacity-60">尚無決策紀錄</p>
    : <ul class="space-y-3">
        {decisions.map(d => (
          <li class="glass rounded-xl p-4">
            <div class="flex items-baseline gap-3">
              <span class="mono opacity-70 text-sm">{d.date}</span>
              <TickerChip ticker={d.ticker} />
              <span class="text-sm">{d.action} {d.size_pct ? `(${d.size_pct}%)` : ""}</span>
            </div>
            <p class="text-sm opacity-90 mt-2">論點：{d.thesis}</p>
            {d.follow_up && <p class="text-xs opacity-70 mt-1">追蹤：{d.follow_up}</p>}
          </li>
        ))}
      </ul>}
</Base>
```

- [x] **Step 3: Commit**

```bash
git add web/src/data/decisions.json web/src/pages/decisions.astro
git commit -m "feat(dashboard): decisions journal page"
```

---

### Task 9: UI polish

Apply ui-ux-pro-max heuristics:
- spacing rhythm 8px scale
- consistent border-radius (lg/xl/2xl)
- focus rings (`focus-visible:ring-accent-500`)
- contrast ≥ AA on text
- mono font for any number / ticker

- [x] **Step 1: Touch up `global.css` if needed**

Add focus state + skeleton placeholder helper. Skip if existing class works.

- [x] **Step 2: Add `web/src/components/StatLine.astro`** for reuse on per-stock page

```astro
---
interface Props { label: string; value: string; delta?: number | null }
const { label, value, delta = null } = Astro.props;
---
<div class="flex justify-between items-baseline border-b border-white/5 py-1 last:border-b-0">
  <span class="text-xs uppercase tracking-wider opacity-60">{label}</span>
  <span class="mono text-sm">{value}</span>
  {delta != null && <span class={`mono text-xs ml-2 ${delta >= 0 ? "delta-up" : "delta-down"}`}>{delta >= 0 ? "+" : ""}{delta.toFixed(2)}%</span>}
</div>
```

- [x] **Step 3: Commit**

```bash
git add web/src/components/StatLine.astro web/src/styles/global.css
git commit -m "feat(dashboard): StatLine reusable component + style polish"
```

---

### Task 10: wrangler template + env example

- [x] **Step 1: `web/wrangler.toml.template`**

```toml
# Cloudflare Pages config (TEMPLATE — copy to wrangler.toml and fill in)
name = "daily-news-dashboard"
compatibility_date = "2026-05-01"
pages_build_output_dir = "dist"

# Required env vars (set via `wrangler pages secret put` or CF dashboard):
#   PUBLIC_SITE_URL   — e.g. https://invest.your-domain.com
#
# Optional: bind to your CF account by replacing the placeholder below.
# account_id = "${CF_ACCOUNT_ID}"
```

- [x] **Step 2: `web/.env.example`**

```
# Copy to .env.local and fill in real values. NEVER commit .env or .env.local.

CF_API_TOKEN=replace-with-your-cloudflare-api-token
CF_ACCOUNT_ID=replace-with-your-cloudflare-account-id
CF_DEPLOYMENT_DOMAIN=invest.your-domain.com
PUBLIC_SITE_URL=https://invest.your-domain.com
```

- [x] **Step 3: Commit**

```bash
git add web/wrangler.toml.template web/.env.example
git commit -m "chore(dashboard): wrangler + env templates (placeholders only)"
```

---

### Task 11: launchd export script

- [x] **Step 1: `launchd/export-dashboard-data.sh`**

```bash
#!/usr/bin/env bash
# Daily dashboard data export — chain after daily-news pipeline.
# This script does NOT deploy; it only refreshes JSON snapshots locally.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found, skipping dashboard export" >&2
  exit 0
fi

uv run --with-requirements requirements.txt --python python3 \
  python dashboard_export.py \
  --output "$REPO_ROOT/web/src/data"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] dashboard JSON refreshed"
```

- [x] **Step 2: chmod**

```bash
chmod +x launchd/export-dashboard-data.sh
```

- [x] **Step 3: Commit**

```bash
git add launchd/export-dashboard-data.sh
git commit -m "chore(dashboard): launchd export script (daily JSON refresh)"
```

---

### Task 12: Deployment guide

- [x] **Step 1: `docs/dashboard-deployment.md`**

````markdown
# Investment Dashboard — Cloudflare Pages 部署指南

## 前置條件

- Node.js ≥ 22（建議：`nvm install 22 && nvm use 22`）
- Cloudflare 帳號（免費 tier 已足夠）
- 一個你已擁有的 domain（已加到 Cloudflare）
- `wrangler` CLI：`npm install -g wrangler`

## 第一次設定（手動）

### 1. 本地建置確認

```bash
cd web
npm install
npm run build        # 產生 web/dist/
npm run preview      # http://localhost:4321 確認 5 頁亮著
```

### 2. 建立 Cloudflare Pages 專案

在 Cloudflare dashboard → Pages → Create application → Connect to Git。

- Repository：`andys0919/daily-news`
- Production branch：`main`
- Project name：`daily-news-dashboard`（**請用這個名稱，不要覆蓋既有專案**）
- Build command：`cd web && npm install && npm run build`
- Build output directory：`web/dist`
- Environment variables：
  - `PUBLIC_SITE_URL` = `https://invest.your-domain.com`

### 3. 綁定 custom domain（subdomain only）

Pages → 你的專案 → Custom domains → Set up a custom domain → 輸入 `invest.your-domain.com`（自選 subdomain，請務必使用 subdomain，不要 deploy 到 root）。

### 4. 啟用 Cloudflare Access

Zero Trust → Access → Applications → Add an application:

- Type：Self-hosted
- Application domain：`invest.your-domain.com`
- Identity providers：Google（或 One-time PIN email）
- Policy：Include → Emails → 你的 email（或 emails ending in `@your-domain.com`）

### 5. 本地 wrangler

```bash
cp web/wrangler.toml.template web/wrangler.toml
cp web/.env.example web/.env.local
# 編輯 .env.local 填入 CF_API_TOKEN / CF_ACCOUNT_ID / CF_DEPLOYMENT_DOMAIN
```

## 日常 deploy 流程

每天 launchd 跑完 daily-news 後：

```bash
bash launchd/export-dashboard-data.sh
git add web/src/data/
git commit -m "data: daily snapshot $(date +%F)"
git push                          # CF Pages 自動 rebuild
```

或手動：

```bash
cd web && npm run build && wrangler pages deploy dist --project-name daily-news-dashboard
```

## 不會覆蓋既有服務的保證

- Pages 專案名是 `daily-news-dashboard`，與你既有專案隔離
- 只 deploy 到 subdomain（`invest.*`）
- `wrangler.toml.template` 只放 placeholder
- ralph 自動化不會執行 `wrangler deploy`
````

- [x] **Step 2: Commit**

```bash
git add docs/dashboard-deployment.md
git commit -m "docs(dashboard): cloudflare pages deployment guide"
```

---

### Task 13: Local build smoke

- [x] **Step 1: Check node availability**

```bash
node --version 2>&1 | head -1 || echo "node not available"
```

- [x] **Step 2: If node ≥ 22 present, install + build**

```bash
cd web && npm install --no-audit --no-fund 2>&1 | tail -5
npm run build 2>&1 | tail -20
ls dist/ | head
```

If node is missing, append to `web/README.md`:

```markdown
> **Build prerequisite:** Node 22+ is required. Install via `nvm install 22 && nvm use 22` before running `npm install && npm run build`.
```

- [x] **Step 3: `web/README.md`** (regardless of node availability)

````markdown
# daily-news-dashboard

Astro 5 + Tailwind 4 + TypeScript static site for the daily-news investment dashboard.

## Build prerequisite

Node 22+. Install via `nvm install 22 && nvm use 22`.

## Dev / build

```bash
npm install
npm run dev          # http://localhost:4321
npm run build        # → dist/
npm run preview      # serve dist/ locally
```

## Data refresh

JSON under `src/data/` is regenerated by the Python pipeline:

```bash
cd ..
python dashboard_export.py --output web/src/data
```

## Deployment

See `docs/dashboard-deployment.md`.
````

- [x] **Step 4: Commit**

```bash
git add web/README.md
git commit -m "docs(dashboard): web README + build prerequisites"
```

---

### Task 14: Final commit + PHASE_DONE

- [x] **Step 1: Mark all tasks completed in `openspec/changes/investment-dashboard/tasks.md`** (replace each `- [x]` with `- [x]`)

- [x] **Step 2: openspec validate**

```bash
command -v openspec >/dev/null && openspec validate investment-dashboard 2>&1 | tail -3 || echo "openspec CLI not installed locally — skip"
```

- [x] **Step 3: Final test sweep**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests 2>&1 | grep -E "^(FAIL|ERROR|Ran |FAILED|OK)"
```

Expected: only the two baseline failures.

- [x] **Step 4: Final commit**

```bash
git add openspec/changes/investment-dashboard/tasks.md
git commit -m "openspec: investment-dashboard done

[dashboard ready]

New investment-decision web dashboard scaffolded under web/.
Astro 5 + Tailwind 4 + 5 pages. Python dashboard_export.py
writes JSON snapshots. Cloudflare Pages config templated only —
deploy must be performed manually by user with their own
domain/token. No existing service touched."
```

- [x] **Step 5: Emit promise**

Reply ONLY with `<promise>PHASE_DONE</promise>` (no other text) when:
1. All 14 tasks are committed
2. `openspec validate investment-dashboard` returns `is valid` (or "openspec CLI not installed locally")
3. All checkbox steps marked `[x]` in plan + tasks.md
4. Python test sweep shows only baseline failures
