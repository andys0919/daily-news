import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import financial_reports as fr


def _tmp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return Path(f.name)


class BundleExtensionTests(unittest.TestCase):
    def test_bundle_returns_none_for_new_fields_when_no_rows(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            quarterly = fr.FinancialReport(
                market="us",
                ticker="NVDA",
                company_name="NVIDIA",
                source_type="sec",
                form_type="10-Q",
                fiscal_year=2026,
                fiscal_period="Q1",
                period_end="2026-03-31",
                filed_at="2026-04-25",
                source_url="https://example.com",
                report_kind="quarterly",
                revenue=30_000_000_000.0,
            )
            fr.save_financial_report(db, quarterly)
            bundle = fr.get_financial_snapshot_bundle(db, market="us", ticker="NVDA")
            self.assertIsNotNone(bundle)
            self.assertIsNone(bundle.latest_transcript)
            self.assertIsNone(bundle.recent_insider_summary)
            self.assertIsNone(bundle.latest_13f)
            self.assertIsNone(bundle.short_interest)
        finally:
            db.unlink(missing_ok=True)

    def test_bundle_picks_up_transcript_and_short_interest(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            quarterly = fr.FinancialReport(
                market="us",
                ticker="NVDA",
                company_name="NVIDIA",
                source_type="sec",
                form_type="10-Q",
                fiscal_year=2026,
                fiscal_period="Q1",
                period_end="2026-03-31",
                filed_at="2026-04-25",
                source_url="https://example.com",
                report_kind="quarterly",
                revenue=30_000_000_000.0,
            )
            fr.save_financial_report(db, quarterly)
            fr.save_issuer_material(
                db,
                {
                    "market": "us",
                    "ticker": "NVDA",
                    "material_type": "transcript",
                    "title": "NVDA Q1 transcript",
                    "body_text": "Blackwell ramp.",
                    "source_url": "https://x",
                    "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
                },
            )
            fr.save_short_interest_snapshot(
                db,
                {
                    "market": "us",
                    "ticker": "NVDA",
                    "period_end": date(2026, 5, 9),
                    "short_interest": 200000.0,
                    "days_to_cover": 1.5,
                    "short_interest_ratio": 0.05,
                    "source": "FINRA",
                    "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
                },
            )
            bundle = fr.get_financial_snapshot_bundle(db, market="us", ticker="NVDA")
            self.assertIsNotNone(bundle.latest_transcript)
            self.assertEqual(bundle.latest_transcript["material_type"], "transcript")
            self.assertIsNotNone(bundle.short_interest)
            self.assertAlmostEqual(bundle.short_interest["short_interest_ratio"], 0.05)
            self.assertIsNone(bundle.recent_insider_summary)
            self.assertIsNone(bundle.latest_13f)
        finally:
            db.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
