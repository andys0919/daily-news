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
            "研究指引",
            "下一步",
            "法說時間",
            "日曆圖",
            "市場日曆",
            "重要總經",
            "台股事件",
            "美股事件",
            "法人預估",
            "新聞索引",
            "對應新聞",
        ]
        for copy in required_copy:
            self.assertIn(copy, self.index)

        self.assertNotIn("本頁如何使用", self.index)
        self.assertNotIn("details class=\"guide\"", self.index)
        self.assertNotIn("今日研究隊列", self.index)
        self.assertNotIn("高優先研究", self.index)
        self.assertNotIn("風險雷達", self.index)
        self.assertNotIn("最新資料流", self.index)
        self.assertNotIn("最近進來的個股資料", self.index)
        self.assertNotIn("score {item.score}", self.index)
        self.assertNotIn(">score ", self.index)

    def test_homepage_uses_stock_search_data_sources(self):
        self.assertIn('import newsData from "../data/news.json";', self.index)
        self.assertIn('import tickerIndex from "../data/tickers.json";', self.index)
        self.assertIn('import screens from "../data/screens.json";', self.index)
        self.assertIn("actionBoard", self.index)
        self.assertIn("researchQueue", self.index)
        self.assertIn("callEvents", self.index)
        self.assertIn("analystEstimates", self.index)
        self.assertIn("newsIndex", self.index)
        self.assertIn("marketCalendar", self.index)
        self.assertIn("callCalendar", self.index)
        self.assertIn("display_name", self.index)
        self.assertIn("stockSearchItems", self.index)
        self.assertIn("momentumByTicker", self.index)
        self.assertIn("researchQueue.slice(0, 3)", self.index)

    def test_homepage_splits_news_and_calendar_workbench(self):
        self.assertIn('class="news-calendar-workbench"', self.index)
        self.assertIn('class="news-column"', self.index)
        self.assertIn('id="calls" class="calendar-rail"', self.index)
        self.assertIn('class="workbench-panel research-panel"', self.index)
        self.assertIn('class="workbench-panel estimates-panel"', self.index)
        self.assertIn('class="workbench-panel news-index-panel"', self.index)
        self.assertLess(
            self.index.index('class="news-column"'),
            self.index.index('class="calendar-rail"'),
        )

    def test_homepage_has_responsive_search_portal_styles(self):
        required_selectors = [
            ".search-hero",
            ".stock-command",
            ".quick-ticker-grid",
            ".coverage-grid",
            ".source-lane",
            ".ticker-result-list",
            ".ticker-name",
            ".call-calendar",
            ".calendar-day",
            ".calendar-legend",
            ".calendar-event",
            ".calendar-event.macro",
            ".calendar-event.tw-event",
            ".calendar-event.us-event",
            ".news-calendar-workbench",
            ".news-column",
            ".calendar-rail",
            ".workbench-panel",
            ".calendar-rail .call-calendar",
        ]
        for selector in required_selectors:
            self.assertIn(selector, self.css)
        self.assertNotIn(".calendar-event.tw-market", self.css)
        self.assertNotIn(".calendar-event.us-market", self.css)

    def test_homepage_uses_wide_dashboard_shell(self):
        self.assertIn("--shell-max-width: 1680px;", self.css)
        self.assertIn("--shell-gutter: clamp(16px, 2vw, 34px);", self.css)
        self.assertIn("max-width: var(--shell-max-width);", self.css)
        self.assertIn("padding: var(--s-8) var(--shell-gutter) var(--s-12);", self.css)
        self.assertIn("padding: var(--s-4) var(--shell-gutter) var(--s-8);", self.css)
        self.assertIn(
            "grid-template-columns: minmax(680px, 1.45fr) minmax(480px, 0.95fr);",
            self.css,
        )
        self.assertIn("@media (max-width: 1240px)", self.css)

    def test_stock_routes_are_limited_to_search_index(self):
        self.assertIn('import tickerIndex from "../../data/tickers.json";', self.stock_page)
        self.assertIn("allowedTickers", self.stock_page)
        self.assertIn("allowedTickers.has(ticker)", self.stock_page)


if __name__ == "__main__":
    unittest.main()
