"""RSS 爬蟲模組 — 抓取各來源 RSS 並存入 SQLite"""

import asyncio
import hashlib
import json
import os
import random
import re
import sqlite3
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import aiohttp
import feedparser
import yaml

DB_PATH = Path(__file__).parent / "data" / "news.db"
CONFIG_PATH = Path(__file__).parent / "config.yaml"
SOURCE_HEALTH_PATH = Path(__file__).parent / "data" / "source_health.json"

TW_TZ = timezone(timedelta(hours=8))
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 0.8
REQUEST_TIMEOUT_SECONDS = 30
CONCURRENT_REQUESTS = 8
RETRY_STATUSES = {429, 500, 502, 503, 504}
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
ENV_PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "yclid",
    "mc_eid",
    "ga_source",
}


def load_config() -> dict[str, Any]:
    """載入 daily-news 設定檔（含 RSS 與市場設定）"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _resolve_config_env_placeholders(raw)


def _resolve_string_env_placeholders(value: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        env_key = match.group(1)
        return os.getenv(env_key, match.group(0))

    return ENV_PLACEHOLDER_PATTERN.sub(_replace, value)


def _resolve_config_env_placeholders(value: Any) -> Any:
    if isinstance(value, str):
        return _resolve_string_env_placeholders(value)
    if isinstance(value, list):
        return [_resolve_config_env_placeholders(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _resolve_config_env_placeholders(item) for key, item in value.items()
        }
    return value


def _is_resolved_config_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(value.strip()) and ENV_PLACEHOLDER_PATTERN.search(value) is None


def _select_source_url(source: Mapping[str, Any]) -> str:
    for key in ("preferred_url", "url", "fallback_url"):
        candidate = source.get(key)
        if _is_resolved_config_string(candidate):
            return str(candidate).strip()

    for key in ("preferred_url", "url", "fallback_url"):
        candidate = source.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    raise KeyError("url")


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


SOURCE_HEALTH_DISABLE_THRESHOLD = max(
    2, _safe_int(os.getenv("SOURCE_HEALTH_DISABLE_THRESHOLD", "3"), default=3)
)
SOURCE_HEALTH_COOLDOWN_MINUTES = max(
    30, _safe_int(os.getenv("SOURCE_HEALTH_COOLDOWN_MINUTES", "360"), default=360)
)
CATEGORY_DEFAULT_QUOTA = max(
    0, _safe_int(os.getenv("CATEGORY_DEFAULT_QUOTA", "0"), default=0)
)
ARTICLE_FETCH_TIMEOUT = aiohttp.ClientTimeout(
    total=max(10, int(os.getenv("ARTICLE_FETCH_TIMEOUT_SECONDS", "20")))
)
ENRICH_ARTICLE_BODIES = os.getenv("ENRICH_ARTICLE_BODIES", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ENRICH_MIN_PRIORITY = max(0, _safe_int(os.getenv("ENRICH_MIN_PRIORITY", "8"), default=8))
ENRICH_PER_SOURCE_MAX = max(
    0, _safe_int(os.getenv("ENRICH_PER_SOURCE_MAX", "4"), default=4)
)


class SourceHealthRegistry:
    """來源健康狀態：連續失敗達門檻後暫停一段時間。"""

    def __init__(
        self,
        path: Path = SOURCE_HEALTH_PATH,
        disable_threshold: int = SOURCE_HEALTH_DISABLE_THRESHOLD,
        cooldown_minutes: int = SOURCE_HEALTH_COOLDOWN_MINUTES,
        now_fn: Any | None = None,
    ) -> None:
        self.path = path
        self.disable_threshold = max(1, _safe_int(disable_threshold, default=3))
        self.cooldown_minutes = max(1, _safe_int(cooldown_minutes, default=360))
        self._now_fn = now_fn or (lambda: datetime.now(TW_TZ))
        self._state: dict[str, dict[str, Any]] = self._load()

    def _now(self) -> datetime:
        return self._now_fn()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        state: dict[str, dict[str, Any]] = {}
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, dict):
                state[key] = dict(value)
        return state

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _record(self, source_key: str) -> dict[str, Any]:
        rec = self._state.setdefault(source_key, {})
        return rec

    def _parse_dt(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    def disabled_until(self, source_key: str) -> datetime | None:
        rec = self._state.get(source_key, {})
        return self._parse_dt(rec.get("disabled_until"))

    def disabled_until_label(self, source_key: str) -> str:
        until = self.disabled_until(source_key)
        if not until:
            return ""
        return until.strftime("%m-%d %H:%M")

    def is_temporarily_disabled(self, source_key: str) -> bool:
        until = self.disabled_until(source_key)
        if not until:
            return False
        if until > self._now():
            return True

        rec = self._record(source_key)
        rec["disabled_until"] = ""
        rec["consecutive_failures"] = 0
        self._save()
        return False

    def mark_failure(self, source_key: str, reason: str = "") -> None:
        now = self._now()
        rec = self._record(source_key)
        consecutive = _safe_int(rec.get("consecutive_failures"), default=0) + 1
        rec["consecutive_failures"] = consecutive
        rec["last_failure"] = now.isoformat()
        rec["last_error"] = str(reason or "fetch_failed")[:200]

        if consecutive >= self.disable_threshold:
            until = now + timedelta(minutes=self.cooldown_minutes)
            rec["disabled_until"] = until.isoformat()

        self._save()

    def mark_success(self, source_key: str) -> None:
        now = self._now()
        rec = self._record(source_key)
        rec["consecutive_failures"] = 0
        rec["disabled_until"] = ""
        rec["last_success"] = now.isoformat()
        self._save()


def normalize_source_config(
    feed_key: str, feed_config: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    """將來源欄位補齊預設值，支援可控來源 metadata"""
    preferred_url = source.get("preferred_url")
    fallback_url = source.get("fallback_url")
    return {
        "name": source["name"],
        "url": _select_source_url(source),
        "preferred_url": str(preferred_url).strip() if isinstance(preferred_url, str) else "",
        "fallback_url": str(fallback_url).strip() if isinstance(fallback_url, str) else "",
        "active": bool(source.get("active", True)),
        "priority": _safe_int(source.get("priority", 5)),
        "region": str(source.get("region", "global")),
        "topics": source.get("topics", []),
        "max_articles": _safe_int(source.get("max_articles"), default=0),
        "summary_prompt": source.get("summary_prompt"),
        "quality": source.get("quality", "medium"),
        "feed_key": feed_key,
        "source_key": f"{feed_key}:{source['name']}",
        "feed_category": feed_config["category"],
        "default_prompt": feed_config.get("summary_prompt", "news"),
        "default_region": feed_config.get("region", "global"),
    }


@dataclass
class Article:
    title: str
    summary: str
    link: str
    source: str
    source_key: str
    category: str
    summary_prompt: str | None
    published: datetime
    body_text: str = ""
    source_priority: int = 5
    source_quality: str = "medium"
    feed_key: str = ""
    region: str = "global"
    topics: list[str] = field(default_factory=list)
    published_raw: str = ""
    published_confidence: str = "feed"
    body_source: str = ""
    extraction_status: str = "not_attempted"
    publisher: str = ""
    author: str = ""
    companies: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)
    event_type: str = ""
    event_key: str = ""
    url_hash: str = field(default="")

    def __post_init__(self):
        self.summary = self.summary or ""
        self.body_text = self.body_text or ""
        self.source_key = self.source_key or ""
        self.source_quality = (self.source_quality or "medium").lower()
        self.feed_key = self.feed_key or ""
        self.region = self.region or "global"
        self.topics = [str(topic) for topic in (self.topics or []) if str(topic).strip()]
        self.published_raw = self.published_raw or ""
        self.published_confidence = self.published_confidence or "feed"
        self.body_source = self.body_source or ""
        self.extraction_status = self.extraction_status or "not_attempted"
        self.publisher = self.publisher or ""
        self.author = self.author or ""
        self.companies = [str(company) for company in (self.companies or []) if str(company).strip()]
        self.tickers = [str(ticker) for ticker in (self.tickers or []) if str(ticker).strip()]
        self.event_type = self.event_type or ""
        self.event_key = self.event_key or ""
        if not self.url_hash:
            canonical_link = normalize_url(self.link)
            if canonical_link != self.link:
                self.link = canonical_link

            fallback = f"{self.source}|{self.title}|{self.published.isoformat()}"
            dedupe_value = canonical_link or fallback
            self.url_hash = hashlib.md5(dedupe_value.encode("utf-8")).hexdigest()


ARTICLE_EXTRA_COLUMNS = {
    "source_key": "TEXT NOT NULL DEFAULT ''",
    "summary_prompt": "TEXT",
    "source_priority": "INTEGER NOT NULL DEFAULT 5",
    "source_quality": "TEXT NOT NULL DEFAULT 'medium'",
    "feed_key": "TEXT NOT NULL DEFAULT ''",
    "region": "TEXT NOT NULL DEFAULT 'global'",
    "topics_json": "TEXT NOT NULL DEFAULT '[]'",
    "published_raw": "TEXT NOT NULL DEFAULT ''",
    "published_confidence": "TEXT NOT NULL DEFAULT 'feed'",
    "body_text": "TEXT NOT NULL DEFAULT ''",
    "body_source": "TEXT NOT NULL DEFAULT ''",
    "extraction_status": "TEXT NOT NULL DEFAULT 'not_attempted'",
    "publisher": "TEXT NOT NULL DEFAULT ''",
    "author": "TEXT NOT NULL DEFAULT ''",
    "companies_json": "TEXT NOT NULL DEFAULT '[]'",
    "tickers_json": "TEXT NOT NULL DEFAULT '[]'",
    "event_type": "TEXT NOT NULL DEFAULT ''",
    "event_key": "TEXT NOT NULL DEFAULT ''",
}


def _json_dumps(value: Any, default: str) -> str:
    try:
        return json.dumps(value if value is not None else json.loads(default), ensure_ascii=False)
    except Exception:
        return default


def _json_loads_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    try:
        raw = json.loads(str(value))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _ensure_article_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()
    }
    for column_name, column_sql in ARTICLE_EXTRA_COLUMNS.items():
        if column_name in existing_columns:
            continue
        conn.execute(f"ALTER TABLE articles ADD COLUMN {column_name} {column_sql}")


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
            crawled_at TEXT NOT NULL,
            source_key TEXT NOT NULL DEFAULT '',
            summary_prompt TEXT,
            source_priority INTEGER NOT NULL DEFAULT 5,
            source_quality TEXT NOT NULL DEFAULT 'medium',
            feed_key TEXT NOT NULL DEFAULT '',
            region TEXT NOT NULL DEFAULT 'global',
            topics_json TEXT NOT NULL DEFAULT '[]',
            published_raw TEXT NOT NULL DEFAULT '',
            published_confidence TEXT NOT NULL DEFAULT 'feed',
            body_text TEXT NOT NULL DEFAULT '',
            body_source TEXT NOT NULL DEFAULT '',
            extraction_status TEXT NOT NULL DEFAULT 'not_attempted',
            publisher TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            companies_json TEXT NOT NULL DEFAULT '[]',
            tickers_json TEXT NOT NULL DEFAULT '[]',
            event_type TEXT NOT NULL DEFAULT '',
            event_key TEXT NOT NULL DEFAULT ''
        )
    """)
    _ensure_article_columns(conn)
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
           (url_hash, title, summary, link, source, category, published, crawled_at,
            source_key, summary_prompt, source_priority, source_quality, feed_key,
            region, topics_json, published_raw, published_confidence, body_text,
            body_source, extraction_status, publisher, author, companies_json,
            tickers_json, event_type, event_key)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            article.url_hash,
            article.title,
            article.summary,
            article.link,
            article.source,
            article.category,
            article.published.isoformat(),
            datetime.now(TW_TZ).isoformat(),
            article.source_key,
            article.summary_prompt,
            int(article.source_priority),
            article.source_quality,
            article.feed_key,
            article.region,
            _json_dumps(article.topics, "[]"),
            article.published_raw,
            article.published_confidence,
            article.body_text,
            article.body_source,
            article.extraction_status,
            article.publisher,
            article.author,
            _json_dumps(article.companies, "[]"),
            _json_dumps(article.tickers, "[]"),
            article.event_type,
            article.event_key,
        ),
    )


