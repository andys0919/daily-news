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
