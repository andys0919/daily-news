import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from crawler import Article
import main as daily_main


class DailyPipelineRoutingTests(unittest.TestCase):
    def test_daily_report_does_not_require_telegram_sender(self):
        article = Article(
            title="Daily launchd pipeline should finish without Telegram",
            summary="summary",
            link="https://example.com/no-telegram",
            source="Example",
            source_key="finance:Example",
            category="💰 財經與總經",
            summary_prompt="news",
            published=daily_main.datetime.now(daily_main.TW_TZ),
        )
        articles = {"💰 財經與總經": [article]}

        fake_crawler = ModuleType("crawler")

        async def fake_crawl_all(hours_back: int = 24):
            return articles

        def fake_get_recent_articles(hours_back: int = 24):
            return articles

        fake_crawler.crawl_all = fake_crawl_all
        fake_crawler.get_recent_articles = fake_get_recent_articles

        fake_market = ModuleType("market_data")
        fake_market.get_market_overview = lambda: SimpleNamespace(indices=[])

        fake_earnings = ModuleType("earnings_data")
        fake_earnings.refresh_us_financial_reports_for_articles = (
            lambda *_args, **_kwargs: []
        )

        fake_tw = ModuleType("tw_financials")
        fake_tw.refresh_tw_financial_reports_for_articles = (
            lambda *_args, **_kwargs: []
        )

        fake_tpex = ModuleType("tpex_financials")
        fake_tpex.refresh_tpex_financial_reports_for_articles = (
            lambda *_args, **_kwargs: []
        )

        fake_mops = ModuleType("mops_financials")
        fake_mops.refresh_mops_financial_reports_for_articles = (
            lambda *_args, **_kwargs: []
        )

        tmpfile = Path(tempfile.NamedTemporaryFile(suffix=".html", delete=False).name)
        tmpfile.write_text("<html></html>", encoding="utf-8")

        fake_html = ModuleType("html_generator")
        fake_html.generate_report = lambda *_args, **_kwargs: tmpfile

        fake_missing_sender = ModuleType("telegram_sender")

        with patch.dict(
            sys.modules,
            {
                "crawler": fake_crawler,
                "market_data": fake_market,
                "earnings_data": fake_earnings,
                "tw_financials": fake_tw,
                "tpex_financials": fake_tpex,
                "mops_financials": fake_mops,
                "html_generator": fake_html,
                "telegram_sender": fake_missing_sender,
            },
        ):
            report_path = asyncio.run(
                daily_main.run(hours_back=1, skip_summary=True, report_type="daily")
            )

        self.assertEqual(report_path, tmpfile)

    def test_daily_report_refreshes_us_and_tw_financial_context(self):
        calls = {"us_refresh": 0, "tw_refresh": 0}
        us_article = Article(
            title="Apple earnings",
            summary="summary",
            link="https://example.com/aapl",
            source="Reuters",
            source_key="finance:Reuters",
            category="💰 財經與總經",
            summary_prompt="news",
            published=daily_main.datetime.now(daily_main.TW_TZ),
            tickers=["AAPL"],
            event_type="earnings",
        )
        tw_article = Article(
            title="台積電法說",
            summary="summary",
            link="https://example.com/2330",
            source="經濟日報",
            source_key="finance:經濟日報 股市",
            category="💰 財經與總經",
            summary_prompt="news",
            published=daily_main.datetime.now(daily_main.TW_TZ),
            tickers=["2330"],
            event_type="earnings",
        )
        articles = {"💰 財經與總經": [us_article, tw_article]}

        fake_crawler = ModuleType("crawler")

        async def fake_crawl_all(hours_back: int = 24):
            return articles

        def fake_get_recent_articles(hours_back: int = 24):
            return articles

        fake_crawler.crawl_all = fake_crawl_all
        fake_crawler.get_recent_articles = fake_get_recent_articles

        fake_summarizer = ModuleType("summarizer")
        fake_summarizer.generate_daily_memo_from_articles = lambda _articles: "## 今日主線\nmemo"
        fake_summarizer.summarize_ai_github_digest = lambda *_args, **_kwargs: ("", {})
        fake_summarizer.reset_usage_stats = lambda: None
        fake_summarizer.get_usage_summary = lambda: {}

        fake_market = ModuleType("market_data")
        fake_market.get_market_overview = lambda: SimpleNamespace(indices=[])

        fake_earnings = ModuleType("earnings_data")

        def fake_refresh_us(_articles, **_kwargs):
            calls["us_refresh"] += 1
            self.assertEqual(_articles, articles)
            return []

        fake_earnings.refresh_us_financial_reports_for_articles = fake_refresh_us

        fake_tw = ModuleType("tw_financials")

        def fake_refresh_tw(_articles, **_kwargs):
            calls["tw_refresh"] += 1
            self.assertEqual(_articles, articles)
            return []

        fake_tw.refresh_tw_financial_reports_for_articles = fake_refresh_tw

        tmpfile = Path(tempfile.NamedTemporaryFile(suffix=".html", delete=False).name)
        tmpfile.write_text("<html></html>", encoding="utf-8")

        fake_html = ModuleType("html_generator")
        fake_html.generate_report = lambda *_args, **_kwargs: tmpfile

        with patch.dict(
            sys.modules,
            {
                "crawler": fake_crawler,
                "summarizer": fake_summarizer,
                "market_data": fake_market,
                "earnings_data": fake_earnings,
                "tw_financials": fake_tw,
                "html_generator": fake_html,
            },
        ):
            asyncio.run(
                daily_main.run(hours_back=1, skip_summary=False, report_type="daily")
            )

        self.assertEqual(calls["us_refresh"], 1)
        self.assertEqual(calls["tw_refresh"], 1)

    def test_daily_report_bypasses_category_summary_pipeline(self):
        calls = {"summaries": 0, "daily_memo_from_articles": 0, "ai_github": 0}
        article = Article(
            title="Global liquidity shifts into defensive assets",
            summary="Gold and volatility move together while semis pull back.",
            link="https://example.com/macro",
            source="Example",
            source_key="finance:Example",
            category="💰 財經與總經",
            summary_prompt="news",
            published=daily_main.datetime.now(daily_main.TW_TZ),
        )
        ai_article = Article(
            title="MCP workflow repo gains traction",
            summary="Developers are sharing MCP server integration patterns.",
            link="https://github.com/modelcontextprotocol/servers",
            source="GitHub Trending (Python)",
            source_key="ai_practice:GitHub Trending (Python)",
            category="🛠️ AI 工具與實戰",
            summary_prompt="ai_practice",
            published=daily_main.datetime.now(daily_main.TW_TZ),
        )
        articles = {
            "💰 財經與總經": [article],
            "🛠️ AI 工具與實戰": [ai_article],
        }

        fake_crawler = ModuleType("crawler")

        async def fake_crawl_all(hours_back: int = 24):
            return articles

        def fake_get_recent_articles(hours_back: int = 24):
            return articles

        fake_crawler.crawl_all = fake_crawl_all
        fake_crawler.get_recent_articles = fake_get_recent_articles

        fake_summarizer = ModuleType("summarizer")

        def fake_summarize_all(_articles):
            calls["summaries"] += 1
            raise AssertionError("daily report should not call summarize_all")

        def fake_generate_daily_memo_from_articles(_articles):
            calls["daily_memo_from_articles"] += 1
            return "## 今日主線\n市場正在重定價黃金與風險偏好。"

        def fake_summarize_ai_github_digest(category, category_articles):
            calls["ai_github"] += 1
            self.assertEqual(category, "🛠️ AI 工具與實戰")
            self.assertEqual(category_articles, [ai_article])
            return (
                "### GitHub 熱門 AI 工具\n- **MCP workflow repo gains traction**：MCP workflow 升溫。[1]",
                {1: ai_article.link},
            )

        fake_summarizer.summarize_all = fake_summarize_all
        fake_summarizer.generate_daily_memo_from_articles = (
            fake_generate_daily_memo_from_articles
        )
        fake_summarizer.summarize_ai_github_digest = fake_summarize_ai_github_digest
        fake_summarizer.generate_daily_memo = (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("daily report should use direct memo path")
            )
        )
        fake_summarizer.reset_usage_stats = lambda: None
        fake_summarizer.get_usage_summary = lambda: {}
        fake_market = ModuleType("market_data")
        fake_market.get_market_overview = lambda: SimpleNamespace(indices=[])

        tmpfile = Path(tempfile.NamedTemporaryFile(suffix=".html", delete=False).name)
        tmpfile.write_text("<html></html>", encoding="utf-8")

        fake_html = ModuleType("html_generator")

        def fake_generate_report(
            _articles,
            summaries,
            market,
            memo="",
            citation_links=None,
            **_kwargs,
        ):
            self.assertEqual(
                summaries,
                {
                    "🛠️ AI 工具與實戰": (
                        "### GitHub 熱門 AI 工具\n"
                        "- **MCP workflow repo gains traction**：MCP workflow 升溫。[1]"
                    )
                },
            )
            self.assertEqual(market.indices, [])
            self.assertIn("今日主線", memo)
            self.assertEqual(
                citation_links,
                {"🛠️ AI 工具與實戰": {1: ai_article.link}},
            )
            return tmpfile

        fake_html.generate_report = fake_generate_report

        with patch.dict(
            sys.modules,
            {
                "crawler": fake_crawler,
                "summarizer": fake_summarizer,
                "market_data": fake_market,
                "html_generator": fake_html,
            },
        ):
            asyncio.run(
                daily_main.run(hours_back=1, skip_summary=False, report_type="daily")
            )

        self.assertEqual(calls["summaries"], 0)
        self.assertEqual(calls["daily_memo_from_articles"], 1)
        self.assertEqual(calls["ai_github"], 1)

    def test_weekly_report_keeps_category_summary_pipeline(self):
        calls = {"summaries": 0, "daily_memo": 0}
        article = Article(
            title="Policy shift pressures semiconductor exports",
            summary="Weekly context should still pass through category summaries first.",
            link="https://example.com/weekly",
            source="Example",
            source_key="finance:Example",
            category="💰 財經與總經",
            summary_prompt="news",
            published=daily_main.datetime.now(daily_main.TW_TZ),
        )
        articles = {"💰 財經與總經": [article]}

        fake_crawler = ModuleType("crawler")

        async def fake_crawl_all(hours_back: int = 168):
            return articles

        def fake_get_recent_articles(hours_back: int = 168):
            return articles

        fake_crawler.crawl_all = fake_crawl_all
        fake_crawler.get_recent_articles = fake_get_recent_articles

        fake_summarizer = ModuleType("summarizer")

        def fake_summarize_all(_articles):
            calls["summaries"] += 1
            return {"💰 財經與總經": "weekly summary"}

        def fake_generate_daily_memo(_articles, summaries):
            calls["daily_memo"] += 1
            self.assertEqual(summaries, {"💰 財經與總經": "weekly summary"})
            return "## 今日主線\nweekly memo"

        fake_summarizer.summarize_all = fake_summarize_all
        fake_summarizer.generate_daily_memo = fake_generate_daily_memo
        fake_summarizer.generate_daily_memo_from_articles = (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("weekly report should keep summary pipeline")
            )
        )
        fake_summarizer.reset_usage_stats = lambda: None
        fake_summarizer.get_usage_summary = lambda: {}
        fake_summarizer.build_all_citation_links = lambda _articles: {}

        fake_market = ModuleType("market_data")
        fake_market.get_market_overview = lambda: SimpleNamespace(indices=[])

        tmpfile = Path(tempfile.NamedTemporaryFile(suffix=".html", delete=False).name)
        tmpfile.write_text("<html></html>", encoding="utf-8")

        fake_html = ModuleType("html_generator")
        fake_html.generate_report = lambda *_args, **_kwargs: tmpfile

        with patch.dict(
            sys.modules,
            {
                "crawler": fake_crawler,
                "summarizer": fake_summarizer,
                "market_data": fake_market,
                "html_generator": fake_html,
            },
        ):
            asyncio.run(
                daily_main.run(hours_back=1, skip_summary=False, report_type="weekly")
            )

        self.assertEqual(calls["summaries"], 1)
        self.assertEqual(calls["daily_memo"], 1)


if __name__ == "__main__":
    unittest.main()
