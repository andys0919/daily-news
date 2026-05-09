"""IR materials ingest — earnings transcripts and SEC 8-K filing text."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
    *,
    _db_path: Any | None = None,
    _persist: bool = True,
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
    if _persist and results:
        try:
            from financial_reports import save_issuer_material, DB_PATH
            target = _db_path or DB_PATH
            for item in results:
                save_issuer_material(
                    target,
                    {
                        "market": item.market,
                        "ticker": item.ticker,
                        "material_type": item.material_type,
                        "title": item.title,
                        "body_text": item.body_text,
                        "source_url": item.source_url,
                        "fiscal_year": item.fiscal_year,
                        "fiscal_period": item.fiscal_period,
                        "fetched_at": item.fetched_at,
                    },
                )
        except Exception:
            pass
    return results
