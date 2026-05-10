import unittest

import financial_reports as fr


def _make_bundle(**overrides):
    quarterly = fr.FinancialReport(
        market="us",
        ticker="NVDA",
        company_name="NVIDIA",
        source_type="sec",
        form_type="10-Q",
        fiscal_year=2026,
        fiscal_period="Q1",
        period_end="2026-03-31",
        filed_at="2026-04-25",
        source_url="https://example.com",
        report_kind="quarterly",
        revenue=30_000_000_000.0,
    )
    base = dict(
        market="us",
        ticker="NVDA",
        company_name="NVIDIA",
        quarterly=quarterly,
    )
    base.update(overrides)
    return fr.FinancialSnapshotBundle(**base)


class BundleContextTests(unittest.TestCase):
    def test_includes_transcript_excerpt_when_present(self):
        bundle = _make_bundle(
            latest_transcript={
                "title": "NVDA Q1 transcript",
                "body_text": "Blackwell ramp drives data center revenue.",
                "material_type": "transcript",
            }
        )
        context = fr.format_financial_snapshot_bundle_context(bundle)
        self.assertIn("Blackwell", context)

    def test_includes_short_interest_line_when_present(self):
        bundle = _make_bundle(
            short_interest={
                "short_interest": 200000.0,
                "days_to_cover": 1.5,
                "short_interest_ratio": 0.05,
                "source": "FINRA",
            }
        )
        context = fr.format_financial_snapshot_bundle_context(bundle)
        self.assertIn("融券", context)

    def test_includes_insider_summary_when_present(self):
        bundle = _make_bundle(
            recent_insider_summary={
                "count": 3,
                "buys": 1,
                "sells": 2,
                "latest": {"insider_name": "Cook", "transaction_type": "S"},
            }
        )
        context = fr.format_financial_snapshot_bundle_context(bundle)
        self.assertIn("3", context)
        self.assertIn("內部人", context)


if __name__ == "__main__":
    unittest.main()
