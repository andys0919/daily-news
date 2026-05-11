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

    news_path = output_dir / "news.json"
    _write(news_path, {"articles": _recent_news(db_path, limit=300)})
    artefacts["news"] = news_path

    events_path = output_dir / "events.json"
    _write(events_path, {"events": []})
    artefacts["events"] = events_path

    decisions_path = output_dir / "decisions.json"
    _write(decisions_path, {"decisions": []})
    artefacts["decisions"] = decisions_path

    watchlist_path = output_dir / "watchlist.json"
    _write(watchlist_path, {"tickers": tickers})
    artefacts["watchlist"] = watchlist_path

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
