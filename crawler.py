"""RSS 爬蟲模組 — 抓取各來源 RSS 並存入 SQLite"""

import asyncio
import hashlib
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiohttp
import feedparser
import yaml

DB_PATH = Path(__file__).parent / "data" / "news.db"
CONFIG_PATH = Path(__file__).parent / "config.yaml"

# 台灣時區
TW_TZ = timezone(timedelta(hours=8))


@dataclass
class Article:
    """一篇新聞文章"""
    title: str
    summary: str
    link: str
    source: str
    category: str
    published: datetime
    url_hash: str = field(default="")

    def __post_init__(self):
        if not self.url_hash:
            self.url_hash = hashlib.md5(self.link.encode()).hexdigest()


def init_db():
    """初始化 SQLite 資料庫"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            url_hash TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT,
            link TEXT NOT NULL,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            published TEXT NOT NULL,
            crawled_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_published ON articles(published)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_category ON articles(category)
    """)
    conn.commit()
    conn.close()


def is_duplicate(conn: sqlite3.Connection, url_hash: str) -> bool:
    """檢查文章是否已存在"""
    cursor = conn.execute("SELECT 1 FROM articles WHERE url_hash = ?", (url_hash,))
    return cursor.fetchone() is not None


def save_article(conn: sqlite3.Connection, article: Article):
    """儲存文章到 SQLite"""
    conn.execute(
        """INSERT OR IGNORE INTO articles
           (url_hash, title, summary, link, source, category, published, crawled_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            article.url_hash,
            article.title,
            article.summary,
            article.link,
            article.source,
            article.category,
            article.published.isoformat(),
            datetime.now(TW_TZ).isoformat(),
        ),
    )


def parse_published(entry) -> Optional[datetime]:
    """解析 RSS entry 的發佈時間"""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                return dt.astimezone(TW_TZ)
            except Exception:
                continue
    return datetime.now(TW_TZ)


def clean_summary(text: str) -> str:
    """清理摘要文字（移除 HTML tag）"""
    import re
    clean = re.sub(r"<[^>]+>", "", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:500]  # 限制長度


async def fetch_feed(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """非同步抓取 RSS feed"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) DailyNewsBot/1.0"
        }
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.text()
            else:
                print(f"  ⚠️ HTTP {resp.status}: {url}")
                return None
    except Exception as e:
        print(f"  ❌ Error fetching {url}: {e}")
        return None


async def crawl_source(
    session: aiohttp.ClientSession,
    source_name: str,
    url: str,
    category: str,
    hours_back: int = 24,
) -> list[Article]:
    """爬取單一 RSS 來源"""
    print(f"  📡 {source_name}...", end=" ")
    content = await fetch_feed(session, url)
    if not content:
        print("失敗")
        return []

    feed = feedparser.parse(content)
    cutoff = datetime.now(TW_TZ) - timedelta(hours=hours_back)
    articles = []

    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        summary = clean_summary(entry.get("summary", "") or entry.get("description", ""))
        published = parse_published(entry)

        if not title or not link:
            continue

        # 只取最近 N 小時的文章
        if published < cutoff:
            continue

        articles.append(
            Article(
                title=title,
                summary=summary,
                link=link,
                source=source_name,
                category=category,
                published=published,
            )
        )

    print(f"✅ {len(articles)} 篇")
    return articles


async def crawl_all(hours_back: int = 24) -> dict[str, list[Article]]:
    """爬取所有設定的 RSS 來源"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    init_db()
    conn = sqlite3.connect(str(DB_PATH))

    all_articles: dict[str, list[Article]] = {}
    new_count = 0
    dup_count = 0

    async with aiohttp.ClientSession() as session:
        for feed_key, feed_config in config["feeds"].items():
            category = feed_config["category"]
            print(f"\n📂 {category}")
            category_articles = []

            tasks = []
            for source in feed_config["sources"]:
                tasks.append(
                    crawl_source(
                        session,
                        source["name"],
                        source["url"],
                        category,
                        hours_back,
                    )
                )

            results = await asyncio.gather(*tasks)
            for articles in results:
                for article in articles:
                    if not is_duplicate(conn, article.url_hash):
                        save_article(conn, article)
                        category_articles.append(article)
                        new_count += 1
                    else:
                        dup_count += 1

            # 按時間排序（最新的在前）
            category_articles.sort(key=lambda a: a.published, reverse=True)
            if category_articles:
                all_articles[category] = category_articles

    conn.commit()
    conn.close()

    print(f"\n📊 總計：{new_count} 篇新文章，{dup_count} 篇重複跳過")
    return all_articles


def get_today_articles() -> dict[str, list[Article]]:
    """從 DB 取得今天的文章"""
    conn = sqlite3.connect(str(DB_PATH))
    today = datetime.now(TW_TZ).strftime("%Y-%m-%d")

    cursor = conn.execute(
        """SELECT title, summary, link, source, category, published
           FROM articles WHERE published LIKE ?
           ORDER BY category, published DESC""",
        (f"{today}%",),
    )

    articles: dict[str, list[Article]] = {}
    for row in cursor.fetchall():
        article = Article(
            title=row[0],
            summary=row[1],
            link=row[2],
            source=row[3],
            category=row[4],
            published=datetime.fromisoformat(row[5]),
        )
        if article.category not in articles:
            articles[article.category] = []
        articles[article.category].append(article)

    conn.close()
    return articles


if __name__ == "__main__":
    results = asyncio.run(crawl_all(hours_back=48))
    for cat, articles in results.items():
        print(f"\n{'='*60}")
        print(f"📂 {cat} ({len(articles)} 篇)")
        for a in articles[:3]:
            print(f"  • {a.title}")
            print(f"    {a.source} | {a.published.strftime('%H:%M')}")
