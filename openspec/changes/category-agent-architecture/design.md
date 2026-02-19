## Context

每日新聞聚合器透過 RSS 爬取 ~2000 篇新聞，分成 8 個分類，每個分類用 Azure OpenAI (gpt-5-nano) 產出摘要。原架構中 `_build_category_synthesis_prompt()` 和 `_build_category_merge_prompt()` 使用 3 個硬編碼分支（default / ai_practice / x_trends），導致：

1. 財經、半導體、地緣政治、科技廠、AI 研究、深度觀點 — 共用同一個泛用 prompt，無法產出分類專屬的分析角度
2. 新增或修改分類需要改 Python 程式碼，而非修改 config
3. 各分類的輸出格式不一致，缺乏結構化的分析框架

### 現有 prompt 流程
```
articles → _build_category_synthesis_prompt(category, prompt_type, text)
         → [if chunks > 1] _build_category_merge_prompt(category, prompt_type, summaries)
         → build_top10_prompt(all_summaries)  # 跨分類整合
```

`prompt_type` 由 `_get_prompt_type(category, articles)` 從 config feeds 的 `summary_prompt` 欄位決定，值為 "news" / "geopolitics" / "semiconductor" / "tech_industry" / "ai_research" / "ai_practice" / "x_trends"。

## Goals / Non-Goals

**Goals:**
- 每個分類有專屬的 AI 代理人（persona + framework + metrics + output_sections + anti_patterns）
- 全部由 `config.yaml` 驅動，新增/修改分類只需改 YAML
- ai_practice 分類作為「技術雷達」而非投資分析
- 保持向下相容：不改變 `summarize_category()` 和 `_get_prompt_type()` 的外部介面

**Non-Goals:**
- 不改變 LLM provider（仍用 Azure OpenAI）
- 不改變分段/合併邏輯（chunk size、citation 系統不變）
- 不改變 HTML 報告生成或 Telegram 推送格式

## Decisions

### 1. Config 結構：`category_agents` 與 `investor_persona` 分離

**選擇**：`investor_persona` 保留為共用基底（focus_sectors / global_anti_patterns），`category_agents` 定義 8 個獨立代理人。

**替代方案**：把所有資訊都放在 `category_agents` 內，不要共用基底。

**理由**：focus_sectors 和 global_anti_patterns 是跨分類共用的（如「不做漲跌預測」），放在共用基底避免重複。但 ai_practice 是技術雷達，不顯示 focus_sectors。

### 2. Agent key 解析：`_resolve_agent_key(category, prompt_type)`

**選擇**：兩階段解析 — 先嘗試 prompt_type 直接匹配 agent key，再從 feeds config 反查 feed key → agent key。

**問題**：`prompt_type = "news"` 被 finance 和 deep_analysis 兩個分類共用，無法直接映射。

**解法**：當 prompt_type 為 "news" 時，從 config feeds 找到分類名稱對應的 feed key（如 "finance" / "deep_analysis"），再映射到 agent key。`_FEED_TO_AGENT_KEY = {"tech_companies": "tech_industry"}` 處理 key 不一致的情況。

### 3. Prompt 模板：單一動態模板取代 3 個硬編碼分支

**選擇**：一個模板函式，從 agent config 動態插入 persona / framework / key_metrics / output_sections / anti_patterns。

**替代方案**：保留分支但增加到 8 個。

**理由**：8 個分支會有大量重複程式碼。動態模板只需 ~40 行，新增分類只需加 YAML。output_sections 的描述文字（如「今日必知新工具（3-5 個：名稱+版本+一句話說明）」）已足夠引導 LLM 產出結構化輸出。

### 4. ai_practice 不顯示投資板塊

**選擇**：`if agent_key != "ai_practice": sectors_blk = ...`

**理由**：使用者明確說明 ai_practice 是「個人技術雷達 — 追蹤 GitHub trending、新 LLM 工具、model releases」，不是投資分析。加入 focus_sectors 會誤導 LLM 產出投資觀點而非工具評測。

## Risks / Trade-offs

- **[Risk] LLM 可能不完全遵循 config 定義的 output_sections** → 現有的 `_clean_llm_output()` 後處理已能處理格式偏差；output_sections 的描述文字足夠具體（含數量和內容要求）
- **[Risk] Config YAML 膨脹（新增 ~200 行）** → 可接受，因為消除了 ~60 行 Python 重複程式碼，且 YAML 比 Python f-string 更容易維護
- **[Risk] AI 研究合併 timeout** → 已有 fallback 機制（串接各段），不影響最終輸出品質
- **[Trade-off] Prompt 長度略增** → 每次 API 呼叫增加 <500 tokens（framework + key_metrics），總成本影響 <5%
