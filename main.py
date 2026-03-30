"""每日新聞聚合器 — 主流程"""

import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

TW_TZ = timezone(timedelta(hours=8))


def _find_ai_radar_category(articles: dict[str, list[object]]) -> str | None:
    for category, category_articles in articles.items():
        for article in category_articles:
            if getattr(article, "summary_prompt", None) == "ai_practice":
                return category
            if "AI 工具與實戰" in (getattr(article, "category", "") or ""):
                return category
    return None


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
    from earnings_data import refresh_us_financial_reports_for_articles
    from mops_financials import refresh_mops_financial_reports_for_articles
    from tpex_financials import refresh_tpex_financial_reports_for_articles
    from tw_financials import refresh_tw_financial_reports_for_articles

    async def _fetch_market_in_background():
        started = time.time()
        try:
            result = await asyncio.to_thread(get_market_overview)
            return result, None, time.time() - started
        except Exception as e:
            return None, e, time.time() - started

    async def _refresh_financials_in_background():
        started = time.time()
        us_count = tw_count = tpex_count = mops_count = 0
        errors: list[str] = []
        try:
            us_reports = await asyncio.to_thread(
                refresh_us_financial_reports_for_articles, articles
            )
            us_count = len(us_reports)
        except Exception as e:
            errors.append(f"US: {e}")
        try:
            tw_reports = await asyncio.to_thread(
                refresh_tw_financial_reports_for_articles, articles
            )
            tw_count = len(tw_reports)
        except Exception as e:
            errors.append(f"TW: {e}")
        try:
            tpex_reports = await asyncio.to_thread(
                refresh_tpex_financial_reports_for_articles, articles
            )
            tpex_count = len(tpex_reports)
        except Exception as e:
            errors.append(f"TPEX: {e}")
        try:
            mops_reports = await asyncio.to_thread(
                refresh_mops_financial_reports_for_articles, articles
            )
            mops_count = len(mops_reports)
        except Exception as e:
            errors.append(f"MOPS: {e}")
        return {"us": us_count, "tw": tw_count, "tpex": tpex_count, "mops": mops_count}, errors, time.time() - started

    market_task = asyncio.create_task(_fetch_market_in_background())
    financial_task = asyncio.create_task(_refresh_financials_in_background())
    market = None
    print("🚀 市場數據與財務資料背景抓取中", flush=True)

    financial_counts, financial_errors, financial_elapsed = await financial_task
    stage_times["Step 2.5 財務資料"] = financial_elapsed
    print(f"⏱️ Step 2.5 財務資料 耗時：{financial_elapsed:.1f} 秒", flush=True)
    if financial_errors:
        print(
            f"⚠️ 財務資料刷新部分失敗: {' | '.join(financial_errors)}",
            flush=True,
        )
    else:
        print(
            "✅ 財務資料刷新完成: "
            f"US {financial_counts['us']} 筆 / TW {financial_counts['tw']} 筆 / TPEX {financial_counts['tpex']} 筆 / MOPS {financial_counts['mops']} 筆",
            flush=True,
        )

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
        if report_type == "daily":
            from summarizer import (
                generate_daily_memo_from_articles,
                get_usage_summary,
                reset_usage_stats,
                summarize_ai_github_digest,
            )

            reset_usage_stats()
            summaries = {}
            citation_links = {}
            print(f"開始準備每日整體 Memo 輸入（{len(articles)} 個分類）...", flush=True)

            print(f"\n{'─' * 40}")
            print("🧭 Step 3.5: 每日整體 Memo")
            print(f"{'─' * 40}", flush=True)
            top10_text = generate_daily_memo_from_articles(articles)
            print(f"✅ 每日整體 Memo 生成完成", flush=True)

            ai_radar_category = _find_ai_radar_category(articles)
            if ai_radar_category:
                print(f"\n{'─' * 40}")
                print("🛠️ Step 3.6: AI 技術雷達")
                print(f"{'─' * 40}", flush=True)
                try:
                    (
                        summaries[ai_radar_category],
                        citation_links[ai_radar_category],
                    ) = summarize_ai_github_digest(
                        ai_radar_category,
                        articles[ai_radar_category],
                    )
                    print(f"✅ AI 技術雷達摘要完成", flush=True)
                except Exception as e:
                    print(f"⚠️ AI 技術雷達摘要失敗：{e}", flush=True)
        else:
            from summarizer import (
                summarize_all,
                generate_daily_memo,
                reset_usage_stats,
                get_usage_summary,
                build_all_citation_links,
            )

            reset_usage_stats()
            print(f"開始摘要 {len(articles)} 個分類...", flush=True)
            summaries = summarize_all(articles)
            citation_links = build_all_citation_links(articles)
            print(f"✅ 完成所有分類摘要", flush=True)

            # Step 3.5: 每日整體 memo
            print(f"\n{'─' * 40}")
            print("🧭 Step 3.5: 每日整體 Memo")
            print(f"{'─' * 40}", flush=True)
            top10_text = generate_daily_memo(articles, summaries)
            print(f"✅ 每日整體 Memo 生成完成", flush=True)

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
        memo=top10_text,
        top10=top10_text,
        ai_usage=usage_summary,
        citation_links=citation_links,
        report_type=report_type,
    )
    print(f"✅ 報告已生成: {report_path}", flush=True)
    _record_stage("Step 4 產生報告", step4_start)

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
            "Step 2.5 財務資料",
            "Step 3 AI 摘要",
            "Step 4 產生報告",
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
