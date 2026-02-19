"""每日新聞聚合器 — 主流程"""

import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

TW_TZ = timezone(timedelta(hours=8))


async def run(
    hours_back: int = 168,
    skip_summary: bool = False,
    report_type: Literal["daily", "weekly"] = "weekly",
):
    """執行完整的新聞聚合流程"""
    start = time.time()
    stage_times: dict[str, float] = {}

    def _record_stage(name: str, stage_start: float) -> None:
        elapsed = time.time() - stage_start
        stage_times[name] = elapsed
        print(f"⏱️ {name} 耗時：{elapsed:.1f} 秒", flush=True)

    now = datetime.now(TW_TZ)
    print(f"{'=' * 60}")
    title = "每日新聞聚合器" if report_type == "daily" else "每週新聞聚合器"
    print(f"📰 {title}")
    print(f"⏰ {now.strftime('%Y-%m-%d %H:%M:%S')} (GMT+8)")
    print(f"📡 抓取最近 {hours_back} 小時的新聞")
    print(f"{'=' * 60}")

    # Step 1: 爬取 RSS
    step1_start = time.time()
    print(f"\n{'─' * 40}")
    print("📡 Step 1: 爬取 RSS 來源")
    print(f"{'─' * 40}", flush=True)
    from crawler import crawl_all, get_recent_articles

    new_articles = await crawl_all(hours_back=hours_back)
    articles = get_recent_articles(hours_back=hours_back)

    if not articles:
        print("\n⚠️ 今天沒有任何新聞，結束", flush=True)
        return

    new_total_articles = sum(len(a) for a in new_articles.values())
    total_articles = sum(len(a) for a in articles.values())
    print(
        f"✅ 本次新增 {new_total_articles} 篇；近 {hours_back} 小時累積 {total_articles} 篇，{len(articles)} 個分類",
        flush=True,
    )
    _record_stage("Step 1 爬取 RSS", step1_start)

    # Step 2: 市場數據
    print(f"\n{'─' * 40}")
    print("📈 Step 2: 抓取市場數據（與 AI 摘要並行）")
    print(f"{'─' * 40}", flush=True)
    from market_data import get_market_overview

    async def _fetch_market_in_background():
        started = time.time()
        try:
            result = await asyncio.to_thread(get_market_overview)
            return result, None, time.time() - started
        except Exception as e:
            return None, e, time.time() - started

    market_task = asyncio.create_task(_fetch_market_in_background())
    market = None
    print("🚀 市場數據背景抓取中", flush=True)

    # Step 3: AI 摘要
    step3_start = time.time()
    print(f"\n{'─' * 40}")
    print("🧠 Step 3: AI 智慧摘要")
    print(f"{'─' * 40}", flush=True)
    usage_summary: dict = {}
    citation_links: dict[str, dict[int, str]] = {}
    if skip_summary:
        print("⏭️ 跳過 AI 摘要（--no-summary）", flush=True)
        summaries = {}
        top10_text = ""
    else:
        from summarizer import (
            summarize_all,
            generate_top10,
            reset_usage_stats,
            get_usage_summary,
            build_all_citation_links,
        )

        reset_usage_stats()
        print(f"開始摘要 {len(articles)} 個分類...", flush=True)
        summaries = summarize_all(articles)
        citation_links = build_all_citation_links(articles)
        print(f"✅ 完成所有分類摘要", flush=True)

        # Step 3.5: 今日全重點綜整
        print(f"\n{'─' * 40}")
        print("🧭 Step 3.5: 今日全重點綜整")
        print(f"{'─' * 40}", flush=True)
        top10_text = generate_top10(articles, summaries)
        print(f"✅ 今日全重點生成完成", flush=True)

        usage_summary = get_usage_summary()
        if usage_summary.get("total_cost_usd") is not None:
            print(
                "💵 成本估算: "
                f"model={usage_summary.get('model')} "
                f"in={usage_summary.get('input_tokens')} "
                f"out={usage_summary.get('output_tokens')} "
                f"cost=${float(usage_summary['total_cost_usd']):.6f} USD",
                flush=True,
            )
    _record_stage("Step 3 AI 摘要", step3_start)

    # 收斂 Step 2 結果（背景任務）
    market, market_error, market_elapsed = await market_task
    stage_times["Step 2 市場數據"] = market_elapsed
    print(f"⏱️ Step 2 市場數據 耗時：{market_elapsed:.1f} 秒", flush=True)
    if market_error:
        print(f"⚠️ 市場數據抓取失敗: {market_error}", flush=True)
        market = None
    elif market:
        print(f"✅ 成功抓取 {len(market.indices)} 個市場指標", flush=True)

    # Step 4: 產生 HTML 報告
    step4_start = time.time()
    print(f"\n{'─' * 40}")
    print("📄 Step 4: 產生 HTML 報告")
    print(f"{'─' * 40}", flush=True)
    from html_generator import generate_report

    report_path = generate_report(
        articles,
        summaries,
        market,
        top10=top10_text,
        ai_usage=usage_summary,
        citation_links=citation_links,
        report_type=report_type,
    )
    print(f"✅ 報告已生成: {report_path}", flush=True)
    _record_stage("Step 4 產生報告", step4_start)

    # Step 5: Telegram 推送
    step5_start = time.time()
    print(f"\n{'─' * 40}")
    print("📤 Step 5: Telegram 推送")
    print(f"{'─' * 40}", flush=True)
    from telegram_sender import send_report, build_text_summary

    text_summary = build_text_summary(summaries, market, top10=top10_text, report_type=report_type)
    sent_ok = await send_report(report_path, text_summary, report_type=report_type)
    if sent_ok:
        print(f"✅ 已推送到 Telegram", flush=True)
    else:
        print(f"ℹ️ Telegram 推送已跳過或失敗", flush=True)
    _record_stage("Step 5 Telegram 推送", step5_start)

    # 完成
    elapsed = time.time() - start
    total_articles = sum(len(a) for a in articles.values())
    print(f"\n{'=' * 60}")
    print(f"✅ 完成！")
    print(f"📊 共 {total_articles} 篇新聞，{len(articles)} 個分類")
    print(f"📄 報告：{report_path}")
    print(f"⏱️ 耗時：{elapsed:.1f} 秒")
    if stage_times:
        print("⏱️ 各階段耗時：")
        for stage_name in [
            "Step 1 爬取 RSS",
            "Step 2 市場數據",
            "Step 3 AI 摘要",
            "Step 4 產生報告",
            "Step 5 Telegram 推送",
        ]:
            if stage_name in stage_times:
                print(f"  - {stage_name}: {stage_times[stage_name]:.1f} 秒")
    print(f"{'=' * 60}")

    return report_path


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="每日新聞聚合器")
    parser.add_argument(
        "--hours",
        type=int,
        default=168,
        help="抓取最近 N 小時的新聞（預設 168 = 近一週）",
    )
    parser.add_argument(
        "--no-summary", action="store_true", help="跳過 AI 摘要（快速測試用）"
    )
    parser.add_argument(
        "--report-type",
        choices=["daily", "weekly"],
        default="weekly",
        help="報告類型：daily（每日）或 weekly（每週）",
    )
    args = parser.parse_args()

    selected_report_type: Literal["daily", "weekly"] = (
        "daily" if args.report_type == "daily" else "weekly"
    )

    asyncio.run(
        run(
            hours_back=args.hours,
            skip_summary=args.no_summary,
            report_type=selected_report_type,
        )
    )


if __name__ == "__main__":
    main()
