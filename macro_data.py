"""Macro-level aggregations: hyperscaler capex, macro release signals."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


HYPERSCALERS = ("MSFT", "GOOG", "AMZN", "META")


@dataclass
class CapexAggregate:
    period_end: str
    tickers_included: list[str]
    total_usd: float
    fetched_at: datetime


@dataclass
class MacroRelease:
    metric: str
    value: float
    unit: str
    article_title: str
    fetched_at: datetime


_DEFAULT_DB = Path(__file__).resolve().parent / "data" / "news.db"


def aggregate_hyperscaler_capex(
    *,
    _db_path: Path | None = None,
) -> CapexAggregate:
    path = Path(_db_path) if _db_path is not None else _DEFAULT_DB
    if not path.exists():
        return CapexAggregate(
            period_end="",
            tickers_included=[],
            total_usd=0.0,
            fetched_at=datetime.now(timezone.utc),
        )
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            f"""
            SELECT ticker, period_end, capex
            FROM financial_reports
            WHERE ticker IN ({",".join("?" for _ in HYPERSCALERS)})
              AND capex IS NOT NULL
            ORDER BY period_end DESC
            """,
            HYPERSCALERS,
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return CapexAggregate(
            period_end="",
            tickers_included=[],
            total_usd=0.0,
            fetched_at=datetime.now(timezone.utc),
        )
    latest_period = rows[0][1]
    tickers: list[str] = []
    total = 0.0
    for ticker, period_end, capex in rows:
        if period_end != latest_period:
            continue
        if ticker in tickers:
            continue
        tickers.append(ticker)
        try:
            total += float(capex or 0)
        except (TypeError, ValueError):
            continue
    return CapexAggregate(
        period_end=latest_period,
        tickers_included=tickers,
        total_usd=total,
        fetched_at=datetime.now(timezone.utc),
    )


_MACRO_PATTERNS = [
    ("CPI", re.compile(r"\bCPI[^\d]{0,40}?(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)),
    ("PPI", re.compile(r"\bPPI[^\d]{0,40}?(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)),
    ("PCE", re.compile(r"\bPCE[^\d]{0,40}?(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)),
    (
        "unemployment",
        re.compile(r"\bunemployment[^\d]{0,40}?(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE),
    ),
]


def extract_macro_signals_from_articles(
    articles: dict[str, Iterable[Any]],
) -> list[MacroRelease]:
    releases: list[MacroRelease] = []
    for items in articles.values():
        for item in items:
            text = "{} {}".format(
                getattr(item, "title", "") or "",
                getattr(item, "body_text", "") or "",
            )
            for metric, pattern in _MACRO_PATTERNS:
                match = pattern.search(text)
                if not match:
                    continue
                try:
                    value = float(match.group(1))
                except ValueError:
                    continue
                releases.append(
                    MacroRelease(
                        metric=metric,
                        value=value,
                        unit="%",
                        article_title=getattr(item, "title", "") or "",
                        fetched_at=datetime.now(timezone.utc),
                    )
                )
    return releases


def refresh_macro_releases() -> dict[str, Any]:
    return {"capex": aggregate_hyperscaler_capex(), "signals": []}
