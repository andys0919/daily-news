"""Telegram 推送模組"""

import asyncio
import os
import re
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"
DB_PATH = Path(__file__).parent / "data" / "news.db"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def send_report(
    report_path: Path,
    text_summary: str = "",
    report_type: str = "weekly",
):
    """透過 Telegram Bot 傳送 HTML 報告"""
    import aiohttp

    config = load_config()
    token = os.environ.get(
        "TELEGRAM_BOT_TOKEN", config["telegram"].get("bot_token", "")
    )
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", config["telegram"].get("chat_id", ""))

    if not token or token.startswith("$"):
        print("⚠️ 未設定 TELEGRAM_BOT_TOKEN，跳過推送")
        print(f"📄 報告位置：{report_path}")
        return False

    if not chat_id or chat_id.startswith("$"):
        print("⚠️ 未設定 TELEGRAM_CHAT_ID，跳過推送")
        return False

    base_url = f"https://api.telegram.org/bot{token}"

    async with aiohttp.ClientSession() as session:
        # 1. 先傳一條文字摘要
        if text_summary:
            text_data = {
                "chat_id": chat_id,
                "text": text_summary,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            async with session.post(f"{base_url}/sendMessage", json=text_data) as resp:
                if resp.status == 200:
                    print("✅ 文字摘要已推送")
                else:
                    error = await resp.text()
                    print(f"⚠️ 文字推送失敗: {error}")

        # 2. 傳送 HTML 檔案
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        caption = "📰 每日新聞速報" if report_type == "daily" else "📰 每週新聞速報"
        data.add_field("caption", caption)
        data.add_field(
            "document",
            open(report_path, "rb"),
            filename=report_path.name,
            content_type="text/html",
        )

        async with session.post(f"{base_url}/sendDocument", data=data) as resp:
            if resp.status == 200:
                print("✅ HTML 報告已推送到 Telegram")
                return True
            else:
                error = await resp.text()
                print(f"❌ 報告推送失敗: {error}")
                return False


_WEEKDAY_ZH = ["一", "二", "三", "四", "五", "六", "日"]

# 用於從 markdown 摘要提取 bullet 的 regex
_BULLET_RE = re.compile(r"^[-•]\s+(.+)$", re.MULTILINE)
# 用於提取公司名/ticker 作為去重 key
_DEDUP_KEY_RE = re.compile(
    r"(?:NVDA|MSFT|GOOGL|META|AMZN|AAPL|TSLA|AMD|ASML|INTC|TSM|AVGO|"
    r"台積電|鴻海|聯發科|日月光|NVIDIA|Microsoft|Google|Apple|Amazon|"
    r"Tesla|Intel|Broadcom|Samsung|SK ?海力士|Fed|FOMC|CPI|"
    r"BTC|ETH|Bitcoin|Ethereum|HBM|CoWoS)",
    re.IGNORECASE,
)


def _extract_bullets(summary: str, max_bullets: int = 5) -> list[str]:
    """從 markdown 摘要提取 bullet points"""
    bullets = _BULLET_RE.findall(summary)
    # 過濾太短或太空泛的 bullet
    result = []
    for b in bullets:
        b = b.strip()
        # 跳過太短的、純標題的、或空泛的
        if len(b) < 10:
            continue
        # 跳過「目前資訊不足」之類的 filler
        if "目前資訊不足" in b or "目前尚無" in b:
            continue
        result.append(b)
        if len(result) >= max_bullets:
            break
    return result


def _dedup_key(text: str) -> set[str]:
    """提取文字中的公司名/ticker 作為去重 key"""
    return {m.upper() for m in _DEDUP_KEY_RE.findall(text)}


def _extract_memo_main_thread(memo: str) -> str:
    """從 memo 文字提取今日主線段落"""
    if not memo:
        return ""
    # 找 "### 今日主線" 段落
    lines = memo.split("\n")
    capture = False
    result = []
    for line in lines:
        if "今日主線" in line:
            capture = True
            continue
        if capture:
            if line.startswith("###"):
                break
            stripped = line.strip()
            if not stripped:
                continue
            # 清理編號前綴（1. 2. 等）和 markdown
            stripped = re.sub(r"^[-•]\s*\d+\)\s*", "", stripped)
            stripped = re.sub(r"^\d+[.）)]\s*", "", stripped)
            stripped = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
            if len(stripped) > 120:
                stripped = stripped[:117].rstrip("，、；") + "…"
            if stripped:
                result.append(stripped)
    return "\n".join(result[:4])  # 最多 4 句


def _extract_memo_observations(memo: str) -> list[str]:
    """從 memo 文字提取 48 小時觀察點"""
    if not memo:
        return []

    obs_lines = []
    capture = False
    for line in memo.split("\n"):
        if ("48" in line or "四十八" in line) and ("觀察" in line or "清單" in line):
            capture = True
            continue
        if capture:
            if line.startswith("###"):
                break
            stripped = line.strip()
            if not stripped:
                continue
            if stripped[0] in "-•" or (
                len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".）)"
            ):
                clean = re.sub(r"^\d+[.）)]\s*", "", stripped.lstrip("-• ")).strip()
                clean = re.sub(r"\s*\[\d+\]", "", clean).strip()
                if len(clean) > 100:
                    clean = clean[:97].rstrip("，、；") + "…"
                if clean:
                    obs_lines.append(f"• {clean}")
    return obs_lines


def _format_market_compact(market) -> list[str]:
    """市場數據壓縮為單行格式"""
    if not market or not market.indices:
        return []

    # 定義要顯示的 key indices（按 group 排序）
    key_symbols = {
        "S&P 500",
        "NASDAQ",
        "台股加權",
        "Bitcoin",
        "VIX 恐慌",
        "USD/TWD",
        "Gold",
        "Silver",
    }
    lines = ["━━━ 市場速覽 ━━━"]
    row = []
    for idx in market.indices:
        if idx.name not in key_symbols or idx.price <= 0:
            continue
        arrow = "🟢" if idx.change >= 0 else "🔴"
        if idx.name == "VIX 恐慌":
            row.append(f"VIX {idx.price:.1f}")
        elif idx.name == "USD/TWD":
            row.append(f"USD/TWD {idx.price:.2f}")
        elif idx.name == "Bitcoin":
            row.append(f"{arrow} BTC {idx.change_pct:+.1f}%")
        elif idx.name == "Gold":
            row.append(f"{arrow} Gold {idx.change_pct:+.1f}%")
        elif idx.name == "Silver":
            row.append(f"{arrow} Silver {idx.change_pct:+.1f}%")
        else:
            row.append(f"{arrow} {idx.name} {idx.change_pct:+.2f}%")

    # 每行 2-3 個指標
    for i in range(0, len(row), 3):
        lines.append(" │ ".join(row[i : i + 3]))
    return lines


def build_text_summary(
    summaries: dict[str, str],
    market=None,
    memo: str = "",
    top10: str = "",
    report_type: str = "weekly",
    articles: dict | None = None,
) -> str:
    """產生投行晨報風格的 Telegram 文字摘要"""
    from datetime import datetime, timedelta, timezone

    TW_TZ = timezone(timedelta(hours=8))
    now = datetime.now(TW_TZ)
    weekday = _WEEKDAY_ZH[now.weekday()]

    title = "每日新聞日報" if report_type == "daily" else "每週新聞週報"
    lines = [f"📊 {title} — {now.strftime('%Y-%m-%d')} ({weekday})", ""]

    # 市場速覽（壓縮格式）
    market_lines = _format_market_compact(market)
    if market_lines:
        lines.extend(market_lines)
        lines.append("")

    memo_text = memo or top10

    # 今日主線（從 memo 提取）
    main_thread = _extract_memo_main_thread(memo_text)
    if main_thread:
        lines.append("━━━ 今日主線 ━━━")
        lines.append(main_thread)
        lines.append("")

    if articles:
        try:
            from financial_reports import build_financial_highlight_entries

            highlights = build_financial_highlight_entries(articles, db_path=DB_PATH, max_entries=3)
        except Exception:
            highlights = []
        if highlights:
            lines.append("━━━ 財報重點 ━━━")
            for item in highlights:
                lines.append(f"• {item['company_name']} ({item['ticker']})：{item['summary']}")
            lines.append("")

    if not memo_text:
        # 分類速覽（fallback：只有在尚未切到單篇 memo 時使用）
        seen_keys: set[str] = set()
        if main_thread:
            seen_keys.update(_dedup_key(main_thread))

        category_sections = []
        for category, summary in summaries.items():
            if not summary:
                continue
            bullets = _extract_bullets(summary, max_bullets=5)
            if not bullets:
                continue

            deduped_bullets = []
            for b in bullets:
                b_keys = _dedup_key(b)
                if b_keys and b_keys.issubset(seen_keys):
                    continue
                seen_keys.update(b_keys)
                clean = re.sub(r"\s*\[\d+\]", "", b).strip()
                clean = re.sub(r"[；。，]?\s*來源：\s*$", "", clean).strip()
                clean = re.sub(r"[；。，]?\s*引用：\s*$", "", clean).strip()
                if len(clean) > 120:
                    clean = clean[:117].rstrip("，、；") + "…"
                if len(clean) < 10:
                    continue
                deduped_bullets.append(f"• {clean}")

            if deduped_bullets:
                category_sections.append((category, deduped_bullets[:5]))

        if category_sections:
            lines.append("━━━ 分類速覽 ━━━")
            for cat, bullets in category_sections:
                lines.append(f"*{cat}*")
                lines.extend(bullets)
                lines.append("")

    obs_lines = _extract_memo_observations(memo_text)
    if obs_lines:
        lines.append("━━━ 48h 觀察 ━━━")
        lines.extend(obs_lines[:4])
        lines.append("")

    lines.append("📎 完整報告見附件")

    # 長度控制：Telegram 限 4096 字元
    result = "\n".join(lines)
    if len(result) > 3500:
        # 截斷分類速覽中較長的部分
        result = result[:3450].rsplit("\n", 1)[0] + "\n\n📎 完整報告見附件"

    return result


if __name__ == "__main__":
    # 測試
    test_summary = build_text_summary(
        {"💰 財經與總經": "- NVIDIA Q4 營收 $350 億超預期，guidance 上調 15% [1]\n- Fed 鮑威爾重申通膨黏性，降息預期推至 H2 [2]"},
        None,
        top10="### 今日主線\nNVIDIA 財報超預期帶動 AI 算力需求敘事，Fed 偏鷹推遲降息預期。",
        report_type="daily",
    )
    print(test_summary)
