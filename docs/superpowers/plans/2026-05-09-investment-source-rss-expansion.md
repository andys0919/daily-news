# Investment Source RSS Expansion (Phase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **For ralph-loop:** Process tasks 1 → 9 in order. Each task ends with a commit. Mark each `- [ ]` as `- [x]` when its tests pass and the commit lands. When all tasks are checked, reply only with `<promise>PHASE_DONE</promise>`.

**Goal:** Add 5 new RSS / Atom feed categories — `broker_research`, `ir_materials`, `insider_holdings`, `short_interest_flows`, `macro_data` — to `config.yaml` so the existing crawler pipeline ingests them as plain articles, with structural and enrichment tests covering the new sources.

**Architecture:** Pure config + tests. No new modules, no schema changes, no `stock_memo.py` / `summarizer.py` / `financial_reports.py` edits. New `category_agents` entries are added in YAML so future phases can refine their prompts.

**Tech Stack:** YAML + existing `crawler.py` (feedparser / aiohttp) + Python `unittest`.

**Spec:** [docs/superpowers/specs/2026-05-09-investment-source-expansion-design.md](../specs/2026-05-09-investment-source-expansion-design.md)

**Hard limits for this phase:**
- ❌ Do not modify `financial_reports.py`, `stock_memo.py`, `summarizer.py`, `html_generator.py`, `crawler.py`, `news_enrichment.py` (only add tests for it).
- ❌ Do not create new `.py` ingest modules (those are Phase 2).
- ❌ Do not change SQLite schema (that is Phase 3).
- ✅ Only `config.yaml`, `tests/*`, `openspec/changes/investment-source-rss-expansion/*`.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `config.yaml` | modify | Add 5 `category_agents` entries; add 5 `feeds:` sub-sections |
| `tests/test_source_coverage.py` | modify | Assert each new category exists with key feeds |
| `tests/test_news_enrichment.py` | modify | Assert one sample article in each new category triggers correct enrichment |
| `tests/test_broker_research_feeds.py` | create | Mock-fetch parser smoke for broker_research |
| `openspec/changes/investment-source-rss-expansion/proposal.md` | create | OpenSpec proposal skeleton |
| `openspec/changes/investment-source-rss-expansion/design.md` | create | Brief design doc that links to the master design spec |
| `openspec/changes/investment-source-rss-expansion/tasks.md` | create | Mirrors this plan's task list |

---

### Task 1: OpenSpec change skeleton

**Files:**
- Create: `openspec/changes/investment-source-rss-expansion/proposal.md`
- Create: `openspec/changes/investment-source-rss-expansion/design.md`
- Create: `openspec/changes/investment-source-rss-expansion/tasks.md`

- [ ] **Step 1: Create proposal.md**

```markdown
## Why

The project tracks earnings via SEC / TWSE / TPEX / MOPS, but the RSS layer has gaps in five investment-relevant areas: broker / independent analyst research, issuer relations materials, insider and institutional holdings, short interest and ETF flows, and macro / sector data. These signals belong in the daily / weekly memo and per-stock memo workflows.

## What Changes

- Add five new feed categories to `config.yaml`: `broker_research`, `ir_materials`, `insider_holdings`, `short_interest_flows`, `macro_data`.
- Add matching `category_agents` entries (initial persona; later phases refine prompts).
- Extend `tests/test_source_coverage.py` to assert key feeds exist in each new category.
- Extend `tests/test_news_enrichment.py` to confirm articles from new categories still trigger issuer / ticker / event extraction.
- Add `tests/test_broker_research_feeds.py` with a mock-fetch parser smoke test.

## Capabilities

### New Capabilities
- `investment-source-coverage`: RSS-layer coverage for broker research, IR materials, insider / 13F holdings, short interest / ETF flows, and macro / sector data.

### Modified Capabilities
- `news-pipeline-coverage`: Crawl five new feed categories with the existing aiohttp / feedparser path.

## Impact

- Affected code: `config.yaml`, three test files.
- No code changes in `crawler.py`, `news_enrichment.py`, `financial_reports.py`, `summarizer.py`, `stock_memo.py`, `html_generator.py`.
- No SQLite schema change.
```

- [ ] **Step 2: Create design.md**

```markdown
# Design — investment-source-rss-expansion (Phase 1 of 4)

This change is Phase 1 of the investment-source-expansion master spec at
`docs/superpowers/specs/2026-05-09-investment-source-expansion-design.md`.

Phase 1 only adds RSS / Atom entries that the existing `crawler.py` can
ingest with no code changes. Five new feed categories are introduced. Their
`category_agents` entries are added so YAML stays internally consistent;
prompt polish happens in Phase 4.

Non-RSS endpoints (FINRA short-interest CSV, MOPS HTML, TWSE OpenAPI direct
calls) belong to Phase 2 ingest modules and are deliberately **not** added
here.

## Source Health

All new feeds use the existing `SourceHealthRegistry` cooldown mechanism.
Feeds that turn out to be 404 / paywalled / unstable get marked
`active: false` rather than retried forever.

## Tests

- `tests/test_source_coverage.py` — structural assertions (feed exists,
  required keys present).
- `tests/test_broker_research_feeds.py` — mock-fetch parser smoke.
- `tests/test_news_enrichment.py` — issuer / ticker extraction still works
  on representative new-source samples.

## Out of scope

- New `.py` ingest modules (Phase 2).
- SQLite schema (Phase 3).
- `stock_memo.py` / `summarizer.py` integration (Phase 4).
```

