import unittest
from datetime import date
from pathlib import Path

import short_interest


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "short_interest"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ShortInterestTests(unittest.TestCase):
    def test_finra_parser_returns_rows_for_target_ticker(self):
        def fake_fetch(url):
            return _load("finra_sample.txt")

        rows = short_interest.fetch_us_finra_short_interest(
            "TSLA", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.ticker, "TSLA")
        self.assertEqual(row.market, "us")
        self.assertEqual(row.short_interest, 1500000)
        self.assertGreater(row.short_interest_ratio, 0)
        self.assertEqual(row.period_end, date(2026, 5, 9))

    def test_twse_credit_parser_returns_rows(self):
        def fake_fetch(url):
            return _load("twse_credit_sample.json")

        rows = short_interest.fetch_tw_credit_balance(
            "2330", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.ticker, "2330")
        self.assertEqual(row.market, "tw")
        self.assertEqual(row.short_interest, 1500)
        self.assertEqual(row.period_end, date(2026, 5, 8))


import sqlite3 as _sqlite3
import tempfile as _tempfile
from pathlib import Path as _Path


class ShortInterestPersistTests(unittest.TestCase):
    def test_refresh_persists_finra_row(self):
        f = _tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = _Path(f.name)
        try:
            def fake_fetch(url):
                return _load("finra_sample.txt")

            original = short_interest.fetch_us_finra_short_interest

            def patched_fetch(ticker, _fetch_fn=None):
                return original(ticker, _fetch_fn=fake_fetch)

            short_interest.fetch_us_finra_short_interest = patched_fetch  # type: ignore
            try:
                short_interest.refresh_short_interest("us", ["TSLA"], _db_path=db)
            finally:
                short_interest.fetch_us_finra_short_interest = original  # type: ignore

            conn = _sqlite3.connect(db)
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM short_interest_snapshots WHERE ticker='TSLA'"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertGreaterEqual(count, 1)
        finally:
            db.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
