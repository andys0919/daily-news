import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from crawler import Article
import html_generator
from market_data import IndexData, MarketOverview


TW_TZ = timezone(timedelta(hours=8))


def make_article(category: str) -> Article:
    return Article(
        title="Sample title",
        summary="Sample summary",
        link="https://example.com/article",
        source="Example Source",
        source_key=f"{category}:example",
        category=category,
        summary_prompt="news",
        published=datetime.now(TW_TZ),
    )


class DailyMemoReportTests(unittest.TestCase):
    def test_generate_report_prefers_single_daily_memo_over_category_cards(self):
        market = MarketOverview(
            indices=[
                IndexData("S&P 500", "^GSPC", 6000, -10, -0.2, 6010, group="us"),
                IndexData("Gold", "GC=F", 2900, 15, 0.5, 2885, group="metals"),
                IndexData("Silver", "SI=F", 32, 0.4, 1.2, 31.6, group="metals"),
            ],
            timestamp=datetime.now(TW_TZ),
        )
        articles = {"💰 財經與總經": [make_article("💰 財經與總經")]}

        with tempfile.TemporaryDirectory() as tmpdir:
            original_report_dir = html_generator.REPORT_DIR
            html_generator.REPORT_DIR = Path(tmpdir)
            try:
                report_path = html_generator.generate_report(
                    articles,
                    summaries={"💰 財經與總經": "舊分類摘要"},
                    market=market,
                    memo="## 今日主線\n市場正在交易黃金與風險偏好的再平衡。",
                    report_type="daily",
                )
                html = report_path.read_text(encoding="utf-8")
            finally:
                html_generator.REPORT_DIR = original_report_dir
        self.assertIn("🧭 每日整體 Memo", html)
        self.assertIn("今日主線", html)
        self.assertIn("Gold", html)
        self.assertIn("Silver", html)
        self.assertIn("News Source Atlas", html)
        self.assertIn("news-source-atlas.html", html)
        self.assertNotIn("💰 財經與總經", html)
        self.assertNotIn("舊分類摘要", html)
        self.assertNotIn("📎 原始來源附錄", html)

    def test_generate_report_renders_github_title_plus_brief_zh_tw_card(self):
        ai_article = Article(
            title="GitHub Trending: openai/codex keeps rising",
            summary="Codex remains one of the fastest-rising repos today.",
            link="https://github.com/openai/codex",
            source="GitHub Trending (All)",
            source_key="ai_practice:GitHub Trending (All)",
            category="🛠️ AI 工具與實戰",
            summary_prompt="ai_practice",
            published=datetime.now(TW_TZ),
        )
        ai_article_2 = Article(
            title="Trending: modelcontextprotocol/servers momentum",
            summary="MCP servers stack is seeing strong developer momentum.",
            link="https://github.com/modelcontextprotocol/servers",
            source="GitHub Trending (Python)",
            source_key="ai_practice:GitHub Trending (Python)",
            category="🛠️ AI 工具與實戰",
            summary_prompt="ai_practice",
            published=datetime.now(TW_TZ),
        )
        macro_article = make_article("💰 財經與總經")
        articles = {
            "🛠️ AI 工具與實戰": [ai_article, ai_article_2],
            "💰 財經與總經": [macro_article],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            original_report_dir = html_generator.REPORT_DIR
            html_generator.REPORT_DIR = Path(tmpdir)
            try:
                report_path = html_generator.generate_report(
                    articles,
                    summaries={
                        "🛠️ AI 工具與實戰": (
                            "### GitHub 熱門 AI 工具\n"
                            "- **GitHub Trending: openai/codex keeps rising**：正體中文簡單說明 codex 為何值得看。[1]\n"
                            "- **Trending: modelcontextprotocol/servers momentum**：正體中文簡單說明 MCP servers 在做什麼。[2]\n"
                        )
                    },
                    market=None,
                    memo="## 今日主線\n主文仍維持單篇 memo。",
                    citation_links={
                        "🛠️ AI 工具與實戰": {
                            1: ai_article.link,
                            2: ai_article_2.link,
                        }
                    },
                    report_type="daily",
                )
                html = report_path.read_text(encoding="utf-8")
            finally:
                html_generator.REPORT_DIR = original_report_dir

        self.assertIn("🛠️ GitHub 熱門 AI 工具", html)
        self.assertIn("GitHub Trending: openai/codex keeps rising", html)
        self.assertIn("正體中文簡單說明 codex 為何值得看", html)
        self.assertIn("原始來源", html)
        self.assertNotIn("今日最熱 AI 技術", html)
        self.assertNotIn("Codex remains one of the fastest-rising repos today.", html)

    def test_generate_report_keeps_legacy_ai_practice_category_visible(self):
        legacy_ai_article = Article(
            title="microsoft/mcp-for-beginners",
            summary="Legacy rows may not preserve summary_prompt, but should still be surfaced.",
            link="https://github.com/microsoft/mcp-for-beginners",
            source="GitHub Trending (All)",
            source_key="legacy",
            category="🛠️ AI 工具與實戰",
            summary_prompt=None,
            published=datetime.now(TW_TZ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_report_dir = html_generator.REPORT_DIR
            html_generator.REPORT_DIR = Path(tmpdir)
            try:
                report_path = html_generator.generate_report(
                    {"🛠️ AI 工具與實戰": [legacy_ai_article]},
                    summaries={},
                    market=None,
                    memo="## 今日主線\n主文仍維持單篇 memo。",
                    report_type="daily",
                )
                html = report_path.read_text(encoding="utf-8")
            finally:
                html_generator.REPORT_DIR = original_report_dir

        self.assertIn("🛠️ GitHub 熱門 AI 工具", html)
        self.assertIn("microsoft/mcp-for-beginners", html)
        self.assertNotIn(legacy_ai_article.summary, html)

    def test_market_config_includes_gold_and_silver(self):
        config_path = Path(__file__).resolve().parents[1] / "config.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        names = {item["name"] for item in config["market"]["indices"]}

        self.assertIn("Gold", names)
        self.assertIn("Silver", names)

    def test_generate_report_renders_x_trends_group_cards(self):
        x_articles = [
            Article(
                title="OpenAI ships new model capability",
                summary="Official lab update.",
                link="https://x.com/OpenAI/status/1",
                source="X @OpenAI",
                source_key="x_trends:X @OpenAI",
                category="🔥 X 社群熱議",
                summary_prompt="x_trends",
                published=datetime.now(TW_TZ),
                topics=["x_group_labs"],
            ),
            Article(
                title="OpenAIDevs adds new Codex integration",
                summary="Developer tool workflow update.",
                link="https://x.com/OpenAIDevs/status/2",
                source="X @OpenAIDevs",
                source_key="x_trends:X @OpenAIDevs",
                category="🔥 X 社群熱議",
                summary_prompt="x_trends",
                published=datetime.now(TW_TZ),
                topics=["x_group_devtools"],
            ),
            Article(
                title="vLLM posts new inference benchmark",
                summary="Infra and deployment note.",
                link="https://x.com/vllm_project/status/3",
                source="X @vllm_project",
                source_key="x_trends:X @vllm_project",
                category="🔥 X 社群熱議",
                summary_prompt="x_trends",
                published=datetime.now(TW_TZ),
                topics=["x_group_infra"],
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            original_report_dir = html_generator.REPORT_DIR
            html_generator.REPORT_DIR = Path(tmpdir)
            try:
                report_path = html_generator.generate_report(
                    {"🔥 X 社群熱議": x_articles},
                    summaries={},
                    market=None,
                    memo="## 今日主線\nX watchlist 分組測試。",
                    report_type="daily",
                )
                html = report_path.read_text(encoding="utf-8")
            finally:
                html_generator.REPORT_DIR = original_report_dir

        self.assertIn("🔥 X 高訊號分組", html)
        self.assertIn("模型實驗室 / 官方", html)
        self.assertIn("開發工具 / Agent 工作流", html)
        self.assertIn("推理基礎設施 / 部署", html)
        self.assertIn("OpenAI ships new model capability", html)
        self.assertIn("近期", html)
        self.assertIn("高訊號貼文", html)


if __name__ == "__main__":
    unittest.main()
