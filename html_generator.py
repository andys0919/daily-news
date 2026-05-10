"""HTML 報告產生器"""

import html as html_lib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import markdown
from jinja2 import Environment, FileSystemLoader

from crawler import Article
from market_data import MarketOverview


def md_to_html(text: str) -> str:
    """將 Markdown 文字轉成 HTML（支援連結、粗體、標題等）"""
    if not text:
        return ""
    return markdown.markdown(
        text,
        extensions=["nl2br"],  # 換行轉 <br>
        output_format="html",
    )


_CITATION_RE = re.compile(r"\[(\d{1,4})\](?!\()")


def _link_numeric_citations(text: str, citation_links: dict[int, str] | None) -> str:
    """把摘要中的 [n] 轉成可點擊原文連結"""
    if not text or not citation_links:
        return text or ""

    def _replace(match: re.Match[str]) -> str:
        raw_num = match.group(1)
        try:
            idx = int(raw_num)
        except ValueError:
            return match.group(0)
        link = citation_links.get(idx)
        if not link:
            return match.group(0)
        return f'<a href="{link}" target="_blank">[{idx}]</a>'

    return _CITATION_RE.sub(_replace, text)


def _filter_articles_by_summary_prompt(
    articles: dict[str, list[Article]], summary_prompt: str
) -> list[Article]:
    filtered = [
        article
        for group in articles.values()
        for article in group
        if article.summary_prompt == summary_prompt
        or (
            summary_prompt == "ai_practice"
            and "AI 工具與實戰" in (article.category or "")
        )
    ]
    return sorted(filtered, key=lambda article: article.published, reverse=True)


def _filter_github_articles(articles: dict[str, list[Article]]) -> list[Article]:
    filtered = [
        article
        for group in articles.values()
        for article in group
        if (
            "github" in (article.source or "").lower()
            or "github.com" in (article.link or "").lower()
        )
    ]
    return sorted(filtered, key=lambda article: article.published, reverse=True)


def _find_summary_category(
    articles: dict[str, list[Article]],
    summaries: dict[str, str],
    summary_prompt: str,
) -> str | None:
    for category, category_articles in articles.items():
        if any(
            article.summary_prompt == summary_prompt
            or (
                summary_prompt == "ai_practice"
                and "AI 工具與實戰" in (article.category or "")
            )
            for article in category_articles
        ):
            return category

    if summary_prompt == "ai_practice":
        for category in summaries:
            if "AI 工具與實戰" in category:
                return category
    return None


TEMPLATE_DIR = Path(__file__).parent / "templates"
REPORT_DIR = Path(__file__).parent / "data" / "reports"
DB_PATH = Path(__file__).parent / "data" / "news.db"
TW_TZ = timezone(timedelta(hours=8))
_X_GROUP_LABELS = {
    "x_group_labs": "模型實驗室 / 官方",
    "x_group_devtools": "開發工具 / Agent 工作流",
    "x_group_infra": "推理基礎設施 / 部署",
    "x_group_platforms": "模型平台 / 企業產品",
    "x_group_semis": "晶片 / 算力供應鏈",
}
_X_GROUP_ORDER = [
    "x_group_labs",
    "x_group_devtools",
    "x_group_infra",
    "x_group_platforms",
    "x_group_semis",
]
_X_GROUP_PREFIX = {
    "x_group_labs": "近期實驗室與官方更新聚焦在",
    "x_group_devtools": "近期工具鏈與 agent 工作流焦點在",
    "x_group_infra": "近期推理部署與基礎設施焦點在",
    "x_group_platforms": "近期模型平台與產品化重點在",
    "x_group_semis": "近期晶片與算力供應鏈重點在",
}

WEEKDAY_MAP = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}


def _article_x_group_key(article: Article) -> str:
    for topic in getattr(article, "topics", []) or []:
        key = str(topic).strip()
        if key in _X_GROUP_LABELS:
            return key
    return ""


def _clean_x_group_summary_text(text: str) -> str:
    cleaned = html_lib.unescape(text or "")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"https?://\\S+", "", cleaned)
    cleaned = " ".join(cleaned.split()).strip(" -|;:,")
    return cleaned


def _shorten_x_group_summary_text(text: str, max_len: int = 44) -> str:
    normalized = _clean_x_group_summary_text(text)
    if len(normalized) <= max_len:
        return normalized
    return normalized[:max_len].rstrip() + "…"


