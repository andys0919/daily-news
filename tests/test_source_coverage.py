import unittest
from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def _load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


class SourceCoverageTests(unittest.TestCase):
    def test_deep_analysis_feed_exists_with_curated_sources(self):
        feeds = _load_config().get("feeds", {})
        self.assertIn("deep_analysis", feeds)

        deep = feeds["deep_analysis"]
        self.assertEqual(deep.get("category"), "🧭 深度觀點與分析")
        sources = deep.get("sources", [])
        self.assertGreaterEqual(len(sources), 8)

        names = {s.get("name", "") for s in sources}
        self.assertIn("Stratechery", names)
        self.assertIn("The Pragmatic Engineer", names)
        self.assertIn("War on the Rocks", names)

    def test_ai_practice_includes_discussion_sources(self):
        feeds = _load_config().get("feeds", {})
        ai_practice = feeds.get("ai_practice", {})
        urls = {s.get("url", "") for s in ai_practice.get("sources", [])}

        self.assertIn("https://www.reddit.com/r/MachineLearning/.rss", urls)
        self.assertIn("https://www.reddit.com/r/LocalLLaMA/.rss", urls)

    def test_finance_has_macro_policy_depth_sources(self):
        feeds = _load_config().get("feeds", {})
        finance = feeds.get("finance", {})
        names = {s.get("name", "") for s in finance.get("sources", [])}

        self.assertIn("WSJ Markets", names)
        self.assertIn("WSJ World", names)
        self.assertIn("ECB Press", names)

    def test_finance_includes_official_macro_release_feeds(self):
        feeds = _load_config().get("feeds", {})
        finance = feeds.get("finance", {})
        names = {s.get("name", "") for s in finance.get("sources", [])}

        self.assertIn("BLS Latest Releases", names)
        self.assertIn("FRED Blog", names)
        self.assertIn("BIS Central Bank Speeches", names)
        self.assertIn("BIS Press Releases", names)
        self.assertIn("Liberty Street Economics", names)
        self.assertIn("BIS Statistics", names)
        self.assertIn("Fed Speeches", names)

    def test_semiconductor_and_policy_have_specialized_official_sources(self):
        feeds = _load_config().get("feeds", {})
        semiconductor_names = {
            s.get("name", "") for s in feeds.get("semiconductor", {}).get("sources", [])
        }
        geopolitics_names = {
            s.get("name", "") for s in feeds.get("geopolitics", {}).get("sources", [])
        }

        self.assertIn("Semiconductor Digest", semiconductor_names)
        self.assertIn("NIST Cybersecurity Insights", geopolitics_names)

    def test_known_unstable_sources_are_disabled(self):
        feeds = _load_config().get("feeds", {})

        geopolitics_sources = {
            s.get("name", ""): s for s in feeds.get("geopolitics", {}).get("sources", [])
        }
        semiconductor_sources = {
            s.get("name", ""): s for s in feeds.get("semiconductor", {}).get("sources", [])
        }
        deep_analysis_sources = {
            s.get("name", ""): s for s in feeds.get("deep_analysis", {}).get("sources", [])
        }

        self.assertFalse(geopolitics_sources["日經亞洲"].get("active", True))
        self.assertFalse(semiconductor_sources["WikiChip"].get("active", True))
        self.assertFalse(deep_analysis_sources["The Information"].get("active", True))


if __name__ == "__main__":
    unittest.main()