def parse_published(entry) -> datetime:
    """解析 RSS entry 的發佈時間"""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                return dt.astimezone(TW_TZ)
            except Exception:
                continue

    for key in ("published", "updated", "pubDate", "date"):
        raw = _get_text_field(getattr(entry, key, None))
        if not raw:
            try:
                raw = _get_text_field(entry.get(key))
            except Exception:
                raw = ""

        if raw:
            formats = (
                "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S",
            )
            for fmt in formats:
                try:
                    dt = datetime.strptime(raw, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(TW_TZ)
                except Exception:
                    continue

            try:
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(TW_TZ)
            except Exception:
                pass

    return datetime.now(TW_TZ)


def clean_summary(text: str) -> str:
    """清理摘要文字（移除 HTML tag）"""
    import re

    clean = re.sub(r"<[^>]+>", "", text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:500]


def normalize_url(url: str) -> str:
    """正規化 URL，用於去重。"""
    if not url:
        return ""

    url = str(url).strip()
    parsed = urllib.parse.urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in TRACKING_QUERY_PARAMS
    ]

    normalized_query = urllib.parse.urlencode(sorted(query), doseq=True)
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            normalized_query,
            "",
        )
    )


def _get_text_field(value: Any) -> str:
    """從 RSS 欄位取出可用字串值。"""
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        value = value[0]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value).strip()


