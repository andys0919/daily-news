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

# High-precision guidance phrases: must appear as 2+ word chunks tied to
# financials so political/macro headlines don't leak into the leaderboard.
GUIDANCE_UP_PHRASES = [
    "raises guidance", "raised guidance", "raise guidance", "raising guidance",
    "lifts guidance", "lifted guidance", "boosts guidance", "boosted guidance",
    "raises forecast", "raised forecast", "raises outlook", "lifts outlook",
    "lifts target", "raises target", "raised target", "raising target",
    "upgrade to buy", "upgrade to overweight", "outperform rating",
    "upgrades stock", "upgraded stock", "raises rating",
    "beats estimates", "beat estimates", "beats expectations", "beat expectations",
    "exceeds estimates", "exceeded estimates", "above estimates",
    "beats eps", "beat eps", "tops estimates", "topped estimates",
    "stronger than expected", "better than expected",
    "上修財測", "上修目標價", "上修評等", "上修預估", "上修獲利", "上看",
    "目標價上調", "獲利上修", "財測上修", "上修全年", "獲利優於預期",
    "毛利率上修", "outperform 評等",
]
GUIDANCE_DOWN_PHRASES = [
    "cuts guidance", "cut guidance", "cutting guidance", "lowers guidance",
    "lowered guidance", "slashes guidance", "trimmed guidance",
    "cuts forecast", "lowers forecast", "lowered forecast",
    "cuts outlook", "lowers outlook", "trimmed outlook",
    "cuts target", "lowers target", "lowered target", "slashes target",
    "downgrade to sell", "downgrade to underweight", "underperform rating",
    "downgrades stock", "downgraded stock", "lowers rating",
    "misses estimates", "missed estimates", "miss estimates",
    "misses expectations", "missed expectations",
    "misses eps", "missed eps", "missed by $", "missed by 0",
    "below estimates", "fell short of",
    "weaker than expected", "worse than expected", "disappointing",
    "guidance cut", "profit warning", "warns on", "warned of",
    "plummets", "plummeted", "tumbles", "tumbled",
    "下修財測", "下修目標價", "下修評等", "下修預估", "下修獲利",
    "目標價下調", "獲利下修", "財測下修", "下修全年", "獲利不如預期",
    "毛利率下修", "砍單", "砍價", "下砍", "獲利衰退",
]
GUIDANCE_NEUTRAL_PHRASES = [
    "reaffirms guidance", "reaffirmed guidance", "maintains guidance",
    "maintained guidance", "in line with estimates", "in-line",
    "as expected", "meets estimates", "met estimates",
    "維持財測", "維持目標價", "符合預期", "符合預估",
]
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


def _meaningful_news_for_ticker(db_path: Path, ticker: str, limit: int = 40) -> list[dict]:
    """Pull only news with investment substance for a ticker.

    Substance = (a) event_type is set, OR (b) title contains a guidance phrase.
    Plain ticker-mention noise is dropped.
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT title, link, source, category, published, summary, body_text,
                   tickers_json, companies_json, event_type
            FROM articles
            WHERE tickers_json LIKE ?
            ORDER BY published DESC
            LIMIT 400
            """,
            (f'%"{ticker}"%',),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    NOISY_SOURCE_SUBSTR = (
        "arxiv", "lobsters", "servethehome", "github trending",
        "x @googledeepmind", "x @openai", "reddit r/", "hackernews",
        "semiconductor engineering",
    )
    NOISY_TITLE_PATTERNS = (
        "arxiv:",
        "/ (arxiv",
        " (arxiv",
        "[paper]",
        "open-source github",
        "github.com/",
        "best gaming",
        "best laptop",
        "best deal",
        "early black friday",
        "amazon.com:",
    )
    out: list[dict] = []
    seen_titles: set[str] = set()
    for row in rows:
        rec = dict(row)
        t_list = _parse_tickers(rec.pop("tickers_json", None))
        if ticker.upper() not in t_list:
            continue
        title = (rec["title"] or "").strip()
        if not title:
            continue
        src = (rec.get("source") or "").strip().lower()
        if any(s in src for s in NOISY_SOURCE_SUBSTR):
            continue
        lower_title = title.lower()
        if any(p in lower_title for p in NOISY_TITLE_PATTERNS):
            continue
        norm = lower_title.split(" - ")[0].strip()
        if norm in seen_titles:
            continue
        seen_titles.add(norm)
        event = (rec.get("event_type") or "").lower()
        has_specific_event = event in {"earnings", "capex", "policy", "filing"}
        guidance_dir = _classify_guidance(title)
        if not has_specific_event and not guidance_dir:
            continue
        rec["tickers"] = t_list
        rec["companies"] = _parse_companies(rec.pop("companies_json", None))
        rec["guidance_direction"] = guidance_dir
        rec["body_text"] = (rec.get("body_text") or "")[:400]
        out.append(rec)
        if len(out) >= limit:
            break
    return out


