import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import crawler
import summarizer


TW_TZ = timezone(timedelta(hours=8))


class EarningsDataTests(unittest.TestCase):
    def test_financial_report_store_and_sec_cache_persist(self):
        from financial_reports import (
            FinancialReport,
            cache_sec_issuer,
            get_cached_sec_issuer,
            get_latest_financial_report,
            init_financial_report_store,
            save_financial_report,
        )

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            init_financial_report_store(db_path)
            cache_sec_issuer(
                db_path,
                ticker="AAPL",
                cik="0000320193",
                company_name="Apple Inc.",
            )
            cached = get_cached_sec_issuer(db_path, "AAPL")
            self.assertEqual(cached["cik"], "0000320193")

            report = FinancialReport(
                market="us",
                ticker="AAPL",
                company_name="Apple Inc.",
                cik="0000320193",
                source_type="sec-companyfacts",
                source_confidence="official",
                form_type="10-Q",
                fiscal_year=2026,
                fiscal_period="Q1",
                period_end="2025-12-27",
                filed_at="2026-01-30",
                source_url="https://data.sec.gov/submissions/CIK0000320193.json",
                revenue=124300000000.0,
                eps_diluted=2.4,
                net_income=36330000000.0,
                operating_cash_flow=40100000000.0,
                capex=3500000000.0,
                free_cash_flow=36600000000.0,
            )
            save_financial_report(db_path, report)

            loaded = get_latest_financial_report(db_path, market="us", ticker="AAPL")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.ticker, "AAPL")
            self.assertEqual(loaded.form_type, "10-Q")
            self.assertEqual(loaded.revenue, 124300000000.0)

    def test_build_us_financial_report_maps_companyfacts(self):
        from earnings_data import build_us_financial_report

        submissions_payload = {
            "name": "Apple Inc.",
            "filings": {
                "recent": {
                    "form": ["10-Q", "8-K"],
                    "filingDate": ["2026-01-30", "2026-01-30"],
                    "reportDate": ["2025-12-27", "2025-12-27"],
                    "accessionNumber": ["0000320193-26-000010", "0000320193-26-000011"],
                    "primaryDocument": ["aapl-20251227x10q.htm", "earnings.htm"],
                }
            },
        }
        companyfacts_payload = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {
                            "USD": [
                                {
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-01-30",
                                    "end": "2025-12-27",
                                    "val": 124300000000.0,
                                }
                            ]
                        }
                    },
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                {
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-01-30",
                                    "end": "2025-12-27",
                                    "val": 36330000000.0,
                                }
                            ]
                        }
                    },
                    "OperatingIncomeLoss": {
                        "units": {
                            "USD": [
                                {
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-01-30",
                                    "end": "2025-12-27",
                                    "val": 42800000000.0,
                                }
                            ]
                        }
                    },
                    "GrossProfit": {
                        "units": {
                            "USD": [
                                {
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-01-30",
                                    "end": "2025-12-27",
                                    "val": 58500000000.0,
                                }
                            ]
                        }
                    },
                    "DilutedEarningsPerShare": {
                        "units": {
                            "USD/shares": [
                                {
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-01-30",
                                    "end": "2025-12-27",
                                    "val": 2.4,
                                }
                            ]
                        }
                    },
                    "NetCashProvidedByUsedInOperatingActivities": {
                        "units": {
                            "USD": [
                                {
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-01-30",
                                    "end": "2025-12-27",
                                    "val": 40100000000.0,
                                }
                            ]
                        }
                    },
                    "PaymentsToAcquirePropertyPlantAndEquipment": {
                        "units": {
                            "USD": [
                                {
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-01-30",
                                    "end": "2025-12-27",
                                    "val": 3500000000.0,
                                }
                            ]
                        }
                    },
                }
            }
        }

        report = build_us_financial_report(
            ticker="AAPL",
            cik="0000320193",
            submissions_payload=submissions_payload,
            companyfacts_payload=companyfacts_payload,
        )

        self.assertIsNotNone(report)
        self.assertEqual(report.ticker, "AAPL")
        self.assertEqual(report.form_type, "10-Q")
        self.assertEqual(report.fiscal_year, 2026)
        self.assertEqual(report.fiscal_period, "Q1")
        self.assertEqual(report.revenue, 124300000000.0)
        self.assertEqual(report.eps_diluted, 2.4)
        self.assertEqual(report.free_cash_flow, 36600000000.0)
        self.assertAlmostEqual(report.gross_margin or 0.0, 58500000000.0 / 124300000000.0, places=6)

    def test_build_us_financial_report_prefers_10q_over_more_recent_8k(self):
        from earnings_data import build_us_financial_report

        submissions_payload = {
            "name": "Apple Inc.",
            "filings": {
                "recent": {
                    "form": ["8-K", "10-Q"],
                    "filingDate": ["2026-02-01", "2026-01-30"],
                    "reportDate": ["2025-12-27", "2025-12-27"],
                    "accessionNumber": ["0000320193-26-000011", "0000320193-26-000010"],
                    "primaryDocument": ["earnings.htm", "aapl-20251227x10q.htm"],
                }
            },
        }
        companyfacts_payload = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {
                            "USD": [
                                {
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-01-30",
                                    "end": "2025-12-27",
                                    "val": 124300000000.0,
                                }
                            ]
                        }
                    }
                }
            }
        }

        report = build_us_financial_report(
            ticker="AAPL",
            cik="0000320193",
            submissions_payload=submissions_payload,
            companyfacts_payload=companyfacts_payload,
        )

        self.assertEqual(report.form_type, "10-Q")

    def test_refresh_us_financial_reports_for_articles_is_bounded(self):
        from earnings_data import refresh_us_financial_reports_for_articles

        article_a = crawler.Article(
            title="Apple earnings",
            summary="summary",
            link="https://example.com/aapl",
            source="Reuters",
            source_key="finance:Reuters",
            category="💰 財經與總經",
            summary_prompt="news",
            published=datetime.now(TW_TZ),
            tickers=["AAPL"],
            event_type="earnings",
        )
        article_b = crawler.Article(
            title="Microsoft filing",
            summary="summary",
            link="https://example.com/msft",
            source="Reuters",
            source_key="finance:Reuters",
            category="💰 財經與總經",
            summary_prompt="news",
            published=datetime.now(TW_TZ),
            tickers=["MSFT"],
            event_type="filing",
        )
        article_c = crawler.Article(
            title="NVIDIA earnings",
            summary="summary",
            link="https://example.com/nvda",
            source="Reuters",
            source_key="finance:Reuters",
            category="💰 財經與總經",
            summary_prompt="news",
            published=datetime.now(TW_TZ),
            tickers=["NVDA"],
            event_type="earnings",
        )

        captured: list[str] = []

        def _fake_refresh(tickers, **_kwargs):
            captured.extend(tickers)
            return []

        refresh_us_financial_reports_for_articles(
            {"💰 財經與總經": [article_a, article_b, article_c]},
            max_issuers=2,
            refresh_fn=_fake_refresh,
        )

        self.assertEqual(captured, ["AAPL", "MSFT"])

    def test_build_articles_text_includes_official_financial_context(self):
        from financial_reports import FinancialReport, init_financial_report_store, save_financial_report

        article = crawler.Article(
            title="NVIDIA Q1 results top expectations",
            summary="media summary",
            body_text="Detailed article body.",
            link="https://example.com/nvda",
            source="Reuters",
            source_key="finance:Reuters",
            category="💰 財經與總經",
            summary_prompt="news",
            published=datetime.now(TW_TZ),
            tickers=["NVDA"],
            companies=["NVIDIA"],
            event_type="earnings",
        )

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            init_financial_report_store(db_path)
            save_financial_report(
                db_path,
                FinancialReport(
                    market="us",
                    ticker="NVDA",
                    company_name="NVIDIA",
                    cik="0001045810",
                    source_type="sec-companyfacts",
                    source_confidence="official",
                    form_type="10-Q",
                    fiscal_year=2026,
                    fiscal_period="Q1",
                    period_end="2026-01-31",
                    filed_at="2026-02-25",
                    source_url="https://data.sec.gov/submissions/CIK0001045810.json",
                    revenue=26000000000.0,
                    eps_diluted=5.98,
                    net_income=16000000000.0,
                    operating_cash_flow=18000000000.0,
                    capex=1200000000.0,
                    free_cash_flow=16800000000.0,
                ),
            )

            with patch("summarizer.DB_PATH", db_path):
                text = summarizer._build_articles_text([article])

        self.assertIn("財務重點：官方財報", text)
        self.assertIn("營收 260.0 億美元", text)
        self.assertIn("EPS 5.98", text)


if __name__ == "__main__":
    unittest.main()
