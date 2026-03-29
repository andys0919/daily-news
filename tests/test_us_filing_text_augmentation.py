import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crawler import Article
from financial_reports import (
    FinancialReport,
    get_financial_snapshot_bundle,
    init_financial_report_store,
    save_financial_report,
)
import summarizer


class UsFilingTextAugmentationTests(unittest.TestCase):
    def test_extract_sec_filing_highlights_picks_guidance_and_capex_sentences(self):
        from earnings_data import extract_sec_filing_highlights

        html = """
        <html><body>
          <p>The company expects fiscal 2026 revenue to grow at a double-digit rate.</p>
          <p>Management said capital expenditures will increase to support AI data center demand.</p>
          <p>Another generic sentence that should rank lower.</p>
        </body></html>
        """

        highlights = extract_sec_filing_highlights(html)

        self.assertIn("expects fiscal 2026 revenue", highlights["guidance_summary"].lower())
        self.assertIn("capital expenditures", highlights["filing_excerpt"].lower())

    def test_refresh_us_financial_reports_stores_filing_text_highlights(self):
        from earnings_data import refresh_us_financial_reports

        submissions_payload = {
            "name": "Apple Inc.",
            "filings": {
                "recent": {
                    "form": ["10-Q"],
                    "filingDate": ["2026-01-30"],
                    "reportDate": ["2025-12-27"],
                    "accessionNumber": ["0000320193-26-000010"],
                    "primaryDocument": ["aapl-20251227x10q.htm"],
                }
            },
            "cik": "0000320193",
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
        filing_html = """
        <html><body>
          <p>We expect March-quarter gross margin to remain in the mid-40s.</p>
          <p>Capital expenditures are expected to rise as AI infrastructure demand increases.</p>
        </body></html>
        """
        mapping_payload = {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}

        def _fake_fetch_json(url: str):
            if "company_tickers" in url:
                return mapping_payload
            if "submissions" in url:
                return submissions_payload
            if "companyfacts" in url:
                return companyfacts_payload
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            reports = refresh_us_financial_reports(
                ["AAPL"],
                db_path=db_path,
                fetch_json=_fake_fetch_json,
                fetch_text=lambda _url: filing_html,
                sleep_sec=0,
            )
            bundle = get_financial_snapshot_bundle(db_path, market="us", ticker="AAPL")

        self.assertEqual(len(reports), 1)
        self.assertIsNotNone(bundle)
        self.assertIn("gross margin", bundle.quarterly.guidance_summary.lower())
        self.assertIn("capital expenditures", bundle.quarterly.filing_excerpt.lower())

    def test_refresh_us_financial_reports_prefers_recent_8k_for_text_highlights(self):
        from earnings_data import refresh_us_financial_reports

        submissions_payload = {
            "name": "Apple Inc.",
            "filings": {
                "recent": {
                    "form": ["8-K", "10-Q"],
                    "filingDate": ["2026-02-01", "2026-01-30"],
                    "reportDate": ["2025-12-27", "2025-12-27"],
                    "accessionNumber": ["0000320193-26-000011", "0000320193-26-000010"],
                    "primaryDocument": ["earnings-release.htm", "aapl-20251227x10q.htm"],
                }
            },
            "cik": "0000320193",
        }
        companyfacts_payload = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {"USD": [{"fy": 2026, "fp": "Q1", "form": "10-Q", "filed": "2026-01-30", "end": "2025-12-27", "val": 124300000000.0}]}
                    }
                }
            }
        }
        mapping_payload = {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}
        requested_urls: list[str] = []

        def _fake_fetch_json(url: str):
            if "company_tickers" in url:
                return mapping_payload
            if "submissions" in url:
                return submissions_payload
            if "companyfacts" in url:
                return companyfacts_payload
            raise AssertionError(url)

        def _fake_fetch_text(url: str) -> str:
            requested_urls.append(url)
            return "<html><body><p>Management expects revenue growth to accelerate.</p></body></html>"

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            refresh_us_financial_reports(
                ["AAPL"],
                db_path=db_path,
                fetch_json=_fake_fetch_json,
                fetch_text=_fake_fetch_text,
                sleep_sec=0,
            )

        self.assertTrue(any("earnings-release.htm" in url for url in requested_urls))

    def test_extract_sec_filing_highlights_skips_table_like_text(self):
        from earnings_data import extract_sec_filing_highlights

        html = """
        <html><body>
          <div>Three Months Ended December 27, 2025 December 28, 2024 Total shareholders' equity beginning balances 73,733 56,950</div>
          <p>Management expects fiscal 2026 revenue growth to accelerate in the services segment.</p>
          <p>Capital expenditures are expected to rise as AI infrastructure demand increases.</p>
        </body></html>
        """

        highlights = extract_sec_filing_highlights(html)

        self.assertNotIn("three months ended", highlights["guidance_summary"].lower())
        self.assertNotIn("three months ended", highlights["filing_excerpt"].lower())

    def test_article_financial_context_includes_filing_text(self):
        article = Article(
            title="Apple quarter highlights",
            summary="summary",
            link="https://example.com/aapl",
            source="Reuters",
            source_key="finance:Reuters",
            category="💰 財經與總經",
            summary_prompt="news",
            published=summarizer.datetime.now(),
            tickers=["AAPL"],
            event_type="earnings",
        )

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            init_financial_report_store(db_path)
            save_financial_report(
                db_path,
                FinancialReport(
                    market="us",
                    ticker="AAPL",
                    company_name="Apple Inc.",
                    source_type="sec-companyfacts",
                    source_confidence="official",
                    form_type="10-Q",
                    fiscal_year=2026,
                    fiscal_period="Q1",
                    period_end="2025-12-27",
                    filed_at="2026-01-30",
                    report_kind="quarterly",
                    revenue=124300000000.0,
                    eps_diluted=2.4,
                    guidance_summary="Management expects services revenue growth to stay strong.",
                    filing_excerpt="Capital expenditures are expected to rise with AI infrastructure demand.",
                ),
            )
            with patch("summarizer.DB_PATH", db_path):
                context = summarizer._article_financial_context(article)

        self.assertIn("services revenue growth", context)
        self.assertIn("Capital expenditures", context)


if __name__ == "__main__":
    unittest.main()
