## ADDED Requirements

### Requirement: render_stock_memo includes five new structured sections
The system SHALL render five new markdown sections in per-stock memos when corresponding bundle data is present, and a graceful「（暫無資料）」placeholder when not.

#### Scenario: transcript section appears when bundle.latest_transcript is set
- **WHEN** rendering a memo for a ticker whose bundle has `latest_transcript={"title":"X","body_text":"Blackwell ramp"}`
- **THEN** the rendered markdown SHALL contain `## 最新法說會重點` and SHALL include `Blackwell` somewhere in that section

#### Scenario: insider section summarises buys vs sells
- **WHEN** bundle.recent_insider_summary is `{"count":3,"buys":1,"sells":2,"latest":{...}}`
- **THEN** the section `## 近 90 天內部人交易` SHALL include `3 筆`, `買 1`, `賣 2`

#### Scenario: short interest section appears with ratio
- **WHEN** bundle.short_interest is `{"short_interest":200000,"short_interest_ratio":0.05,...}`
- **THEN** the section `## 融券與 ETF 資金流` SHALL include `200,000` and a percentage

#### Scenario: macro section always present
- **WHEN** rendering any memo
- **THEN** the section `## 宏觀脈絡` SHALL be present in the output

### Requirement: format_financial_snapshot_bundle_context surfaces structured fields
The system SHALL extend `format_financial_snapshot_bundle_context` so daily / weekly summarizer prompts see the four new bundle fields when present.

#### Scenario: transcript excerpt appears in context
- **WHEN** `format_financial_snapshot_bundle_context(bundle)` is called with a bundle whose `latest_transcript = {"title":"NVDA Q1","body_text":"Blackwell ramp ...","material_type":"transcript"}`
- **THEN** the returned context string SHALL contain `Blackwell`

#### Scenario: short-interest one-liner appears in context
- **WHEN** the bundle has `short_interest = {"short_interest":200000,"short_interest_ratio":0.05,...}`
- **THEN** the returned context string SHALL contain `融券`
