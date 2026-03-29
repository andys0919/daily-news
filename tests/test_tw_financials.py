import tempfile
import unittest
import urllib.error
import ssl
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, Mock

import crawler
import summarizer


TW_TZ = timezone(timedelta(hours=8))


class TwFinancialsTests(unittest.TestCase):
    def test_fetch_json_retries_twse_with_unverified_ssl_on_cert_error(self):
        import tw_financials

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'[{"ok": true}]'

        calls: list[object] = []

        def _fake_urlopen(request, timeout=20, context=None):
            calls.append(context)
            if len(calls) == 1:
                raise urllib.error.URLError(
                    ssl.SSLCertVerificationError("certificate verify failed")
                )
            return _FakeResponse()

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            payload = tw_financials._fetch_json(tw_financials.TW_MONTHLY_REVENUE_URL)

        self.assertEqual(payload, [{"ok": True}])
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0])
        self.assertIsInstance(calls[1], ssl.SSLContext)

    def test_map_tw_monthly_revenue_row_to_financial_report(self):
        from tw_financials import map_tw_monthly_revenue_row

        report = map_tw_monthly_revenue_row(
            {
                "出表日期": "1150317",
                "資料年月": "11502",
                "公司代號": "2330",
                "公司名稱": "台積電",
                "營業收入-當月營收": "260009000",
            }
        )

        self.assertEqual(report.market, "tw")
        self.assertEqual(report.ticker, "2330")
        self.assertEqual(report.report_kind, "monthly_revenue")
        self.assertEqual(report.monthly_revenue, 260009000.0)
        self.assertEqual(report.source_confidence, "official-openapi")

    def test_build_tw_quarterly_financial_report_maps_income_and_balance_rows(self):
        from tw_financials import build_tw_quarterly_financial_report

        income_rows = [
            {
                "出表日期": "1150325",
                "年度": "114",
                "季別": "4",
                "公司代號": "2330",
                "公司名稱": "台積電",
                "營業收入": "2894300000.00",
                "營業毛利（毛損）淨額": "1600000000.00",
                "營業利益（損失）": "1400000000.00",
                "淨利（淨損）歸屬於母公司業主": "1200000000.00",
                "基本每股盈餘（元）": "46.32",
            }
        ]
        balance_rows = [
            {
                "出表日期": "1150325",
                "年度": "114",
                "季別": "4",
                "公司代號": "2330",
                "公司名稱": "台積電",
                "資產總額": "6500000000.00",
                "權益總額": "4200000000.00",
                "每股參考淨值": "162.40",
            }
        ]

        report = build_tw_quarterly_financial_report(
            ticker="2330",
            income_rows=income_rows,
            balance_rows=balance_rows,
        )

        self.assertIsNotNone(report)
        self.assertEqual(report.ticker, "2330")
        self.assertEqual(report.fiscal_year, 114)
        self.assertEqual(report.fiscal_period, "Q4")
        self.assertEqual(report.revenue, 2894300000.0)
        self.assertEqual(report.eps_diluted, 46.32)
        self.assertAlmostEqual(report.gross_margin or 0.0, 1600000000.0 / 2894300000.0, places=6)
        self.assertAlmostEqual(report.operating_margin or 0.0, 1400000000.0 / 2894300000.0, places=6)

    def test_refresh_tw_financial_reports_for_articles_is_bounded(self):
        from tw_financials import refresh_tw_financial_reports_for_articles

        articles = {
            "💰 財經與總經": [
                crawler.Article(
                    title="台積電法說",
                    summary="summary",
                    link="https://example.com/2330",
                    source="鉅亨網",
                    source_key="finance:鉅亨網 台股",
                    category="💰 財經與總經",
                    summary_prompt="news",
                    published=datetime.now(TW_TZ),
                    tickers=["2330"],
                    event_type="earnings",
                ),
                crawler.Article(
                    title="鴻海月營收",
                    summary="summary",
                    link="https://example.com/2317",
                    source="鉅亨網",
                    source_key="finance:鉅亨網 台股",
                    category="💰 財經與總經",
                    summary_prompt="news",
                    published=datetime.now(TW_TZ),
                    tickers=["2317"],
                    event_type="earnings",
                ),
                crawler.Article(
                    title="聯發科法說",
                    summary="summary",
                    link="https://example.com/2454",
                    source="鉅亨網",
                    source_key="finance:鉅亨網 台股",
                    category="💰 財經與總經",
                    summary_prompt="news",
                    published=datetime.now(TW_TZ),
                    tickers=["2454"],
                    event_type="earnings",
                ),
            ]
        }

        captured: list[str] = []

        def _fake_refresh(tickers, **_kwargs):
            captured.extend(tickers)
            return []

        refresh_tw_financial_reports_for_articles(
            articles,
            max_issuers=2,
            refresh_fn=_fake_refresh,
        )

        self.assertEqual(captured, ["2330", "2317"])

    def test_build_articles_text_includes_tw_financial_context(self):
        from financial_reports import FinancialReport, init_financial_report_store, save_financial_report

        article = crawler.Article(
            title="台積電法說會後市場聚焦資本支出",
            summary="summary",
            body_text="Detailed article body.",
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

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            init_financial_report_store(db_path)
            save_financial_report(
                db_path,
                FinancialReport(
                    market="tw",
                    ticker="2330",
                    company_name="台積電",
                    source_type="twse-openapi",
                    source_confidence="official-openapi",
                    form_type="TWSE-Q",
                    fiscal_year=114,
                    fiscal_period="Q4",
                    period_end="1150325",
                    filed_at="1150325",
                    source_url="https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci",
                    revenue=2894300000.0,
                    eps_diluted=46.32,
                    net_income=1200000000.0,
                ),
            )

            with patch("summarizer.DB_PATH", db_path):
                text = summarizer._build_articles_text([article])

        self.assertIn("財務重點：台股財務資料", text)
        self.assertIn("營收 28.9 億元", text)
        self.assertIn("EPS 46.32", text)


if __name__ == "__main__":
    unittest.main()
