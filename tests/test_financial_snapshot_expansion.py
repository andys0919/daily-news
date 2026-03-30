import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from crawler import Article
from financial_reports import FinancialReport, init_financial_report_store, save_financial_report
import html_generator
import tw_financials


TW_TZ = timezone(timedelta(hours=8))


class FinancialSnapshotExpansionTests(unittest.TestCase):
    def test_refresh_tw_financial_reports_supports_financial_sector_endpoints(self):
        income_general = []
        balance_general = []
        income_financial = [
            {
                "出表日期": "1150325",
                "年度": "114",
                "季別": "4",
                "公司代號": "2881",
                "公司名稱": "富邦金",
                "利息淨收益": "1000000.00",
                "繼續營業單位本期淨利（淨損）": "550000.00",
                "本期淨利（淨損）": "550000.00",
                "基本每股盈餘（元）": "4.10",
            }
        ]
        balance_financial = [
            {
                "出表日期": "1150325",
                "年度": "114",
                "季別": "4",
                "公司代號": "2881",
                "公司名稱": "富邦金",
                "資產總計": "12000000.00",
                "權益總計": "900000.00",
                "每股參考淨值": "68.20",
            }
        ]
        monthly_rows = []

        payloads = {
            tw_financials.TW_MONTHLY_REVENUE_URL: monthly_rows,
            tw_financials.TW_INCOME_STATEMENT_URLS[0]["url"]: income_general,
            tw_financials.TW_BALANCE_SHEET_URLS[0]["url"]: balance_general,
            tw_financials.TW_INCOME_STATEMENT_URLS[1]["url"]: income_financial,
            tw_financials.TW_BALANCE_SHEET_URLS[1]["url"]: balance_financial,
        }

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            reports = tw_financials.refresh_tw_financial_reports(
                ["2881"],
                db_path=db_path,
                fetch_json=lambda url: payloads.get(url, []),
            )

        quarterly_reports = [report for report in reports if report.report_kind == "quarterly"]
        self.assertEqual(len(quarterly_reports), 1)
        self.assertEqual(quarterly_reports[0].ticker, "2881")
        self.assertEqual(quarterly_reports[0].source_type, "twse-openapi-listed-basi")
        self.assertEqual(quarterly_reports[0].eps_diluted, 4.10)

    def test_financial_snapshot_bundle_merges_quarterly_and_monthly_revenue(self):
        from financial_reports import get_financial_snapshot_bundle, format_financial_snapshot_bundle_context

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            init_financial_report_store(db_path)
            save_financial_report(
                db_path,
                FinancialReport(
                    market="tw",
                    ticker="2330",
                    company_name="台積電",
                    source_type="twse-openapi-listed-ci",
                    source_confidence="official-openapi",
                    form_type="TWSE-Q",
                    fiscal_year=114,
                    fiscal_period="Q4",
                    period_end="1150325",
                    filed_at="1150325",
                    report_kind="quarterly",
                    revenue=2894300000.0,
                    eps_diluted=46.32,
                ),
            )
            save_financial_report(
                db_path,
                FinancialReport(
                    market="tw",
                    ticker="2330",
                    company_name="台積電",
                    source_type="twse-openapi",
                    source_confidence="official-openapi",
                    form_type="TWSE-MONTHLY",
                    fiscal_period="11502",
                    period_end="11502",
                    filed_at="1150317",
                    report_kind="monthly_revenue",
                    monthly_revenue=260009000.0,
                ),
            )

            bundle = get_financial_snapshot_bundle(db_path, market="tw", ticker="2330")
            context = format_financial_snapshot_bundle_context(bundle)

        self.assertIsNotNone(bundle)
        self.assertIsNotNone(bundle.quarterly)
        self.assertIsNotNone(bundle.monthly_revenue)
        self.assertIn("FY114 Q4", context)
        self.assertIn("11502 月營收", context)
        self.assertIn("EPS 46.32", context)

    def test_financial_snapshot_bundle_prefers_latest_tw_quarter_across_calendar_formats(self):
        from financial_reports import get_financial_snapshot_bundle

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            init_financial_report_store(db_path)
            save_financial_report(
                db_path,
                FinancialReport(
                    market="tw",
                    ticker="2330",
                    company_name="台積電",
                    source_type="tpex-finance-report",
                    source_confidence="official-tpex",
                    form_type="TPEX-Q",
                    fiscal_year=2025,
                    fiscal_period="Q3",
                    period_end="2025Q3",
                    filed_at="2025Q3",
                    report_kind="quarterly",
                    revenue=2762963851.0,
                    eps_diluted=46.75,
                ),
            )
            save_financial_report(
                db_path,
                FinancialReport(
                    market="tw",
                    ticker="2330",
                    company_name="台積電",
                    source_type="mops-api",
                    source_confidence="official-mops",
                    form_type="MOPS-Q",
                    fiscal_year=114,
                    fiscal_period="Q4",
                    period_end="114Q4",
                    filed_at="114Q4",
                    report_kind="quarterly",
                    revenue=3809054272.0,
                    eps_diluted=66.26,
                ),
            )

            bundle = get_financial_snapshot_bundle(db_path, market="tw", ticker="2330")

        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertIsNotNone(bundle.quarterly)
        assert bundle.quarterly is not None
        self.assertEqual(bundle.quarterly.source_type, "mops-api")
        self.assertEqual(bundle.quarterly.fiscal_period, "Q4")
        self.assertEqual(bundle.quarterly.eps_diluted, 66.26)

    def test_generate_report_renders_financial_highlights_card(self):
        article = Article(
            title="台積電法說後市場聚焦 AI 需求",
            summary="summary",
            link="https://example.com/2330",
            source="經濟日報",
            source_key="finance:經濟日報 股市",
            category="💰 財經與總經",
            summary_prompt="news",
            published=datetime.now(TW_TZ),
            tickers=["2330"],
            companies=["台積電"],
            event_type="earnings",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "news.db"
            init_financial_report_store(db_path)
            save_financial_report(
                db_path,
                FinancialReport(
                    market="tw",
                    ticker="2330",
                    company_name="台積電",
                    source_type="twse-openapi-listed-ci",
                    source_confidence="official-openapi",
                    form_type="TWSE-Q",
                    fiscal_year=114,
                    fiscal_period="Q4",
                    period_end="1150325",
                    filed_at="1150325",
                    report_kind="quarterly",
                    revenue=2894300000.0,
                    eps_diluted=46.32,
                ),
            )
            save_financial_report(
                db_path,
                FinancialReport(
                    market="tw",
                    ticker="2330",
                    company_name="台積電",
                    source_type="twse-openapi",
                    source_confidence="official-openapi",
                    form_type="TWSE-MONTHLY",
                    fiscal_period="11502",
                    period_end="11502",
                    filed_at="1150317",
                    report_kind="monthly_revenue",
                    monthly_revenue=260009000.0,
                ),
            )

            original_report_dir = html_generator.REPORT_DIR
            html_generator.REPORT_DIR = Path(tmpdir)
            try:
                with patch.object(html_generator, "DB_PATH", db_path):
                    report_path = html_generator.generate_report(
                        {"💰 財經與總經": [article]},
                        summaries={},
                        market=None,
                        memo="## 今日主線\nmemo",
                        report_type="daily",
                    )
                    html = report_path.read_text(encoding="utf-8")
            finally:
                html_generator.REPORT_DIR = original_report_dir

        self.assertIn("📑 財報重點", html)
        self.assertIn("台積電", html)
        self.assertIn("FY114 Q4", html)
        self.assertIn("11502 月營收", html)

if __name__ == "__main__":
    unittest.main()
