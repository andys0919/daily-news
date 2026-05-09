import unittest
from datetime import date
from pathlib import Path

import insider_holdings


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "insider_holdings"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class InsiderHoldingsTests(unittest.TestCase):
    def test_form4_parser_returns_insider_trade(self):
        def fake_fetch(url):
            return _load("form4_sample.xml")

        trades = insider_holdings.fetch_us_form4_recent(
            "AAPL", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade.ticker, "AAPL")
        self.assertEqual(trade.insider_name, "Cook Timothy D")
        self.assertEqual(trade.insider_role, "CEO")
        self.assertEqual(trade.transaction_type, "S")
        self.assertEqual(trade.shares, 10000)
        self.assertAlmostEqual(trade.price, 180.50)
        self.assertEqual(trade.transaction_date, date(2026, 4, 15))

    def test_13f_parser_returns_two_holdings(self):
        def fake_fetch(url):
            return _load("13f_sample.xml")

        holdings = insider_holdings.fetch_us_13f_holdings(
            "0001067983", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(holdings), 2)
        names = {h.issuer_name for h in holdings}
        self.assertIn("NVIDIA CORP", names)
        self.assertIn("APPLE INC", names)
        nvda = next(h for h in holdings if h.issuer_name == "NVIDIA CORP")
        self.assertEqual(nvda.shares, 50000)
        self.assertEqual(nvda.value_usd, 5000000)


import sqlite3 as _sqlite3
import tempfile as _tempfile
from pathlib import Path as _Path


class InsiderPersistTests(unittest.TestCase):
    def test_refresh_persists_form4_trade(self):
        f = _tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = _Path(f.name)
        try:
            def fake_fetch(url):
                return _load("form4_sample.xml")

            original = insider_holdings.fetch_us_form4_recent

            def patched_fetch(ticker, _fetch_fn=None):
                return original(ticker, _fetch_fn=fake_fetch)

            insider_holdings.fetch_us_form4_recent = patched_fetch  # type: ignore
            try:
                insider_holdings.refresh_insider_transactions(["AAPL"], _db_path=db)
            finally:
                insider_holdings.fetch_us_form4_recent = original  # type: ignore

            conn = _sqlite3.connect(db)
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM insider_transactions WHERE ticker='AAPL'"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertGreaterEqual(count, 1)
        finally:
            db.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
