import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class DashboardHomepageContractTests(unittest.TestCase):
    def setUp(self):
        self.index = (ROOT / "web" / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
        self.stock_page = (ROOT / "web" / "src" / "pages" / "stocks" / "[ticker].astro").read_text(encoding="utf-8")
        self.css = (ROOT / "web" / "src" / "styles" / "global.css").read_text(encoding="utf-8")

    def test_homepage_is_stock_search_portal_not_research_queue(self):
        required_copy = [
            "個股快搜",
            "即時個股資訊入口",
            "即時新聞",
            "法人 / 分析師",
            "財報",
            "電話會議",
            "快速搜尋",
            "熱門快搜",
            "相關資料入口",
        ]
        for copy in required_copy:
            self.assertIn(copy, self.index)

        self.assertNotIn("本頁如何使用", self.index)
        self.assertNotIn("details class=\"guide\"", self.index)
        self.assertNotIn("今日研究隊列", self.index)
        self.assertNotIn("高優先研究", self.index)
        self.assertNotIn("風險雷達", self.index)

    def test_homepage_uses_stock_search_data_sources(self):
        self.assertIn('import newsData from "../data/news.json";', self.index)
        self.assertIn('import tickerIndex from "../data/tickers.json";', self.index)
        self.assertIn('import screens from "../data/screens.json";', self.index)
        self.assertIn("stockSearchItems", self.index)
        self.assertIn("callArticles", self.index)
        self.assertIn("momentumByTicker", self.index)

    def test_homepage_has_responsive_search_portal_styles(self):
        required_selectors = [
            ".search-hero",
            ".stock-command",
            ".quick-ticker-grid",
            ".coverage-grid",
            ".source-lane",
            ".ticker-result-list",
        ]
        for selector in required_selectors:
            self.assertIn(selector, self.css)

    def test_stock_routes_are_limited_to_search_index(self):
        self.assertIn('import tickerIndex from "../../data/tickers.json";', self.stock_page)
        self.assertIn("allowedTickers", self.stock_page)
        self.assertIn("allowedTickers.has(ticker)", self.stock_page)


if __name__ == "__main__":
    unittest.main()
