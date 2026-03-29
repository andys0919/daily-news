import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crawler import Article
from financial_reports import get_financial_snapshot_bundle, init_financial_report_store


class TpexFinancialExpansionTests(unittest.TestCase):
    def test_parse_tpex_company_endpoints_from_company_page(self):
        from tpex_financials import parse_tpex_company_endpoints

        html = """
        <script>
        $.ajax({url: "https://dsp.tpex.org.tw/storage/company_basic/company_basic.php?s=6488&m=21", dataType:"jsonp"});
        $.ajax({url: "https://dsp.tpex.org.tw/storage/finance_report/company_finance_report.php?s=6488&m=21", dataType:"jsonp"});
        </script>
        """

        endpoints = parse_tpex_company_endpoints(html)

        self.assertEqual(endpoints["company_basic"], "https://dsp.tpex.org.tw/storage/company_basic/company_basic.php?s=6488&m=21")
        self.assertEqual(endpoints["finance_report"], "https://dsp.tpex.org.tw/storage/finance_report/company_finance_report.php?s=6488&m=21")

    def test_build_tpex_financial_reports_maps_balance_income_and_cashflow(self):
        from tpex_financials import build_tpex_financial_reports

        finance_payload = {
            "Company_ID": "6488",
            "AccOp": [{"accYear": 2025, "accSeason": 3, "accType": [{"type1": "3 "}]}],
            "Data": [
                {
                    "ReportKind": "A",
                    "year": 2025,
                    "Season": 3,
                    "BookValue": "187.77",
                    "detail": [
                        {"Account_ID_X": "1XXX", "Amont": 215046585},
                        {"Account_ID_X": "2XXX", "Amont": 125276226},
                        {"Account_ID_X": "31XX", "Amont": 89773723},
                    ],
                },
                {
                    "ReportKind": "B",
                    "year": 2025,
                    "Season": 3,
                    "detail": [
                        {"Account_ID_X": "4000", "Amont": 46095865},
                        {"Account_ID_X": "7900", "Amont": 6609220},
                        {"Account_ID_X": "9750", "Amont": 10.68},
                    ],
                },
                {
                    "ReportKind": "C",
                    "year": 2025,
                    "Season": 3,
                    "detail": [
                        {"Account_ID_X": "AAAA", "Amont": 7828249},
                        {"Account_ID_X": "BBBB", "Amont": -33690540},
                        {"Account_ID_X": "CCCC", "Amont": 3077086},
                    ],
                },
            ],
        }
        company_payload = {"COMPANY_ID": "6488", "COMPANY_NAME": "環球晶圓股份有限公司", "MAR_KIND": "otc"}

        reports = build_tpex_financial_reports(
            ticker="6488",
            company_payload=company_payload,
            finance_payload=finance_payload,
        )

        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertEqual(report.ticker, "6488")
        self.assertEqual(report.market, "tw")
        self.assertEqual(report.revenue, 46095865)
        self.assertEqual(report.eps_diluted, 10.68)
        self.assertEqual(report.operating_cash_flow, 7828249)
        self.assertIn("標準式無保留", report.guidance_summary)

    def test_refresh_tpex_financial_reports_for_articles_persists_bundle(self):
        from tpex_financials import refresh_tpex_financial_reports_for_articles

        article = Article(
            title="環球晶法說",
            summary="summary",
            link="https://example.com/6488",
            source="Example",
            source_key="finance:Example",
            category="💰 財經與總經",
            summary_prompt="news",
            published=__import__("datetime").datetime.now(),
            tickers=["6488"],
        )
        company_page_html = """
        <script>
        $.ajax({url: "https://dsp.tpex.org.tw/storage/company_basic/company_basic.php?s=6488&m=21", dataType:"jsonp"});
        $.ajax({url: "https://dsp.tpex.org.tw/storage/finance_report/company_finance_report.php?s=6488&m=21", dataType:"jsonp"});
        </script>
        """
        company_jsonp = 'getCompanyBasic({"COMPANY_ID":"6488","COMPANY_NAME":"環球晶圓股份有限公司","MAR_KIND":"otc"})'
        finance_jsonp = 'getCompanyFinanceReport({"Company_ID":"6488","AccOp":[{"accYear":2025,"accSeason":3,"accType":[{"type1":"3 "}]}],"Data":[{"ReportKind":"B","year":2025,"Season":3,"detail":[{"Account_ID_X":"4000","Amont":46095865},{"Account_ID_X":"9750","Amont":10.68}]},{"ReportKind":"C","year":2025,"Season":3,"detail":[{"Account_ID_X":"AAAA","Amont":7828249}]}]})'

        def _fake_fetch_text(url: str) -> str:
            if "company_basic.php?stk_code=6488" in url:
                return company_page_html
            if "storage/company_basic" in url:
                return company_jsonp
            if "storage/finance_report" in url:
                return finance_jsonp
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            init_financial_report_store(db_path)
            reports = refresh_tpex_financial_reports_for_articles(
                {"💰 財經與總經": [article]},
                db_path=db_path,
                fetch_text=_fake_fetch_text,
            )
            bundle = get_financial_snapshot_bundle(db_path, market="tw", ticker="6488")

        self.assertEqual(len(reports), 1)
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.quarterly.ticker, "6488")
        self.assertIn("標準式無保留", bundle.quarterly.guidance_summary)


if __name__ == "__main__":
    unittest.main()
