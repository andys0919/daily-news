import unittest
from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Test Broker Feed</title><link>https://example.com</link>
<item>
  <title>Quarterly outlook on NVDA — bullish on Blackwell ramp</title>
  <link>https://example.com/post1</link>
  <description>Channel checks suggest NVDA Q2 guidance beat.</description>
  <pubDate>Mon, 01 Jan 2026 00:00:00 +0000</pubDate>
</item>
</channel></rss>
"""


class BrokerResearchFeedsTests(unittest.TestCase):
    def test_config_block_parses_with_required_keys(self):
        config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        broker = config["feeds"]["broker_research"]
        for source in broker["sources"]:
            for key in ("name", "url", "priority", "summary_prompt"):
                self.assertIn(key, source, f"missing {key} on {source.get('name')}")
            self.assertEqual(source["summary_prompt"], "broker_research")

    def test_parser_handles_sample_feed_without_crash(self):
        import feedparser

        parsed = feedparser.parse(SAMPLE_FEED)
        self.assertEqual(parsed.feed.title, "Test Broker Feed")
        self.assertEqual(len(parsed.entries), 1)
        self.assertIn("NVDA", parsed.entries[0].title)
