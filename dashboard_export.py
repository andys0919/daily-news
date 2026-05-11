"""Export daily-news SQLite + bundle data to JSON for the investment dashboard.

Aggregates everything from ~55K articles + ~300 financial reports + watchlist
into rich, decision-grade JSON consumed by the Astro frontend.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import financial_reports as fr


DEFAULT_DB = Path(__file__).resolve().parent / "data" / "news.db"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "web" / "src" / "data"

US_TICKER_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")
TW_TICKER_RE = re.compile(r"^\d{4,6}$")
# Year-like numbers frequently appear in article titles ("Q1 2026"); drop them
# from ticker aggregations so they don't dominate the leaderboards.
YEAR_NOISE = {str(y) for y in range(1990, 2035)}

THEME_KEYWORDS = {
    "AI 算力": ["GPU", "AI chip", "AI 算力", "HBM", "AI server", "AI 伺服器", "GB200", "Blackwell", "H100", "H200"],
    "先進製程": ["3nm", "2nm", "先進製程", "advanced node", "Foundry", "晶圓代工", "EUV"],
    "記憶體": ["DRAM", "NAND", "HBM", "memory", "記憶體", "SK Hynix", "Micron", "美光", "南亞科", "華邦"],
    "電動車": ["EV", "electric vehicle", "電動車", "Tesla", "BYD", "Rivian", "Lucid", "車用"],
    "雲端 / SaaS": ["cloud", "雲端", "SaaS", "AWS", "Azure", "Google Cloud", "Oracle", "ServiceNow"],
    "美國政策": ["Fed", "CHIPS Act", "Trump", "tariff", "關稅", "Federal Reserve", "Powell"],
    "中國科技": ["China", "中國", "中芯", "SMIC", "華為", "Huawei", "BYD", "DeepSeek"],
    "半導體設備": ["ASML", "Applied Materials", "AMAT", "Lam Research", "Tokyo Electron", "KLA"],
    "資料中心": ["data center", "資料中心", "hyperscaler", "co-lo", "colocation", "Equinix"],
    "重大事件": ["acquisition", "merger", "M&A", "IPO", "spin-off", "split", "buyback", "回購"],
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        return ["NVDA", "TSM", "2330", "AAPL", "MSFT", "GOOGL", "META", "AMD", "AVGO", "2454"]
    try:
        import yaml

        loaded = yaml.safe_load(candidate.read_text(encoding="utf-8")) or []
        if isinstance(loaded, list):
            return [str(t).strip() for t in loaded if t]
        if isinstance(loaded, dict) and "tickers" in loaded:
            return [str(t).strip() for t in loaded["tickers"] if t]
    except Exception:
        pass
    return ["NVDA", "TSM", "2330", "AAPL", "MSFT", "GOOGL", "META", "AMD", "AVGO", "2454"]


def _parse_tickers(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [
                str(t).strip().upper()
                for t in parsed
                if t and str(t).strip() not in YEAR_NOISE
            ]
    except Exception:
        pass
    return []


def _parse_companies(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if t]
    except Exception:
        pass
    return []


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_count(conn: sqlite3.Connection, table: str, where: str = "1=1", params: tuple = ()) -> int:
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params)
        return int(cur.fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def _recent_news(conn: sqlite3.Connection, limit: int = 300) -> list[dict]:
    try:
        rows = conn.execute(
            """
            SELECT title, link, source, category, published, summary,
                   tickers_json, companies_json, event_type, publisher, author
            FROM articles
            ORDER BY published DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[dict] = []
    for row in rows:
        record = dict(row)
        record["tickers"] = _parse_tickers(record.pop("tickers_json", None))
        record["companies"] = _parse_companies(record.pop("companies_json", None))
        out.append(record)
    return out


