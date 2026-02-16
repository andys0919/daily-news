"""LLM 摘要模組 — 用 Codex CLI stdin 或 Claude API 產生智慧新聞摘要"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

from crawler import Article

CONFIG_PATH = Path(__file__).parent / "config.yaml"

# Codex CLI 設定
CODEX_PATH = "/opt/homebrew/bin/codex"
CODEX_MODEL = "gpt-5.2"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_articles_text(articles: list[Article], limit: int = 20) -> str:
    """將文章列表轉成文字"""
    text = ""
    for i, a in enumerate(articles[:limit], 1):
        text += f"""
---
[{i}] {a.title}
來源：{a.source} | 時間：{a.published.strftime('%Y-%m-%d %H:%M')}
摘要：{a.summary}
連結：{a.link}
"""
    return text


def build_prompt(category: str, articles: list[Article], prompt_type: str = "news") -> str:
    """建立摘要 prompt（根據分類選不同 prompt）"""
    articles_text = _build_articles_text(articles)

    builders = {
        "news": _build_news_prompt,
        "geopolitics": _build_geopolitics_prompt,
        "semiconductor": _build_semiconductor_prompt,
        "ai_research": _build_ai_research_prompt,
        "ai_practice": _build_ai_practice_prompt,
        "tech_industry": _build_tech_industry_prompt,
    }

    builder = builders.get(prompt_type, _build_news_prompt)
    return builder(category, articles_text)


def _build_news_prompt(category: str, articles_text: str) -> str:
    """一般新聞摘要 prompt"""
    return f"""你是一位專業的財經新聞編輯，讀者是科技業投資人。以下是今天 **{category}** 的新聞。

讀完後整理成一篇精煉的中文短文，**聚焦有投資 insight 的新聞**。

### 格式要求

用 `### 主題名稱` 分成 3-5 個主題段落。每段 2-4 句，段末列引用來源。

### 讀者關心什麼（依此篩選重點）
- 企業擴產、資本支出、併購動態（誰投多少錢做什麼）
- 政策變動對產業鏈的實際影響（關稅、補貼、監管）
- 供應鏈重組訊號（轉單、新廠、良率、產能）
- 科技大廠的技術路線變動（改用什麼架構、棄用什麼）
- 央行決策背後的具體數據與邏輯

### 不要寫的
- 空洞結論：「看多」「看空」「需求強勁」「持續成長」
- 沒有具體數字的泛泛敘述
- 股價漲跌的日內波動分析

⚠️ 規則：
- 用**繁體中文**
- 每段 2-4 句，要具體（金額、人名、數據）
- 來源用 `▸ [短標題](url) (MM/DD HH:MM)` 格式，短標題不超過 20 字，括號內是新聞發布時間
- 寫「為什麼會這樣」— 因果脈絡，不要預測未來
- 直接輸出，不要開場白

以下是今天的新聞：
{articles_text}
"""


def _build_ai_practice_prompt(category: str, articles_text: str) -> str:
    """AI 實戰應用專屬 prompt — 著重工具用法、GitHub 熱門、社群討論"""
    return f"""你是一位 AI/LLM 實戰專家。以下是今天從 GitHub Trending、Dev.to、Lobsters、Hacker News 等來源收集的內容。

讀完後整理成一篇**實戰導向的技術短文**。

### 格式要求

用以下三個 `### 標題` 分段，每段 2-4 句話講重點，段末列出引用來源：

### 🔥 熱門專案
挑 3-5 個最值得關注的 AI/LLM 專案，每個一句話說明用途與亮點。特別關注 Claude、Codex、Agent、MCP、RAG 相關的。

### 🛠️ 實戰技巧
社群文章裡有什麼可以直接拿來用的？講清楚怎麼用、解決什麼問題。

### 🌊 社群動態
開發者在熱議什麼？什麼新趨勢正在形成？

每段末尾另起一行列引用，格式：`▸ [專案名或短標題](連結)`

