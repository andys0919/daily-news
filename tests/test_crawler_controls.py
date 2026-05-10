import asyncio
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import crawler


TW_TZ = timezone(timedelta(hours=8))


def _rss_with_entries(count: int) -> str:
    now = datetime.now(timezone.utc)
    items = []
    for i in range(count):
        pub = (now - timedelta(minutes=i)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        items.append(
            f"""
            <item>
              <title>entry-{i}</title>
              <link>https://example.com/{i}</link>
              <description>summary {i}</description>
              <pubDate>{pub}</pubDate>
            </item>
            """
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>test</title>
        {''.join(items)}
      </channel>
    </rss>
    """


class CrawlerControlsTests(unittest.TestCase):
    def test_load_config_resolves_env_placeholders_recursively(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.yaml"
            cfg_path.write_text(
                """
feeds:
  x_trends:
    category: "🔥 X 社群熱議"
    sources:
      - name: "X @OpenAI"
        preferred_url: "${RSSHUB_URL}/twitter/user/OpenAI"
        fallback_url: "https://example.com/fallback.xml"
                """.strip(),
                encoding="utf-8",
            )

            with patch.object(crawler, "CONFIG_PATH", cfg_path), patch.dict(
                os.environ, {"RSSHUB_URL": "https://rsshub.example.com"}, clear=False
            ):
                config = crawler.load_config()

            source = config["feeds"]["x_trends"]["sources"][0]
            self.assertEqual(
                source["preferred_url"],
                "https://rsshub.example.com/twitter/user/OpenAI",
            )

    def test_normalize_source_config_uses_fallback_when_preferred_url_unresolved(self):
        source_cfg = crawler.normalize_source_config(
            "x_trends",
            {"category": "🔥 X 社群熱議", "summary_prompt": "x_trends"},
            {
                "name": "X @OpenAI",
                "preferred_url": "${RSSHUB_URL}/twitter/user/OpenAI",
                "fallback_url": "https://example.com/fallback.xml",
                "summary_prompt": "x_trends",
            },
        )

        self.assertEqual(source_cfg["url"], "https://example.com/fallback.xml")

    def test_normalize_source_config_prefers_resolved_preferred_url(self):
        source_cfg = crawler.normalize_source_config(
            "x_trends",
            {"category": "🔥 X 社群熱議", "summary_prompt": "x_trends"},
            {
                "name": "X @OpenAI",
                "preferred_url": "https://rsshub.example.com/twitter/user/OpenAI",
                "fallback_url": "https://example.com/fallback.xml",
                "summary_prompt": "x_trends",
            },
        )

        self.assertEqual(
            source_cfg["url"], "https://rsshub.example.com/twitter/user/OpenAI"
        )

    def test_source_health_registry_disables_after_failures_then_recovers(self):
        with tempfile.TemporaryDirectory() as td:
            health_path = Path(td) / "source_health.json"
            now = datetime(2026, 2, 18, 12, 0, tzinfo=TW_TZ)
            clock = {"now": now}

            def _now():
                return clock["now"]

            registry = crawler.SourceHealthRegistry(
                path=health_path,
                disable_threshold=2,
                cooldown_minutes=60,
                now_fn=_now,
            )

            source_key = "finance:WSJ Markets"
            self.assertFalse(registry.is_temporarily_disabled(source_key))

            registry.mark_failure(source_key, reason="http_500")
            self.assertFalse(registry.is_temporarily_disabled(source_key))

            registry.mark_failure(source_key, reason="timeout")
            self.assertTrue(registry.is_temporarily_disabled(source_key))

            clock["now"] = clock["now"] + timedelta(hours=2)
            self.assertFalse(registry.is_temporarily_disabled(source_key))

            registry.mark_success(source_key)
            self.assertFalse(registry.is_temporarily_disabled(source_key))

    def test_crawl_source_applies_per_source_max_articles(self):
        source_cfg = {
            "name": "Test Source",
            "url": "https://example.com/feed.xml",
            "active": True,
            "max_articles": 2,
            "summary_prompt": "news",
            "default_prompt": "news",
            "source_key": "test:source",
            "feed_category": "💰 財經與總經",
        }

        async def _run():
            with patch(
                "crawler.fetch_feed",
                new=AsyncMock(return_value=_rss_with_entries(6)),
            ):
                return await crawler.crawl_source(
                    session=object(),
                    source_config=source_cfg,
                    hours_back=24,
                    semaphore=asyncio.Semaphore(1),
                )

        articles = asyncio.run(_run())
        self.assertEqual(len(articles), 2)

    def test_crawl_source_falls_back_when_primary_feed_fails(self):
        source_cfg = {
            "name": "X @OpenAI",
            "url": "https://rsshub.example.com/twitter/user/OpenAI",
            "fallback_url": "https://example.com/fallback.xml",
            "active": True,
            "max_articles": 2,
            "summary_prompt": "x_trends",
            "default_prompt": "x_trends",
            "source_key": "x_trends:X @OpenAI",
            "feed_category": "🔥 X 社群熱議",
        }
        seen_urls: list[str] = []

        async def _fake_fetch(_session, url):
            seen_urls.append(url)
            if "rsshub.example.com" in url:
                return None
            return _rss_with_entries(2)

        async def _run():
            with patch("crawler.fetch_feed", new=AsyncMock(side_effect=_fake_fetch)):
                return await crawler.crawl_source(
                    session=object(),
                    source_config=source_cfg,
                    hours_back=24,
                    semaphore=asyncio.Semaphore(1),
                )

        articles = asyncio.run(_run())
        self.assertEqual(len(articles), 2)
        self.assertEqual(
            seen_urls,
            [
                "https://rsshub.example.com/twitter/user/OpenAI",
                "https://example.com/fallback.xml",
            ],
        )

    def test_get_recent_articles_applies_category_quota(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            db_path = temp_dir / "news.db"
            cfg_path = temp_dir / "config.yaml"
            cfg_path.write_text(
                """
feeds:
  finance:
    category: "💰 財經與總經"
    category_quota: 2
    sources: []
                """.strip(),
                encoding="utf-8",
            )

            with patch.object(crawler, "DB_PATH", db_path), patch.object(
                crawler, "CONFIG_PATH", cfg_path
            ):
                crawler.init_db()
                conn = sqlite3.connect(str(db_path))
                now = datetime.now(TW_TZ)
                for i in range(4):
                    article = crawler.Article(
                        title=f"title-{i}",
                        summary="summary",
                        link=f"https://example.com/a-{i}",
                        source="Test",
                        source_key="finance:Test",
                        category="💰 財經與總經",
                        summary_prompt="news",
                        published=now - timedelta(minutes=i),
                    )
                    crawler.save_article(conn, article)
                conn.commit()
                conn.close()

                recent = crawler.get_recent_articles(hours_back=24)
                self.assertIn("💰 財經與總經", recent)
                self.assertEqual(len(recent["💰 財經與總經"]), 2)


if __name__ == "__main__":
    unittest.main()
