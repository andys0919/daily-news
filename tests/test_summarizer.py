import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from crawler import Article
import summarizer


TW_TZ = timezone(timedelta(hours=8))


def make_article(
    *,
    title: str,
    link: str,
    source: str,
    source_key: str,
    category: str,
    summary_prompt: str,
    summary: str = "has details",
) -> Article:
    return Article(
        title=title,
        summary=summary,
        link=link,
        source=source,
        source_key=source_key,
        category=category,
        summary_prompt=summary_prompt,
        published=datetime.now(TW_TZ),
    )


class SummarizerTests(unittest.TestCase):
    def test_build_all_citation_links_returns_numeric_mapping(self):
        category = "💰 財經與總經"
        article = make_article(
            title="Fed keeps rates unchanged",
            link="https://reuters.com/world/us/fed-keeps-rates",
            source="Reuters",
            source_key="macro:Reuters",
            category=category,
            summary_prompt="news",
        )
        links = summarizer.build_all_citation_links({category: [article]})
        self.assertEqual(links[category], {1: article.link})

    def test_ai_practice_uses_deterministic_hotlist_without_llm(self):
        category = "🛠️ AI 工具與實戰"
        articles = [
            make_article(
                title="Trending: openai/codex is rising",
                link="https://github.com/openai/codex",
                source="GitHub Trending (All)",
                source_key="ai_practice:GitHub Trending (All)",
                category=category,
                summary_prompt="ai_practice",
            ),
            make_article(
                title="Trending: modelcontextprotocol/servers momentum",
                link="https://github.com/modelcontextprotocol/servers",
                source="GitHub Trending (Python)",
                source_key="ai_practice:GitHub Trending (Python)",
                category=category,
                summary_prompt="ai_practice",
            ),
        ]
        with patch(
            "summarizer._summarize_with_provider",
            side_effect=AssertionError("LLM should not be called for ai_practice"),
        ):
            summary = summarizer.summarize_category(category, articles)

        self.assertIn("熱門開源專案", summary)
        self.assertIn("openai/codex", summary)

    def test_invalid_non_numeric_citations_are_rejected(self):
        category = "💰 財經與總經"
        article = make_article(
            title="US chip export control update",
            link="https://reuters.com/technology/export-control-update",
            source="Reuters",
            source_key="geopolitics:Reuters",
            category=category,
            summary_prompt="news",
        )
        with patch(
            "summarizer._summarize_with_provider",
            side_effect=[
                "### 主軸\n- 政策收緊 [來源]",
                "### 主軸\n- 政策收緊 [來源]",
            ],
        ):
            with self.assertRaises(RuntimeError):
                summarizer.summarize_category(category, [article])

    def test_generate_top10_strips_non_numeric_brackets(self):
        with patch("summarizer._summary_provider", return_value="azure"):
            with patch(
                "summarizer._summarize_with_provider",
                return_value="### 今日主線\n[地緣政治與科技政策] [3]",
            ):
                result = summarizer.generate_top10({}, {"💰 財經與總經": "dummy"})

        self.assertNotIn("[地緣政治與科技政策]", result)
        self.assertIn("[3]", result)

    def test_x_trends_uses_llm_summary_with_content_sections(self):
        category = "🔥 X 社群熱議"
        articles = [
            make_article(
                title="OpenAI releases new reasoning workflow #OpenAI #AI",
                link="https://x.com/openai/status/1",
                source="X @OpenAI",
                source_key="x_trends:X @OpenAI",
                category=category,
                summary_prompt="x_trends",
                summary="討論 OpenAI 新推理流程是否能降低企業導入門檻與成本。",
            ),
            make_article(
                title="NVIDIA Blackwell supply update sparks discussion #NVIDIA #AI",
                link="https://x.com/nvidia/status/2",
                source="X @NVIDIA",
                source_key="x_trends:X @NVIDIA",
                category=category,
                summary_prompt="x_trends",
                summary="社群聚焦 Blackwell 供應節奏與推理成本壓力。",
            ),
            make_article(
                title="MCP agent stack integration guide goes viral #MCP #AI",
                link="https://x.com/someone/status/3",
                source="X @Someone",
                source_key="x_trends:X @Someone",
                category=category,
                summary_prompt="x_trends",
                summary="大量在聊 MCP agent stack 在實務上如何串接工具。",
            ),
        ]

        llm_output = """### 🔥 X 社群熱議 AI 導讀
### 今日在討論什麼（內文）
- OpenAI 新推理流程重點放在企業導入門檻與成本。[1]
- Blackwell 供應節奏與推理成本仍是核心焦點。[2]
- MCP agent stack 串接實作討論快速升溫。[3]
### 主線與背後動機
- 討論主軸集中於可部署性與效率。[1][2]
### 可驗證訊號
- 追蹤官方發布與部署案例是否持續增加。[1][2][3]
### 影響與機會（若有）
- 目前可見 API 平台與工具鏈整合需求升溫。[1][3]
### 代表性貼文
- OpenAI workflow 討論具體提到成本與導入門檻。[1]
### 48h 行動清單
- 觀察是否出現連續兩天的官方部署更新。[1][2][3]
"""
        with patch(
            "summarizer._summarize_with_provider",
            return_value=llm_output,
        ) as mocked_provider:
            summary = summarizer.summarize_category(category, articles)

        self.assertGreaterEqual(mocked_provider.call_count, 1)
        self.assertIn("AI 導讀", summary)
        self.assertIn("今日在討論什麼（內文）", summary)
        self.assertIn("主線與背後動機", summary)
        self.assertIn("影響與機會（若有）", summary)
        self.assertIn("推理流程", summary)
        self.assertRegex(summary, r"\[\d+\]")

    def test_x_trends_prompt_enforces_content_first_guidance(self):
        category = "🔥 X 社群熱議"
        articles = [
            make_article(
                title="OpenAI policy thread sparks debate",
                link="https://x.com/openai/status/100",
                source="X @OpenAI",
                source_key="x_trends:X @OpenAI",
                category=category,
                summary_prompt="x_trends",
                summary="貼文內容討論模型安全政策如何影響企業導入節奏。",
            )
        ]
        prompt = summarizer.build_prompt(category, articles, "x_trends")

        self.assertIn("社群在討論什麼（內文）", prompt)
        self.assertIn("主線與背後動機", prompt)
        self.assertIn("代表性貼文", prompt)
        self.assertIn("不可只列來源或連結；必須先講內容。", prompt)

    def test_x_trends_summary_includes_numeric_citations(self):
        category = "🔥 X 社群熱議"
        articles = [
            make_article(
                title="Claude workflow thread gets attention #Claude #AI",
                link="https://x.com/anthropicai/status/10",
                source="X @AnthropicAI",
                source_key="x_trends:X @AnthropicAI",
                category=category,
                summary_prompt="x_trends",
            ),
            make_article(
                title="GPU cluster tuning notes #GPU #AI",
                link="https://x.com/infra/status/11",
                source="X @Infra",
                source_key="x_trends:X @Infra",
                category=category,
                summary_prompt="x_trends",
            ),
        ]

        with patch(
            "summarizer._summarize_with_provider",
            return_value=(
                "### 🔥 X 社群熱議 AI 導讀\n"
                "### 今日在討論什麼（內文）\n"
                "- Claude workflow 討論升溫。[1]\n"
                "- GPU tuning 討論聚焦成本與吞吐。[2]\n"
                "### 主線與背後動機\n"
                "- 主軸為可部署性與效率。[1][2]\n"
                "### 可驗證訊號\n"
                "- 關注官方部署案例。[1][2]\n"
                "### 影響與機會（若有）\n"
                "- 目前仍屬早期訊號。[1][2]\n"
                "### 代表性貼文\n"
                "- Claude workflow thread。[1]\n"
                "### 48h 行動清單\n"
                "- 追蹤是否有後續版本更新。[1][2]\n"
            ),
        ):
            summary = summarizer.summarize_category(category, articles)
        self.assertRegex(summary, r"\[\d+\]")

    def test_clean_x_discussion_text_removes_transport_noise(self):
        raw = "x.com/openai/status/10 &nbsp; MCP agent launch https://x.com/abc"
        cleaned = summarizer._clean_x_discussion_text(raw)
        self.assertNotIn("x.com", cleaned.lower())
        self.assertNotIn("nbsp", cleaned.lower())
        self.assertIn("MCP agent launch", cleaned)


if __name__ == "__main__":
    unittest.main()
