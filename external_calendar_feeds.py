"""External calendar feeds (NASDAQ earnings, Forex Factory macro).

Wraps two free public sources into a list of MarketCalendarEvent-shaped dicts
(`kind`, `label`, `date`, `time`, `ticker`, `display_name`, `title`, `source`,
`link`, `importance`) ready for direct merge with the article-derived
calendar built in `_market_calendar()`.

Why these sources:
- The existing pipeline derives calendar events from RSS news titles, which
  only surfaces events for which someone has already published a news story.
  Forward weeks are typically empty.
- NASDAQ exposes a public JSON earnings calendar that lists scheduled
  earnings releases by date.
- Forex Factory publishes a weekly XML feed with high/medium-impact macro
  events (FOMC, CPI prints, ECB, BoJ, etc.) including release date and time.

TWSE conference (法說) data still flows through the RSS pipeline because
MOPS rejects programmatic POST requests; we improve coverage there by
extending the date extractor and adding more focused RSS sources elsewhere.
"""
from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Iterable
import xml.etree.ElementTree as ET

import requests

_LOGGER = logging.getLogger(__name__)
_HTTP_TIMEOUT = 12
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
}

NASDAQ_EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings"
FOREX_FACTORY_WEEKLY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

# Forex Factory countries we surface (anchor markets)
_MACRO_KEEP_COUNTRIES: set[str] = {"USD", "EUR", "JPY", "CNY", "GBP", "TWD"}
_MACRO_KEEP_IMPACT: set[str] = {"High", "Medium"}


def fetch_nasdaq_earnings(
    *,
    target_dates: Iterable[date],
    tickers_filter: set[str] | None = None,
    fetcher=None,
) -> list[dict]:
    """Pull NASDAQ earnings calendar across the given dates.

    Args:
        target_dates: dates to query (one HTTP call per date).
        tickers_filter: if provided, only retain rows whose symbol is in the set
            (uppercase). When None, retain everything.
        fetcher: optional callable accepting (url, params) -> dict, used by tests.

    Returns:
        list of MarketCalendarEvent-shaped dicts. Always returns something,
        possibly empty; transient failures are logged and swallowed so that
        the dashboard export run never aborts on calendar issues.
    """
    fetcher = fetcher or _default_json_fetcher
    out: list[dict] = []
    for target in target_dates:
        try:
            payload = fetcher(NASDAQ_EARNINGS_URL, {"date": target.isoformat()})
        except Exception as exc:  # pragma: no cover - network-dependent
            _LOGGER.warning(
                "NASDAQ earnings fetch failed for %s: %s", target.isoformat(), exc
            )
            continue
        rows = ((payload or {}).get("data") or {}).get("rows") or []
        for row in rows:
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            if tickers_filter is not None and symbol not in tickers_filter:
                continue
            time_label = _normalize_nasdaq_time(row.get("time"))
            company = (row.get("name") or symbol).strip()
            title_parts = [f"{symbol} {company}"]
            if time_label:
                title_parts.append(f"({time_label})")
            out.append(
                {
                    "kind": "us_event",
                    "label": "美股事件",
                    "date": target.isoformat(),
                    "time": time_label or None,
                    "ticker": symbol,
                    "display_name": company,
                    "title": " ".join(title_parts),
                    "source": "NASDAQ Earnings Calendar",
                    "link": (
                        f"https://www.nasdaq.com/market-activity/stocks/"
                        f"{symbol.lower()}/earnings"
                    ),
                    "importance": 75,
                }
            )
    return out


def fetch_forex_factory_macro(*, fetcher=None) -> list[dict]:
    """Pull this week's high/medium-impact macro events from Forex Factory.

    Args:
        fetcher: optional callable accepting (url) -> bytes for tests.
    """
    fetcher = fetcher or _default_bytes_fetcher
    try:
        raw = fetcher(FOREX_FACTORY_WEEKLY_URL)
    except Exception as exc:  # pragma: no cover - network-dependent
        _LOGGER.warning("Forex Factory weekly fetch failed: %s", exc)
        return []
    if not raw:
        return []
    try:
        text = raw.decode("windows-1252", errors="replace")
        root = ET.fromstring(text)
    except Exception as exc:
        _LOGGER.warning("Forex Factory XML parse failed: %s", exc)
        return []
    out: list[dict] = []
    for event in root.findall("event"):
        country = (event.findtext("country") or "").strip().upper()
        impact = (event.findtext("impact") or "").strip()
        title = (event.findtext("title") or "").strip()
        date_raw = (event.findtext("date") or "").strip()
        time_raw = (event.findtext("time") or "").strip()
        url = (event.findtext("url") or "").strip() or None
        if not country or not title:
            continue
        if country not in _MACRO_KEEP_COUNTRIES:
            continue
        if impact not in _MACRO_KEEP_IMPACT:
            continue
        iso_date = _parse_ff_date(date_raw)
        if not iso_date:
            continue
        out.append(
            {
                "kind": "macro",
                "label": "重要總經",
                "date": iso_date,
                "time": _normalize_ff_time(time_raw),
                "ticker": None,
                "display_name": None,
                "title": f"{country} · {title}",
                "source": "Forex Factory",
                "link": url,
                "importance": 95 if impact == "High" else 80,
            }
        )
    return out


def fetch_all_external_calendar_events(
    *,
    target_dates: Iterable[date],
    us_tickers_filter: set[str] | None = None,
) -> list[dict]:
    """Convenience: fetch NASDAQ earnings + Forex Factory macro in one call."""
    events: list[dict] = []
    events.extend(
        fetch_nasdaq_earnings(
            target_dates=target_dates, tickers_filter=us_tickers_filter
        )
    )
    events.extend(fetch_forex_factory_macro())
    return events


# ----- helpers -----

def _default_json_fetcher(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, headers=_HTTP_HEADERS, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _default_bytes_fetcher(url: str) -> bytes:
    resp = requests.get(url, headers=_HTTP_HEADERS, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def _normalize_nasdaq_time(raw: str | None) -> str:
    if not raw:
        return ""
    cleaned = raw.replace("time-", "").replace("-", " ").strip()
    mapping = {
        "pre market": "盤前",
        "after hours": "盤後",
        "after market close": "盤後",
        "amc": "盤後",
        "bmo": "盤前",
        "time not supplied": "",
        "not supplied": "",
    }
    return mapping.get(cleaned.lower(), cleaned)


def _normalize_ff_time(raw: str) -> str | None:
    cleaned = (raw or "").strip()
    if not cleaned or cleaned.lower() in {"all day", "tentative"}:
        return None
    return cleaned


def _parse_ff_date(raw: str) -> str | None:
    """Forex Factory dates are MM-DD-YYYY."""
    try:
        return datetime.strptime(raw, "%m-%d-%Y").date().isoformat()
    except ValueError:
        return None
