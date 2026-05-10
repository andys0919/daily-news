"""Issuer-first stock memo builder for TW and US equities."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from crawler import Article
from earnings_data import (
    SEC_COMPANYFACTS_URL,
    SEC_SUBMISSIONS_URL,
    refresh_us_financial_reports,
)
from financial_reports import (
    DB_PATH,
    FinancialSnapshotBundle,
    format_financial_snapshot_bundle_context,
    get_financial_snapshot_bundle,
)
from mops_financials import MOPS_QUERY_REFERER, refresh_mops_financial_reports
from tpex_financials import TPEX_COMPANY_PAGE_URL, refresh_tpex_financial_reports
from tw_financials import TW_MONTHLY_REVENUE_URL, refresh_tw_financial_reports


TW_TZ = timezone(timedelta(hours=8))
MEMO_OUTPUT_DIR = Path(__file__).parent / "data" / "memos"
MOPS_INVESTOR_LOOKUP_URL = "https://mops.twse.com.tw/mops/web/t100sb07_1"
MOPS_XBRL_LOOKUP_URL = "https://mops.twse.com.tw/mops/web/t164sb03"
TWSE_INVESTOR_VIDEO_SEARCH_URL = "https://webpro.twse.com.tw/WebPortal/search/investor/"
TPEX_INVESTOR_VIDEO_SEARCH_URL = "https://www.tpex.org.tw/zh-tw/about/company/media/seminar.html"


@dataclass
class OfficialMaterial:
    title: str
    url: str
    material_type: str
    source_type: str
    note: str = ""


@dataclass
class StockMemoPacket:
    market: Literal["tw", "us"]
    ticker: str
    company_name: str
    bundle: FinancialSnapshotBundle
    official_materials: list[OfficialMaterial] = field(default_factory=list)
    related_articles: list[Article] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(TW_TZ))


def _normalize_ticker(ticker: str, market: str | None = None) -> str:
    raw = str(ticker or "").strip().upper().replace("$", "")
    if raw.endswith(".TW") or raw.endswith(".TWO"):
        raw = raw.replace(".TW", "").replace(".TWO", "")
    if market == "tw" or raw.isdigit():
        return "".join(ch for ch in raw if ch.isdigit())
    return raw


def _infer_market(ticker: str) -> Literal["tw", "us"]:
    return "tw" if _normalize_ticker(ticker).isdigit() else "us"


def _article_market(article: Article) -> Literal["tw", "us"]:
    for ticker in getattr(article, "tickers", []) or []:
        if _normalize_ticker(str(ticker)).isdigit():
            return "tw"
    return "us"


def _json_loads_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _load_recent_articles(
    *,
    db_path: str | Path = DB_PATH,
    hours_back: int = 24 * 30,
) -> dict[str, list[Article]]:
    path = Path(db_path)
    if not path.exists():
        return {}

    cutoff = datetime.now(TW_TZ) - timedelta(hours=hours_back)
    conn = sqlite3.connect(str(path))
    try:
        table_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"
        ).fetchone()
        if not table_row:
            return {}
        cursor = conn.execute(
            """SELECT title, summary, link, source, category, published,
                      source_key, summary_prompt, source_priority, source_quality,
                      feed_key, region, topics_json, published_raw,
                      published_confidence, body_text, body_source,
                      extraction_status, publisher, author, companies_json,
                      tickers_json, event_type, event_key
               FROM articles WHERE published >= ?
               ORDER BY category, published DESC""",
            (cutoff.isoformat(),),
        )
        articles: dict[str, list[Article]] = {}
        for row in cursor.fetchall():
            article = Article(
                title=row[0],
                summary=row[1],
                link=row[2],
                source=row[3],
                source_key=row[6],
                category=row[4],
                summary_prompt=row[7],
                published=datetime.fromisoformat(row[5]),
                source_priority=int(row[8] or 5),
                source_quality=str(row[9] or "medium"),
                feed_key=str(row[10] or ""),
                region=str(row[11] or "global"),
                topics=_json_loads_list(row[12]),
                published_raw=str(row[13] or ""),
                published_confidence=str(row[14] or "feed"),
                body_text=str(row[15] or ""),
                body_source=str(row[16] or ""),
                extraction_status=str(row[17] or "not_attempted"),
                publisher=str(row[18] or ""),
                author=str(row[19] or ""),
                companies=_json_loads_list(row[20]),
                tickers=_json_loads_list(row[21]),
                event_type=str(row[22] or ""),
                event_key=str(row[23] or ""),
            )
            articles.setdefault(article.category, []).append(article)
        return articles
    finally:
        conn.close()


def _match_article(
    article: Article,
    *,
    market: Literal["tw", "us"],
    ticker: str,
    company_name: str,
) -> bool:
    article_tickers = {
        _normalize_ticker(str(raw), market) for raw in (getattr(article, "tickers", []) or [])
    }
    if ticker in article_tickers:
        return True

    article_companies = {str(name).strip().lower() for name in (getattr(article, "companies", []) or [])}
    if company_name.strip().lower() in article_companies:
        return True

    return False


def _select_related_articles(
    articles_by_category: dict[str, list[Article]],
    *,
    market: Literal["tw", "us"],
    ticker: str,
    company_name: str,
    max_articles: int = 8,
) -> list[Article]:
    candidates: list[Article] = []
    seen: set[str] = set()
    for articles in articles_by_category.values():
        for article in articles:
            if not _match_article(
                article,
                market=market,
                ticker=ticker,
                company_name=company_name,
            ):
                continue
            dedupe_key = (
                getattr(article, "event_key", "")
                or getattr(article, "link", "")
                or getattr(article, "title", "")
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            candidates.append(article)
    candidates.sort(key=lambda article: article.published, reverse=True)
    return candidates[:max_articles]


def _append_material(
    materials: list[OfficialMaterial],
    seen_urls: set[str],
    *,
    title: str,
    url: str,
    material_type: str,
    source_type: str,
    note: str = "",
) -> None:
    clean_url = str(url or "").strip()
    if not clean_url or clean_url in seen_urls:
        return
    seen_urls.add(clean_url)
    materials.append(
        OfficialMaterial(
            title=title,
            url=clean_url,
            material_type=material_type,
            source_type=source_type,
            note=note,
        )
    )


def _tw_official_materials(bundle: FinancialSnapshotBundle) -> list[OfficialMaterial]:
    materials: list[OfficialMaterial] = []
    seen_urls: set[str] = set()
    ticker = bundle.ticker

    if bundle.quarterly:
        report = bundle.quarterly
        _append_material(
            materials,
            seen_urls,
            title=f"{bundle.company_name} 最新季度財務資料",
            url=report.source_url,
            material_type="quarterly_financial",
            source_type=report.source_type,
        )
    if bundle.monthly_revenue:
        monthly = bundle.monthly_revenue
        _append_material(
            materials,
            seen_urls,
            title=f"{bundle.company_name} 月營收資料",
            url=monthly.source_url,
            material_type="monthly_revenue",
            source_type=monthly.source_type,
        )

    _append_material(
        materials,
        seen_urls,
        title="MOPS 法人說明會查詢",
        url=MOPS_INVESTOR_LOOKUP_URL,
        material_type="investor_conference_lookup",
        source_type="mops",
        note=f"可用公司代號 {ticker} 查法說簡報與會議資訊",
    )
    _append_material(
        materials,
        seen_urls,
        title="TWSE 法人說明會影音",
        url=TWSE_INVESTOR_VIDEO_SEARCH_URL,
        material_type="investor_video_lookup",
        source_type="twse-webpro",
        note=f"可搜尋 {ticker} 的法說會 / 公司自辦法說會影音",
    )
    _append_material(
        materials,
        seen_urls,
        title="TPEx 法人說明會影音",
        url=TPEX_INVESTOR_VIDEO_SEARCH_URL,
        material_type="investor_video_lookup",
        source_type="tpex",
        note=f"若為上櫃/興櫃，可搜尋 {ticker} 的法說 / 業績發表會影音",
    )
    _append_material(
        materials,
        seen_urls,
        title="MOPS XBRL / iXBRL 財報查詢",
        url=MOPS_XBRL_LOOKUP_URL,
        material_type="xbrl_lookup",
        source_type="mops",
        note=f"可查 {ticker} 的完整財報與附註",
    )
    if bundle.quarterly and bundle.quarterly.source_type == "tpex-finance-report":
        _append_material(
            materials,
            seen_urls,
            title="TPEx 公司基本資料頁",
            url=TPEX_COMPANY_PAGE_URL.format(ticker=ticker),
            material_type="company_profile",
            source_type="tpex",
        )
    return materials


def _us_official_materials(bundle: FinancialSnapshotBundle) -> list[OfficialMaterial]:
    materials: list[OfficialMaterial] = []
    seen_urls: set[str] = set()
    quarterly = bundle.quarterly
    cik = quarterly.cik if quarterly else ""

    if cik:
        _append_material(
            materials,
            seen_urls,
            title="SEC CompanyFacts API",
            url=SEC_COMPANYFACTS_URL.format(cik=str(cik).zfill(10)),
            material_type="companyfacts_api",
            source_type="sec",
        )
        _append_material(
            materials,
            seen_urls,
            title="SEC Submissions API",
            url=SEC_SUBMISSIONS_URL.format(cik=str(cik).zfill(10)),
            material_type="submissions_api",
            source_type="sec",
        )
    if quarterly and quarterly.source_url:
        filing_title = f"Latest SEC {quarterly.form_type or 'filing'}"
        _append_material(
            materials,
            seen_urls,
            title=filing_title,
            url=quarterly.source_url,
            material_type="filing",
            source_type=quarterly.source_type,
        )
        try:
            payload = json.loads(quarterly.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        filing = payload.get("submissions", {})
        if isinstance(filing, dict):
            filing_url = str(filing.get("source_url", "")).strip()
            filing_form = str(filing.get("form_type", "")).strip()
            _append_material(
                materials,
                seen_urls,
                title=f"Recent SEC {filing_form or 'filing'} record",
                url=filing_url,
                material_type="filing",
                source_type="sec-submissions",
            )
    return materials


def _build_official_materials(bundle: FinancialSnapshotBundle) -> list[OfficialMaterial]:
    if bundle.market == "tw":
        return _tw_official_materials(bundle)
    return _us_official_materials(bundle)


def _refresh_bundle(
    *,
    market: Literal["tw", "us"],
    ticker: str,
    db_path: str | Path,
) -> list[str]:
    warnings: list[str] = []
    if market == "us":
        try:
            refresh_us_financial_reports([ticker], db_path=db_path)
        except Exception as exc:
            warnings.append(f"US official refresh failed: {exc}")
        return warnings

    refreshed = False
    for refresh_fn in (refresh_tw_financial_reports, refresh_mops_financial_reports):
        try:
            reports = refresh_fn([ticker], db_path=db_path)
            refreshed = refreshed or bool(reports)
        except Exception as exc:
            warnings.append(f"{refresh_fn.__name__} failed: {exc}")
    if refreshed:
        return warnings
    try:
        refresh_tpex_financial_reports([ticker], db_path=db_path)
    except Exception as exc:
        warnings.append(f"refresh_tpex_financial_reports failed: {exc}")
    return warnings


def collect_stock_memo_packet(
    *,
    ticker: str,
    market: Literal["tw", "us"] | None = None,
    db_path: str | Path = DB_PATH,
    hours_back: int = 24 * 30,
    articles_by_category: dict[str, list[Article]] | None = None,
    refresh_official_data: bool = True,
) -> StockMemoPacket:
    resolved_market = market or _infer_market(ticker)
    normalized_ticker = _normalize_ticker(ticker, resolved_market)
    warnings: list[str] = []

    if refresh_official_data:
        warnings.extend(
            _refresh_bundle(
                market=resolved_market,
                ticker=normalized_ticker,
                db_path=db_path,
            )
        )

    bundle = get_financial_snapshot_bundle(
        db_path=db_path,
        market=resolved_market,
        ticker=normalized_ticker,
    )
    if not bundle:
        raise ValueError(f"找不到 {normalized_ticker} 的官方財務資料")

    articles = articles_by_category
    if articles is None:
        articles = _load_recent_articles(db_path=db_path, hours_back=hours_back)

    related_articles = _select_related_articles(
        articles,
        market=resolved_market,
        ticker=normalized_ticker,
        company_name=bundle.company_name,
    )
    if not related_articles:
        warnings.append("近期待對應新聞為空，memo 主要依官方財務資料生成")

    return StockMemoPacket(
        market=resolved_market,
        ticker=normalized_ticker,
        company_name=bundle.company_name or normalized_ticker,
        bundle=bundle,
        official_materials=_build_official_materials(bundle),
        related_articles=related_articles,
        warnings=warnings,
    )


def render_stock_memo(packet: StockMemoPacket) -> str:
    market_label = "台股" if packet.market == "tw" else "美股"
    summary = format_financial_snapshot_bundle_context(packet.bundle)
    lines = [
        f"# {packet.company_name} ({packet.ticker}) 個股 Memo",
        "",
        f"- 市場：{market_label}",
        f"- 生成時間：{packet.generated_at.strftime('%Y-%m-%d %H:%M:%S')} (GMT+8)",
        f"- 主要資料基準：{summary}",
        "",
        "## 官方財務快照",
    ]

    if packet.bundle.quarterly:
        quarterly = packet.bundle.quarterly
        quarter_bits = [quarterly.form_type or "官方財報"]
        if quarterly.fiscal_year and quarterly.fiscal_period:
            quarter_bits.append(f"FY{quarterly.fiscal_year} {quarterly.fiscal_period}")
        if quarterly.revenue is not None:
            quarter_bits.append(f"營收 {quarterly.revenue:,.0f}")
        if quarterly.eps_diluted is not None:
            quarter_bits.append(f"EPS {quarterly.eps_diluted:.2f}")
        if quarterly.free_cash_flow is not None:
            quarter_bits.append(f"FCF {quarterly.free_cash_flow:,.0f}")
        lines.append(f"- {' | '.join(quarter_bits)}")
        if quarterly.guidance_summary:
            lines.append(f"- Guidance / 管理層重點：{quarterly.guidance_summary}")
        if quarterly.filing_excerpt:
            lines.append(f"- Filing / 財報摘錄：{quarterly.filing_excerpt}")

    if packet.bundle.monthly_revenue and packet.bundle.monthly_revenue.monthly_revenue is not None:
        monthly = packet.bundle.monthly_revenue
        lines.append(
            f"- {monthly.fiscal_period} 月營收 {monthly.monthly_revenue:,.0f}"
        )

    bundle = packet.bundle

    lines.extend(["", "## 最新法說會重點"])
    if bundle.latest_transcript:
        title = (bundle.latest_transcript.get("title") or "").strip()
        body = (bundle.latest_transcript.get("body_text") or "").strip()
        excerpt = body[:600].replace("\n", " ")
        if title:
            lines.append(f"- {title}")
        if excerpt:
            lines.append(f"- 摘錄：{excerpt}")
    else:
        lines.append("- （暫無法說 / transcript 紀錄）")

    lines.extend(["", "## 近 90 天內部人交易"])
    if bundle.recent_insider_summary:
        s = bundle.recent_insider_summary
        lines.append(
            f"- 共 {s.get('count', 0)} 筆 (買 {s.get('buys', 0)} / 賣 {s.get('sells', 0)})"
        )
        latest = s.get("latest") or {}
        if latest:
            lines.append(
                f"- 最近一筆：{latest.get('insider_name', '')} "
                f"{latest.get('transaction_type', '')} "
                f"{latest.get('shares', 0):,} 股 @ {latest.get('price', 0):.2f}"
            )
    else:
        lines.append("- （暫無內部人交易紀錄）")

    lines.extend(["", "## 13F 機構動向"])
    if bundle.latest_13f:
        h = bundle.latest_13f
        lines.append(
            f"- {h.get('reporter_name', '')} 持有 {h.get('issuer_name', '')} "
            f"{h.get('shares', 0):,} 股 (期間 {h.get('period_end', '')})"
        )
    else:
        lines.append("- （暫無 13F 持股紀錄）")

    lines.extend(["", "## 融券與 ETF 資金流"])
    if bundle.short_interest:
        si = bundle.short_interest
        ratio = si.get("short_interest_ratio") or 0
        lines.append(
            f"- 融券餘額 {si.get('short_interest', 0):,.0f} "
            f"(券資比 {ratio:.1%}, 來源 {si.get('source', '')})"
        )
    else:
        lines.append("- （暫無融券 / ETF 資金流紀錄）")

    lines.extend(["", "## 宏觀脈絡"])
    try:
        from macro_data import aggregate_hyperscaler_capex
        capex = aggregate_hyperscaler_capex()
        if capex.tickers_included:
            tickers_str = "/".join(capex.tickers_included)
            lines.append(
                f"- 本季 {tickers_str} capex 合計 ${capex.total_usd / 1_000_000_000:,.1f}B "
                f"(period {capex.period_end})"
            )
        else:
            lines.append("- （無 hyperscaler capex 對照資料）")
    except Exception:
        lines.append("- （無 hyperscaler capex 對照資料）")

    lines.extend(["", "## 官方資料來源"])
    for idx, material in enumerate(packet.official_materials, 1):
        note_suffix = f"；{material.note}" if material.note else ""
        lines.append(
            f"{idx}. [{material.title}]({material.url})"
            f" `{material.material_type}` / `{material.source_type}`{note_suffix}"
        )

    lines.extend(["", "## 近期相關新聞"])
    if packet.related_articles:
        for idx, article in enumerate(packet.related_articles, 1):
            event_label = f" | {article.event_type}" if article.event_type else ""
            lines.append(
                f"{idx}. {article.published.strftime('%Y-%m-%d')} | {article.source}{event_label} | "
                f"[{article.title}]({article.link})"
            )
    else:
        lines.append("- 無近期對應新聞，需另補法說簡報 / transcript / Q&A 原文。")

    lines.extend(["", "## 判讀底稿"])
    if packet.market == "tw":
        lines.append("- 台股法說素材優先看 MOPS 法說查詢、TWSE WebPro 影音與 MOPS iXBRL 財報。")
    else:
        lines.append("- 美股法說素材優先看 SEC filing，再補 issuer IR 網站的 webcast / transcript / slides。")
    if packet.bundle.quarterly and packet.bundle.quarterly.guidance_summary:
        lines.append(f"- 最新管理層訊號：{packet.bundle.quarterly.guidance_summary}")
    if packet.bundle.quarterly and packet.bundle.quarterly.filing_excerpt:
        lines.append(f"- 最新 filing 摘錄：{packet.bundle.quarterly.filing_excerpt}")
    if packet.warnings:
        lines.append(f"- 補抓提醒：{' | '.join(packet.warnings)}")

    return "\n".join(lines).strip() + "\n"


def write_stock_memo(
    *,
    ticker: str,
    market: Literal["tw", "us"] | None = None,
    db_path: str | Path = DB_PATH,
    hours_back: int = 24 * 30,
    articles_by_category: dict[str, list[Article]] | None = None,
    refresh_official_data: bool = True,
    output_path: str | Path | None = None,
) -> Path:
    packet = collect_stock_memo_packet(
        ticker=ticker,
        market=market,
        db_path=db_path,
        hours_back=hours_back,
        articles_by_category=articles_by_category,
        refresh_official_data=refresh_official_data,
    )
    rendered = render_stock_memo(packet)

    resolved_output = (
        Path(output_path)
        if output_path is not None
        else MEMO_OUTPUT_DIR
        / f"{packet.generated_at.strftime('%Y-%m-%d')}-{packet.market}-{packet.ticker}-memo.md"
    )
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(rendered, encoding="utf-8")
    return resolved_output


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="Generate issuer-first stock memo")
    parser.add_argument("--ticker", required=True, help="Stock ticker or TW code")
    parser.add_argument(
        "--market",
        choices=["tw", "us"],
        default=None,
        help="Optional market override",
    )
    parser.add_argument(
        "--db-path",
        default=str(DB_PATH),
        help="SQLite path containing financial_reports/articles",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24 * 30,
        help="Recent news lookback window in hours",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional markdown output path",
    )
    parser.add_argument(
        "--no-refresh-official-data",
        action="store_true",
        help="Use existing DB snapshot only; skip network refresh",
    )
    args = parser.parse_args(argv)

    output_path = write_stock_memo(
        ticker=args.ticker,
        market=args.market,
        db_path=args.db_path,
        hours_back=args.hours,
        refresh_official_data=not args.no_refresh_official_data,
        output_path=args.output,
    )
    print(f"✅ 已產生個股 memo：{output_path}")
    return output_path


if __name__ == "__main__":
    main()
