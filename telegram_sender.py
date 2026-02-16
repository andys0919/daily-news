"""Telegram 推送模組"""

import asyncio
import os
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def send_report(report_path: Path, text_summary: str = ""):
    """透過 Telegram Bot 傳送 HTML 報告"""
    import aiohttp

    config = load_config()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", config["telegram"].get("bot_token", ""))
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
        data.add_field("caption", "📰 每日新聞速報")
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


def build_text_summary(
    summaries: dict[str, str],
    market=None,
) -> str:
    """產生 Telegram 文字摘要（精簡版）"""
    from datetime import datetime, timedelta, timezone

    TW_TZ = timezone(timedelta(hours=8))
    now = datetime.now(TW_TZ)

    lines = [f"📰 *每日新聞速報* — {now.strftime('%Y-%m-%d %H:%M')}\n"]

    # 市場概覽
    if market:
        lines.append("📊 *市場概覽*")
        for idx in market.indices:
            if idx.price > 0:
                arrow = "🟢" if idx.change >= 0 else "🔴"
                lines.append(
                    f"  {arrow} {idx.name}: {idx.price:,.2f} ({idx.change_pct:+.2f}%)"
                )
        lines.append("")

    # 各分類摘要（只取前 200 字）
    for category, summary in summaries.items():
        lines.append(f"*{category}*")
        # 截取摘要重點
        short = summary[:300].rsplit("。", 1)[0] + "。" if len(summary) > 300 else summary
        lines.append(short)
        lines.append("")

    lines.append("📎 完整報告見附件 HTML")

    return "\n".join(lines)


if __name__ == "__main__":
    # 測試
    test_summary = build_text_summary(
        {"🇺🇸 美國財經": "NVIDIA 財報超預期，AI 晶片需求強勁。Fed 暗示延後降息。"},
        None,
    )
    print(test_summary)
