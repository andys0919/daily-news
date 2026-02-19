## 1. Config 層

- [x] 1.1 在 config.yaml 新增 `category_agents` 區塊，定義 8 個分類代理人（persona / framework / key_metrics / output_sections / anti_patterns）
- [x] 1.2 重構 `investor_persona` 為共用基底（保留 focus_sectors / global_anti_patterns，移除 category_focus / name / key_signals）

## 2. Summarizer 基礎設施

- [x] 2.1 新增 `_CATEGORY_AGENTS_CACHE` 變數和 `_load_category_agents()` 快取函式
- [x] 2.2 新增 `_FEED_TO_AGENT_KEY` 映射和 `_resolve_agent_key(category, prompt_type)` 解析函式
- [x] 2.3 驗證 agent key 解析：finance（"news"→feed lookup）、deep_analysis（"news"→feed lookup）、semiconductor（直接匹配）、tech_industry（feed key "tech_companies"→映射）

## 3. Prompt 重寫

- [x] 3.1 重寫 `_build_category_synthesis_prompt()` — 單一動態模板取代 3 個硬編碼分支（default / ai_practice / x_trends）
- [x] 3.2 重寫 `_build_category_merge_prompt()` — 同樣改為單一動態模板
- [x] 3.3 確認 ai_practice 分類不顯示 focus_sectors（投資板塊）
- [x] 3.4 確認 anti_patterns 正確合併（agent 專屬 + global_anti_patterns）

## 4. 驗證

- [x] 4.1 Python 語法檢查通過（`py_compile`）
- [x] 4.2 完整 pipeline 執行成功（`python main.py --hours 24 --report-type daily`）
- [x] 4.3 全部 8 個分類摘要成功產出
- [x] 4.4 HTML 報告正常生成
- [x] 4.5 Telegram 文字摘要格式正確
