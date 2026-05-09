import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import macro_data


def _make_article(title: str, body_text: str):
    class A:
        pass

    a = A()
    a.title = title
    a.body_text = body_text
    a.summary = ""
    a.tickers = []
    a.published = datetime.now(timezone.utc)
    return a


class MacroDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE financial_reports (
                ticker TEXT,
                market TEXT,
                period_end TEXT,
                capex REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO financial_reports VALUES (?, ?, ?, ?)",
            [
                ("MSFT", "us", "2026-03-31", 22000.0),
                ("GOOG", "us", "2026-03-31", 18000.0),
                ("AMZN", "us", "2026-03-31", 25000.0),
                ("META", "us", "2026-03-31", 14000.0),
                ("NVDA", "us", "2026-03-31", 5000.0),
            ],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)

    def test_aggregate_hyperscaler_capex_sums_four_tickers(self):
        agg = macro_data.aggregate_hyperscaler_capex(_db_path=self.db_path)
        self.assertEqual(agg.total_usd, 22000.0 + 18000.0 + 25000.0 + 14000.0)
        self.assertEqual(sorted(agg.tickers_included), ["AMZN", "GOOG", "META", "MSFT"])
        self.assertEqual(agg.period_end, "2026-03-31")

    def test_extract_macro_signals_picks_cpi_number(self):
        articles = {
            "🌐 宏觀與產業數據": [
                _make_article(
                    title="US CPI rose to 3.2% in April",
                    body_text="The April CPI print came in at 3.2 percent, above 3.1% consensus.",
                ),
                _make_article(title="ECB holds rate", body_text="No data quoted."),
            ]
        }
        signals = macro_data.extract_macro_signals_from_articles(articles)
        cpi_signals = [s for s in signals if s.metric == "CPI"]
        self.assertGreaterEqual(len(cpi_signals), 1)
        self.assertAlmostEqual(cpi_signals[0].value, 3.2)


if __name__ == "__main__":
    unittest.main()
