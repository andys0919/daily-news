## Why

每日新聞聚合器的 AI 摘要品質不佳：8 個分類共用同一套泛用 prompt，導致財經分類缺乏因果鏈分析、半導體分類沒有產能數字、AI 工具分類被當投資分析寫、X 熱議分類看不到 KOL 觀點。需要讓每個分類都有**專屬的分析代理人**，擁有獨立的人設、分析框架、關鍵指標和輸出格式，全部由 config.yaml 驅動，不再硬編碼。

## What Changes

- **新增 `config.yaml` 的 `category_agents` 區塊**：定義 8 個分類代理人（finance / geopolitics / semiconductor / tech_industry / ai_research / ai_practice / deep_analysis / x_trends），每個包含 persona、framework、key_metrics、output_sections、anti_patterns
- **重構 `investor_persona` 為共用基底**：保留 focus_sectors 和 global_anti_patterns 作為全域參考，移除 category_focus（被 agent framework 取代）
- **新增 `_load_category_agents()` / `_resolve_agent_key()`**：從分類名稱 + prompt_type 自動解析到對應的 agent config key
- **重寫 `_build_category_synthesis_prompt()`**：從 3 個硬編碼分支（default / ai_practice / x_trends）改為單一動態模板，完全由 config 驅動
- **重寫 `_build_category_merge_prompt()`**：同樣改為單一動態模板
- **ai_practice 分類特殊處理**：不顯示投資板塊（focus_sectors），因為它是使用者的個人技術雷達，不是投資分析
- **淨減 ~60 行程式碼**：消除重複的 prompt 內容

## Capabilities

### New Capabilities
- `category-agent-config`: config.yaml 中 8 個分類代理人的定義結構（persona / framework / key_metrics / output_sections / anti_patterns）
- `dynamic-prompt-builder`: 根據 category_agents config 動態建構每個分類的 synthesis 和 merge prompt，取代硬編碼分支

### Modified Capabilities
（無既有 spec 需修改 — 這是首次建立 openspec）

## Impact

- **`config.yaml`**：新增 ~200 行 `category_agents` 區塊；`investor_persona` 結構簡化（移除 category_focus、name、key_signals）
- **`summarizer.py`**：新增 `_load_category_agents()` / `_resolve_agent_key()`（~35 行）；重寫 `_build_category_synthesis_prompt()` 和 `_build_category_merge_prompt()`（淨減 ~60 行）
- **向下相容**：`_get_prompt_type()` 和 `summarize_category()` 不變，不影響呼叫端
- **LLM 成本**：prompt 長度略增（加入 framework + key_metrics），但每次 API 呼叫增加 <500 tokens，總成本影響 <5%
