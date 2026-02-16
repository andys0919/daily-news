"""每日新聞聚合器 — 主流程"""

import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone

TW_TZ = timezone(timedelta(hours=8))


async def run(hours_back: int = 24, skip_summary: bool = False):
    """執行完整的新聞聚合流程"""
    start = time.time()
    now = datetime.now(TW_TZ)
    print(f"{'='*60}")
    print(f"📰 每日新聞聚合器")
    print(f"⏰ {now.strftime('%Y-%m-%d %H:%M:%S')} (GMT+8)")
    print(f"📡 抓取最近 {hours_back} 小時的新聞")
    print(f"{'='*60}")

    # Step 1: 爬取 RSS
    print(f"\n{'─'*40}")
    print("📡 Step 1: 爬取 RSS 來源")
    print(f"{'─'*40}", flush=True)
    from crawler import crawl_all
    articles = await crawl_all(hours_back=hours_back)

    if not articles:
        print("\n⚠️ 沒有抓到任何新聞，結束", flush=True)
        return

    total_articles = sum(len(a) for a in articles.values())
    print(f"✅ 共抓取 {total_articles} 篇新聞，{len(articles)} 個分類", flush=True)

    # Step 2: 市場數據
    print(f"\n{'─'*40}")
    print("📈 Step 2: 抓取市場數據")
    print(f"{'─'*40}", flush=True)
    from market_data import get_market_overview
    try:
        market = get_market_overview()
        if market:
            print(f"✅ 成功抓取 {len(market.indices)} 個市場指標", flush=True)
    except Exception as e:
        print(f"⚠️ 市場數據抓取失敗: {e}", flush=True)
        market = None

    # Step 3: AI 摘要
    print(f"\n{'─'*40}")
    print("🧠 Step 3: AI 智慧摘要")
    print(f"{'─'*40}", flush=True)
    if skip_summary:
        print("⏭️ 跳過 AI 摘要（--no-summary）", flush=True)
        summaries = {}
        top10_text = ""
    else:
        from summarizer import summarize_all, generate_top10
        print(f"開始摘要 {len(articles)} 個分類...", flush=True)
        summaries = summarize_all(articles)
        print(f"✅ 完成所有分類摘要", flush=True)

        # Step 3.5: Top 10 必讀精選
        print(f"\n{'─'*40}")
        print("🏆 Step 3.5: Top 10 必讀精選")
        print(f"{'─'*40}", flush=True)
        top10_text = generate_top10(articles, summaries)
        print(f"✅ Top 10 生成完成", flush=True)

    # Step 4: 產生 HTML 報告
    print(f"\n{'─'*40}")
    print("📄 Step 4: 產生 HTML 報告")
    print(f"{'─'*40}", flush=True)
    from html_generator import generate_report
    report_path = generate_report(articles, summaries, market, top10=top10_text)
    print(f"✅ 報告已生成: {report_path}", flush=True)

    # Step 5: Telegram 推送
    print(f"\n{'─'*40}")
    print("📤 Step 5: Telegram 推送")
    print(f"{'─'*40}", flush=True)
    from telegram_sender import send_report, build_text_summary
    text_summary = build_text_summary(summaries, market)
    await send_report(report_path, text_summary)
    print(f"✅ 已推送到 Telegram", flush=True)

    # 完成
    elapsed = time.time() - start
    total_articles = sum(len(a) for a in articles.values())
    print(f"\n{'='*60}")
    print(f"✅ 完成！")
    print(f"📊 共 {total_articles} 篇新聞，{len(articles)} 個分類")
    print(f"📄 報告：{report_path}")
    print(f"⏱️ 耗時：{elapsed:.1f} 秒")
    print(f"{'='*60}")

    return report_path


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="每日新聞聚合器")
    parser.add_argument(
        "--hours", type=int, default=24,
        help="抓取最近 N 小時的新聞（預設 24）"
    )
    parser.add_argument(
        "--no-summary", action="store_true",
        help="跳過 AI 摘要（快速測試用）"
    )
    args = parser.parse_args()

    asyncio.run(run(hours_back=args.hours, skip_summary=args.no_summary))


if __name__ == "__main__":
    main()
