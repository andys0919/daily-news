"""Unit tests for external_calendar_feeds.py (network-free)."""
from __future__ import annotations

from datetime import date

import pytest

import external_calendar_feeds as ecf


# ---------- NASDAQ earnings ----------

def test_nasdaq_earnings_returns_us_event_shape():
    def fake_fetcher(url, params):
        assert "earnings" in url
        return {
            "data": {
                "rows": [
                    {
                        "symbol": "NVDA",
                        "name": "NVIDIA Corporation",
                        "time": "time-after-hours",
                    },
                    {
                        "symbol": "AAPL",
                        "name": "Apple Inc.",
                        "time": "time-pre-market",
                    },
                ]
            }
        }

    events = ecf.fetch_nasdaq_earnings(
        target_dates=[date(2026, 5, 14)],
        fetcher=fake_fetcher,
    )
    assert len(events) == 2
    nvda = events[0]
    assert nvda["kind"] == "us_event"
    assert nvda["label"] == "美股事件"
    assert nvda["date"] == "2026-05-14"
    assert nvda["ticker"] == "NVDA"
    assert nvda["time"] == "盤後"
    assert "NVIDIA" in nvda["title"]
    assert nvda["source"] == "NASDAQ Earnings Calendar"
    assert nvda["link"].endswith("/nvda/earnings")
    assert events[1]["time"] == "盤前"


def test_nasdaq_earnings_respects_tickers_filter():
    def fake_fetcher(url, params):
        return {
            "data": {
                "rows": [
                    {"symbol": "NVDA", "name": "NVIDIA", "time": "time-after-hours"},
                    {"symbol": "RANDOM", "name": "Random Co", "time": "time-pre-market"},
                ]
            }
        }

    events = ecf.fetch_nasdaq_earnings(
        target_dates=[date(2026, 5, 14)],
        tickers_filter={"NVDA"},
        fetcher=fake_fetcher,
    )
    assert [e["ticker"] for e in events] == ["NVDA"]


def test_nasdaq_earnings_handles_fetch_error_gracefully():
    def boom(url, params):
        raise RuntimeError("network down")

    events = ecf.fetch_nasdaq_earnings(
        target_dates=[date(2026, 5, 14)],
        fetcher=boom,
    )
    assert events == []


def test_nasdaq_earnings_iterates_each_date():
    captured: list[str] = []

    def fake_fetcher(url, params):
        captured.append(params["date"])
        return {"data": {"rows": []}}

    ecf.fetch_nasdaq_earnings(
        target_dates=[date(2026, 5, 14), date(2026, 5, 15)],
        fetcher=fake_fetcher,
    )
    assert captured == ["2026-05-14", "2026-05-15"]


# ---------- Forex Factory macro ----------

_FF_FIXTURE = b"""<?xml version="1.0" encoding="windows-1252"?>
<weeklyevents>
    <event>
        <title>CPI y/y</title>
        <country>USD</country>
        <date><![CDATA[05-14-2026]]></date>
        <time><![CDATA[8:30am]]></time>
        <impact><![CDATA[High]]></impact>
        <url><![CDATA[https://www.forexfactory.com/calendar/123-us-cpi-yy]]></url>
    </event>
    <event>
        <title>Retail Sales m/m</title>
        <country>USD</country>
        <date><![CDATA[05-15-2026]]></date>
        <time><![CDATA[8:30am]]></time>
        <impact><![CDATA[Medium]]></impact>
        <url><![CDATA[https://www.forexfactory.com/calendar/124-us-retail]]></url>
    </event>
    <event>
        <title>Tentative speech</title>
        <country>USD</country>
        <date><![CDATA[05-16-2026]]></date>
        <time><![CDATA[All Day]]></time>
        <impact><![CDATA[Low]]></impact>
    </event>
    <event>
        <title>Random emerging market</title>
        <country>BRL</country>
        <date><![CDATA[05-14-2026]]></date>
        <impact><![CDATA[High]]></impact>
    </event>
</weeklyevents>
"""


def test_forex_factory_filters_country_and_impact():
    events = ecf.fetch_forex_factory_macro(fetcher=lambda url: _FF_FIXTURE)
    titles = [e["title"] for e in events]
    assert "USD · CPI y/y" in titles
    assert "USD · Retail Sales m/m" in titles
    assert "USD · Tentative speech" not in titles  # filtered out (Low impact)
    assert all("BRL" not in t for t in titles)  # filtered out (not in keep list)


def test_forex_factory_event_shape_and_importance():
    events = ecf.fetch_forex_factory_macro(fetcher=lambda url: _FF_FIXTURE)
    cpi = next(e for e in events if "CPI" in e["title"])
    assert cpi["kind"] == "macro"
    assert cpi["label"] == "重要總經"
    assert cpi["date"] == "2026-05-14"
    assert cpi["time"] == "8:30am"
    assert cpi["importance"] == 95  # High
    assert cpi["source"] == "Forex Factory"
    assert cpi["link"].startswith("https://www.forexfactory.com/")
    retail = next(e for e in events if "Retail" in e["title"])
    assert retail["importance"] == 80  # Medium


def test_forex_factory_handles_fetch_error_gracefully():
    def boom(url):
        raise RuntimeError("network down")

    assert ecf.fetch_forex_factory_macro(fetcher=boom) == []


def test_forex_factory_handles_malformed_xml():
    assert ecf.fetch_forex_factory_macro(fetcher=lambda url: b"not xml") == []


# ---------- aggregate helper ----------

def test_fetch_all_external_calendar_events_combines_sources(monkeypatch):
    monkeypatch.setattr(
        ecf,
        "fetch_nasdaq_earnings",
        lambda *, target_dates, tickers_filter=None: [
            {"kind": "us_event", "ticker": "NVDA"}
        ],
    )
    monkeypatch.setattr(
        ecf,
        "fetch_forex_factory_macro",
        lambda: [{"kind": "macro", "title": "CPI"}],
    )
    combined = ecf.fetch_all_external_calendar_events(
        target_dates=[date(2026, 5, 14)],
        us_tickers_filter={"NVDA"},
    )
    kinds = sorted(e["kind"] for e in combined)
    assert kinds == ["macro", "us_event"]


# ---------- helper unit tests ----------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("time-after-hours", "盤後"),
        ("time-pre-market", "盤前"),
        ("time-amc", "盤後"),
        ("time-bmo", "盤前"),
        ("time-not-supplied", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_nasdaq_time(raw, expected):
    assert ecf._normalize_nasdaq_time(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("05-14-2026", "2026-05-14"),
        ("12-31-2026", "2026-12-31"),
        ("", None),
        ("not a date", None),
    ],
)
def test_parse_ff_date(raw, expected):
    assert ecf._parse_ff_date(raw) == expected
