## ADDED Requirements

### Requirement: Dynamic synthesis prompt from agent config

`_build_category_synthesis_prompt(category, prompt_type, articles_text)` SHALL construct the prompt dynamically from the resolved agent's config fields, not from hardcoded branches. The prompt SHALL include: agent persona, analysis framework, key metrics, output sections, combined anti-patterns (agent + global), and the articles text.

#### Scenario: Finance category gets finance agent prompt
- **WHEN** category is "💰 財經與總經" and prompt_type is "news"
- **THEN** the prompt SHALL contain the finance agent's persona ("高盛首席宏觀策略師") and framework (宏觀環境 → 財報與預期 → 資金流向 → 風險定價 → 加密另類)

#### Scenario: Semiconductor category gets semiconductor agent prompt
- **WHEN** category is "🔬 半導體與硬體" and prompt_type is "semiconductor"
- **THEN** the prompt SHALL contain the semiconductor agent's persona and framework (產能良率 → 先進封裝 → 記憶體循環 → 設備訂單 → 供需缺口定價)

#### Scenario: Output sections are dynamically generated
- **WHEN** any category's prompt is built
- **THEN** the output format section SHALL contain `### {section}` for each item in the agent's `output_sections` list, in order

### Requirement: ai_practice excludes investment sector context

When building the synthesis prompt for the `ai_practice` agent, the prompt SHALL NOT include the `investor_persona.focus_sectors` block. All other categories SHALL include it.

#### Scenario: ai_practice prompt has no focus_sectors
- **WHEN** agent_key is "ai_practice"
- **THEN** the prompt SHALL NOT contain "關注板塊" section

#### Scenario: Finance prompt includes focus_sectors
- **WHEN** agent_key is "finance"
- **THEN** the prompt SHALL contain a "關注板塊" section with the investor_persona.focus_sectors items

### Requirement: Combined anti-patterns in prompts

Both synthesis and merge prompts SHALL combine the agent's `anti_patterns` with `investor_persona.global_anti_patterns` into a single "禁止事項" section.

#### Scenario: Anti-patterns are merged
- **WHEN** agent has 2 anti_patterns and global has 5 anti_patterns
- **THEN** the prompt's 禁止事項 section SHALL contain all 7 items

### Requirement: Dynamic merge prompt from agent config

`_build_category_merge_prompt(category, prompt_type, chunk_summaries, total_articles)` SHALL construct the merge prompt dynamically from the resolved agent's config. The merge prompt SHALL include: agent persona, output sections, combined anti-patterns, and the merged chunk summaries.

#### Scenario: Merge prompt uses same output_sections as synthesis
- **WHEN** a category has chunked summaries that need merging
- **THEN** the merge prompt's output format SHALL match the same `output_sections` as the synthesis prompt for that category

#### Scenario: Merge prompt includes citation rules
- **WHEN** the merge prompt is built
- **THEN** it SHALL instruct the LLM to reuse existing `[n]` citations without inventing new ones

### Requirement: Single template replaces multiple branches

There SHALL be exactly one code path in `_build_category_synthesis_prompt()` and one in `_build_category_merge_prompt()` — no `if prompt_type == ...` branching. All differentiation comes from the agent config values.

#### Scenario: No hardcoded prompt_type branches
- **WHEN** the source code of `_build_category_synthesis_prompt` is inspected
- **THEN** it SHALL NOT contain any `if prompt_type ==` conditional branches