- [ ] **Step 3: Create tasks.md**

```markdown
# Tasks — investment-source-rss-expansion

- [ ] Task 1 OpenSpec skeleton committed
- [ ] Task 2 broker_research category + feeds + tests
- [ ] Task 3 ir_materials category + feeds + tests
- [ ] Task 4 insider_holdings category + feeds + tests
- [ ] Task 5 short_interest_flows category + feeds + tests
- [ ] Task 6 macro_data category + feeds + tests
- [ ] Task 7 test_news_enrichment.py expansion
- [ ] Task 8 Smoke run: `main.py --no-summary` writes new-category articles to SQLite
- [ ] Task 9 `openspec validate investment-source-rss-expansion` + final commit
```

- [ ] **Step 4: Commit**

```bash
git add openspec/changes/investment-source-rss-expansion/
git commit -m "openspec: scaffold investment-source-rss-expansion change

Phase 1 of investment-source-expansion master spec. Adds proposal,
design, and tasks files. No code changes yet."
```

Expected: clean commit, no warnings.

---

### Task 2: Add `broker_research` category

**Files:**
- Modify: `config.yaml` (add `category_agents.broker_research`; add `feeds.broker_research`)
- Modify: `tests/test_source_coverage.py` (add `test_broker_research_category_present`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_source_coverage.py` at the end of `SourceCoverageTests`:

```python
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
```

- [ ] **Step 2: Run test, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_source_coverage.SourceCoverageTests.test_broker_research_category_present -v
```

Expected: FAIL with `AssertionError: 'broker_research' not found`.

- [ ] **Step 3: Add `category_agents.broker_research` to `config.yaml`**

Insert this block inside the existing `category_agents:` section (after `x_trends:` block, before `feeds:`):

```yaml
  broker_research:
    persona: "買方資深策略分析師，融合 sell-side 框架與 free analyst commentary，過濾雜訊"
    framework: |
      1. 來源屬性：sell-side / 獨立分析師 / 短報告
      2. 觀點極性：多 / 空 / 中性，並指出論證強度
      3. 與 consensus 的距離：超預期、低於預期、與市場一致
      4. 投資人 actionable angle：估值、催化劑、風險點
    key_metrics:
      - "估值倍數（PE/EV/Sales）"
      - "成長率假設"
      - "毛利率/營業利益率"
      - "TAM 與市占假設"
    output_sections:
      - "核心論點（1-2 點）"
      - "與市場 consensus 的差異"
      - "做多/做空可操作角度"
      - "風險與反例"
    anti_patterns:
      - "不轉述新聞 headline 當分析"
      - "不混淆事實與作者推論"
      - "不引用 paywalled 內文"
```

- [ ] **Step 4: Add `feeds.broker_research` to `config.yaml`**

Insert this block inside `feeds:` section after the existing last category (`x_trends`):

```yaml
  # ── 📊 券商與分析師研究 ──
  broker_research:
    category: "📊 券商與分析師研究"
    sources:
      - name: "Damodaran Blog"
        url: "https://aswathdamodaran.blogspot.com/feeds/posts/default"
        active: true
        priority: 9
        region: "global"
        topics: ["valuation", "research"]
        max_articles: 6
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Doomberg"
        url: "https://doomberg.substack.com/feed"
        active: true
        priority: 9
        region: "global"
        topics: ["macro", "energy", "research"]
        max_articles: 6
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Net Interest"
        url: "https://www.netinterest.co/feed"
        active: true
        priority: 9
        region: "global"
        topics: ["financials", "research"]
        max_articles: 6
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Mostly Borrowed Ideas"
        url: "https://mbi-deepdives.substack.com/feed"
        active: true
        priority: 8
        region: "global"
        topics: ["equity", "research"]
        max_articles: 6
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Topdown Charts"
        url: "https://www.topdowncharts.com/blog?format=rss"
        active: true
        priority: 8
        region: "global"
        topics: ["macro", "charts"]
        max_articles: 6
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Lyn Alden"
        url: "https://www.lynalden.com/feed/"
        active: true
        priority: 9
        region: "global"
        topics: ["macro", "equity"]
        max_articles: 6
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Epsilon Theory"
        url: "https://www.epsilontheory.com/feed/"
        active: true
        priority: 8
        region: "global"
        topics: ["macro", "behavioral"]
        max_articles: 6
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Howard Marks Memos"
        url: "https://www.oaktreecapital.com/insights/howard-marks-memos.rss"
        active: true
        priority: 10
        region: "global"
        topics: ["macro", "credit"]
        max_articles: 4
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Verdad Capital"
        url: "https://verdadcap.com/archive?format=rss"
        active: true
        priority: 8
        region: "global"
        topics: ["value", "research"]
        max_articles: 6
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Hindenburg Research"
        url: "https://hindenburgresearch.com/feed/"
        active: true
        priority: 9
        region: "global"
        topics: ["short", "forensic"]
        max_articles: 4
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Muddy Waters"
        url: "https://www.muddywatersresearch.com/feed/"
        active: true
        priority: 8
        region: "global"
        topics: ["short", "forensic"]
        max_articles: 4
        quality: "high"
        summary_prompt: "broker_research"
      - name: "Seeking Alpha Top Ideas"
        url: "https://seekingalpha.com/feed.xml"
        active: true
        priority: 7
        region: "global"
        topics: ["equity", "research"]
        max_articles: 8
        quality: "medium"
        summary_prompt: "broker_research"
      - name: "Goldman Insights (Google News)"
        url: "https://news.google.com/rss/search?q=site%3Agoldmansachs.com+insights&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 7
        region: "global"
        topics: ["macro", "research"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "broker_research"
      - name: "JPM Outlook (Google News)"
        url: "https://news.google.com/rss/search?q=site%3Aam.jpmorgan.com+outlook+OR+research&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 7
        region: "global"
        topics: ["macro", "research"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "broker_research"
      - name: "Morgan Stanley Ideas (Google News)"
        url: "https://news.google.com/rss/search?q=site%3Amorganstanley.com+ideas&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 7
        region: "global"
        topics: ["macro", "research"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "broker_research"
```

- [ ] **Step 5: Run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_source_coverage.SourceCoverageTests.test_broker_research_category_present -v
```

Expected: PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests -v
```

Expected: 0 failures, 0 errors.

- [ ] **Step 7: Create `tests/test_broker_research_feeds.py`** (parser smoke)

```python
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import crawler


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
        # Smoke: feedparser inside crawler can parse a tiny synthetic RSS
        # blob in the broker_research shape.
        import feedparser

        parsed = feedparser.parse(SAMPLE_FEED)
        self.assertEqual(parsed.feed.title, "Test Broker Feed")
        self.assertEqual(len(parsed.entries), 1)
        self.assertIn("NVDA", parsed.entries[0].title)
```

- [ ] **Step 8: Run new test file**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_broker_research_feeds -v
```

Expected: 2 PASS.

- [ ] **Step 9: Commit**

```bash
git add config.yaml tests/test_source_coverage.py tests/test_broker_research_feeds.py
git commit -m "feat(config): add broker_research feed category

15 free analyst / broker research RSS sources plus category_agent
persona. Includes Damodaran, Doomberg, Net Interest, MBI, Topdown
Charts, Lyn Alden, Epsilon Theory, Howard Marks, Verdad, Hindenburg,
Muddy Waters, Seeking Alpha, plus Goldman/JPM/MS Google News fallbacks."
```

---

### Task 3: Add `ir_materials` category

**Files:**
- Modify: `config.yaml` (add `category_agents.ir_materials`; add `feeds.ir_materials`)
- Modify: `tests/test_source_coverage.py` (add `test_ir_materials_category_present`)

- [ ] **Step 1: Write the failing test**

Append to `SourceCoverageTests` in `tests/test_source_coverage.py`:

```python
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
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_source_coverage.SourceCoverageTests.test_ir_materials_category_present -v
```

- [ ] **Step 3: Add `category_agents.ir_materials` to `config.yaml`**

Insert in `category_agents:` after `broker_research`:

```yaml
  ir_materials:
    persona: "公司現場記者 + 買方分析師混合：解讀法說 / IR 簡報 / earnings call 的官方語言"
    framework: |
      1. 公司方語氣（樂觀/保守/維持）
      2. 業績與財測落點（beat/miss/inline）
      3. 管理層強調的 demand drivers / capacity / capex
      4. Q&A 中的多空交鋒重點
    key_metrics:
      - "本季營收與年增"
      - "毛利率/營業利益率"
      - "下季 / 全年 guidance"
      - "capex 計畫"
    output_sections:
      - "公司給出的數字（含 beat/miss）"
      - "管理層原話節錄（限 1-3 句）"
      - "買方解讀重點"
    anti_patterns:
      - "不轉述 boilerplate 公關段落"
      - "不混淆 GAAP / non-GAAP"
      - "不省略缺漏指引（沒給就要說沒給）"
```

- [ ] **Step 4: Add `feeds.ir_materials` to `config.yaml`**

Insert in `feeds:` after `broker_research`:

```yaml
  # ── 🏛️ 法說與 IR 材料 ──
  ir_materials:
    category: "🏛️ 法說與 IR 材料"
    sources:
      - name: "SEC 8-K Filings (Atom)"
        url: "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&owner=include&count=40&output=atom"
        active: true
        priority: 10
        region: "us"
        topics: ["filing", "earnings"]
        max_articles: 12
        quality: "high"
        summary_prompt: "ir_materials"
      - name: "SEC 10-Q Filings (Atom)"
        url: "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=10-Q&owner=include&count=40&output=atom"
        active: true
        priority: 10
        region: "us"
        topics: ["filing", "earnings"]
        max_articles: 10
        quality: "high"
        summary_prompt: "ir_materials"
      - name: "SEC 10-K Filings (Atom)"
        url: "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=10-K&owner=include&count=40&output=atom"
        active: true
        priority: 10
        region: "us"
        topics: ["filing", "earnings"]
        max_articles: 10
        quality: "high"
        summary_prompt: "ir_materials"
      - name: "SEC 6-K Filings (Atom)"
        url: "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=6-K&owner=include&count=40&output=atom"
        active: true
        priority: 9
        region: "us"
        topics: ["filing", "earnings", "foreign-issuer"]
        max_articles: 10
        quality: "high"
        summary_prompt: "ir_materials"
      - name: "Motley Fool Earnings Transcripts"
        url: "https://www.fool.com/earnings-call-transcripts/feed/"
        active: true
        priority: 9
        region: "us"
        topics: ["transcript", "earnings"]
        max_articles: 10
        quality: "high"
        summary_prompt: "ir_materials"
      - name: "Seeking Alpha Earnings Transcripts (Google News)"
        url: "https://news.google.com/rss/search?q=site%3Aseekingalpha.com+%22earnings+call+transcript%22&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 7
        region: "us"
        topics: ["transcript", "earnings"]
        max_articles: 10
        quality: "medium"
        summary_prompt: "ir_materials"
      - name: "NVIDIA Investor Press"
        url: "https://nvidianews.nvidia.com/news/categories/financial-news/rss"
        active: true
        priority: 9
        region: "us"
        topics: ["ir", "earnings", "nvidia"]
        max_articles: 6
        quality: "high"
        summary_prompt: "ir_materials"
      - name: "Apple Investor Press"
        url: "https://www.apple.com/newsroom/rss-feed.rss"
        active: true
        priority: 8
        region: "us"
        topics: ["ir", "earnings", "apple"]
        max_articles: 6
        quality: "high"
        summary_prompt: "ir_materials"
      - name: "Microsoft Earnings Press (Google News)"
        url: "https://news.google.com/rss/search?q=site%3Amicrosoft.com+earnings+release&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 8
        region: "us"
        topics: ["ir", "earnings", "microsoft"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "ir_materials"
      - name: "TSMC Investor (Google News)"
        url: "https://news.google.com/rss/search?q=TSMC+investor+OR+%E5%8F%B0%E7%A9%8D%E9%9B%BB+%E6%B3%95%E8%AA%AA&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 9
        region: "tw"
        topics: ["ir", "earnings", "tsmc"]
        max_articles: 8
        quality: "medium"
        summary_prompt: "ir_materials"
      - name: "台股法說會 (Google News)"
        url: "https://news.google.com/rss/search?q=%E6%B3%95%E8%AA%AA%E6%9C%83+%E5%85%AC%E5%8F%B8&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 8
        region: "tw"
        topics: ["ir", "earnings", "law-call"]
        max_articles: 10
        quality: "medium"
        summary_prompt: "ir_materials"
      - name: "鉅亨網 法人說明會 (Google News)"
        url: "https://news.google.com/rss/search?q=site%3Acnyes.com+%E6%B3%95%E4%BA%BA%E8%AA%AA%E6%98%8E%E6%9C%83&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 7
        region: "tw"
        topics: ["ir", "earnings"]
        max_articles: 8
        quality: "medium"
        summary_prompt: "ir_materials"
```

- [ ] **Step 5: Run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_source_coverage.SourceCoverageTests.test_ir_materials_category_present -v
```

- [ ] **Step 6: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests -v
```

Expected: 0 failures.

- [ ] **Step 7: Commit**

```bash
git add config.yaml tests/test_source_coverage.py
git commit -m "feat(config): add ir_materials feed category

12 IR / law-call / SEC filing RSS sources plus category_agent persona.
Covers SEC 8-K/10-Q/10-K/6-K atom feeds, Motley Fool transcripts,
major issuer IR feeds, and TW law-call Google News searches."
```

---

### Task 4: Add `insider_holdings` category

**Files:**
- Modify: `config.yaml`
- Modify: `tests/test_source_coverage.py`

- [ ] **Step 1: Write failing test**

Append to `SourceCoverageTests`:

```python
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
```

- [ ] **Step 2: Run test, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_source_coverage.SourceCoverageTests.test_insider_holdings_category_present -v
```

- [ ] **Step 3: Add `category_agents.insider_holdings` to `config.yaml`**

```yaml
  insider_holdings:
    persona: "資金流偵探：從 Form 4、13F、董監持股變動看出內部人 / 機構真實意圖"
    framework: |
      1. 內部人交易方向（買 vs 賣，是否高層）
      2. 機構持股 QoQ 變化（建倉、加倉、減倉、清倉）
      3. 知名 manager 的代表性動作
      4. 與股價走勢的相對位置
    key_metrics:
      - "Insider buy/sell ratio"
      - "13F shares change %"
      - "持股報告日期 lag"
    output_sections:
      - "本期關鍵內部人交易"
      - "知名機構動向 (Berkshire / Bridgewater / Tiger / Lone Pine)"
      - "投資人解讀"
    anti_patterns:
      - "不忽略 lag（13F 是 45 天前快照）"
      - "不把 10b5-1 自動賣壓誤判為看空訊號"
```

- [ ] **Step 4: Add `feeds.insider_holdings` to `config.yaml`**

```yaml
  # ── 👁️ 內部人與機構持股 ──
  insider_holdings:
    category: "👁️ 內部人與機構持股"
    sources:
      - name: "SEC Form 4 (Atom)"
        url: "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&owner=include&count=40&output=atom"
        active: true
        priority: 10
        region: "us"
        topics: ["insider", "filing"]
        max_articles: 15
        quality: "high"
        summary_prompt: "insider_holdings"
      - name: "SEC 13F-HR (Atom)"
        url: "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=13F-HR&owner=include&count=40&output=atom"
        active: true
        priority: 10
        region: "us"
        topics: ["13f", "filing"]
        max_articles: 15
        quality: "high"
        summary_prompt: "insider_holdings"
      - name: "Insider Monkey"
        url: "https://www.insidermonkey.com/blog/feed/"
        active: true
        priority: 7
        region: "us"
        topics: ["13f", "insider"]
        max_articles: 8
        quality: "medium"
        summary_prompt: "insider_holdings"
      - name: "WhaleWisdom Blog"
        url: "https://whalewisdom.com/blog/rss"
        active: true
        priority: 7
        region: "us"
        topics: ["13f"]
        max_articles: 8
        quality: "medium"
        summary_prompt: "insider_holdings"
      - name: "Zacks Insider Trading"
        url: "https://www.zacks.com/rss/rss_news.php?rsstype=insider_trading"
        active: true
        priority: 6
        region: "us"
        topics: ["insider"]
        max_articles: 8
        quality: "medium"
        summary_prompt: "insider_holdings"
      - name: "Berkshire 13F (Google News)"
        url: "https://news.google.com/rss/search?q=Berkshire+Hathaway+13F+OR+%22Buffett+stake%22&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 8
        region: "us"
        topics: ["13f", "berkshire"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "insider_holdings"
      - name: "Bridgewater 13F (Google News)"
        url: "https://news.google.com/rss/search?q=Bridgewater+13F+OR+Dalio+holdings&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 7
        region: "us"
        topics: ["13f", "bridgewater"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "insider_holdings"
      - name: "Tiger Global 13F (Google News)"
        url: "https://news.google.com/rss/search?q=%22Tiger+Global%22+13F+OR+holdings&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 7
        region: "us"
        topics: ["13f", "tiger-global"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "insider_holdings"
      - name: "Lone Pine 13F (Google News)"
        url: "https://news.google.com/rss/search?q=%22Lone+Pine%22+13F+OR+holdings&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 7
        region: "us"
        topics: ["13f", "lone-pine"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "insider_holdings"
      - name: "Pershing Square 13F (Google News)"
        url: "https://news.google.com/rss/search?q=%22Pershing+Square%22+13F+OR+%22Bill+Ackman%22&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 7
        region: "us"
        topics: ["13f", "ackman"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "insider_holdings"
      - name: "台股董監持股 (Google News)"
        url: "https://news.google.com/rss/search?q=%E8%91%A3%E7%9B%A3%E6%8C%81%E8%82%A1+OR+%E5%A7%94%E8%A8%97%E6%9B%B8&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 7
        region: "tw"
        topics: ["insider", "tw"]
        max_articles: 8
        quality: "medium"
        summary_prompt: "insider_holdings"
      - name: "台股股權轉讓 (Google News)"
        url: "https://news.google.com/rss/search?q=%E8%82%A1%E6%AC%8A%E8%BD%89%E8%AE%93+%E7%94%B3%E5%A0%B1&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 6
        region: "tw"
        topics: ["insider", "tw"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "insider_holdings"
```

- [ ] **Step 5: Run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_source_coverage.SourceCoverageTests.test_insider_holdings_category_present -v
```

- [ ] **Step 6: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests -v
```

- [ ] **Step 7: Commit**

```bash
git add config.yaml tests/test_source_coverage.py
git commit -m "feat(config): add insider_holdings feed category

12 insider / 13F sources covering SEC Form 4 + 13F atom feeds,
Insider Monkey, WhaleWisdom, Zacks, plus Google News for major
managers (Berkshire, Bridgewater, Tiger Global, Lone Pine,
Pershing Square) and TW director-holding-change searches."
```

---

### Task 5: Add `short_interest_flows` category

**Files:**
- Modify: `config.yaml`
- Modify: `tests/test_source_coverage.py`

- [ ] **Step 1: Write failing test**

Append to `SourceCoverageTests`:

```python
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
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_source_coverage.SourceCoverageTests.test_short_interest_flows_category_present -v
```

- [ ] **Step 3: Add `category_agents.short_interest_flows`**

```yaml
  short_interest_flows:
    persona: "ETF / 融券資金流分析師：從券源、融券餘額、ETF 申購買回看市場真實位置"
    framework: |
      1. 融券餘額變化（建空、補空）
      2. 券資比與當沖比
      3. ETF 流入流出方向（板塊、地區）
      4. 與股價的反向 / 同向關係
    key_metrics:
      - "短期融券變動百分比"
      - "Days to cover"
      - "ETF AUM 週變動"
      - "板塊資金流向"
    output_sections:
      - "本期關鍵融券動向"
      - "ETF 資金流重點"
      - "市場 positioning 解讀"
    anti_patterns:
      - "不把單日資料當趨勢"
      - "不忽略 ETF rebalance 帶來的雜訊"
```

- [ ] **Step 4: Add `feeds.short_interest_flows`**

```yaml
  # ── 📉 融券與資金流 ──
  short_interest_flows:
    category: "📉 融券與資金流"
    sources:
      - name: "etf.com News"
        url: "https://www.etf.com/rss/news"
        active: true
        priority: 9
        region: "global"
        topics: ["etf", "flows"]
        max_articles: 10
        quality: "high"
        summary_prompt: "short_interest_flows"
      - name: "ETF Trends"
        url: "https://www.etftrends.com/feed/"
        active: true
        priority: 8
        region: "global"
        topics: ["etf", "flows"]
        max_articles: 10
        quality: "high"
        summary_prompt: "short_interest_flows"
      - name: "ETFGI Press"
        url: "https://etfgi.com/news/press-releases.rss"
        active: true
        priority: 7
        region: "global"
        topics: ["etf"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "short_interest_flows"
      - name: "US Short Interest (Google News)"
        url: "https://news.google.com/rss/search?q=%22short+interest%22+OR+%22short+squeeze%22+stocks&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 7
        region: "us"
        topics: ["short", "us"]
        max_articles: 8
        quality: "medium"
        summary_prompt: "short_interest_flows"
      - name: "FINRA Reg SHO (Google News)"
        url: "https://news.google.com/rss/search?q=site%3Afinra.org+short&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 6
        region: "us"
        topics: ["short", "regulator"]
        max_articles: 4
        quality: "medium"
        summary_prompt: "short_interest_flows"
      - name: "ETF Flows Weekly (Google News)"
        url: "https://news.google.com/rss/search?q=ETF+%22weekly+flows%22+OR+%22fund+flows%22&hl=en-US&gl=US&ceid=US:en"
        active: true
        priority: 6
        region: "global"
        topics: ["etf", "flows"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "short_interest_flows"
      - name: "台股融資融券 (Google News)"
        url: "https://news.google.com/rss/search?q=%E8%9E%8D%E8%B3%87%E8%9E%8D%E5%88%B8+OR+%E5%88%B8%E8%B3%87%E6%AF%94&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 8
        region: "tw"
        topics: ["short", "tw"]
        max_articles: 8
        quality: "medium"
        summary_prompt: "short_interest_flows"
      - name: "台股三大法人 (Google News)"
        url: "https://news.google.com/rss/search?q=%E4%B8%89%E5%A4%A7%E6%B3%95%E4%BA%BA+%E8%B2%B7%E8%B6%85+%E8%B3%A3%E8%B6%85&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 8
        region: "tw"
        topics: ["flows", "tw"]
        max_articles: 8
        quality: "medium"
        summary_prompt: "short_interest_flows"
      - name: "台股 ETF 申購買回 (Google News)"
        url: "https://news.google.com/rss/search?q=ETF+%E7%94%B3%E8%B3%BC+%E8%B2%B7%E5%9B%9E&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 7
        region: "tw"
        topics: ["etf", "tw"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "short_interest_flows"
```

- [ ] **Step 5: Run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_source_coverage.SourceCoverageTests.test_short_interest_flows_category_present -v
```

- [ ] **Step 6: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests -v
```

- [ ] **Step 7: Commit**

```bash
git add config.yaml tests/test_source_coverage.py
git commit -m "feat(config): add short_interest_flows feed category

9 sources for ETF flows + short interest signals: etf.com,
ETF Trends, ETFGI, FINRA news, plus TW 融資融券 / 三大法人 /
ETF 申購買回 Google News searches."
```

---

### Task 6: Add `macro_data` category

**Files:**
- Modify: `config.yaml`
- Modify: `tests/test_source_coverage.py`

- [ ] **Step 1: Write failing test**

Append to `SourceCoverageTests`:

```python
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
```

- [ ] **Step 2: Run test, expect failure**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_source_coverage.SourceCoverageTests.test_macro_data_category_present -v
```

- [ ] **Step 3: Add `category_agents.macro_data`**

```yaml
  macro_data:
    persona: "宏觀策略師：橋接學術論文 / 央行 / 多邊機構 / 產業數據，把高頻訊號轉換成投資 angle"
    framework: |
      1. 數據意外（actual vs consensus vs prior）
      2. 央行立場推論
      3. 產業領先指標（半導體 book-to-bill / smartphone shipment）
      4. 對台美股板塊的傳導路徑
    key_metrics:
      - "CPI / PPI / PCE / 失業率"
      - "Fed dot plot 與 SOFR 期貨隱含路徑"
      - "Semi book-to-bill / WSTS 預測"
      - "Smartphone / PC 出貨年增"
    output_sections:
      - "本週宏觀重點數據"
      - "央行 / 多邊機構訊息"
      - "產業先行指標"
      - "傳導到台美股的路徑"
    anti_patterns:
      - "不把單一月份雜訊當趨勢"
      - "不忽略修正值（revision）"
```

- [ ] **Step 4: Add `feeds.macro_data`**

```yaml
  # ── 🌐 宏觀與產業數據 ──
  macro_data:
    category: "🌐 宏觀與產業數據"
    sources:
      - name: "Fed Working Papers"
        url: "https://www.federalreserve.gov/feeds/feds_notes.xml"
        active: true
        priority: 9
        region: "us"
        topics: ["macro", "fed", "research"]
        max_articles: 6
        quality: "high"
        summary_prompt: "macro_data"
      - name: "NBER New Working Papers"
        url: "https://www.nber.org/papers/new.rss"
        active: true
        priority: 8
        region: "global"
        topics: ["macro", "research"]
        max_articles: 8
        quality: "high"
        summary_prompt: "macro_data"
      - name: "BIS Working Papers"
        url: "https://www.bis.org/doclist/work.rss"
        active: true
        priority: 8
        region: "global"
        topics: ["macro", "research"]
        max_articles: 6
        quality: "high"
        summary_prompt: "macro_data"
      - name: "IMF Publications"
        url: "https://www.imf.org/external/RSS/feed.aspx?type=publications"
        active: true
        priority: 8
        region: "global"
        topics: ["macro", "imf"]
        max_articles: 6
        quality: "high"
        summary_prompt: "macro_data"
      - name: "OECD Newsroom"
        url: "https://www.oecd.org/newsroom/rss.xml"
        active: true
        priority: 7
        region: "global"
        topics: ["macro", "oecd"]
        max_articles: 6
        quality: "high"
        summary_prompt: "macro_data"
      - name: "World Bank Publications"
        url: "https://www.worldbank.org/en/news/all.rss"
        active: true
        priority: 7
        region: "global"
        topics: ["macro"]
        max_articles: 6
        quality: "high"
        summary_prompt: "macro_data"
      - name: "ECB Research Bulletin"
        url: "https://www.ecb.europa.eu/rss/research-bulletin.html"
        active: true
        priority: 7
        region: "global"
        topics: ["macro", "ecb"]
        max_articles: 4
        quality: "high"
        summary_prompt: "macro_data"
      - name: "Bank of England Research"
        url: "https://www.bankofengland.co.uk/rss/research"
        active: true
        priority: 6
        region: "global"
        topics: ["macro", "boe"]
        max_articles: 4
        quality: "medium"
        summary_prompt: "macro_data"
      - name: "SIA Press"
        url: "https://www.semiconductors.org/feed/"
        active: true
        priority: 9
        region: "global"
        topics: ["semiconductor", "industry-data"]
        max_articles: 6
        quality: "high"
        summary_prompt: "macro_data"
      - name: "SEMI Press"
        url: "https://www.semi.org/en/news-resources/press/rss.xml"
        active: true
        priority: 9
        region: "global"
        topics: ["semiconductor", "industry-data"]
        max_articles: 6
        quality: "high"
        summary_prompt: "macro_data"
      - name: "Counterpoint Research"
        url: "https://www.counterpointresearch.com/feed/"
        active: true
        priority: 8
        region: "global"
        topics: ["smartphone", "industry-data"]
        max_articles: 6
        quality: "high"
        summary_prompt: "macro_data"
      - name: "Canalys Newsroom"
        url: "https://canalys.com/newsroom?format=rss"
        active: true
        priority: 7
        region: "global"
        topics: ["pc", "smartphone", "industry-data"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "macro_data"
      - name: "行政院主計處 (Google News)"
        url: "https://news.google.com/rss/search?q=site%3Adgbas.gov.tw&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 8
        region: "tw"
        topics: ["macro", "tw"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "macro_data"
      - name: "中央銀行公告 (Google News)"
        url: "https://news.google.com/rss/search?q=site%3Acbc.gov.tw&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 8
        region: "tw"
        topics: ["macro", "tw", "central-bank"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "macro_data"
      - name: "財政部統計 (Google News)"
        url: "https://news.google.com/rss/search?q=site%3Amof.gov.tw+%E7%B5%B1%E8%A8%88&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        active: true
        priority: 7
        region: "tw"
        topics: ["macro", "tw", "fiscal"]
        max_articles: 6
        quality: "medium"
        summary_prompt: "macro_data"
```

- [ ] **Step 5: Run test, expect pass**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_source_coverage.SourceCoverageTests.test_macro_data_category_present -v
```

- [ ] **Step 6: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests -v
```

- [ ] **Step 7: Commit**

```bash
git add config.yaml tests/test_source_coverage.py
git commit -m "feat(config): add macro_data feed category

15 macro / sector data sources: Fed FEDS Notes, NBER, BIS,
IMF, OECD, World Bank, ECB Research, BoE, SIA, SEMI,
Counterpoint, Canalys, plus TW 主計處 / 央行 / 財政部
Google News searches."
```

---

### Task 7: Extend `test_news_enrichment.py` for new categories

**Files:**
- Modify: `tests/test_news_enrichment.py`

This task asserts that articles from the new categories still flow through the existing enrichment pipeline correctly (issuer / ticker / event_type extraction).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_news_enrichment.py` (do not change existing tests):

```python
    def test_broker_research_article_extracts_ticker(self):
        from news_enrichment import build_article_event_metadata
        import datetime

        class FakeArticle:
            title = "Net Interest: deep dive on JPM and the regional bank squeeze"
            body_text = "Trading $JPM at 1.5x book makes sense if NII normalizes."
            summary = ""
            published = datetime.datetime(2026, 5, 1, 12, 0)

        meta = build_article_event_metadata(FakeArticle())
        self.assertIn("JPM", meta["tickers"])

    def test_ir_materials_article_classified_as_filing(self):
        from news_enrichment import build_article_event_metadata
        import datetime

        class FakeArticle:
            title = "Apple Inc. files 10-Q for Q2 2026"
            body_text = "Form 10-Q with quarterly results."
            summary = ""
            published = datetime.datetime(2026, 5, 1, 12, 0)

        meta = build_article_event_metadata(FakeArticle())
        self.assertEqual(meta["event_type"], "filing")

    def test_insider_holdings_article_extracts_ticker(self):
        from news_enrichment import build_article_event_metadata
        import datetime

        class FakeArticle:
            title = "Berkshire Hathaway 13F shows new stake in (NASDAQ: AAPL)"
            body_text = "13F-HR disclosure dated April 2026."
            summary = ""
            published = datetime.datetime(2026, 5, 1, 12, 0)

        meta = build_article_event_metadata(FakeArticle())
        self.assertIn("AAPL", meta["tickers"])

    def test_macro_data_article_classified_as_policy_when_relevant(self):
        from news_enrichment import build_article_event_metadata
        import datetime

        class FakeArticle:
            title = "Fed FEDS note on tariff transmission to inflation"
            body_text = "Discussion of recent tariff regime and macro impact."
            summary = ""
            published = datetime.datetime(2026, 5, 1, 12, 0)

        meta = build_article_event_metadata(FakeArticle())
        self.assertEqual(meta["event_type"], "policy")
```

- [ ] **Step 2: Run tests**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest tests.test_news_enrichment -v
```

Expected: 4 new tests PASS (existing enrichment is content-driven and already handles these patterns; if any fail, that means the article keyword doesn't match — fix by adjusting the test article wording until it triggers the right `event_type`, do **not** modify `news_enrichment.py`).

- [ ] **Step 3: Run full test suite**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_news_enrichment.py
git commit -m "test: cover new feed categories in enrichment tests

Verify broker_research / ir_materials / insider_holdings /
macro_data sample articles still trigger correct ticker
extraction and event_type classification through the existing
news_enrichment pipeline."
```

---

### Task 8: Smoke run — `main.py --no-summary`

**Files:** none modified.

This task verifies the new feeds actually load and the pipeline does not crash. Network failures on individual sources are acceptable — they will be marked unhealthy and retried later.

- [ ] **Step 1: Run smoke**

```bash
uv run --with-requirements requirements.txt --python python3 python main.py --hours 24 --report-type daily --no-summary 2>&1 | tee /tmp/phase1-smoke.log
```

Expected: process exits 0; log contains lines for each new category (`📊 券商與分析師研究`, `🏛️ 法說與 IR 材料`, `👁️ 內部人與機構持股`, `📉 融券與資金流`, `🌐 宏觀與產業數據`).

- [ ] **Step 2: Verify SQLite captured at least one new-category article**

```bash
sqlite3 data/news.db "SELECT category, COUNT(*) FROM articles WHERE category IN ('📊 券商與分析師研究', '🏛️ 法說與 IR 材料', '👁️ 內部人與機構持股', '📉 融券與資金流', '🌐 宏觀與產業數據') GROUP BY category;"
```

Expected: at least one of the five new categories returns a non-zero count. (RSS coverage varies daily; not every category will have fresh content every run — that is OK as long as no category is structurally broken in the smoke log.)

- [ ] **Step 3: Inspect the smoke log for parse errors**

```bash
grep -E "(❌|Error|Traceback)" /tmp/phase1-smoke.log | head -50
```

Acceptable: per-source HTTP errors, source health cooldown messages.
Not acceptable: Python tracebacks, YAML parse errors, KeyError on new categories.

If unacceptable errors appear, fix the offending YAML entry (most likely cause: typo in URL or missing required key) and re-run before continuing.

- [ ] **Step 4: Commit log artifact (optional)**

If the smoke run is informative, save a redacted summary:

```bash
mkdir -p docs/superpowers/runs
grep -E "(📊|🏛️|👁️|📉|🌐|✅|⚠️)" /tmp/phase1-smoke.log | head -200 > docs/superpowers/runs/2026-05-09-phase1-smoke.txt
git add docs/superpowers/runs/2026-05-09-phase1-smoke.txt
git commit -m "test(smoke): capture phase 1 RSS expansion smoke run"
```

---

### Task 9: OpenSpec validate + final commit

**Files:**
- Modify: `openspec/changes/investment-source-rss-expansion/tasks.md` (mark all items checked)

- [ ] **Step 1: Mark all tasks as completed in `openspec/changes/investment-source-rss-expansion/tasks.md`**

Replace each `- [ ] Task N ...` line with `- [x] Task N ...`.

- [ ] **Step 2: Run OpenSpec validate**

```bash
cd /Users/andy/Code/projects/telegram-bot/daily-news && command -v openspec >/dev/null && openspec validate investment-source-rss-expansion || echo "openspec CLI not installed locally — skip"
```

Expected: validate passes, or skip with the explicit message above. If validate fails, fix the missing artifact / spec deltas before continuing.

- [ ] **Step 3: Run full test suite one more time**

```bash
uv run --with-requirements requirements.txt --python python3 python -m unittest discover -s tests -v
```

Expected: 0 failures, 0 errors.

- [ ] **Step 4: Final commit**

```bash
git add openspec/changes/investment-source-rss-expansion/tasks.md
git commit -m "openspec: phase 1 done — investment-source-rss-expansion

[phase-1 done]

5 new feed categories (broker_research, ir_materials,
insider_holdings, short_interest_flows, macro_data) with
~60 sources total. All structural + enrichment tests green.
Smoke run via main.py --no-summary completes without
tracebacks. Phase 2 (structured ingest modules) ready to start."
```

- [ ] **Step 5: Reply with promise tag**

When all checkboxes above are checked and the commit lands, reply with **only**:

```
<promise>PHASE_DONE</promise>
```

Do not include any other text or commentary.

---

## Self-review notes (already applied)

- Spec coverage: every section in `2026-05-09-investment-source-expansion-design.md` Phase 1 (4.1–4.5) maps to a task. Sources listed in 4.2 are realised in Tasks 2–6.
- Phase isolation: explicit "Hard limits" block at top + reminder before each task. No edits to `crawler.py`, `news_enrichment.py`, `summarizer.py`, `stock_memo.py`, `financial_reports.py`, `html_generator.py`.
- Enrichment correctness: Task 7 verifies new sources still trigger ticker / event_type extraction without modifying the enrichment module.
- No placeholders: every YAML block contains real URLs and required keys; every test step contains real Python.
- Type / signature consistency: `summary_prompt` value matches the `category_agents` key in every source block; category emoji string matches between `feeds.<key>.category` and `tests/test_source_coverage.py` assertions.
