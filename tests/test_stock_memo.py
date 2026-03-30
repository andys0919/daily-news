import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crawler import Article
from financial_reports import FinancialReport, init_financial_report_store, save_financial_report


TW_TZ = timezone(timedelta(hours=8))


def _article(
    *,
    title: str,
    link: str,
    source: str,
    category: str,
    ticker: str,
    company_name: str,
    event_type: str,
    event_key: str,
) -> Article:
    return Article(
        title=title,
        summary="summary",
        link=link,
        source=source,
        source_key=f"{category}:{source}",
        category=category,
        summary_prompt="news",
        published=datetime.now(TW_TZ),
        tickers=[ticker],
        companies=[company_name],
        event_type=event_type,
        event_key=event_key,
    )


class StockMemoTests(unittest.TestCase):
    def test_render_tw_stock_memo_includes_official_materials_and_related_news(self):
        import stock_memo

        tw_article = _article(
            title="台積電法說聚焦 AI 需求與 CoWoS",
            link="https://example.com/2330-earnings",
            source="經濟日報",
            category="💰 財經與總經",
            ticker="2330",
            company_name="台積電",
            event_type="earnings",
            event_key="tw:2330:earnings:2026q1",
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
                    source_type="mops-api",
                    source_confidence="official-mops",
                    form_type="MOPS-Q",
                    fiscal_year=114,
                    fiscal_period="Q4",
                    period_end="114Q4",
                    filed_at="114Q4",
                    source_url="https://mops.twse.com.tw/mops/api/t164sb04",
                    report_kind="quarterly",
                    revenue=3809054272.0,
                    eps_diluted=66.26,
                    guidance_summary="會計師意見：標準式無保留核閱報告（114Q4）",
                    filing_excerpt="資產總額 1,000,000、負債總額 400,000",
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
                    source_url="https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
                    report_kind="monthly_revenue",
                    monthly_revenue=260009000.0,
                ),
            )

            packet = stock_memo.collect_stock_memo_packet(
                ticker="2330",
                market="tw",
                db_path=db_path,
                articles_by_category={"💰 財經與總經": [tw_article]},
                refresh_official_data=False,
            )
            text = stock_memo.render_stock_memo(packet)

        self.assertIn("台積電 (2330)", text)
        self.assertIn("FY114 Q4", text)
        self.assertIn("11502 月營收", text)
        self.assertIn("MOPS 法人說明會查詢", text)
        self.assertIn("TWSE 法人說明會影音", text)
        self.assertIn("台積電法說聚焦 AI 需求與 CoWoS", text)

    def test_render_us_stock_memo_includes_sec_materials_and_filing_highlights(self):
        import stock_memo

        us_article = _article(
            title="NVIDIA earnings reinforce AI data center capex cycle",
            link="https://example.com/nvda-earnings",
            source="Reuters",
            category="💰 財經與總經",
            ticker="NVDA",
            company_name="NVIDIA",
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
                    cik="0001045810",
                    source_type="sec-companyfacts",
                    source_confidence="official",
                    form_type="10-Q",
                    fiscal_year=2026,
                    fiscal_period="Q1",
                    period_end="2026-01-31",
                    filed_at="2026-02-25",
                    source_url="https://www.sec.gov/Archives/edgar/data/1045810/filing.htm",
                    report_kind="quarterly",
                    revenue=26000000000.0,
                    eps_diluted=5.98,
                    free_cash_flow=16800000000.0,
                    guidance_summary="Management said AI demand remains above current supply.",
                    filing_excerpt="Data center revenue accelerated on hyperscaler demand.",
                    payload_json='{"submissions":{"form_type":"10-Q","source_url":"https://www.sec.gov/Archives/edgar/data/1045810/filing.htm"}}',
                ),
            )

            packet = stock_memo.collect_stock_memo_packet(
                ticker="NVDA",
                market="us",
                db_path=db_path,
                articles_by_category={"💰 財經與總經": [us_article]},
                refresh_official_data=False,
            )
            text = stock_memo.render_stock_memo(packet)

        self.assertIn("NVIDIA (NVDA)", text)
        self.assertIn("10-Q", text)
        self.assertIn("EPS 5.98", text)
        self.assertIn("SEC CompanyFacts API", text)
        self.assertIn("SEC Submissions API", text)
        self.assertIn("https://www.sec.gov/Archives/edgar/data/1045810/filing.htm", text)
        self.assertIn("AI demand remains above current supply", text)
        self.assertIn("NVIDIA earnings reinforce AI data center capex cycle", text)

    def test_write_stock_memo_saves_markdown_file(self):
        import stock_memo

        article = _article(
            title="Apple filing highlights services resilience",
            link="https://example.com/aapl-filing",
            source="WSJ",
            category="💰 財經與總經",
            ticker="AAPL",
            company_name="Apple",
            event_type="filing",
            event_key="us:aapl:filing:2026q1",
        )

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "news.db"
            output_path = Path(td) / "aapl-memo.md"
            init_financial_report_store(db_path)
            save_financial_report(
                db_path,
                FinancialReport(
                    market="us",
                    ticker="AAPL",
                    company_name="Apple",
                    cik="0000320193",
                    source_type="sec-companyfacts",
                    source_confidence="official",
                    form_type="10-Q",
                    fiscal_year=2026,
                    fiscal_period="Q1",
                    period_end="2025-12-27",
                    filed_at="2026-01-30",
                    source_url="https://www.sec.gov/Archives/edgar/data/320193/filing.htm",
                    report_kind="quarterly",
                    revenue=143756000000.0,
                    eps_diluted=6.45,
                ),
            )

            returned_path = stock_memo.write_stock_memo(
                ticker="AAPL",
                market="us",
                db_path=db_path,
                articles_by_category={"💰 財經與總經": [article]},
                refresh_official_data=False,
                output_path=output_path,
            )

            self.assertEqual(returned_path, output_path)
            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")

        self.assertIn("Apple (AAPL)", content)
        self.assertIn("SEC CompanyFacts API", content)


if __name__ == "__main__":
    unittest.main()