⚠️ 規則：
- 用**繁體中文**
- 每段簡短，不要超過 4 句正文
- 來源用 `▸ [短標題](url) (MM/DD HH:MM)` 格式，括號內是新聞發布時間
- 過濾垃圾內容，只留有價值的
- 直接輸出，不要開場白

以下是今天的內容：
{articles_text}
"""


def _build_tech_industry_prompt(category: str, articles_text: str) -> str:
    """科技產業動態 prompt — 聚焦大廠決策、擴產、架構轉向"""
    return f"""你是一位科技產業分析師。以下是今天 **{category}** 的新聞。

讀完後整理成一篇精煉短文，**聚焦對投資決策有價值的產業動態**。

### 格式要求

用 `### 主題名稱` 分段，每段 2-4 句話，段末列引用來源。

### 讀者關心什麼（依此篩選重點）
- 大廠技術決策：誰改用什麼架構？新產品用什麼技術棧？
- 擴產與資本支出：誰在蓋廠、投多少錢、產能規劃
- 供應鏈變動：誰換供應商、誰拿到新訂單、良率變化
- AI 基礎設施：資料中心、GPU 算力、雲端服務的實際部署動態
- 重大產品發布或技術突破的具體規格與數據

### 不要寫的
- 泛泛的「AI 需求持續成長」之類的廢話
- 沒有具體數字或事件的評論
- 股價漲跌分析

⚠️ 規則：
- 用**繁體中文**
- 每段 2-4 句，要具體（金額、規格、產能數字）
- 來源用 `▸ [短標題](url) (MM/DD HH:MM)` 格式，括號內是新聞發布時間
- 寫「為什麼會這樣」— 背後因果，不要預測
- 直接輸出，不要開場白

以下是今天的新聞：
{articles_text}
"""


def _build_geopolitics_prompt(category: str, articles_text: str) -> str:
    """地緣政治與科技政策 prompt — 聚焦出口管制、關稅、補貼、供應鏈重組"""
    return f"""你是一位地緣政治與科技產業分析師。以下是今天 **{category}** 的新聞。

讀完後整理成一篇精煉短文，**聚焦對科技產業鏈和投資決策有實質影響的政策與地緣動態**。

### 格式要求

用 `### 主題名稱` 分段，每段 2-4 句話，段末列引用來源。

### 讀者關心什麼（依此篩選重點）
- 出口管制：具體限制了什麼品項（製程節點、設備型號）、限制哪些國家/實體
- 關稅變動：稅率多少、涵蓋哪些產品類別、何時生效
- 產業補貼：CHIPS Act 或各國補貼的具體金額、受惠廠商、條件
- 供應鏈重組：「誰被限制 → 誰受益 → 供應鏈怎麼重組」的因果鏈
- 科技外交：技術聯盟（例：美日荷設備管制）、技術封鎖的擴散效應

### 不要寫的
- 純政治角力（沒有科技產業影響的）
- 外交辭令和空洞聲明
- 沒有具體政策內容的「可能」「考慮」

⚠️ 規則：
- 用**繁體中文**
- 每段 2-4 句，要具體（品項、稅率、金額、時間表）
- 來源用 `▸ [短標題](url) (MM/DD HH:MM)` 格式，短標題不超過 20 字
- 寫清楚因果鏈：政策 → 直接影響 → 供應鏈連鎖反應
- 直接輸出，不要開場白

以下是今天的新聞：
{articles_text}
"""


def _build_semiconductor_prompt(category: str, articles_text: str) -> str:
    """半導體與硬體 prompt — 聚焦製程、產能、資料中心、設備"""
    return f"""你是一位半導體產業研究員。以下是今天 **{category}** 的新聞。

讀完後整理成一篇精煉短文，**聚焦半導體供應鏈的具體變化和投資級洞察**。

### 格式要求

用 `### 主題名稱` 分段，每段 2-4 句話，段末列引用來源。

