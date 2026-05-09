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


if __name__ == "__main__":
    unittest.main()
