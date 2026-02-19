## ADDED Requirements

### Requirement: Category agent definition in config.yaml

`config.yaml` SHALL contain a `category_agents` mapping where each key is a category identifier (kebab-case) and each value defines a complete agent persona with: `persona` (string), `framework` (multiline string), `key_metrics` (list of strings), `output_sections` (list of strings), `anti_patterns` (list of strings).

#### Scenario: All 8 categories have agent definitions
- **WHEN** config.yaml is loaded
- **THEN** `category_agents` SHALL contain exactly these keys: `finance`, `geopolitics`, `semiconductor`, `tech_industry`, `ai_research`, `ai_practice`, `deep_analysis`, `x_trends`

#### Scenario: Each agent has all required fields
- **WHEN** any agent entry is read from `category_agents`
- **THEN** it SHALL contain non-empty values for `persona`, `framework`, `key_metrics` (>=3 items), `output_sections` (>=3 items), `anti_patterns` (>=1 item)

### Requirement: Shared investor persona as base

`config.yaml` SHALL contain an `investor_persona` mapping with shared fields: `role`, `style`, `time_horizon`, `focus_sectors` (list), `global_anti_patterns` (list). These are used as cross-category context by the prompt builder.

#### Scenario: Global anti-patterns are defined
- **WHEN** `investor_persona.global_anti_patterns` is read
- **THEN** it SHALL contain at least 3 items covering: no price predictions, no empty adjectives, no unsupported opinions

### Requirement: Agent key resolution from category name

The system SHALL provide a function `_resolve_agent_key(category, prompt_type)` that maps a display category name (e.g., "💰 財經與總經") and prompt_type to the corresponding `category_agents` key.

#### Scenario: Direct prompt_type match
- **WHEN** `prompt_type` is "semiconductor" and "semiconductor" exists in `category_agents`
- **THEN** the function SHALL return "semiconductor"

#### Scenario: Ambiguous "news" prompt_type resolved via feed config
- **WHEN** `prompt_type` is "news" and `category` is "💰 財經與總經"
- **THEN** the function SHALL look up the feed key from config feeds and return "finance"

#### Scenario: Deep analysis also uses "news" prompt_type
- **WHEN** `prompt_type` is "news" and `category` is "🧭 深度觀點與分析"
- **THEN** the function SHALL return "deep_analysis"

#### Scenario: Feed key to agent key mapping
- **WHEN** feed key is "tech_companies" (which maps to category "🏢 科技廠動態")
- **THEN** the function SHALL map it to agent key "tech_industry" via `_FEED_TO_AGENT_KEY`

### Requirement: Category agents config caching

`_load_category_agents()` SHALL cache the parsed `category_agents` dict in `_CATEGORY_AGENTS_CACHE` after first load. Subsequent calls SHALL return the cached value without re-reading the YAML file.

#### Scenario: Cache hit
- **WHEN** `_load_category_agents()` is called twice
- **THEN** the second call SHALL return the same dict object without opening the config file again
