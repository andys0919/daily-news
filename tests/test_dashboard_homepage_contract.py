import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class DashboardHomepageContractTests(unittest.TestCase):
    def setUp(self):
        self.index = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
        self.css = (ROOT / "web" / "src" / "styles" / "global.css").read_text(encoding="utf-8")

    def test_homepage_is_investor_research_queue_not_help_page(self):
        required_copy = [
            "今日研究隊列",
            "高優先研究",
            "需要驗證",
            "風險雷達",
            "為什麼現在",
            "下一步查核",
            "風險觸發",
        ]
        for copy in required_copy:
            self.assertIn(copy, self.index)

        self.assertNotIn("本頁如何使用", self.index)
        self.assertNotIn("details class=\"guide\"", self.index)

    def test_homepage_uses_investment_signal_data_sources(self):
        self.assertIn('import screens from "../data/screens.json";', self.index)
        self.assertIn('../data/decisions.json";', self.index)
        self.assertIn("const decisions =", self.index)
        self.assertIn("researchQueue", self.index)
        self.assertIn("momentumByTicker", self.index)

    def test_homepage_has_responsive_research_desk_styles(self):
        required_selectors = [
            ".desk-hero",
            ".idea-grid",
            ".research-card",
            ".signal-lane",
            ".evidence-rail",
        ]
        for selector in required_selectors:
            self.assertIn(selector, self.css)


if __name__ == "__main__":
    unittest.main()
