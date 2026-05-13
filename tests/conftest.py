"""Shared pytest configuration for daily-news.

Disables external calendar feed fetches (NASDAQ earnings, Forex Factory) by
default so the test suite never touches the network.  Tests that exercise the
external feed code paths should mock fetchers explicitly.
"""
import os

os.environ.setdefault("DAILY_NEWS_DISABLE_EXTERNAL_CALENDAR", "1")
