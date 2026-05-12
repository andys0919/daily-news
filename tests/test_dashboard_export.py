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


def _create_articles_table(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                title TEXT NOT NULL,
                summary TEXT,
                link TEXT NOT NULL,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                published TEXT NOT NULL,
                crawled_at TEXT NOT NULL,
                tickers_json TEXT NOT NULL DEFAULT '[]',
                companies_json TEXT NOT NULL DEFAULT '[]',
                event_type TEXT NOT NULL DEFAULT '',
                publisher TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                body_text TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _insert_article(
    db_path: Path,
    *,
    title: str,
    source: str,
    category: str,
    published: str,
    tickers: list[str],
    event_type: str = "news",
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO articles (
                title, summary, link, source, category, published, crawled_at,
                tickers_json, companies_json, event_type, publisher, author, body_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, '', '', '')
            """,
            (
                title,
                title,
                f"https://example.com/{abs(hash((source, title))) % 1000000}",
                source,
                category,
                published,
                published,
                json.dumps(tickers),
                event_type,
            ),
        )
        conn.commit()
    finally:
        conn.close()


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

    def test_stock_dashboard_excludes_dev_and_raw_sec_noise(self):
        _create_articles_table(self.db)
        for i in range(3):
            _insert_article(
                self.db,
                title=f"owner/repo-ai-tool-{i}",
                source="GitHub Trending (Python)",
                category="🧠 AI 研究與突破",
                published=f"2026-05-12T10:0{i}:00+08:00",
                tickers=["1965", "META"],
            )
            _insert_article(
                self.db,
                title=f"4 - Test Insider (00014469{i}9) (Reporting)",
                source="SEC Form 4 (Atom)",
                category="👁️ 內部人與機構持股",
                published=f"2026-05-12T10:1{i}:00+08:00",
                tickers=["1231", "3842"],
                event_type="filing",
            )
        _insert_article(
            self.db,
            title="台積電法說會後外資上修目標價",
            source="TSMC News",
            category="🏢 科技廠動態",
            published="2026-05-12T10:30:00+08:00",
            tickers=["2330"],
            event_type="earnings",
        )
        _insert_article(
            self.db,
            title="JX Metals Shares Drop Most Since April 2025 on Convertible Bond",
            source="Bloomberg Markets",
            category="💰 財經與總經",
            published="2026-05-12T10:31:00+08:00",
            tickers=["META"],
        )
        _insert_article(
            self.db,
            title="RTX 5090 gaming PC hits lowest price in 30 days at Newegg",
            source="AMD News",
            category="🏢 科技廠動態",
            published="2026-05-12T10:32:00+08:00",
            tickers=["5090"],
        )

        dashboard_export.export_all(
            db_path=self.db, output_dir=self.out, tickers=["NVDA", "2330"]
        )

        news = json.loads((self.out / "news.json").read_text())
        news_sources = {article["source"] for article in news["articles"]}
        news_titles = {article["title"] for article in news["articles"]}
        self.assertIn("TSMC News", news_sources)
        self.assertNotIn("GitHub Trending (Python)", news_sources)
        self.assertNotIn("SEC Form 4 (Atom)", news_sources)
        self.assertNotIn("JX Metals Shares Drop Most Since April 2025 on Convertible Bond", news_titles)
        self.assertNotIn("RTX 5090 gaming PC hits lowest price in 30 days at Newegg", news_titles)

        search = json.loads((self.out / "tickers.json").read_text())
        search_tickers = {item["ticker"] for item in search["tickers"]}
        self.assertNotIn("1965", search_tickers)
        self.assertNotIn("3842", search_tickers)
        self.assertNotIn("5090", search_tickers)

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
