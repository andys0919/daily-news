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

    def test_broker_research_category_present(self):
        config = _load_config()
        feeds = config.get("feeds", {})
        agents = config.get("category_agents", {})

        self.assertIn("broker_research", agents)
        self.assertIn("broker_research", feeds)

        broker = feeds["broker_research"]
        self.assertEqual(broker.get("category"), "📊 券商與分析師研究")

        names = {s.get("name", "") for s in broker.get("sources", [])}
        self.assertIn("Damodaran Blog", names)
        self.assertIn("Doomberg", names)
        self.assertIn("Net Interest", names)
        self.assertIn("Mostly Borrowed Ideas", names)
        self.assertIn("Topdown Charts", names)
        self.assertIn("Lyn Alden", names)
        self.assertIn("Epsilon Theory", names)
        self.assertIn("Howard Marks Memos", names)
        self.assertIn("Verdad Capital", names)
        self.assertIn("Goldman Insights (Google News)", names)

        for source in broker["sources"]:
            self.assertIn("url", source)
            self.assertIn("priority", source)
            self.assertEqual(source.get("summary_prompt"), "broker_research")

    def test_ir_materials_category_present(self):
        config = _load_config()
        feeds = config.get("feeds", {})
        agents = config.get("category_agents", {})

        self.assertIn("ir_materials", agents)
        self.assertIn("ir_materials", feeds)

        ir = feeds["ir_materials"]
        self.assertEqual(ir.get("category"), "🏛️ 法說與 IR 材料")

        names = {s.get("name", "") for s in ir.get("sources", [])}
        self.assertIn("SEC 8-K Filings (Atom)", names)
        self.assertIn("SEC 10-Q Filings (Atom)", names)
        self.assertIn("SEC 10-K Filings (Atom)", names)
        self.assertIn("Motley Fool Earnings Transcripts", names)
        self.assertIn("NVIDIA Investor Press", names)
        self.assertIn("台股法說會 (Google News)", names)

        for source in ir["sources"]:
            self.assertEqual(source.get("summary_prompt"), "ir_materials")

    def test_insider_holdings_category_present(self):
        config = _load_config()
        feeds = config.get("feeds", {})
        agents = config.get("category_agents", {})

        self.assertIn("insider_holdings", agents)
        self.assertIn("insider_holdings", feeds)

        ih = feeds["insider_holdings"]
        self.assertEqual(ih.get("category"), "👁️ 內部人與機構持股")

        names = {s.get("name", "") for s in ih.get("sources", [])}
        self.assertIn("SEC Form 4 (Atom)", names)
        self.assertIn("SEC 13F-HR (Atom)", names)
        self.assertIn("Insider Monkey", names)
        self.assertIn("WhaleWisdom Blog", names)
        self.assertIn("Berkshire 13F (Google News)", names)
        self.assertIn("Bridgewater 13F (Google News)", names)

        for source in ih["sources"]:
            self.assertEqual(source.get("summary_prompt"), "insider_holdings")

    def test_short_interest_flows_category_present(self):
        config = _load_config()
        feeds = config.get("feeds", {})
        agents = config.get("category_agents", {})

        self.assertIn("short_interest_flows", agents)
        self.assertIn("short_interest_flows", feeds)

        si = feeds["short_interest_flows"]
        self.assertEqual(si.get("category"), "📉 融券與資金流")

        names = {s.get("name", "") for s in si.get("sources", [])}
        self.assertIn("etf.com News", names)
        self.assertIn("ETF Trends", names)
        self.assertIn("ETFGI Press", names)
        self.assertIn("台股融資融券 (Google News)", names)
        self.assertIn("US Short Interest (Google News)", names)

        for source in si["sources"]:
            self.assertEqual(source.get("summary_prompt"), "short_interest_flows")

    def test_macro_data_category_present(self):
        config = _load_config()
        feeds = config.get("feeds", {})
        agents = config.get("category_agents", {})

        self.assertIn("macro_data", agents)
        self.assertIn("macro_data", feeds)

        macro = feeds["macro_data"]
        self.assertEqual(macro.get("category"), "🌐 宏觀與產業數據")

        names = {s.get("name", "") for s in macro.get("sources", [])}
        self.assertIn("Fed Working Papers", names)
        self.assertIn("NBER New Working Papers", names)
        self.assertIn("BIS Working Papers", names)
        self.assertIn("IMF Publications", names)
        self.assertIn("OECD Newsroom", names)
        self.assertIn("World Bank Publications", names)
        self.assertIn("SIA Press", names)
        self.assertIn("SEMI Press", names)
        self.assertIn("行政院主計處 (Google News)", names)
        self.assertIn("中央銀行公告 (Google News)", names)

        for source in macro["sources"]:
            self.assertEqual(source.get("summary_prompt"), "macro_data")


if __name__ == "__main__":
    unittest.main()
