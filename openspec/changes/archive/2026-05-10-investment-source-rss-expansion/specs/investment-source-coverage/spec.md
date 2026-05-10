## ADDED Requirements

### Requirement: Five investment-relevant feed categories ingest into the news pipeline
The system SHALL define five new RSS / Atom feed categories — `broker_research`, `ir_materials`, `insider_holdings`, `short_interest_flows`, and `macro_data` — in `config.yaml` so that the existing crawler ingests free, repeatable investment sources alongside the existing eight categories.

#### Scenario: broker_research category exists with at least ten free analyst sources
- **WHEN** loading `config.yaml`
- **THEN** `feeds.broker_research` SHALL exist with `category: "📊 券商與分析師研究"` and SHALL contain entries for Damodaran Blog, Doomberg, Net Interest, Mostly Borrowed Ideas, Topdown Charts, Lyn Alden, Epsilon Theory, Howard Marks Memos, Verdad Capital, and Goldman Insights (Google News)

#### Scenario: ir_materials category exposes SEC filings and IR feeds
- **WHEN** loading `config.yaml`
- **THEN** `feeds.ir_materials` SHALL exist with `category: "🏛️ 法說與 IR 材料"` and SHALL contain entries for SEC 8-K / 10-Q / 10-K Atom feeds, Motley Fool earnings transcripts, NVIDIA Investor Press, and a TW law-call Google News search

#### Scenario: insider_holdings category exposes Form 4 / 13F sources
- **WHEN** loading `config.yaml`
- **THEN** `feeds.insider_holdings` SHALL exist with `category: "👁️ 內部人與機構持股"` and SHALL contain entries for SEC Form 4 Atom, SEC 13F-HR Atom, Insider Monkey, WhaleWisdom Blog, and Google News searches for Berkshire and Bridgewater 13F

#### Scenario: short_interest_flows category exposes ETF and short-interest sources
- **WHEN** loading `config.yaml`
- **THEN** `feeds.short_interest_flows` SHALL exist with `category: "📉 融券與資金流"` and SHALL contain entries for etf.com News, ETF Trends, ETFGI Press, US Short Interest (Google News), and 台股融資融券 (Google News)

#### Scenario: macro_data category exposes central bank and sector trackers
- **WHEN** loading `config.yaml`
- **THEN** `feeds.macro_data` SHALL exist with `category: "🌐 宏觀與產業數據"` and SHALL contain entries for Fed Working Papers, NBER, BIS, IMF, OECD, World Bank, SIA Press, SEMI Press, plus 行政院主計處 and 中央銀行公告 (Google News) searches

### Requirement: Each new feed entry carries the keys required by the existing crawler
The system SHALL ensure each new feed entry uses the same schema as existing entries so the crawler ingests them with no code changes.

#### Scenario: every new source has the required keys
- **WHEN** iterating sources under any of the five new feed categories
- **THEN** each source SHALL define `name`, `url`, `priority`, and `summary_prompt`, and `summary_prompt` SHALL match the category key (`broker_research`, `ir_materials`, `insider_holdings`, `short_interest_flows`, or `macro_data`)

### Requirement: Each new category has a matching category_agents persona block
The system SHALL include a matching `category_agents` entry for each new feed category so the configuration stays internally consistent.

#### Scenario: category_agents includes the five new keys
- **WHEN** loading `config.yaml`
- **THEN** `category_agents` SHALL contain keys `broker_research`, `ir_materials`, `insider_holdings`, `short_interest_flows`, and `macro_data`, each with `persona`, `framework`, `key_metrics`, `output_sections`, and `anti_patterns` fields
