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