### 讀者關心什麼（依此篩選重點）
- 先進製程：N3/N2/A14 等節點的良率、產能爬坡進度、客戶導入時程
- HBM/CoWoS：產能（K/月）、良率變化、供需缺口、新供應商進入
- 資料中心：新建規模（MW、投資金額）、GPU/ASIC 部署量、電力需求
- 設備訂單：ASML/Applied Materials/LAM 的訂單變化、交期、客戶結構
- 封測/基板：ABF 載板、先進封裝技術演進、產能規劃
- 記憶體：DRAM/NAND 價格走勢、庫存水位、DDR5/HBM 轉換比例

### 不要寫的
- 沒有具體數字的泛泛描述（「需求強勁」「持續成長」）
- 消費電子的日常產品評測
- 股價漲跌分析

⚠️ 規則：
- 用**繁體中文**
- 每段 2-4 句，**必須有具體數字**（產能 K/月、良率%、投資金額$、時間表）
- 來源用 `▸ [短標題](url) (MM/DD HH:MM)` 格式，短標題不超過 20 字
- 寫供應鏈上下游的連動邏輯
- 直接輸出，不要開場白

以下是今天的新聞：
{articles_text}
"""


def _build_ai_research_prompt(category: str, articles_text: str) -> str:
    """AI 研究與突破 prompt — 聚焦論文突破、模型架構、LLM 經濟學"""
    return f"""你是一位 AI 研究分析師，同時具備投資分析能力。以下是今天 **{category}** 的內容，包含 arXiv 論文、AI 大廠部落格、和科技媒體報導。

讀完後整理成一篇**兼具技術深度和商業洞察的短文**。

### 格式要求

用以下 `### 標題` 分段，每段 2-4 句話，段末列引用來源：

### 🔬 重大研究突破
挑 2-3 個最重要的技術突破（新模型架構、訓練方法、benchmark 刷新），每個說明：
1. 技術上做了什麼（一句話）
2. 為什麼重要 — 對商業應用的意義（推理成本降低 → 哪些應用變可行？效率提升 → 誰受益？）

### 💰 AI 基礎設施與投資
大廠的 AI 資本支出、資料中心建設、算力採購、模型部署成本變化。
寫具體數字：投資金額、GPU 數量、推理成本 $/token 變化。

### 🌊 模型與平台動態
新模型發布、API 更新、開源 vs 閉源的競爭態勢、LLM 成本經濟學變化。

⚠️ 規則：
- 用**繁體中文**
- 每段簡短，不要超過 4 句正文
- arXiv 論文：用論文標題和作者機構標註，不要只寫 arXiv ID
- 來源用 `▸ [短標題](url) (MM/DD HH:MM)` 格式
- **每個技術突破都要寫商業意義** — 「所以呢？對誰有影響？」
- 過濾低影響力的增量研究，只留真正重要的突破
- 直接輸出，不要開場白

以下是今天的內容：
{articles_text}
"""


def build_top10_prompt(all_articles: dict[str, list[Article]], summaries: dict[str, str]) -> str:
    """建立 Top 10 必讀精選 prompt — 整理內文重點"""
    # 收集所有分類的摘要和文章內容
    context = ""
    for category, summary in summaries.items():
        articles = all_articles.get(category, [])
        context += f"\n\n### {category}（{len(articles)} 篇）\n"
        context += f"AI 摘要：\n{summary}\n"
        context += "文章列表：\n"
        for a in articles[:10]:
            context += f"- {a.title} | {a.source} | {a.link}\n"
            if a.summary:
                context += f"  內容：{a.summary[:300]}\n"

    return f"""你是一位 sell-side 研究員，負責撰寫每日晨會投資摘要給基金經理人看。以下是今天所有分類的新聞摘要和文章。

從所有分類中挑出**今天對投資決策最有用的 10 則新聞**，用 buy/sell side research 的風格寫投資摘要。

