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
        _insert_article(
            self.db,
            title="The latest GHG protocol proposal raises the bar for 100% renewable reporting in data centers by 2035",
            source="Data Center Dynamics",
            category="🏭 產業數據",
            published="2026-05-12T10:33:00+08:00",
            tickers=["2035"],
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
        self.assertNotIn("2035", search_tickers)
        self.assertNotIn("3842", search_tickers)
        self.assertNotIn("5090", search_tickers)

    def test_export_action_board_surfaces_calls_estimates_and_news_index(self):
        _create_articles_table(self.db)
        _insert_article(
            self.db,
            title="鴻海(2317)5/12召開法說會，聚焦AI伺服器展望",
            source="台股法說會 (Google News)",
            category="🏛️ 法說與 IR 材料",
            published="2026-05-11T13:57:00+08:00",
            tickers=["2317"],
        )
        _insert_article(
            self.db,
            title="珍珠號噴發！鴻海法人目標價上看250元",
            source="鴻海/Foxconn",
            category="📊 券商與分析師研究",
            published="2026-05-11T14:57:00+08:00",
            tickers=["2317"],
        )
        _insert_article(
            self.db,
            title="鴻海AI伺服器出貨動能延續",
            source="鴻海/Foxconn",
            category="🏢 科技廠動態",
            published="2026-05-11T15:57:00+08:00",
            tickers=["2317"],
        )
        _insert_article(
            self.db,
            title="美國4月CPI將於5/12公布，市場關注Fed降息路徑",
            source="CNBC Top News",
            category="💰 財經與總經",
            published="2026-05-11T20:57:00+08:00",
            tickers=[],
            event_type="policy",
        )
        _insert_article(
            self.db,
            title="Deutsche Bank Raises Nvidia Stock (NVDA) Price Target on AI demand",
            source="NVIDIA News",
            category="📊 券商與分析師研究",
            published="2026-05-10T15:57:00+08:00",
            tickers=["NVDA"],
        )
        _insert_article(
            self.db,
            title="AMD Radeon RX 9070 XT price target article is really hardware pricing",
            source="AMD News",
            category="📊 券商與分析師研究",
            published="2026-05-10T16:57:00+08:00",
            tickers=["9070", "AMD"],
        )
        _insert_article(
            self.db,
            title="8-K - Volato Group, Inc. (0001853070) (Filer)",
            source="SEC 8-K Filings (Atom)",
            category="🏛️ 法說與 IR 材料",
            published="2026-05-11T16:57:00+08:00",
            tickers=["1231", "4522"],
            event_type="filing",
        )

        dashboard_export.export_all(
            db_path=self.db, output_dir=self.out, tickers=["NVDA", "2317"]
        )

        overview = json.loads((self.out / "overview.json").read_text())
        action_board = overview["action_board"]
        self.assertIn("research_queue", action_board)
        self.assertIn("call_events", action_board)
        self.assertIn("analyst_estimates", action_board)
        self.assertIn("news_index", action_board)
        self.assertIn("market_calendar", action_board)
        self.assertEqual(action_board["call_events"][0]["ticker"], "2317")
        self.assertEqual(action_board["call_events"][0]["display_name"], "鴻海")
        self.assertEqual(action_board["call_events"][0]["event_date"], "2026-05-12")
        self.assertNotIn("1231", {item["ticker"] for item in action_board["call_events"]})
        self.assertEqual(action_board["analyst_estimates"][0]["ticker"], "2317")
        self.assertEqual(action_board["analyst_estimates"][0]["display_name"], "鴻海")
        self.assertIn("目標價", action_board["analyst_estimates"][0]["signal"])
        nvda_estimate = next(item for item in action_board["analyst_estimates"] if item["ticker"] == "NVDA")
        self.assertEqual(nvda_estimate["display_name"], "輝達")
        self.assertNotIn("9070", {item["ticker"] for item in action_board["analyst_estimates"]})
        self.assertNotIn("9070", {item["ticker"] for item in action_board["news_index"]})
        self.assertEqual(action_board["news_index"][0]["ticker"], "2317")
        self.assertEqual(action_board["news_index"][0]["display_name"], "鴻海")
        self.assertGreaterEqual(len(action_board["news_index"][0]["headlines"]), 2)
        self.assertIn("下一步", action_board["research_queue"][0]["next_step"])
        queue_2317 = next(item for item in action_board["research_queue"] if item["ticker"] == "2317")
        self.assertEqual(queue_2317["display_name"], "鴻海")
        calendar = action_board["market_calendar"]
        calendar_kinds = {item["kind"] for item in calendar}
        self.assertIn("macro", calendar_kinds)
        self.assertIn("call", calendar_kinds)
        self.assertIn("tw_event", calendar_kinds)
        self.assertIn("us_event", calendar_kinds)
        self.assertNotIn("tw_market", calendar_kinds)
        self.assertNotIn("us_market", calendar_kinds)
        macro_item = next(item for item in calendar if item["kind"] == "macro")
        self.assertEqual(macro_item["date"], "2026-05-12")
        self.assertEqual(macro_item["label"], "重要總經")
        self.assertIn("CPI", macro_item["title"])
        call_item = next(item for item in calendar if item["kind"] == "call")
        self.assertEqual(call_item["ticker"], "2317")
        self.assertEqual(call_item["display_name"], "鴻海")
        self.assertGreater(call_item["importance"], macro_item["importance"])
        tw_item = next(item for item in calendar if item["kind"] == "tw_event")
        us_item = next(item for item in calendar if item["kind"] == "us_event")
        self.assertEqual(tw_item["ticker"], "2317")
        self.assertEqual(tw_item["label"], "台股事件")
        self.assertEqual(tw_item["display_name"], "鴻海")
        self.assertEqual(us_item["ticker"], "NVDA")
        self.assertEqual(us_item["label"], "美股事件")
        self.assertEqual(us_item["display_name"], "輝達")
        self.assertNotIn("AMD", {item.get("ticker") for item in calendar})
        self.assertFalse(any("hardware pricing" in item.get("title", "") for item in calendar))
        self.assertFalse(any(item.get("time") in {"09:00", "13:30", "21:30", "22:30"} for item in calendar))

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