_NOISY_SRC_SUBSTR = (
    "arxiv", "lobsters", "servethehome", "github trending",
    "x @googledeepmind", "x @openai", "reddit r/", "hackernews",
    "semiconductor engineering",
)


def _finance_news_for_ticker(db_path: Path, ticker: str, limit: int = 25) -> list[dict]:
    """Recent news (any tag) for ticker, but filtered to drop dev/academic sources."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT title, link, source, category, published, summary,
                   tickers_json, event_type
            FROM articles
            WHERE tickers_json LIKE ?
            ORDER BY published DESC
            LIMIT 200
            """,
            (f'%"{ticker}"%',),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        rec = dict(r)
        src = (rec.get("source") or "").lower()
        if any(s in src for s in _NOISY_SRC_SUBSTR):
            continue
        title = (rec.get("title") or "").strip()
        if not title:
            continue
        norm = title.lower().split(" - ")[0]
        if norm in seen:
            continue
        seen.add(norm)
        rec["tickers"] = _parse_tickers(rec.pop("tickers_json", None))
        out.append(rec)
        if len(out) >= limit:
            break
    return out


def _per_stock(
    db_path: Path,
    market: str,
    ticker: str,
    recent_news_pool: list[dict] | None = None,
) -> dict:
    bundle = None
    try:
        bundle = fr.get_financial_snapshot_bundle(db_path, market=market, ticker=ticker)
    except Exception:
        bundle = None
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
    # Two-tier news lists:
    #   meaningful_news: strict (earnings/capex/policy/filing OR guidance phrase)
    #   recent_news: finance-source-filtered general news (drops arxiv/dev/etc)
    related = _meaningful_news_for_ticker(db_path, ticker, limit=40)
    general = _finance_news_for_ticker(db_path, ticker, limit=30)
    # Drop articles already in `related` from general to avoid dupes
    related_links = {n.get("link") for n in related if n.get("link")}
    general = [n for n in general if n.get("link") not in related_links]
    co_mentions: Counter[str] = Counter()
    for n in related:
        for other in n.get("tickers") or []:
            if other.upper() != ticker.upper():
                co_mentions[other.upper()] += 1
    latest_fund: dict | None = None
    if history:
        f_sum = _fundamentals_summary(db_path, [ticker])
        if f_sum:
            latest_fund = f_sum[0]
            latest_fund["health"] = _classify_health(latest_fund.get("latest"))
    return {
        "ticker": ticker.upper(),
        "market": market,
        "bundle": _bundle_to_dict(bundle),
        "transcripts": transcripts,
        "insider": insiders,
        "short_interest": shorts,
        "holdings": [],
        "recent_news": related,
        "general_news": general,
        "history": history,
        "fundamentals": latest_fund,
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


def _phrase_match(phrase: str, lower_text: str) -> bool:
    """Word-boundary aware match — avoids 'tumbles' ⊂ 'stumbles' false hits.

    For multi-word phrases or those with non-ASCII / digits we use plain
    substring; for single English words we require word boundaries.
    """
    p = phrase.lower()
    if " " in p or any(ord(c) > 127 for c in p) or any(ch.isdigit() for ch in p):
        return p in lower_text
    return bool(re.search(rf"\b{re.escape(p)}\b", lower_text))


def _classify_guidance(text: str) -> str | None:
    """High-precision classifier: requires multi-word guidance phrases.

    Returns 'up' | 'down' | 'mixed' | 'neutral' | None.
    """
    if not text:
        return None
    lower = text.lower()
    up = sum(1 for p in GUIDANCE_UP_PHRASES if _phrase_match(p, lower))
    down = sum(1 for p in GUIDANCE_DOWN_PHRASES if _phrase_match(p, lower))
    neu = sum(1 for p in GUIDANCE_NEUTRAL_PHRASES if _phrase_match(p, lower))
    if up and not down:
        return "up"
    if down and not up:
        return "down"
    if up and down:
        return "mixed"
    if neu:
        return "neutral"
    return None


def _guidance_feed(
    db_path: Path,
    since_iso: str,
    limit: int = 200,
) -> list[dict]:
    """Pull articles whose title/summary mentions guidance keywords."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT title, link, source, category, published, summary,
                   body_text, tickers_json, companies_json, event_type
            FROM articles
            WHERE published >= ?
            ORDER BY published DESC
            LIMIT 5000
            """,
            (since_iso,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    out: list[dict] = []
    seen_titles: set[str] = set()
    for row in rows:
        title = (row["title"] or "").strip()
        summary = row["summary"] or ""
        body = row["body_text"] or ""
        if not title:
            continue
        norm_title = title.lower().split(" - ")[0].strip()
        if norm_title in seen_titles:
            continue
        seen_titles.add(norm_title)
        direction = _classify_guidance(title)
        if not direction:
            continue
        # Drop obvious tech-product reviews and gaming/lifestyle content that
        # accidentally trigger guidance phrases ("Star Wars Day", "gaming PC").
        lower = title.lower()
        if any(noise in lower for noise in (
            "star wars", "gaming pc", "may the 4th", "may the fourth",
            "best deals", "best gaming", "best laptop", "best headphone",
        )):
            continue
        excerpt = summary.strip() or body[:240].strip()
        out.append({
            "title": title,
            "link": row["link"],
            "source": row["source"],
            "category": row["category"],
            "published": row["published"],
            "direction": direction,
            "excerpt": excerpt,
            "tickers": _parse_tickers(row["tickers_json"]),
            "companies": _parse_companies(row["companies_json"]),
            "event_type": row["event_type"],
        })
        if len(out) >= limit:
            break
    return out


def _us_filing_excerpts(db_path: Path, limit: int = 30) -> list[dict]:
    """Surface raw forward-looking-statement text from US SEC filings."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT ticker, company_name, fiscal_year, fiscal_period, form_type,
                   filed_at, period_end, filing_excerpt, guidance_summary
            FROM financial_reports
            WHERE market='us' AND filing_excerpt IS NOT NULL
              AND LENGTH(filing_excerpt) > 80
            ORDER BY filed_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        ticker = (r["ticker"] or "").upper()
        if ticker in seen:
            continue
        seen.add(ticker)
        out.append({
            "ticker": ticker,
            "company_name": r["company_name"],
            "fiscal_year": r["fiscal_year"],
            "fiscal_period": r["fiscal_period"],
            "form_type": r["form_type"],
            "filed_at": r["filed_at"],
            "period_end": r["period_end"],
            "excerpt": (r["filing_excerpt"] or "").strip()[:600],
            "guidance_summary": (r["guidance_summary"] or "").strip()[:300],
        })
    return out


def _fundamentals_summary(db_path: Path, tickers: list[str]) -> list[dict]:
    """Compute YoY/QoQ revenue, EPS, margin trends per watchlist ticker.

    Dedupes the noisy TWSE rows (same period repeated with different filed_at)
    by taking MAX(metric) within each (ticker, fiscal_year, fiscal_period).
    """
    conn = _connect(db_path)
    out: list[dict] = []
    try:
        for ticker in tickers:
            market = _infer_market(ticker)
            try:
                rows = conn.execute(
                    """
                    SELECT fiscal_year, fiscal_period,
                           MAX(revenue) AS revenue,
                           MAX(gross_profit) AS gross_profit,
                           MAX(operating_income) AS operating_income,
                           MAX(net_income) AS net_income,
                           MAX(eps_diluted) AS eps_diluted,
                           MAX(free_cash_flow) AS fcf,
                           MAX(operating_cash_flow) AS ocf,
                           MAX(capex) AS capex,
                           MAX(company_name) AS company_name
                    FROM financial_reports
                    WHERE UPPER(ticker)=UPPER(?) AND market=?
                      AND fiscal_period IN ('Q1','Q2','Q3','Q4','FY')
                    GROUP BY fiscal_year, fiscal_period
                    ORDER BY fiscal_year DESC,
                             CASE fiscal_period
                                WHEN 'Q4' THEN 4 WHEN 'Q3' THEN 3
                                WHEN 'Q2' THEN 2 WHEN 'Q1' THEN 1
                                WHEN 'FY' THEN 5 ELSE 0 END DESC
                    LIMIT 12
                    """,
                    (ticker, market),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            periods = [dict(r) for r in rows]
            if not periods:
                out.append({"ticker": ticker.upper(), "market": market, "periods": []})
                continue
            latest = periods[0]
            company_name = latest.get("company_name")

            def find_prev_yoy(idx: int) -> dict | None:
                """Find same fiscal_period one year earlier."""
                target_period = periods[idx]["fiscal_period"]
                target_year = periods[idx]["fiscal_year"]
                for p in periods[idx + 1:]:
                    if p["fiscal_period"] == target_period and int(p["fiscal_year"]) == int(target_year) - 1:
                        return p
                return None

            def safe_div(a, b):
                try:
                    if a is None or b is None or float(b) == 0:
                        return None
                    return float(a) / float(b)
                except Exception:
                    return None

            def yoy(curr_val, prev_val):
                if curr_val is None or prev_val is None:
                    return None
                try:
                    if float(prev_val) == 0:
                        return None
                    return (float(curr_val) - float(prev_val)) / abs(float(prev_val)) * 100
                except Exception:
                    return None

            prev_yoy = find_prev_yoy(0)
            prev_q = periods[1] if len(periods) > 1 else None
            metrics = {
                "fiscal_year": latest["fiscal_year"],
                "fiscal_period": latest["fiscal_period"],
                "revenue": latest["revenue"],
                "gross_profit": latest["gross_profit"],
                "operating_income": latest["operating_income"],
                "net_income": latest["net_income"],
                "eps": latest["eps_diluted"],
                "fcf": latest["fcf"],
                "ocf": latest["ocf"],
                "capex": latest["capex"],
                "gross_margin": safe_div(latest["gross_profit"], latest["revenue"]),
                "op_margin": safe_div(latest["operating_income"], latest["revenue"]),
                "net_margin": safe_div(latest["net_income"], latest["revenue"]),
                "fcf_margin": safe_div(latest["fcf"], latest["revenue"]),
                "capex_intensity": safe_div(latest["capex"], latest["revenue"]),
                "rev_yoy": yoy(latest["revenue"], prev_yoy["revenue"] if prev_yoy else None),
                "eps_yoy": yoy(latest["eps_diluted"], prev_yoy["eps_diluted"] if prev_yoy else None),
                "op_income_yoy": yoy(latest["operating_income"], prev_yoy["operating_income"] if prev_yoy else None),
                "rev_qoq": yoy(latest["revenue"], prev_q["revenue"] if prev_q else None),
            }
            # Acceleration: compare current YoY vs prior YoY
            if prev_q:
                prev_q_yoy_pair = find_prev_yoy(1)
                metrics["prior_rev_yoy"] = yoy(
                    prev_q["revenue"],
                    prev_q_yoy_pair["revenue"] if prev_q_yoy_pair else None,
                )
            else:
                metrics["prior_rev_yoy"] = None
            if metrics["rev_yoy"] is not None and metrics["prior_rev_yoy"] is not None:
                metrics["rev_yoy_accel"] = metrics["rev_yoy"] - metrics["prior_rev_yoy"]
            else:
                metrics["rev_yoy_accel"] = None
            out.append({
                "ticker": ticker.upper(),
                "market": market,
                "company_name": company_name,
                "latest": metrics,
                "history": periods[:8],
            })
    finally:
        conn.close()
    return out


def _classify_health(latest: dict | None) -> dict:
    """Plain-language tier + verdict for retail readers.

    Returns dict with: tier (strong/steady/watch/warn/unknown), label, summary.
    Thresholds picked to roughly match large-cap tech/semis norms; not exact
    industry-tuned, but enough to anchor a retail-level "good / OK / bad".
    """
    if not latest:
        return {"tier": "unknown", "label": "資料不足", "summary": "尚未建檔最新一季財報", "icon": "⚫"}

    rev_yoy = latest.get("rev_yoy")
    eps_yoy = latest.get("eps_yoy")
    op_margin = latest.get("op_margin")
    fcf_margin = latest.get("fcf_margin")
    accel = latest.get("rev_yoy_accel")

    bits: list[str] = []
    score = 0  # +ve = healthier

    if rev_yoy is not None:
        if rev_yoy >= 20:
            bits.append(f"營收年增 {rev_yoy:+.0f}% 強勁")
            score += 2
        elif rev_yoy >= 10:
            bits.append(f"營收年增 {rev_yoy:+.0f}% 健康")
            score += 1
        elif rev_yoy >= 0:
            bits.append(f"營收年增 {rev_yoy:+.0f}% 平平")
        elif rev_yoy >= -10:
            bits.append(f"營收年減 {rev_yoy:.0f}% 走弱")
            score -= 1
        else:
            bits.append(f"營收年減 {rev_yoy:.0f}% 大跌")
            score -= 2

    if op_margin is not None:
        op = op_margin * 100
        if op >= 30:
            bits.append(f"營益率 {op:.0f}% 業界頂尖")
            score += 2
        elif op >= 15:
            bits.append(f"營益率 {op:.0f}% 健康")
            score += 1
        elif op >= 5:
            bits.append(f"營益率 {op:.0f}% 偏低")
        else:
            bits.append(f"營益率 {op:.0f}% 偏弱")
            score -= 1

    if fcf_margin is not None:
        f = fcf_margin * 100
        if f >= 20:
            bits.append(f"FCF margin {f:.0f}% 現金力強")
            score += 1
        elif f < 0:
            bits.append(f"FCF margin {f:.0f}% 燒錢中")
            score -= 1

    if accel is not None:
        if accel >= 5:
            bits.append("成長加速中")
            score += 1
        elif accel <= -5:
            bits.append("成長動能放緩")
            score -= 1

    if score >= 4:
        tier, label, icon = "strong", "強勢", "🟢"
    elif score >= 2:
        tier, label, icon = "steady", "穩健", "🔵"
    elif score >= -1:
        tier, label, icon = "watch", "觀望", "🟡"
    else:
        tier, label, icon = "warn", "警示", "🔴"

    summary = "・".join(bits[:3]) if bits else "資料不足"
    return {"tier": tier, "label": label, "summary": summary, "icon": icon, "score": score}


def _per_ticker_guidance(guidance_feed: list[dict]) -> dict[str, dict]:
    """Aggregate guidance counts per ticker for retail-friendly net score."""
    out: dict[str, dict] = defaultdict(lambda: {"up": 0, "down": 0, "neutral": 0, "mixed": 0, "items": []})
    for g in guidance_feed:
        for t in g.get("tickers") or []:
            out[t][g["direction"]] = out[t].get(g["direction"], 0) + 1
            out[t]["items"].append({
                "title": g["title"],
                "direction": g["direction"],
                "published": g["published"],
                "source": g["source"],
                "link": g["link"],
            })
    return {t: {**v, "net": v["up"] - v["down"]} for t, v in out.items()}


def _today_takeaways(
    guidance_up: list[dict],
    guidance_down: list[dict],
    fundamentals: list[dict],
    health_by_ticker: dict[str, dict],
) -> list[dict]:
    """Generate 3 plain-language takeaways for hero."""
    out: list[dict] = []
    up_n, down_n = len(guidance_up), len(guidance_down)
    if up_n + down_n > 0:
        if up_n >= down_n * 2:
            mood = "市場上修聲音明顯多過下修"
            kind = "positive"
        elif down_n >= up_n * 2:
            mood = "市場下修聲音明顯多過上修"
            kind = "negative"
        else:
            mood = "市場上修與下修聲音相當"
            kind = "neutral"
        out.append({
            "kind": kind,
            "headline": f"{mood} ({up_n} 上修 / {down_n} 下修)",
            "detail": "近 30 天分析師目標價、財測、EPS beat/miss 統計。",
        })

    strong = [f for f in fundamentals if (health_by_ticker.get(f["ticker"], {}) or {}).get("tier") == "strong"]
    warn = [f for f in fundamentals if (health_by_ticker.get(f["ticker"], {}) or {}).get("tier") == "warn"]
    if strong:
        names = "、".join(f["ticker"] for f in strong[:4])
        out.append({
            "kind": "positive",
            "headline": f"Watchlist 中 {names} 基本面強勢",
            "detail": "營收年增強、營益率業界頂尖。",
        })
    if warn:
        names = "、".join(f["ticker"] for f in warn[:4])
        out.append({
            "kind": "negative",
            "headline": f"Watchlist 中 {names} 出現警訊",
            "detail": "營收衰退或營益率偏弱，需注意。",
        })

    big_movers = [g for g in (guidance_down or []) if any(
        kw in (g.get("title") or "").lower()
        for kw in ("plummet", "plunges", "slashes", "下修", "崩跌")
    )]
    if big_movers:
        sample = big_movers[0]["title"][:60]
        out.append({
            "kind": "negative",
            "headline": "本週重大下修事件",
            "detail": f"例：{sample}…",
        })

    big_up = [g for g in (guidance_up or []) if any(
        kw in (g.get("title") or "").lower()
        for kw in ("surge", "soar", "上看", "飆", "raises guidance", "lifts target")
    )]
    if big_up and len(out) < 3:
        sample = big_up[0]["title"][:60]
        out.append({
            "kind": "positive",
            "headline": "本週重大上修事件",
            "detail": f"例：{sample}…",
        })

    return out[:3]


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

    guidance_feed = _guidance_feed(db_path, since_30, limit=200)
    filing_excerpts = _us_filing_excerpts(db_path, limit=30)
    fundamentals = _fundamentals_summary(db_path, tickers)

    guidance_up = [g for g in guidance_feed if g["direction"] == "up"]
    guidance_down = [g for g in guidance_feed if g["direction"] == "down"]
    guidance_by_ticker: dict[str, list[dict]] = defaultdict(list)
    for g in guidance_feed:
        for t in g.get("tickers") or []:
            guidance_by_ticker[t].append(g)

    health_by_ticker = {f["ticker"]: _classify_health(f.get("latest")) for f in fundamentals}
    per_ticker_guidance = _per_ticker_guidance(guidance_feed)
    takeaways = _today_takeaways(guidance_up, guidance_down, fundamentals, health_by_ticker)

    # Attach health + guidance count to each fundamentals entry for the UI
    for f in fundamentals:
        f["health"] = health_by_ticker.get(f["ticker"], {"tier": "unknown", "label": "—", "summary": "", "icon": "⚫"})
        pg = per_ticker_guidance.get(f["ticker"], {"up": 0, "down": 0, "net": 0, "items": []})
        f["guidance"] = {"up": pg["up"], "down": pg["down"], "net": pg["net"]}

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
            "guidance_30d": len(guidance_feed),
            "guidance_up_30d": len(guidance_up),
            "guidance_down_30d": len(guidance_down),
        },
        "watchlist": tickers,
        "fundamentals": fundamentals,
        "takeaways": takeaways,
        "guidance_up": guidance_up[:25],
        "guidance_down": guidance_down[:25],
        "guidance_recent": guidance_feed[:40],
        "filing_excerpts": filing_excerpts[:10],
        "event_clusters": clusters,
        "top_transcripts": top_transcripts,
        # Secondary/exploration metrics (kept for /explore noise view)
        "market_indices": _market_overview_cache(repo_root),
        "top_tickers_7d": top_tickers_7d,
        "top_tickers_30d": top_tickers_30d,
        "velocity": velocity,
        "categories": categories,
        "sources": sources,
        "themes": themes,
        "momentum": momentum,
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

    guidance_path = output_dir / "guidance.json"
    _write(guidance_path, {
        "generated_at": _utcnow_iso(),
        "all": guidance_feed,
        "up": guidance_up,
        "down": guidance_down,
        "by_ticker": {t: items[:10] for t, items in guidance_by_ticker.items() if len(items) >= 1},
        "filing_excerpts": filing_excerpts,
    })
    artefacts["guidance"] = guidance_path

    fundamentals_path = output_dir / "fundamentals.json"
    _write(fundamentals_path, {
        "generated_at": _utcnow_iso(),
        "tickers": fundamentals,
    })
    artefacts["fundamentals"] = fundamentals_path

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

    # Build a wider universe of tickers with enough data to merit a page.
    universe: dict[str, dict] = {}
    for c in coverage:
        t = c["ticker"]
        if not t:
            continue
        # Filter: keep if has reports OR >= 3 articles OR is in watchlist
        if c.get("reports", 0) > 0 or c.get("articles", 0) >= 3 or t in {x.upper() for x in tickers}:
            universe[t] = c

    # Always include watchlist
    for t in tickers:
        u = t.upper()
        if u not in universe:
            universe[u] = {"ticker": u, "market": _infer_market(t), "articles": 0, "reports": 0}

    # Generate per-ticker JSON for the full universe
    for ticker, meta in universe.items():
        market = meta.get("market") or _infer_market(ticker)
        path = output_dir / "stocks" / f"{ticker.upper()}.json"
        _write(path, _per_stock(db_path, market, ticker, recent_news_pool=recent_news_pool))
        artefacts[f"stock:{ticker}"] = path

    # Lookup company names from financial_reports
    name_map: dict[str, str] = {}
    try:
        conn2 = _connect(db_path)
        try:
            for row in conn2.execute(
                "SELECT ticker, company_name FROM financial_reports WHERE company_name IS NOT NULL GROUP BY ticker"
            ).fetchall():
                if row["ticker"] and row["company_name"]:
                    name_map[row["ticker"].upper()] = row["company_name"]
        finally:
            conn2.close()
    except Exception:
        pass

    # Search index — articles-first ranking (newsworthy beats raw-reports count)
    search_index = sorted(
        [
            {
                "ticker": t,
                "name": name_map.get(t, ""),
                "market": meta.get("market") or _infer_market(t),
                "articles": meta.get("articles", 0),
                "reports": meta.get("reports", 0),
                "label": f"{t} ({'TW' if (meta.get('market') == 'tw' or t.isdigit()) else 'US'})",
            }
            for t, meta in universe.items()
        ],
        key=lambda x: (
            -1 if x["articles"] == 0 else 0,  # has-articles first
            x["articles"] * 3 + x["reports"],
        ),
        reverse=True,
    )
    search_path = output_dir / "tickers.json"
    _write(search_path, {"generated_at": _utcnow_iso(), "tickers": search_index})
    artefacts["tickers"] = search_path

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