### 挑選標準（按投資價值排序）
- 直接影響產業鏈供需或定價的事件（擴產、砍單、新廠、關稅）
- 大廠技術路線或架構轉向（誰改用什麼、棄用什麼）
- 政策/監管變動對特定產業鏈的實質影響
- AI 基礎設施部署的具體動態（算力、資料中心、雲端）
- 跨市場連動訊號（例：美國政策 → 台灣供應鏈影響）

### 什麼不要選
- ❌ 沒有具體 investment takeaway 的一般新聞
- ❌ 純股價評論、目標價調整
- ❌ 社會新聞、人事異動（除非影響公司策略方向）

### 輸出格式

每篇用 `### 排名. 標題` 作為標題：

### 1. 簡短事件標題

**事實**：1-2 句講發生什麼事（誰、做了什麼、數字）。
**Investment Takeaway**：1-2 句講這件事對哪些產業鏈/標的有什麼具體影響。要寫到產業鏈層級（例：「利好先進封裝設備商」「壓縮 NAND 現貨價」「加速邊緣 AI 晶片需求」），不要只寫「利好半導體」這種空話。
**二階效應**：1 句話寫間接連鎖反應（例：「GPU 需求暴增 → HBM 供不應求 → SK Hynix 加速擴產 → 設備商接單潮」）。

▸ [短標題](原文連結) ・ 來源名 (MM/DD HH:MM)

---

### 範例（這是你要達到的品質）

### 1. Amazon 宣布 2,000 億美元 AI 資本支出計畫

**事實**：Amazon 確認未來三年將投入 $200B 於 AI 基礎設施，其中 60% 用於自建資料中心，40% 用於 Trainium 客製晶片擴產。
**Investment Takeaway**：直接拉動 HBM 與先進封裝需求（日月光、SK Hynix），但同時代表對 NVIDIA GPU 依賴度下降，Trainium 自研晶片放量將壓縮 NVIDIA 在推理端的市佔。電力基礎設施（變壓器、銅纜）短期供不應求。

