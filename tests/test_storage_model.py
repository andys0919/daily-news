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


class StorageModelTests(unittest.TestCase):
    def test_init_creates_four_new_tables_and_is_idempotent(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            fr.init_financial_report_store(db)
            conn = sqlite3.connect(db)
            try:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            finally:
                conn.close()
            for required in (
                "issuer_materials",
                "insider_transactions",
                "holdings_snapshots",
                "short_interest_snapshots",
            ):
                self.assertIn(required, tables)
        finally:
            db.unlink(missing_ok=True)

    def test_save_issuer_material_round_trip(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            payload = {
                "market": "us",
                "ticker": "NVDA",
                "material_type": "transcript",
                "title": "NVDA Q1 2026 transcript",
                "body_text": "Blackwell ramp.",
                "source_url": "https://example.com/x",
                "fiscal_year": 2026,
                "fiscal_period": "q1",
                "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
            }
            fr.save_issuer_material(db, payload)
            rows = fr.get_recent_issuer_materials(db, market="us", ticker="NVDA")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "NVDA Q1 2026 transcript")
            self.assertEqual(rows[0]["material_type"], "transcript")
        finally:
            db.unlink(missing_ok=True)

    def test_save_insider_transaction_round_trip(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            payload = {
                "market": "us",
                "ticker": "AAPL",
                "insider_name": "Cook Timothy D",
                "insider_role": "CEO",
                "transaction_date": date(2026, 4, 15),
                "transaction_type": "S",
                "shares": 10000,
                "price": 180.5,
                "value_usd": 1805000.0,
                "filing_url": "https://example.com/4",
                "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
            }
            fr.save_insider_transaction(db, payload)
            rows = fr.get_recent_insider_transactions(db, ticker="AAPL")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["shares"], 10000)
            self.assertAlmostEqual(rows[0]["price"], 180.5)
        finally:
            db.unlink(missing_ok=True)

    def test_save_holdings_snapshot_round_trip(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            payload = {
                "reporter_cik": "0001067983",
                "reporter_name": "BERKSHIRE",
                "period_end": "2026-03-31",
                "issuer_name": "APPLE INC",
                "cusip": "037833100",
                "ticker": "AAPL",
                "shares": 50000,
                "value_usd": 9000000.0,
                "change_pct": 0.05,
                "filing_url": "https://example.com/13f",
                "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
            }
            fr.save_holdings_snapshot(db, payload)
            rows = fr.get_recent_holdings_snapshots(db, reporter_cik="0001067983")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["issuer_name"], "APPLE INC")
            self.assertEqual(rows[0]["shares"], 50000)
        finally:
            db.unlink(missing_ok=True)

    def test_save_short_interest_snapshot_round_trip(self):
        db = _tmp_db()
        try:
            fr.init_financial_report_store(db)
            payload = {
                "market": "us",
                "ticker": "TSLA",
                "period_end": date(2026, 5, 9),
                "short_interest": 1500000.0,
                "days_to_cover": 1.2,
                "short_interest_ratio": 0.42,
                "source": "FINRA Reg SHO",
                "fetched_at": datetime(2026, 5, 9, tzinfo=timezone.utc),
            }
            fr.save_short_interest_snapshot(db, payload)
            rows = fr.get_recent_short_interest_snapshots(db, ticker="TSLA")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["short_interest"], 1500000.0)
            self.assertAlmostEqual(rows[0]["short_interest_ratio"], 0.42)
        finally:
            db.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