async def fetch_feed(session: aiohttp.ClientSession, url: str) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) DailyNewsBot/1.0",
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.get(
                url, headers=headers, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    return await resp.text()

                if resp.status in RETRY_STATUSES and attempt < MAX_RETRIES:
                    delay = RETRY_DELAY_SECONDS * attempt * random.uniform(0.8, 1.8)
                    print(
                        f"  🔁 HTTP {resp.status}: {url} (重試 {attempt}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    continue

                print(f"  ⚠️ HTTP {resp.status}: {url}")
                return None

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY_SECONDS * attempt * random.uniform(0.8, 1.8)
                print(f"  ⚠️ 連線失敗 ({attempt}/{MAX_RETRIES}): {url} {e}")
                await asyncio.sleep(delay)
                continue
            print(f"  ❌ Error fetching {url}: {e}")
            return None
        except Exception as e:
            print(f"  ❌ Error fetching {url}: {e}")
            return None

    return None


async def fetch_article_page(
    session: aiohttp.ClientSession, url: str
) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) DailyNewsBot/1.0",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with session.get(url, headers=headers, timeout=ARTICLE_FETCH_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None


async def crawl_source(
    session: aiohttp.ClientSession,
    source_config: dict[str, Any],
    hours_back: int = 24,
    semaphore: asyncio.Semaphore | None = None,
    source_health: SourceHealthRegistry | None = None,
) -> list[Article]:
    source_name = source_config["name"]
    source_key = str(source_config.get("source_key", ""))

    if not source_config.get("active", True):
        print(f"  ⏭️ {source_name}: 已停用")
        return []

    if source_health and source_key and source_health.is_temporarily_disabled(source_key):
        until_label = source_health.disabled_until_label(source_key)
        if until_label:
            print(f"  ⏸️ {source_name}: 健康檢查暫停中，至 {until_label}")
        else:
            print(f"  ⏸️ {source_name}: 健康檢查暫停中")
        return []

    gate = semaphore or asyncio.Semaphore(CONCURRENT_REQUESTS)
    async with gate:
        print(f"  📡 {source_name}...", end=" ")
        content = await fetch_feed(session, source_config["url"])

    if not content and source_config.get("fallback_url"):
        fallback_url = str(source_config["fallback_url"]).strip()
        if fallback_url and fallback_url != source_config["url"]:
            print("  ↪️ RSSHub/主來源失敗，改抓 fallback...", end=" ")
            async with gate:
                content = await fetch_feed(session, fallback_url)
            if content:
                source_config["url"] = fallback_url

    if not content:
        print("失敗")
        if source_health and source_key:
            source_health.mark_failure(source_key, reason="fetch_failed")
        return []

    feed = feedparser.parse(content)
    if feed.bozo and getattr(feed, "bozo_exception", None):
        print(f"  ⚠️ parse 警告: {source_name}")

    cutoff = datetime.now(TW_TZ) - timedelta(hours=hours_back)
    articles: list[Article] = []
    source_prompt = (
        source_config.get("summary_prompt")
        or source_config.get("default_prompt")
        or "news"
    )
    source_priority = _safe_int(source_config.get("priority"), default=5)
    source_quality = str(source_config.get("quality", "medium")).lower()
    source_region = str(
        source_config.get("region") or source_config.get("default_region") or "global"
    )
    source_topics = source_config.get("topics", [])

    for entry in feed.entries:
        title = _get_text_field(entry.get("title", ""))
        if not title:
            continue

        link = _get_text_field(entry.get("link", ""))
        if not link:
            link = _get_text_field(entry.get("id", "") or entry.get("guid", ""))
        if not link:
            continue

        summary = _get_text_field(
            entry.get("summary", "") or entry.get("description", "")
        )
        summary = clean_summary(summary)
        published = parse_published(entry)

        if published < cutoff:
            continue

        canonical_link = normalize_url(link)
        if not canonical_link:
            continue

        articles.append(
            Article(
                title=title,
                summary=summary,
                link=canonical_link,
                source=source_name,
                source_key=source_config["source_key"],
                category=source_config["feed_category"],
                summary_prompt=source_prompt,
                published=published,
                source_priority=source_priority,
                source_quality=source_quality,
                feed_key=str(source_config.get("feed_key", "")),
                region=source_region,
                topics=[str(topic) for topic in source_topics if str(topic).strip()],
                published_raw=_get_text_field(
                    entry.get("published", "")
                    or entry.get("updated", "")
                    or entry.get("pubDate", "")
                    or entry.get("date", "")
                ),
            )
        )

    if not articles:
        if source_health and source_key:
            source_health.mark_success(source_key)
        print("✅ 0 篇")
        return []

    articles.sort(key=lambda a: a.published, reverse=True)
    source_limit = _safe_int(source_config.get("max_articles"), default=0)
    if source_limit > 0 and len(articles) > source_limit:
        dropped = len(articles) - source_limit
        articles = articles[:source_limit]
        print(f"  ✂️ {source_name} 每來源上限 {source_limit}，略過 {dropped} 篇")

    if ENRICH_ARTICLE_BODIES and ENRICH_PER_SOURCE_MAX > 0:
        try:
            from news_enrichment import (
                apply_article_event_metadata,
                extract_article_page_metadata,
                should_enrich_article,
            )
        except Exception:
            apply_article_event_metadata = None
            extract_article_page_metadata = None
            should_enrich_article = None

        for idx, article in enumerate(articles):
            if should_enrich_article and idx < ENRICH_PER_SOURCE_MAX and should_enrich_article(
                article, min_priority=ENRICH_MIN_PRIORITY
            ):
                page_html = await fetch_article_page(session, article.link)
                if page_html and extract_article_page_metadata:
                    metadata = extract_article_page_metadata(page_html, article.link)
                    article.link = normalize_url(metadata.get("canonical_url") or article.link)
                    article.body_text = metadata.get("body_text", "") or article.body_text
                    article.body_source = metadata.get("body_source", "") or article.body_source
                    article.extraction_status = metadata.get("extraction_status", "failed")
                    article.publisher = metadata.get("publisher", "") or article.publisher
                    article.author = metadata.get("author", "") or article.author
                    article.published_raw = (
                        metadata.get("published_raw", "") or article.published_raw
                    )
                    if article.body_text:
                        article.published_confidence = "article"
                else:
                    article.extraction_status = "failed"

            if apply_article_event_metadata:
                apply_article_event_metadata(article)

    if source_health and source_key:
        source_health.mark_success(source_key)
    print(f"✅ {len(articles)} 篇")
    return articles


async def crawl_all(hours_back: int = 24) -> dict[str, list[Article]]:
    config = load_config()
    feeds: Mapping[str, Any] = config.get("feeds", {})
    source_health = SourceHealthRegistry(
        path=SOURCE_HEALTH_PATH,
        disable_threshold=SOURCE_HEALTH_DISABLE_THRESHOLD,
        cooldown_minutes=SOURCE_HEALTH_COOLDOWN_MINUTES,
    )

    init_db()
    conn = sqlite3.connect(str(DB_PATH))

    all_articles: dict[str, list[Article]] = {}
    new_count = 0
    dup_count = 0

    try:
        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

            for feed_key, feed_config in feeds.items():
                category = str(feed_config["category"])
                print(f"\n📂 {category}")
                category_articles: list[Article] = []
                local_seen_hashes: set[str] = set()

                normalized_sources = [
                    normalize_source_config(feed_key, feed_config, source)
                    for source in feed_config.get("sources", [])
                    if isinstance(source, Mapping)
                ]
                normalized_sources.sort(key=lambda s: s["priority"], reverse=True)

                tasks = [
                    crawl_source(
                        session,
                        source_config,
                        hours_back,
                        semaphore=semaphore,
                        source_health=source_health,
                    )
                    for source_config in normalized_sources
                ]

                results = await asyncio.gather(*tasks)
                for articles in results:
                    for article in articles:
                        if article.url_hash in local_seen_hashes:
                            dup_count += 1
                            continue

                        local_seen_hashes.add(article.url_hash)

                        if not is_duplicate(conn, article.url_hash):
                            save_article(conn, article)
                            category_articles.append(article)
                            new_count += 1
                        else:
                            dup_count += 1

                category_articles.sort(key=lambda a: a.published, reverse=True)
                if category_articles:
                    all_articles[category] = category_articles

        conn.commit()
        print(f"\n📊 總計：{new_count} 篇新文章，{dup_count} 篇重複跳過")
    finally:
        conn.close()

    return all_articles


def _category_quota_map() -> dict[str, int]:
    """讀取 category -> quota 對應，0 代表不限制。"""
    config = load_config()
    feeds = config.get("feeds", {})
    if not isinstance(feeds, Mapping):
        return {}

    quotas: dict[str, int] = {}
    for feed_config in feeds.values():
        if not isinstance(feed_config, Mapping):
            continue

        category = str(feed_config.get("category", "")).strip()
        if not category:
            continue

        quota = _safe_int(
            feed_config.get("category_quota"), default=CATEGORY_DEFAULT_QUOTA
        )
        if quota > 0:
            quotas[category] = quota

    return quotas


def get_recent_articles(hours_back: int = 168) -> dict[str, list[Article]]:
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    cutoff = datetime.now(TW_TZ) - timedelta(hours=hours_back)
    _ensure_article_columns(conn)

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
            source_priority=_safe_int(row[8], default=5),
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
        if article.category not in articles:
            articles[article.category] = []
        articles[article.category].append(article)

    conn.close()
    quotas = _category_quota_map()
    for category, quota in quotas.items():
        category_articles = articles.get(category, [])
        if quota > 0 and len(category_articles) > quota:
            articles[category] = category_articles[:quota]
    return articles


def get_today_articles() -> dict[str, list[Article]]:
    return get_recent_articles(hours_back=24)


if __name__ == "__main__":
    results = asyncio.run(crawl_all(hours_back=48))
    for cat, articles in results.items():
        print(f"\n{'=' * 60}")
        print(f"📂 {cat} ({len(articles)} 篇)")
        for a in articles[:3]:
            print(f"  • {a.title}")
            print(f"    {a.source} | {a.published.strftime('%H:%M')}")