def _build_x_group_summary(group_key: str, articles: list[Article]) -> str:
    prefix = _X_GROUP_PREFIX.get(group_key, "近期高訊號貼文重點在")
    snippets: list[str] = []
    seen: set[str] = set()
    for article in articles[:3]:
        for candidate in (article.summary, article.title):
            snippet = _shorten_x_group_summary_text(candidate)
            if not snippet or snippet in seen:
                continue
            snippets.append(snippet)
            seen.add(snippet)
            break
        if len(snippets) >= 2:
            break

    if snippets:
        return f"近期 {len(articles)} 則高訊號貼文，{prefix}{'；'.join(snippets)}。"
    return f"近期 {len(articles)} 則高訊號貼文。"


def _build_x_trends_group_cards(
    articles: dict[str, list[Article]],
) -> list[dict[str, object]]:
    x_articles = _filter_articles_by_summary_prompt(articles, "x_trends")
    grouped: dict[str, list[Article]] = {key: [] for key in _X_GROUP_ORDER}
    for article in x_articles:
        key = _article_x_group_key(article)
        if not key:
            continue
        grouped.setdefault(key, []).append(article)

    cards: list[dict[str, object]] = []
    for key in _X_GROUP_ORDER:
        group_articles = grouped.get(key, [])
        if not group_articles:
            continue
        cards.append(
            {
                "key": key,
                "title": _X_GROUP_LABELS[key],
                "count": len(group_articles),
                "summary": _build_x_group_summary(key, group_articles),
                "articles": group_articles[:4],
            }
        )
        if len(cards) >= 4:
            break
    return cards


def generate_report(
    articles: dict[str, list[Article]],
    summaries: dict[str, str],
    market: MarketOverview | None = None,
    memo: str = "",
    top10: str = "",
    ai_usage: dict | None = None,
    citation_links: dict[str, dict[int, str]] | None = None,
    report_type: Literal["daily", "weekly"] = "weekly",
) -> Path:
    """產生 HTML 報告，回傳檔案路徑"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(TW_TZ)
    date_str = now.strftime("%Y-%m-%d")
    weekday = WEEKDAY_MAP.get(now.weekday(), "")
    time_str = now.strftime("%H:%M")
    title = "每日新聞速報" if report_type == "daily" else "每週新聞速報"
    source_atlas_href = "news-source-atlas.html"

    memo_source = memo or top10
    memo_html = md_to_html(memo_source)
    x_group_cards = _build_x_trends_group_cards(articles)
    ai_watch_articles = _filter_github_articles(articles)
    ai_watch_category = _find_summary_category(articles, summaries, "ai_practice")
    ai_watch_summary = ""
    if ai_watch_category:
        summary_md = summaries.get(ai_watch_category, "")
        linked_summary_md = _link_numeric_citations(
            summary_md,
            (citation_links or {}).get(ai_watch_category, {}),
        )
        ai_watch_summary = md_to_html(linked_summary_md)
    try:
        from financial_reports import build_financial_highlight_entries

        financial_highlights = build_financial_highlight_entries(
            articles, db_path=DB_PATH
        )
    except Exception:
        financial_highlights = []

    # 渲染模板
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.html")

    html = template.render(
        title=title,
        date=date_str,
        weekday=f"週{weekday}",
        generated_at=time_str,
        source_atlas_href=source_atlas_href,
        market=market,
        memo=memo_html,
        x_group_cards=x_group_cards,
        financial_highlights=financial_highlights,
        ai_watch_articles=ai_watch_articles,
        ai_watch_summary=ai_watch_summary,
        ai_usage=ai_usage or {},
    )

    if report_type == "daily":
        period = "morning" if now.hour < 12 else "evening"
        filename = f"{date_str}-{period}.html"
    else:
        iso_year, iso_week, _ = now.isocalendar()
        filename = f"{iso_year}-W{iso_week:02d}-weekly.html"
    filepath = REPORT_DIR / filename
    filepath.write_text(html, encoding="utf-8")

    print(f"📄 報告已產生：{filepath}")
    return filepath


if __name__ == "__main__":
    # 測試
    from market_data import IndexData

    test_market = MarketOverview(
        indices=[
            IndexData("台股加權指數", "^TWII", 23456.78, 123.45, 0.53, 23333.33),
            IndexData("S&P 500", "^GSPC", 6234.56, -18.90, -0.30, 6253.46),
        ],
        timestamp=datetime.now(TW_TZ),
    )
    test_articles = {
        "🇺🇸 美國財經": [
            Article(
                title="NVIDIA 財報超預期",
                summary="AI 晶片需求持續強勁",
                link="https://example.com/1",
                source="CNBC",
                source_key="test:CNBC",
                summary_prompt="news",
                category="🇺🇸 美國財經",
                published=datetime.now(TW_TZ),
            )
        ]
    }
    test_summaries = {"🇺🇸 美國財經": "NVIDIA 財報表現強勁，帶動半導體股走高。"}

    path = generate_report(test_articles, test_summaries, test_market)
    print(f"✅ 測試報告：{path}")
