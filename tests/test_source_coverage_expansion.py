import unittest
from datetime import datetime, timedelta, timezone

from crawler import Article
from news_enrichment import build_article_event_metadata


TW_TZ = timezone(timedelta(hours=8))


class SourceCoverageExpansionTests(unittest.TestCase):
    def test_build_article_event_metadata_uses_registry_for_tw_alias(self):
        article = Article(
            title="環球晶第三季獲利優於市場預期",
            summary="管理層提到矽晶圓需求逐步改善。",
            link="https://example.com/6488-news",
            source="經濟日報",
            source_key="finance:經濟日報 股市",
            category="💰 財經與總經",
            summary_prompt="news",
            published=datetime.now(TW_TZ),
        )

        metadata = build_article_event_metadata(article)

        self.assertIn("6488", metadata["tickers"])
        self.assertIn("環球晶", metadata["companies"])

    def test_build_article_event_metadata_uses_registry_for_us_alias(self):
        article = Article(
            title="Berkshire trims Apple stake and raises cash",
            summary="Buffett discussed capital allocation and insurance float.",
            link="https://example.com/brk-news",
            source="Reuters",
            source_key="finance:Reuters",
            category="💰 財經與總經",
            summary_prompt="news",
            published=datetime.now(TW_TZ),
        )

        metadata = build_article_event_metadata(article)

        self.assertIn("BRK-B", metadata["tickers"])
        self.assertIn("Berkshire", metadata["companies"])


if __name__ == "__main__":
    unittest.main()
