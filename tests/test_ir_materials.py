import unittest
from datetime import datetime
from pathlib import Path

import ir_materials


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ir_materials"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _make_article(ticker: str):
    class A:
        pass

    a = A()
    a.tickers = [ticker]
    a.companies = []
    a.title = f"{ticker} earnings"
    a.body_text = ""
    a.summary = ""
    return a


class IRMaterialsTests(unittest.TestCase):
    def test_fetch_us_transcripts_parses_motley_fool_html(self):
        def fake_fetch(url):
            return _load_fixture("motley_fool_sample.html")

        results = ir_materials.fetch_us_transcripts(
            "NVDA", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item.ticker, "NVDA")
        self.assertEqual(item.market, "us")
        self.assertEqual(item.material_type, "transcript")
        self.assertIn("Blackwell", item.body_text)
        self.assertIsInstance(item.fetched_at, datetime)

    def test_fetch_us_8k_text_parses_filing_text(self):
        def fake_fetch(url):
            return _load_fixture("sec_8k_sample.txt")

        results = ir_materials.fetch_us_8k_text(
            "NVDA", _fetch_fn=fake_fetch
        )
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item.ticker, "NVDA")
        self.assertEqual(item.material_type, "8-K-text")
        self.assertIn("Item 7.01", item.body_text)

    def test_refresh_ir_materials_for_articles_collects_unique_tickers(self):
        articles = {
            "🏛️ 法說與 IR 材料": [
                _make_article(ticker="NVDA"),
                _make_article(ticker="AAPL"),
                _make_article(ticker="NVDA"),
            ]
        }
        seen = []

        def fake_transcripts(ticker, _fetch_fn=None):
            seen.append(ticker)
            return []

        original = ir_materials.fetch_us_transcripts
        ir_materials.fetch_us_transcripts = fake_transcripts  # type: ignore
        try:
            ir_materials.refresh_ir_materials_for_articles(articles, _persist=False)
        finally:
            ir_materials.fetch_us_transcripts = original  # type: ignore

        self.assertEqual(sorted(set(seen)), ["AAPL", "NVDA"])


import sqlite3 as _sqlite3
import tempfile as _tempfile
from datetime import datetime as _dt, timezone as _tz
from pathlib import Path as _Path


class IRMaterialsPersistTests(unittest.TestCase):
    def test_refresh_persists_when_default_persist_true(self):
        f = _tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = _Path(f.name)
        try:
            articles = {
                "🏛️ 法說與 IR 材料": [_make_article(ticker="NVDA")]
            }

            captured = []

            def fake_transcripts(ticker, _fetch_fn=None):
                captured.append(ticker)
                return [
                    ir_materials.IRMaterial(
                        market="us",
                        ticker=ticker,
                        material_type="transcript",
                        title="X",
                        body_text="body",
                        source_url="u",
                        fetched_at=_dt.now(_tz.utc),
                    )
                ]

            original = ir_materials.fetch_us_transcripts
            ir_materials.fetch_us_transcripts = fake_transcripts  # type: ignore
            try:
                ir_materials.refresh_ir_materials_for_articles(
                    articles, _db_path=db
                )
            finally:
                ir_materials.fetch_us_transcripts = original  # type: ignore

            conn = _sqlite3.connect(db)
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM issuer_materials WHERE ticker='NVDA'"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(count, 1)
        finally:
            db.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
