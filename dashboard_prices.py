"""Fetch daily prices for watchlist tickers from Yahoo Finance unofficial endpoint.

Outputs web/src/data/prices.json with returns, 52w hi/lo, and sparkline data.
No API key required. ~1y of daily OHLCV per ticker.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_OUTPUT = Path(__file__).resolve().parent / "web" / "src" / "data" / "prices.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


def _yf_symbol(ticker: str) -> str:
    """Map watchlist ticker to Yahoo Finance symbol (TW digits → .TW suffix)."""
    t = ticker.strip().upper()
    if t.isdigit():
        return f"{t}.TW"
    return t


YAHOO_HOSTS = ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]


def _fetch_chart(ticker: str, range_: str = "1y", interval: str = "1d") -> dict | None:
    sym = _yf_symbol(ticker)
    last_err: Exception | None = None
    for host in YAHOO_HOSTS:
        url = (
            f"https://{host}/v8/finance/chart/{quote(sym)}"
            f"?range={range_}&interval={interval}&includePrePost=false"
        )
        req = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with urlopen(req, timeout=10) as r:
                payload = json.loads(r.read().decode("utf-8"))
            break
        except Exception as e:
            last_err = e
            time.sleep(1.0)
            continue
    else:
        print(f"[warn] {ticker}: fetch failed — {last_err}", file=sys.stderr)
        return None
    chart = payload.get("chart") or {}
    if chart.get("error"):
        print(f"[warn] {ticker}: chart error — {chart['error']}", file=sys.stderr)
        return None
    result = (chart.get("result") or [None])[0]
    if not result:
        return None
    return result


def _compute_metrics(result: dict) -> dict:
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote = (indicators.get("quote") or [{}])[0]
    closes_raw = quote.get("close") or []
    # Filter out gaps
    paired = [
        (ts, float(c))
        for ts, c in zip(timestamps, closes_raw)
        if c is not None
    ]
    if not paired:
        return {}
    closes = [c for _, c in paired]
    dates = [datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") for ts, _ in paired]
    last = closes[-1]

    def return_pct(ago_idx: int) -> float | None:
        if ago_idx < 0 or ago_idx >= len(closes):
            return None
        base = closes[-(ago_idx + 1)]
        if base == 0:
            return None
        return round(((last - base) / base) * 100, 2)

    # Year-to-date: find first trading day with year == current year
    today = datetime.now(timezone.utc)
    ytd_base = None
    for d, c in zip(dates, closes):
        if d.startswith(f"{today.year}-"):
            ytd_base = c
            break
    ytd_pct = None
    if ytd_base and ytd_base != 0:
        ytd_pct = round(((last - ytd_base) / ytd_base) * 100, 2)

    hi52 = max(closes)
    lo52 = min(closes)
    from_hi = round(((last - hi52) / hi52) * 100, 2) if hi52 else None
    from_lo = round(((last - lo52) / lo52) * 100, 2) if lo52 else None

    # Sparkline subsample: every 5th close to keep payload small (~50 points)
    step = max(1, len(closes) // 60)
    spark = closes[::step]

    meta = result.get("meta") or {}
    currency = meta.get("currency") or ""
    exch = meta.get("exchangeName") or ""
    return {
        "last": round(last, 4),
        "currency": currency,
        "exchange": exch,
        "as_of": dates[-1],
        "ret_1d": return_pct(1),
        "ret_5d": return_pct(5),
        "ret_1m": return_pct(21),
        "ret_3m": return_pct(63),
        "ret_6m": return_pct(126),
        "ret_ytd": ytd_pct,
        "ret_1y": return_pct(len(closes) - 1) if len(closes) > 1 else None,
        "high_52w": round(hi52, 4),
        "low_52w": round(lo52, 4),
        "from_52w_high_pct": from_hi,
        "from_52w_low_pct": from_lo,
        "spark": [round(v, 4) for v in spark],
        "spark_dates": dates[::step],
    }


def fetch_all(tickers: list[str], output: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for ticker in tickers:
        result = _fetch_chart(ticker)
        if not result:
            out[ticker.upper()] = {"error": "fetch_failed"}
            continue
        metrics = _compute_metrics(result)
        if not metrics:
            out[ticker.upper()] = {"error": "no_data"}
            continue
        metrics["ticker"] = ticker.upper()
        metrics["yahoo_symbol"] = _yf_symbol(ticker)
        out[ticker.upper()] = metrics
        time.sleep(1.2)  # be polite + avoid rate limit

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prices": out,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _load_watchlist() -> list[str]:
    repo_root = Path(__file__).resolve().parent
    candidate = repo_root / "data" / "watchlist.yaml"
    if candidate.exists():
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--ticker", action="append", default=None)
    args = parser.parse_args(argv)
    tickers = args.ticker or _load_watchlist()
    result = fetch_all(tickers, Path(args.output))
    ok = sum(1 for v in result.values() if "error" not in v)
    print(f"✅ prices fetched — {ok}/{len(tickers)} OK")
    for t, v in result.items():
        if "error" in v:
            print(f"  ✗ {t}: {v['error']}")
        else:
            print(f"  ✓ {t}: {v.get('last')} {v.get('currency')} · 1d {v.get('ret_1d')}% · 1m {v.get('ret_1m')}% · 3m {v.get('ret_3m')}% · ytd {v.get('ret_ytd')}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
