import tempfile
import unittest
from pathlib import Path

from financial_reports import FinancialReport, get_financial_snapshot_bundle, init_financial_report_store, save_financial_report


class MopsFinancialCompletenessTests(unittest.TestCase):
    def test_build_mops_financial_report_maps_income_balance_and_cashflow(self):
        from mops_financials import build_mops_financial_report

        income_payload = {
            "result": {
                "year": "114",
                "season": "4",
                "companyAbbreviation": "台積電",
                "reportList": [
                    ["營業收入合計", "3,809,054,272", "100.00", "2,894,307,699", "100.00"],
                    ["稅前淨利（淨損）", "2,041,662,840", "53.60", "1,405,838,635", "48.57"],
                    ["本期淨利（淨損）", "1,715,396,780", "45.03", "1,172,431,759", "40.51"],
                    ["　基本每股盈餘", "66.26", "", "45.25", ""],
                ],
            }
        }
        balance_payload = {
            "result": {
                "reportList": [
                    ["　資產總額", "7,933,023,878", "100.00", "6,691,938,000", "100.00"],
                    ["　負債總額", "2,472,228,595", "31.16", "2,368,362,135", "35.39"],
                    ["　權益總額", "5,460,795,283", "68.84", "4,323,575,865", "64.61"],
                ]
            }
        }
        cashflow_payload = {
            "result": {
                "reportList": [
                    ["營業活動之淨現金流入（流出）", "2,274,975,625", "1,826,177,068"],
                    ["　取得不動產、廠房及設備", "-1,272,410,529", "-956,006,536"],
                    ["　投資活動之淨現金流入（流出）", "-1,144,393,407", "-864,842,769"],
                    ["　籌資活動之淨現金流入（流出）", "-440,344,692", "-346,300,910"],
                ]
            }
        }

        report = build_mops_financial_report(
            ticker="2330",
            income_payload=income_payload,
            balance_payload=balance_payload,
            cashflow_payload=cashflow_payload,
        )

        self.assertEqual(report.ticker, "2330")
        self.assertEqual(report.source_type, "mops-api")
        self.assertEqual(report.revenue, 3809054272.0)
        self.assertEqual(report.eps_diluted, 66.26)
        self.assertEqual(report.operating_cash_flow, 2274975625.0)
        self.assertEqual(report.capex, 1272410529.0)
        self.assertEqual(report.net_income, 1715396780.0)

    def test_financial_snapshot_bundle_prefers_mops_quarterly_for_tw(self):
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
                    source_type="mops-api",
                    source_confidence="official-mops",
                    form_type="MOPS-Q",
                    fiscal_year=114,
                    fiscal_period="Q4",
                    period_end="1150325",
                    filed_at="1150325",
                    report_kind="quarterly",
                    revenue=3809054272.0,
                    eps_diluted=66.26,
                    operating_cash_flow=2274975625.0,
                ),
            )

            bundle = get_financial_snapshot_bundle(db_path, market="tw", ticker="2330")

        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.quarterly.source_type, "mops-api")
        self.assertEqual(bundle.quarterly.eps_diluted, 66.26)


if __name__ == "__main__":
    unittest.main()
