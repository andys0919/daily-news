import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import crawler
import summarizer


TW_TZ = timezone(timedelta(hours=8))


class NewsEnrichmentTests(unittest.TestCase):
    def test_init_db_adds_enrichment_columns_and_hydrates_new_fields(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            db_path = temp_dir / "news.db"
            cfg_path = temp_dir / "config.yaml"
            cfg_path.write_text(
                """
feeds:
  finance:
    category: "💰 財經與總經"
    sources: []
                """.strip(),
                encoding="utf-8",
            )

            with patch.object(crawler, "DB_PATH", db_path), patch.object(
                crawler, "CONFIG_PATH", cfg_path
            ):
                crawler.init_db()
                conn = sqlite3.connect(str(db_path))
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(articles)").fetchall()
                }
                expected_columns = {
                    "source_key",
                    "summary_prompt",
                    "source_priority",
                    "source_quality",
                    "feed_key",
                    "region",
                    "topics_json",
                    "published_raw",
                    "published_confidence",
                    "body_text",
                    "body_source",
                    "extraction_status",
                    "publisher",
                    "author",
                    "companies_json",
                    "tickers_json",
                    "event_type",
                    "event_key",
                }
                self.assertTrue(expected_columns.issubset(columns))

                published_at = datetime.now(TW_TZ) - timedelta(hours=1)
                article = crawler.Article(
                    title="NVIDIA guides Q2 data center revenue higher",
                    summary="RSS summary fallback",
                    body_text="Full article body with guidance details and capex notes.",
                    link="https://example.com/nvda-q2",
                    source="Reuters",
                    source_key="finance:Reuters",
                    category="💰 財經與總經",
                    summary_prompt="news",
                    published=published_at,
                    source_priority=9,
                    source_quality="high",
                    feed_key="finance",
                    region="global",
                    topics=["finance", "earnings"],
                    published_raw=published_at.astimezone(timezone.utc).isoformat(),
                    published_confidence="article",
                    body_source="article",
                    extraction_status="success",
                    publisher="Reuters",
                    author="Jane Doe",
                    companies=["NVIDIA"],
                    tickers=["NVDA"],
                    event_type="earnings",
                    event_key="us:nvda:earnings:2026q1",
                )
                crawler.save_article(conn, article)
                conn.commit()
                conn.close()

                recent = crawler.get_recent_articles(hours_back=48)
                loaded = recent["💰 財經與總經"][0]
                self.assertEqual(loaded.source_key, "finance:Reuters")
                self.assertEqual(loaded.summary_prompt, "news")
                self.assertEqual(loaded.body_text, article.body_text)
                self.assertEqual(loaded.publisher, "Reuters")
                self.assertEqual(loaded.tickers, ["NVDA"])
                self.assertEqual(loaded.event_key, "us:nvda:earnings:2026q1")

    def test_extract_article_page_metadata_prefers_structured_fields(self):
        from news_enrichment import extract_article_page_metadata

        html = """
        <html>
          <head>
            <link rel="canonical" href="https://example.com/final-story" />
            <meta property="article:published_time" content="2026-03-28T02:15:00Z" />
            <script type="application/ld+json">
              {
                "@context": "https://schema.org",
                "@type": "NewsArticle",
                "headline": "Apple reports fiscal Q1 results",
                "author": {"@type": "Person", "name": "John Appleseed"},
                "publisher": {"@type": "Organization", "name": "Example News"},
                "datePublished": "2026-03-28T02:15:00Z"
              }
            </script>
          </head>
          <body>
            <article>
              <p>Apple reported revenue of $124.3 billion for the quarter.</p>
              <p>Services gross margin expanded while iPhone sales were roughly flat.</p>
            </article>
          </body>
        </html>
        """

        metadata = extract_article_page_metadata(html, "https://example.com/raw")

        self.assertEqual(metadata["canonical_url"], "https://example.com/final-story")
        self.assertEqual(metadata["publisher"], "Example News")
        self.assertEqual(metadata["author"], "John Appleseed")
        self.assertEqual(metadata["published_raw"], "2026-03-28T02:15:00Z")
        self.assertIn("$124.3 billion", metadata["body_text"])
        self.assertEqual(metadata["body_source"], "article")
        self.assertEqual(metadata["extraction_status"], "success")

    def test_build_article_event_metadata_identifies_earnings_signal(self):
        from news_enrichment import build_article_event_metadata

        article = crawler.Article(
            title="NVIDIA Q1 revenue jumps to $26B as EPS beats prior run-rate",
            summary="NVIDIA said data center demand stayed strong and gave new guidance.",
            body_text="NVIDIA (NASDAQ: NVDA) reported quarterly revenue of $26 billion and EPS of $5.98.",
            link="https://example.com/nvda-q1",
            source="Reuters",
            source_key="finance:Reuters",
            category="💰 財經與總經",
            summary_prompt="news",
            published=datetime(2026, 3, 28, 9, 0, tzinfo=TW_TZ),
        )

        metadata = build_article_event_metadata(article)

        self.assertEqual(metadata["event_type"], "earnings")
        self.assertIn("NVDA", metadata["tickers"])
        self.assertIn("NVIDIA", metadata["companies"])
        self.assertIn("earnings", metadata["event_key"])

    def test_cluster_daily_memo_events_prefers_article_event_key(self):
        base_kwargs = {
            "source": "Reuters",
            "source_key": "finance:Reuters",
            "category": "💰 財經與總經",
            "summary_prompt": "news",
            "published": datetime(2026, 3, 28, 9, 0, tzinfo=TW_TZ),
        }
        prepared = [
            (
                "💰 財經與總經",
                crawler.Article(
                    title="NVIDIA Q1 results top expectations",
                    summary="summary",
                    body_text="body",
                    link="https://example.com/a",
                    event_key="us:nvda:earnings:2026q1",
                    **base_kwargs,
                ),
            ),
            (
                "💰 財經與總經",
                crawler.Article(
                    title="NVDA reports fiscal first-quarter revenue surge",
                    summary="summary",
                    body_text="body",
                    link="https://example.com/b",
                    event_key="us:nvda:earnings:2026q1",
                    **base_kwargs,
                ),
            ),
        ]

        clusters = summarizer._cluster_daily_memo_events(prepared)

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["key"], "us:nvda:earnings:2026q1")
        self.assertEqual(len(clusters[0]["articles"]), 2)

    def test_build_articles_text_prefers_body_text_and_structured_context(self):
        article = crawler.Article(
            title="Microsoft expands AI capex",
            summary="short rss summary",
            body_text="Full article body with detailed capex and Azure demand discussion.",
            link="https://example.com/msft",
            source="CNBC",
            source_key="tech:CNBC",
            category="🏢 科技廠動態",
            summary_prompt="tech_industry",
            published=datetime(2026, 3, 28, 9, 0, tzinfo=TW_TZ),
            companies=["Microsoft"],
            tickers=["MSFT"],
            event_type="capex",
            event_key="us:msft:capex:2026-03-28",
        )

        text = summarizer._build_articles_text([article])

        self.assertIn("Full article body with detailed capex", text)
        self.assertIn("公司：Microsoft", text)
        self.assertIn("代號：MSFT", text)
        self.assertIn("事件：capex", text)
        self.assertNotIn("short rss summary", text)

    def test_broker_research_article_extracts_ticker(self):
        from news_enrichment import build_article_event_metadata

        class FakeArticle:
            title = "Net Interest: deep dive on JPM and the regional bank squeeze"
            body_text = "Trading $JPM at 1.5x book makes sense if NII normalizes."
            summary = ""
            published = datetime(2026, 5, 1, 12, 0)

        meta = build_article_event_metadata(FakeArticle())
        self.assertIn("JPM", meta["tickers"])

    def test_ir_materials_article_classified_as_filing(self):
        from news_enrichment import build_article_event_metadata

        class FakeArticle:
            title = "Apple Inc. files Form 8-K disclosing material change"
            body_text = "Form 8-K with disclosure under Item 1.01."
            summary = ""
            published = datetime(2026, 5, 1, 12, 0)

        meta = build_article_event_metadata(FakeArticle())
        self.assertEqual(meta["event_type"], "filing")

    def test_insider_holdings_article_extracts_ticker(self):
        from news_enrichment import build_article_event_metadata

        class FakeArticle:
            title = "Berkshire Hathaway 13F shows new stake in (NASDAQ: AAPL)"
            body_text = "13F-HR disclosure dated April 2026."
            summary = ""
            published = datetime(2026, 5, 1, 12, 0)

        meta = build_article_event_metadata(FakeArticle())
        self.assertIn("AAPL", meta["tickers"])

    def test_macro_data_article_classified_as_policy_when_relevant(self):
        from news_enrichment import build_article_event_metadata

        class FakeArticle:
            title = "Fed FEDS note on tariff transmission to inflation"
            body_text = "Discussion of recent tariff regime and macro impact."
            summary = ""
            published = datetime(2026, 5, 1, 12, 0)

        meta = build_article_event_metadata(FakeArticle())
        self.assertEqual(meta["event_type"], "policy")


if __name__ == "__main__":
    unittest.main()