def _articles_for_window(conn: sqlite3.Connection, since_iso: str, limit: int = 5000) -> list[dict]:
    try:
        rows = conn.execute(
            """
            SELECT title, source, category, published, tickers_json, event_type
            FROM articles
            WHERE published >= ?
            ORDER BY published DESC
            LIMIT ?
            """,
            (since_iso, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[dict] = []
    for row in rows:
        rec = dict(row)
        rec["tickers"] = _parse_tickers(rec.pop("tickers_json", None))
        out.append(rec)
    return out


def _ticker_mention_table(articles: Iterable[dict]) -> list[dict]:
    counter: Counter[str] = Counter()
    last_seen: dict[str, str] = {}
    for art in articles:
        published = art.get("published") or ""
        for ticker in art.get("tickers", []):
            counter[ticker] += 1
            if ticker not in last_seen or published > last_seen[ticker]:
                last_seen[ticker] = published
    return [
        {"ticker": t, "mentions": n, "last_seen": last_seen.get(t, "")[:10]}
        for t, n in counter.most_common(40)
    ]


def _news_velocity(articles: Iterable[dict], days: int = 14) -> dict:
    by_day_category: dict[str, Counter[str]] = defaultdict(Counter)
    by_day_total: Counter[str] = Counter()
    for art in articles:
        published = (art.get("published") or "")[:10]
        if not published:
            continue
        cat = art.get("category") or "（其他）"
        by_day_category[published][cat] += 1
        by_day_total[published] += 1
    days_sorted = sorted(by_day_total.keys())[-days:]
    return {
        "days": days_sorted,
        "totals": [by_day_total[d] for d in days_sorted],
        "by_category": {
            d: dict(by_day_category[d].most_common(8))
            for d in days_sorted
        },
    }


def _category_breakdown(articles: Iterable[dict]) -> list[dict]:
    counter: Counter[str] = Counter()
    for art in articles:
        cat = art.get("category") or "（其他）"
        counter[cat] += 1
    total = sum(counter.values()) or 1
    return [
        {"category": cat, "count": n, "pct": round(100 * n / total, 1)}
        for cat, n in counter.most_common(20)
    ]


def _top_sources(articles: Iterable[dict], top: int = 12) -> list[dict]:
    counter: Counter[str] = Counter()
    for art in articles:
        src = art.get("source") or "（unknown）"
        counter[src] += 1
    return [{"source": s, "count": n} for s, n in counter.most_common(top)]


def _event_clusters(articles: Iterable[dict]) -> dict[str, list[dict]]:
    clusters: dict[str, list[dict]] = defaultdict(list)
    for art in articles:
        et = art.get("event_type")
        if not et:
            continue
        clusters[et].append(art)
    out: dict[str, list[dict]] = {}
    for et, items in clusters.items():
        items.sort(key=lambda a: a.get("published") or "", reverse=True)
        out[et] = items[:15]
    return out


def _theme_extract(articles: Iterable[dict]) -> list[dict]:
    hits: dict[str, list[dict]] = {theme: [] for theme in THEME_KEYWORDS}
    for art in articles:
        title = (art.get("title") or "") + " " + (art.get("summary") or "")
        if not title:
            continue
        for theme, keywords in THEME_KEYWORDS.items():
            if any(kw.lower() in title.lower() for kw in keywords):
                hits[theme].append({
                    "title": art.get("title"),
                    "source": art.get("source"),
                    "published": art.get("published"),
                    "link": art.get("link"),
                    "tickers": art.get("tickers", []),
                })
    out: list[dict] = []
    for theme, items in hits.items():
        items.sort(key=lambda a: a.get("published") or "", reverse=True)
        out.append({"theme": theme, "count": len(items), "examples": items[:5]})
    out.sort(key=lambda x: x["count"], reverse=True)
    return out


def _momentum_screen(conn: sqlite3.Connection, today: datetime) -> list[dict]:
    last_7 = (today - timedelta(days=7)).isoformat()
    prev_7 = (today - timedelta(days=14)).isoformat()
    recent = _articles_for_window(conn, last_7, limit=10000)
    prior = _articles_for_window(conn, prev_7, limit=10000)
    prior_recent_cutoff = last_7
    prior_only = [a for a in prior if (a.get("published") or "") < prior_recent_cutoff]
    cur: Counter[str] = Counter()
    prv: Counter[str] = Counter()
    for a in recent:
        for t in a.get("tickers", []):
            cur[t] += 1
    for a in prior_only:
        for t in a.get("tickers", []):
            prv[t] += 1
    rows = []
    for ticker, n in cur.most_common(60):
        if n < 3:
            continue
        baseline = prv.get(ticker, 0)
        delta = n - baseline
        pct = (delta / baseline * 100) if baseline else 100.0
        rows.append({
            "ticker": ticker,
            "mentions_7d": n,
            "mentions_prior_7d": baseline,
            "delta": delta,
            "pct_change": round(pct, 1),
        })
    rows.sort(key=lambda r: r["delta"], reverse=True)
    return rows[:20]


def _market_overview_cache(repo_root: Path) -> dict:
    cache = repo_root / "data" / "market_overview_cache.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _financial_history(db_path: Path, ticker: str, market: str, limit: int = 20) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT fiscal_year, fiscal_period, period_end, filed_at, source_type, form_type,
                   revenue, monthly_revenue, net_income, operating_income, gross_profit,
                   eps_diluted, operating_cash_flow, capex, free_cash_flow, guidance_summary
            FROM financial_reports
            WHERE UPPER(ticker)=UPPER(?) AND market=?
            ORDER BY COALESCE(period_end, filed_at) DESC
            LIMIT ?
            """,
            (ticker, market, limit),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


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


def _per_stock(
    db_path: Path,
    market: str,
    ticker: str,
    recent_news_pool: list[dict] | None = None,
) -> dict:
    bundle = fr.get_financial_snapshot_bundle(db_path, market=market, ticker=ticker)
    try:
        transcripts = fr.get_recent_issuer_materials(db_path, market=market, ticker=ticker, limit=5) or []
    except Exception:
        transcripts = []
    try:
        insiders = fr.get_recent_insider_transactions(db_path, ticker=ticker, limit=20) or []
    except Exception:
        insiders = []
    try:
        shorts = fr.get_recent_short_interest_snapshots(db_path, ticker=ticker, limit=20) or []
    except Exception:
        shorts = []
    history = _financial_history(db_path, ticker, market, limit=20)
    if recent_news_pool is None:
        conn = _connect(db_path)
        try:
            recent_news_pool = _recent_news(conn, limit=2000)
        finally:
            conn.close()
    related = [n for n in recent_news_pool if ticker.upper() in (n.get("tickers") or [])][:40]
    co_mentions: Counter[str] = Counter()
    for n in related:
        for other in n.get("tickers") or []:
            if other.upper() != ticker.upper():
                co_mentions[other.upper()] += 1
    return {
        "ticker": ticker.upper(),
        "market": market,
        "bundle": _bundle_to_dict(bundle),
        "transcripts": transcripts,
        "insider": insiders,
        "short_interest": shorts,
        "holdings": [],
        "recent_news": related,
        "history": history,
        "co_mentions": [{"ticker": t, "count": c} for t, c in co_mentions.most_common(10)],
        "generated_at": _utcnow_iso(),
    }


def _infer_market(ticker: str) -> str:
    return "tw" if ticker.strip().isdigit() else "us"


def _coverage_map(db_path: Path) -> list[dict]:
    """Return list of all tickers we have any data on, with counts."""
    conn = _connect(db_path)
    articles: list = []
    fin: list = []
    try:
        try:
            articles = conn.execute(
                "SELECT tickers_json FROM articles WHERE tickers_json IS NOT NULL AND tickers_json!='[]' LIMIT 50000"
            ).fetchall()
        except sqlite3.OperationalError:
            articles = []
        try:
            fin = conn.execute(
                "SELECT ticker, market, COUNT(*) as n FROM financial_reports GROUP BY ticker, market"
            ).fetchall()
        except sqlite3.OperationalError:
            fin = []
    finally:
        conn.close()
    art_counter: Counter[str] = Counter()
    for row in articles:
        for t in _parse_tickers(row["tickers_json"]):
            art_counter[t] += 1
    coverage: dict[str, dict] = {}
    for row in fin:
        t = (row["ticker"] or "").upper()
        market = row["market"]
        coverage.setdefault(t, {"ticker": t, "market": market, "articles": 0, "reports": 0})
        coverage[t]["reports"] = row["n"]
    for ticker, n in art_counter.most_common(500):
        coverage.setdefault(ticker, {"ticker": ticker, "market": _infer_market(ticker), "articles": 0, "reports": 0})
        coverage[ticker]["articles"] = n
    return sorted(coverage.values(), key=lambda x: (x["reports"], x["articles"]), reverse=True)


def _events_calendar(articles: list[dict]) -> list[dict]:
    """Build event entries from earnings / capex / policy / filing tagged articles."""
    events = []
    for art in articles:
        et = art.get("event_type")
        if et not in {"earnings", "capex", "policy", "filing"}:
            continue
        events.append({
            "kind": et,
            "title": art.get("title"),
            "date": (art.get("published") or "")[:10],
            "source": art.get("source"),
            "link": art.get("link"),
            "tickers": art.get("tickers") or [],
            "category": art.get("category"),
        })
    events.sort(key=lambda e: e["date"], reverse=True)
    return events[:200]


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

    conn = _connect(db_path)
    try:
        total_articles = _safe_count(conn, "articles")
        total_reports = _safe_count(conn, "financial_reports")
        total_insider = _safe_count(conn, "insider_transactions")
        total_13f = _safe_count(conn, "holdings_snapshots")
        total_short = _safe_count(conn, "short_interest_snapshots")
        total_ir = _safe_count(conn, "issuer_materials")

        now = datetime.now(timezone.utc)
        since_30 = (now - timedelta(days=30)).isoformat()
        since_7 = (now - timedelta(days=7)).isoformat()
        since_24h = (now - timedelta(hours=24)).isoformat()

        window_30 = _articles_for_window(conn, since_30, limit=15000)
        window_7 = [a for a in window_30 if (a.get("published") or "") >= since_7]
        window_24h = [a for a in window_30 if (a.get("published") or "") >= since_24h]

        top_tickers_7d = _ticker_mention_table(window_7)
        top_tickers_30d = _ticker_mention_table(window_30)
        velocity = _news_velocity(window_30)
        categories = _category_breakdown(window_30)
        sources = _top_sources(window_30)
        clusters = _event_clusters(window_30)
        themes = _theme_extract(window_30)
        momentum = _momentum_screen(conn, now)

        recent_news_pool = _recent_news(conn, limit=2000)
        coverage = _coverage_map(db_path)
        events = _events_calendar(window_30)

        try:
            transcripts_rows = conn.execute(
                "SELECT * FROM issuer_materials WHERE material_type='transcript' "
                "ORDER BY fetched_at DESC LIMIT 5"
            ).fetchall()
            top_transcripts = [dict(r) for r in transcripts_rows]
        except sqlite3.OperationalError:
            top_transcripts = []
    finally:
        conn.close()

    artefacts: dict[str, Path] = {}

    overview = {
        "generated_at": _utcnow_iso(),
        "stats": {
            "articles_total": total_articles,
            "articles_24h": len(window_24h),
            "articles_7d": len(window_7),
            "articles_30d": len(window_30),
            "reports_total": total_reports,
            "insider_total": total_insider,
            "holdings_total": total_13f,
            "short_total": total_short,
            "ir_total": total_ir,
            "tickers_tracked": len(coverage),
        },
        "market_indices": _market_overview_cache(repo_root),
        "top_tickers_7d": top_tickers_7d,
        "top_tickers_30d": top_tickers_30d,
        "velocity": velocity,
        "categories": categories,
        "sources": sources,
        "themes": themes,
        "momentum": momentum,
        "event_clusters": clusters,
        "top_transcripts": top_transcripts,
        "top_insider_trades": [],
        "top_holdings_changes": [],
        "watchlist": tickers,
    }
    overview_path = output_dir / "overview.json"
    _write(overview_path, overview)
    artefacts["overview"] = overview_path

    news_path = output_dir / "news.json"
    _write(news_path, {
        "generated_at": _utcnow_iso(),
        "articles": recent_news_pool[:300],
        "categories": categories,
        "sources": sources,
    })
    artefacts["news"] = news_path

    events_path = output_dir / "events.json"
    _write(events_path, {"generated_at": _utcnow_iso(), "events": events})
    artefacts["events"] = events_path

    screens_path = output_dir / "screens.json"
    _write(screens_path, {
        "generated_at": _utcnow_iso(),
        "momentum": momentum,
        "themes": themes,
        "event_clusters": clusters,
        "top_tickers_7d": top_tickers_7d,
        "top_tickers_30d": top_tickers_30d,
    })
    artefacts["screens"] = screens_path

    coverage_path = output_dir / "coverage.json"
    _write(coverage_path, {"generated_at": _utcnow_iso(), "coverage": coverage[:300]})
    artefacts["coverage"] = coverage_path

    decisions_path = output_dir / "decisions.json"
    if not decisions_path.exists():
        _write(decisions_path, {"decisions": []})
    artefacts["decisions"] = decisions_path

    watchlist_path = output_dir / "watchlist.json"
    _write(watchlist_path, {"tickers": tickers})
    artefacts["watchlist"] = watchlist_path

    for ticker in tickers:
        market = _infer_market(ticker)
        path = output_dir / "stocks" / f"{ticker.upper()}.json"
        _write(path, _per_stock(db_path, market, ticker, recent_news_pool=recent_news_pool))
        artefacts[f"stock:{ticker}"] = path

    return artefacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--ticker", action="append", default=None)
    args = parser.parse_args(argv)
    artefacts = export_all(
        db_path=Path(args.db),
        output_dir=Path(args.output),
        tickers=args.ticker,
    )
    print(f"✅ dashboard export complete — {len(artefacts)} files")
    for k, v in sorted(artefacts.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
