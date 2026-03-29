import unittest
from datetime import datetime, timedelta, timezone
import tempfile
from pathlib import Path
from unittest.mock import patch

from crawler import Article
from financial_reports import FinancialReport, init_financial_report_store, save_financial_report
import summarizer


TW_TZ = timezone(timedelta(hours=8))


def make_article(
    *,
    title: str,
    category: str,
    source: str,
    source_key: str,
    summary: str,
) -> Article:
    return Article(
        title=title,
        summary=summary,
        link=f"https://example.com/{source_key.replace(':', '-')}",
        source=source,
        source_key=source_key,
        category=category,
        summary_prompt="news",
        published=datetime.now(TW_TZ),
    )


class DailyMemoPrepareTests(unittest.TestCase):
    def test_cluster_daily_memo_events_merges_same_title_across_categories(self):
        prepared_articles = [
            (
                "💰 財經與總經",
                make_article(
                    title="NVIDIA exports face tighter review",
                    category="💰 財經與總經",
                    source="Reuters",
                    source_key="finance:Reuters",
                    summary="Macro angle on the same policy event.",
                ),
            ),
            (
                "🌏 地緣政治與科技政策",
                make_article(
                    title="NVIDIA exports face tighter review",
                    category="🌏 地緣政治與科技政策",
                    source="AP",
                    source_key="geo:AP",
                    summary="Policy angle on the same policy event.",
                ),
            ),
            (
                "🏢 科技廠動態",
                make_article(
                    title="TSMC slips below 1900 on policy fears",
                    category="🏢 科技廠動態",
                    source="CNA",
                    source_key="tech:CNA",
                    summary="Different event should stay separate.",
                ),
            ),
        ]

        clusters = summarizer._cluster_daily_memo_events(prepared_articles)

        self.assertEqual(len(clusters), 2)
        self.assertEqual(len(clusters[0]["articles"]), 2)
        self.assertEqual(
            {item[0] for item in clusters[0]["articles"]},
            {"💰 財經與總經", "🌏 地緣政治與科技政策"},
        )

    def test_build_daily_memo_prompt_from_articles_groups_duplicate_event_once(self):
        prepared_articles = [
            (
                "💰 財經與總經",
                make_article(
                    title="NVIDIA exports face tighter review",
                    category="💰 財經與總經",
                    source="Reuters",
                    source_key="finance:Reuters",
                    summary="Macro angle on the same policy event.",
                ),
            ),
            (
                "🌏 地緣政治與科技政策",
                make_article(
                    title="NVIDIA exports face tighter review",
                    category="🌏 地緣政治與科技政策",
                    source="AP",
                    source_key="geo:AP",
                    summary="Policy angle on the same policy event.",
                ),
            ),
        ]

        prompt = summarizer.build_daily_memo_prompt_from_articles(prepared_articles)

        self.assertIn("### 事件 1", prompt)
        self.assertIn("來源數：2", prompt)
        self.assertEqual(prompt.count("標題主軸：NVIDIA exports face tighter review"), 1)

    def test_build_daily_memo_prompt_from_articles_includes_financial_context(self):
        article = Article(
            title="NVIDIA results reprice AI capex expectations",
            summary="Reuters summary",
            body_text="Detailed article body about earnings and data center demand.",
            link="https://example.com/nvda-q1",
            source="Reuters",
            source_key="finance:Reuters",
            category="💰 財經與總經",
            summary_prompt="news",
            published=datetime.now(TW_TZ),
            tickers=["NVDA"],
            companies=["NVIDIA"],
            event_type="earnings",
            event_key="us:nvda:earnings:2026q1",
        )

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            init_financial_report_store(db_path)
            save_financial_report(
                db_path,
                FinancialReport(
                    market="us",
                    ticker="NVDA",
                    company_name="NVIDIA",
                    source_type="sec-companyfacts",
                    source_confidence="official",
                    form_type="10-Q",
                    fiscal_year=2026,
                    fiscal_period="Q1",
                    period_end="2026-01-31",
                    filed_at="2026-02-25",
                    source_url="https://data.sec.gov/submissions/CIK0001045810.json",
                    revenue=26000000000.0,
                    eps_diluted=5.98,
                    net_income=16000000000.0,
                ),
            )

            with patch("summarizer.DB_PATH", db_path):
                prompt = summarizer.build_daily_memo_prompt_from_articles(
                    [("💰 財經與總經", article)]
                )

        self.assertIn("財務重點：官方財報", prompt)
        self.assertIn("營收 260.0 億美元", prompt)
        self.assertIn("EPS 5.98", prompt)


if __name__ == "__main__":
    unittest.main()