▸ [Amazon 2000 億 AI 資本支出](https://...) ・ CNBC (02/15 09:30)

---

### 最後：🔗 今日主線

在 10 篇之後，加一段 **🔗 今日主線**（50 字以內），把今天跨分類的重大新聞串成一條投資邏輯線。
例：「AI 資本支出擴張 → 半導體設備訂單 → 先進封裝產能吃緊 → 台系封測廠受惠」

⚠️ 規則：
- 用**繁體中文**
- 嚴格 10 篇，涵蓋至少 3 個不同分類
- **Investment Takeaway 要具體到產業鏈層級**，不要空泛
- **二階效應要寫間接連鎖反應**，不要重複 Investment Takeaway
- 每篇之間用 `---` 分隔
- 最後一定要有 🔗 今日主線
- 直接輸出，不要開場白

以下是今天所有分類的內容：
{context}
"""


def generate_top10(all_articles: dict[str, list[Article]], summaries: dict[str, str]) -> str:
    """用 Codex 產生 Top 10 必讀精選"""
    prompt = build_top10_prompt(all_articles, summaries)

    print(f"  → Codex {CODEX_MODEL} stdin...", end=" ")
    result = _summarize_with_codex(prompt, "Top 10")
    if result:
        print("✅")
        return result

    print("失敗")
    return ""


def _summarize_with_codex(prompt: str, category: str) -> str | None:
    """用原生 Codex CLI stdin 模式做摘要"""
    import time
    codex_path = CODEX_PATH

    if not os.path.exists(codex_path):
        print(f"codex not found at {codex_path}")
        return None

    try:
        # codex exec -m model --json - (stdin)
        start_time = time.time()
        print(f"    ⏱️ Calling {CODEX_MODEL} API...", flush=True)
        result = subprocess.run(
            [
                codex_path, "exec",
                "-m", CODEX_MODEL,
                "--json",
                "--ephemeral",
                "--skip-git-repo-check",
                "-",  # 從 stdin 讀取 prompt
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=tempfile.gettempdir(),
        )
        elapsed = time.time() - start_time
        print(f"    ⏱️ API returned in {elapsed:.1f}s", flush=True)

        if result.returncode == 0 and result.stdout.strip():
            # 解析 JSON lines，提取 agent_message text
            text_parts = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "item.completed":
                        item = event.get("item", {})
                        if item.get("type") == "agent_message" and "text" in item:
                            text_parts.append(item["text"])
                except json.JSONDecodeError:
                    continue

            if text_parts:
                return "\n\n".join(text_parts)

        # fallback: 看 stderr 有沒有有用的資訊
        if result.stderr:
            # 過濾掉 ERROR log 行，只印有意義的
            meaningful = [
                l for l in result.stderr.split("\n")
                if l.strip() and "ERROR codex_core::rollout" not in l
            ]
            if meaningful:
                print(f"  ⚠️ stderr: {meaningful[0][:200]}")
        return None

    except subprocess.TimeoutExpired:
        print(f"    ⏱️ ⚠️ {CODEX_MODEL} API timeout after 180s ({category})")
        return None
    except Exception as e:
        print(f"  ⚠️ Codex 錯誤 ({category}): {e}")
        return None



def _get_prompt_type(category: str) -> str:
    """根據 config 中的 summary_prompt 決定 prompt 類型"""
    config = load_config()
    for feed_key, feed_config in config.get("feeds", {}).items():
        if feed_config.get("category") == category:
            return feed_config.get("summary_prompt", "news")
    return "news"


def summarize_category(category: str, articles: list[Article]) -> str:
    """摘要單一分類的新聞（優先用 Codex CLI，備用 Claude API）"""
    if not articles:
        print(f"  ⏭️ {category}: 無新聞，跳過")
        return f"今天 {category} 無新聞。"

    print(f"  📝 摘要 {category} ({len(articles)} 篇文章)...")
    prompt_type = _get_prompt_type(category)
    prompt = build_prompt(category, articles, prompt_type)

    # Codex CLI
    result = _summarize_with_codex(prompt, category)
    if result:
        print(f"    ✅ {category} 摘要完成")
        return result

    # 失敗：純列表
    print(f"    ⚠️ {category} API 失敗，使用簡單列表")
    return _simple_summary(category, articles)


def _simple_summary(category: str, articles: list[Article]) -> str:
    """無 API 時的簡單摘要（純列表）"""
    lines = [f"**{category}** — {len(articles)} 篇新聞\n"]
    for a in articles[:10]:
        lines.append(f"• **{a.title}**")
        if a.summary:
            lines.append(f"  {a.summary[:100]}...")
        lines.append(f"  — {a.source} | {a.published.strftime('%H:%M')}\n")
    return "\n".join(lines)


def summarize_all(all_articles: dict[str, list[Article]]) -> dict[str, str]:
    """摘要所有分類"""
    summaries = {}
    for category, articles in all_articles.items():
        print(f"🧠 摘要 {category} ({len(articles)} 篇)...")
        summaries[category] = summarize_category(category, articles)
    return summaries


if __name__ == "__main__":
    from datetime import datetime, timezone, timedelta

    TW_TZ = timezone(timedelta(hours=8))
    test_articles = [
        Article(
            title="NVIDIA 財報超預期，AI 晶片需求持續強勁",
            summary="NVIDIA 第四季營收達 350 億美元，超出市場預期。CEO 黃仁勳表示 AI 推理需求正在快速增長。",
            link="https://example.com/1",
            source="CNBC",
            category="🇺🇸 美國財經",
            published=datetime.now(TW_TZ),
        ),
        Article(
            title="Fed 暗示可能延後降息",
            summary="聯準會主席鮑威爾表示通膨仍具黏性，市場降息預期推遲至下半年。",
            link="https://example.com/2",
            source="CNN",
            category="🇺🇸 美國財經",
            published=datetime.now(TW_TZ),
        ),
    ]
    result = summarize_category("🇺🇸 美國財經", test_articles)
    print(result)
