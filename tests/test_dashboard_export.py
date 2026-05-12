import json
import math
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import dashboard_export
import financial_reports as fr


def _tmp_dir() -> Path:
    return Path(tempfile.mkdtemp())


class DashboardExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = _tmp_dir()
        self.db = self.tmp / "news.db"
        self.out = self.tmp / "out"
        self.out.mkdir(parents=True, exist_ok=True)

        fr.init_financial_report_store(self.db)
        fr.save_financial_report(
            self.db,
            fr.FinancialReport(
                market="us", ticker="NVDA", company_name="NVIDIA",
                source_type="sec", form_type="10-Q",
                fiscal_year=2026, fiscal_period="Q1",
                period_end="2026-03-31", filed_at="2026-04-25",
                source_url="https://example.com", report_kind="quarterly",
                revenue=30_000_000_000.0,
            ),
        )
        fr.save_issuer_material(
            self.db,
            {
                "market": "us", "ticker": "NVDA",
                "material_type": "transcript",
                "title": "NVDA Q1 transcript",
                "body_text": "Blackwell ramp drives growth.",
                "source_url": "https://x",
                "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
            },
        )

    def test_export_overview_writes_json(self):
        dashboard_export.export_all(
            db_path=self.db, output_dir=self.out, tickers=["NVDA"]
        )
        overview = json.loads((self.out / "overview.json").read_text())
        self.assertIn("top_transcripts", overview)
        self.assertIn("watchlist", overview)
        self.assertIsInstance(overview["top_transcripts"], list)

    def test_export_per_stock_json(self):
        dashboard_export.export_all(
            db_path=self.db, output_dir=self.out, tickers=["NVDA"]
        )
        path = self.out / "stocks" / "NVDA.json"
        self.assertTrue(path.exists())
        payload = json.loads(path.read_text())
        self.assertEqual(payload["ticker"], "NVDA")
        self.assertIn("bundle", payload)
        self.assertIn("transcripts", payload)

    def test_export_news_json_with_empty_db(self):
        dashboard_export.export_all(
            db_path=self.db, output_dir=self.out, tickers=["NVDA"]
        )
        news = json.loads((self.out / "news.json").read_text())
        self.assertIn("articles", news)
        self.assertIsInstance(news["articles"], list)

    def test_repo_watchlist_yaml_exists_for_dashboard_defaults(self):
        repo_root = Path(dashboard_export.__file__).resolve().parent

        tickers = dashboard_export._load_watchlist(repo_root)

        self.assertTrue((repo_root / "data" / "watchlist.yaml").exists())
        self.assertEqual(tickers[:3], ["NVDA", "TSM", "2330"])

    def test_revenue_pulse_normalizes_tw_roc_year_for_yoy(self):
        for fiscal_year, revenue in ((2025, 200.0), (113, 100.0)):
            fr.save_financial_report(
                self.db,
                fr.FinancialReport(
                    market="tw",
                    ticker="2330",
                    company_name="台積電",
                    source_type="mops-api",
                    form_type="MOPS-Q",
                    fiscal_year=fiscal_year,
                    fiscal_period="Q4",
                    period_end=f"{fiscal_year}Q4",
                    filed_at=f"{fiscal_year}Q4",
                    source_url="https://example.com",
                    report_kind="quarterly",
                    revenue=revenue,
                ),
            )

        rows = dashboard_export._revenue_pulse(
            self.db,
            limit=5,
            watchlist=["2330"],
        )

        self.assertEqual(rows[0]["q_year"], 2025)
        self.assertEqual(rows[0]["q_period"], "Q4")
        self.assertEqual(rows[0]["q_rev_yoy"], 100.0)

    def test_write_converts_non_finite_numbers_to_json_null(self):
        path = self.out / "non_finite.json"

        dashboard_export._write(path, {"value": math.nan})

        self.assertEqual(json.loads(path.read_text()), {"value": None})


if __name__ == "__main__":
    unittest.main()
