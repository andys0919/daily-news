import json
import os
import re
import subprocess
import tempfile
import math
import html as html_lib
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
import urllib.error
import urllib.parse
import urllib.request

import yaml

from crawler import Article

CONFIG_PATH = Path(__file__).parent / "config.yaml"
AZURE_CONFIG_PATH = Path(__file__).parent / "Azure.txt"
DB_PATH = Path(__file__).parent / "data" / "news.db"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Codex CLI 設定
CODEX_PATH = "/opt/homebrew/bin/codex"
CODEX_MODEL = os.getenv("CODEX_MODEL", "gpt-5.3-codex-spark")
CODEX_REASONING_EFFORT = os.getenv("CODEX_REASONING_EFFORT", "medium")
CODEX_FALLBACK_MODELS: list[str] = []
SUMMARY_PROVIDER = os.getenv("SUMMARY_PROVIDER", "azure").strip().lower()
SUMMARY_BATCH_WORKERS = int(os.getenv("SUMMARY_BATCH_WORKERS", "2"))
SUMMARY_MAX_ARTICLES = max(0, int(os.getenv("SUMMARY_MAX_ARTICLES", "0")))
SUMMARY_MIN_BODY_CHARS = max(1, int(os.getenv("SUMMARY_MIN_BODY_CHARS", "1")))
SUMMARY_BODY_MAX_CHARS = max(80, int(os.getenv("SUMMARY_BODY_MAX_CHARS", "1200")))
SUMMARY_CHUNK_ARTICLES = max(0, int(os.getenv("SUMMARY_CHUNK_ARTICLES", "100")))
SUMMARY_MAX_PER_SOURCE = max(0, int(os.getenv("SUMMARY_MAX_PER_SOURCE", "8")))
SUMMARY_X_GROUP_MAX_ARTICLES = max(
    0, int(os.getenv("SUMMARY_X_GROUP_MAX_ARTICLES", "4"))
)
SUMMARY_MAX_INPUT_CHARS = max(0, int(os.getenv("SUMMARY_MAX_INPUT_CHARS", "18000")))
SUMMARY_FULL_READ_MODE = _env_bool("SUMMARY_FULL_READ_MODE", True)
SUMMARY_TOP10_CATEGORY_MAX_CHARS = max(
    0, int(os.getenv("SUMMARY_TOP10_CATEGORY_MAX_CHARS", "1800"))
)
DAILY_MEMO_MAX_ARTICLES = max(1, int(os.getenv("DAILY_MEMO_MAX_ARTICLES", "24")))
DAILY_MEMO_MAX_PER_CATEGORY = max(
    1, int(os.getenv("DAILY_MEMO_MAX_PER_CATEGORY", "6"))
)
DAILY_MEMO_MAX_INPUT_CHARS = max(
    0, int(os.getenv("DAILY_MEMO_MAX_INPUT_CHARS", "24000"))
)
SUMMARY_INCLUDE_LINKS_IN_PROMPT = _env_bool("SUMMARY_INCLUDE_LINKS_IN_PROMPT", False)
SUMMARY_TITLE_FALLBACK = _env_bool("SUMMARY_TITLE_FALLBACK", True)
SUMMARY_TITLE_DEDUP = _env_bool("SUMMARY_TITLE_DEDUP", True)
SUMMARY_FILTER_LOW_SIGNAL = _env_bool("SUMMARY_FILTER_LOW_SIGNAL", True)
SUMMARY_SIGNAL_RANKING = _env_bool("SUMMARY_SIGNAL_RANKING", True)
SUMMARY_PRIMARY_SOURCE_FILTER = _env_bool("SUMMARY_PRIMARY_SOURCE_FILTER", True)
SUMMARY_PRIMARY_SOURCE_MIN_ARTICLES = max(
    2, int(os.getenv("SUMMARY_PRIMARY_SOURCE_MIN_ARTICLES", "5"))
)
SUMMARY_RECENCY_HALF_LIFE_HOURS = max(
    1, int(os.getenv("SUMMARY_RECENCY_HALF_LIFE_HOURS", "24"))
)
SUMMARY_MIN_CITATIONS = max(2, int(os.getenv("SUMMARY_MIN_CITATIONS", "4")))
AZURE_OPENAI_URL = os.getenv("AZURE_OPENAI_URL", "").strip()
AZURE_OPENAI_API_KEY = (
    os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    or os.getenv("AZURE_OPENAI_KEY", "").strip()
)
AZURE_OPENAI_MODEL = os.getenv("AZURE_OPENAI_MODEL", "gpt-5-mini").strip()
AZURE_OPENAI_TIMEOUT_SEC = max(30, int(os.getenv("AZURE_OPENAI_TIMEOUT_SEC", "300")))
AZURE_OPENAI_MAX_RETRIES = max(1, int(os.getenv("AZURE_OPENAI_MAX_RETRIES", "5")))
AZURE_OPENAI_RETRY_BASE_SEC = max(
    1, int(os.getenv("AZURE_OPENAI_RETRY_BASE_SEC", "15"))
)
AZURE_OPENAI_REASONING_EFFORT = os.getenv(
    "AZURE_OPENAI_REASONING_EFFORT", "low"
).strip()
AZURE_OPENAI_VERBOSITY = os.getenv("AZURE_OPENAI_VERBOSITY", "low").strip()
AZURE_RETAIL_PRICES_API = "https://prices.azure.com/api/retail/prices"

_USAGE_LOCK = Lock()
_USAGE_STATE = {
    "provider": "",
    "model": "",
    "input_tokens": 0,
    "output_tokens": 0,
    "requests": 0,
}
_PRICING_CACHE: dict[str, object] = {}
_SOURCE_META_CACHE: dict[str, dict[str, object]] | None = None
_X_GROUP_LABELS = {
    "x_group_labs": "模型實驗室 / 官方",
    "x_group_devtools": "開發工具 / Agent 工作流",
    "x_group_infra": "推理基礎設施 / 部署",
    "x_group_platforms": "模型平台 / 企業產品",
    "x_group_semis": "晶片 / 算力供應鏈",
}
_GITHUB_REPO_CACHE: dict[str, dict[str, object] | None] = {}
_PERSONA_CACHE: dict | None = None
_CATEGORY_AGENTS_CACHE: dict | None = None


def _load_persona() -> dict:
    """從 config.yaml 載入投資人設"""
    global _PERSONA_CACHE
    if _PERSONA_CACHE is not None:
        return _PERSONA_CACHE
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    _PERSONA_CACHE = cfg.get("investor_persona", {})
    return _PERSONA_CACHE


def _persona_block() -> str:
    """產生 prompt 用的人設區塊"""
    p = _load_persona()
    if not p:
        return ""
    signals = "\n".join(f"  - {s}" for s in p.get("key_signals", []))
    anti = "\n".join(f"  - {a}" for a in p.get("anti_patterns", []))
    sectors = "\n".join(f"  - {s}" for s in p.get("focus_sectors", []))
    return f"""### 研究人設
- 角色：{p.get("role", "投資研究員")}
- 風格：{p.get("style", "混合型")}
- 時間框架：{p.get("time_horizon", "中長期")}
- 關注板塊：
{sectors}
- 高價值訊號：
{signals}
- 禁止事項：
{anti}"""


def _load_category_agents() -> dict:
    """從 config.yaml 載入 category_agents"""
    global _CATEGORY_AGENTS_CACHE
    if _CATEGORY_AGENTS_CACHE is not None:
        return _CATEGORY_AGENTS_CACHE
    cfg = load_config()
    _CATEGORY_AGENTS_CACHE = cfg.get("category_agents", {})
    return _CATEGORY_AGENTS_CACHE


# feed key → agent key 映射（處理 key 名稱不一致的情況）
_FEED_TO_AGENT_KEY = {"tech_companies": "tech_industry"}


def _resolve_agent_key(category: str, prompt_type: str) -> str:
    """從 category 名稱和 prompt_type 解析 category_agents key"""
    agents = _load_category_agents()
    # prompt_type 直接匹配 agent key（除 "news" 外，因多個分類共用 "news"）
    if prompt_type != "news" and prompt_type in agents:
        return prompt_type
    # 從 config feeds 找 feed key → agent key
    cfg = load_config()
    for feed_key, feed_config in cfg.get("feeds", {}).items():
        if feed_config.get("category") == category:
            agent_key = _FEED_TO_AGENT_KEY.get(feed_key, feed_key)
            if agent_key in agents:
                return agent_key
            break
    return "finance"


_TITLE_CLEAN_RE = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")
_SOURCE_TRAIL_RE = re.compile(
    r"\s*[-|–—]\s*(bloomberg(?:\.com)?|reuters(?:\.com)?|investing(?:\.com)?|"
    r"seeking alpha|cnbc(?:\.com)?|wsj(?:\.com)?|financial times)\s*$",
    flags=re.IGNORECASE,
)
_LOW_SIGNAL_TITLE_PATTERNS = [
    re.compile(
        r"\b(initiates?|upgrades?|downgrades?|reiterates?)\b.*\b(stock|shares?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(stock rating|price target)\b", re.IGNORECASE),
    re.compile(r"\bearnings call transcript\b", re.IGNORECASE),
    re.compile(r"\bearnings ahead\b", re.IGNORECASE),
]
_HIGH_SIGNAL_KEYWORDS = [
    "guidance",
    "capex",
    "tariff",
    "export control",
    "ban",
    "sanction",
    "yield",
    "capacity",
    "order",
    "backlog",
    "pricing",
    "margin",
    "datacenter",
    "hbm",
    "cowos",
    "n2",
    "n3",
    "chip",
    "fab",
    "gpu",
    "inference",
    "ai",
    "補貼",
    "關稅",
    "出口管制",
    "資本支出",
    "產能",
    "良率",
    "投資",
    "訂單",
]
_QUALITY_SCORE = {
    "high": 2.0,
    "medium": 1.0,
    "low": 0.0,
}
_SECOND_HAND_HOSTS = {
    "news.google.com",
    "hnrss.org",
    "rsshub.app",
}
_SECOND_HAND_SOURCE_KEYWORDS = (
    "google news",
    "彙整",
    "聚合",
    "轉載",
)
_PRIMARY_SOURCE_HOSTS = {
    "cnbc.com",
    "bloomberg.com",
    "reuters.com",
    "federalreserve.gov",
    "cna.com.tw",
    "money.udn.com",
    "nvidianews.nvidia.com",
    "apple.com",
    "blogs.microsoft.com",
    "about.fb.com",
    "blog.google",
    "newsroom.intel.com",
    "aws.amazon.com",
    "openai.com",
    "huggingface.co",
    "arxiv.org",
    "rss.arxiv.org",
    "semianalysis.com",
    "semiengineering.com",
    "trendforce.com",
    "digitimes.com.tw",
    "technews.tw",
    "servethehome.com",
    "eetimes.com",
    "tomshardware.com",
    "datacenterdynamics.com",
    "technologyreview.com",
}
_LOW_SIGNAL_CONTENT_HOSTS = {
    "dev.to",
    "medium.com",
    "substack.com",
}
_INVESTMENT_CATEGORIES = {
    "💰 財經與總經",
    "🌏 地緣政治與科技政策",
    "🔬 半導體與硬體",
    "🏢 科技廠動態",
    "🧠 AI 研究與突破",
}
_NUMERIC_CITATION_RE = re.compile(r"\[(\d{1,4})\](?!\()")
_NON_NUMERIC_BRACKET_RE = re.compile(r"\[([^\]]+)\](?!\()")
_GITHUB_REPO_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")
_X_URL_RE = re.compile(r"https?://\S+|www\.\S+", flags=re.IGNORECASE)
_X_HASHTAG_RE = re.compile(r"(?<!\w)#([A-Za-z][A-Za-z0-9_]{1,40})")
_X_CASHTAG_RE = re.compile(r"(?<!\w)\$([A-Za-z]{1,8})")
_X_ENG_TOKEN_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9+._-]{2,})\b")
_X_CJK_TOKEN_RE = re.compile(r"([\u4e00-\u9fff]{2,8})")
_X_TOPIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "about",
    "are",
    "as",
    "after",
    "again",
    "agentic",
    "also",
    "analysis",
    "at",
    "around",
    "be",
    "before",
    "by",
    "breaking",
    "build",
    "check",
    "comment",
    "daily",
    "data",
    "did",
    "deep",
    "details",
    "discuss",
    "does",
    "early",
    "for",
    "from",
    "gets",
    "good",
    "guide",
    "has",
    "have",
    "highlights",
    "how",
    "if",
    "in",
    "inside",
    "into",
    "is",
    "it",
    "latest",
    "live",
    "many",
    "may",
    "new",
    "next",
    "not",
    "now",
    "more",
    "most",
    "news",
    "notes",
    "of",
    "on",
    "or",
    "post",
    "preview",
    "report",
    "repost",
    "says",
    "see",
    "share",
    "shares",
    "shows",
    "some",
    "source",
    "story",
    "than",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "thread",
    "this",
    "today",
    "too",
    "use",
    "update",
    "video",
    "viral",
    "watch",
    "what",
    "when",
    "where",
    "which",
    "who",
    "will",
    "why",
    "with",
    "x",
    "xcom",
    "x.com",
    "com",
    "www",
    "http",
    "https",
    "status",
    "amp",
    "nbsp",
    "quot",
    "tco",
    "img",
    "you",
    "your",
}
_X_TOPIC_STOPWORDS_ZH = {
    "今天",
    "大家",
    "討論",
    "話題",
    "熱議",
    "更新",
    "分享",
    "重點",
    "消息",
    "全文",
    "影片",
    "整理",
    "觀點",
    "新聞",
}
_X_PRIORITY_KEYWORDS = {
    "openai",
    "anthropic",
    "nvidia",
    "xai",
    "grok",
    "mcp",
    "agent",
    "agents",
    "rag",
    "gpu",
    "inference",
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
    "fed",
    "fomc",
    "tsmc",
    "apple",
    "microsoft",
    "meta",
    "google",
    "claude",
    "codex",
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _source_meta_map() -> dict[str, dict[str, object]]:
    global _SOURCE_META_CACHE
    if _SOURCE_META_CACHE is not None:
        return _SOURCE_META_CACHE

    meta: dict[str, dict[str, object]] = {}
    try:
        config = load_config()
    except Exception:
        _SOURCE_META_CACHE = meta
        return meta

    feeds = config.get("feeds", {})
    if not isinstance(feeds, dict):
        _SOURCE_META_CACHE = meta
        return meta

    for feed_key, feed_cfg in feeds.items():
        if not isinstance(feed_cfg, dict):
            continue
        sources = feed_cfg.get("sources", [])
        if not isinstance(sources, list):
            continue
        for src in sources:
            if not isinstance(src, dict):
                continue
            name = _normalize_inline_text(str(src.get("name", "")))
            if not name:
                continue
            source_key = f"{feed_key}:{name}"
            priority = _safe_int(src.get("priority"), 5)
            quality = _normalize_inline_text(str(src.get("quality", "medium"))).lower()
            source_url = _normalize_inline_text(str(src.get("url", "")))
            parsed = urllib.parse.urlsplit(source_url)
            source_host = parsed.netloc.lower()
            meta[source_key] = {
                "priority": max(0, min(priority, 10)),
                "quality": quality if quality in _QUALITY_SCORE else "medium",
                "url": source_url,
                "host": source_host,
                "topics": [str(topic) for topic in src.get("topics", []) if str(topic).strip()],
            }

    _SOURCE_META_CACHE = meta
    return meta


def _title_keyword_bonus(title: str) -> float:
    title_lc = title.lower()
    bonus = 0.0
    for keyword in _HIGH_SIGNAL_KEYWORDS:
        if keyword in title_lc:
            bonus += 0.35
    if re.search(r"\d", title_lc):
        bonus += 0.5
    return min(3.0, bonus)


def _article_signal_score(article: Article) -> float:
    if not SUMMARY_SIGNAL_RANKING:
        return 0.0

    meta = _source_meta_map().get(article.source_key, {})
    priority = _safe_int(meta.get("priority"), 5)
    quality_name = str(meta.get("quality", "medium")).lower()
    quality_score = float(_QUALITY_SCORE.get(quality_name, 1.0))

    now = datetime.now(article.published.tzinfo)
    age_hours = max(0.0, (now - article.published).total_seconds() / 3600.0)
    half_life = float(SUMMARY_RECENCY_HALF_LIFE_HOURS)
    # Exponential decay keeps very recent news in front without dropping older key events.
    recency_score = 3.0 * math.exp(-math.log(2) * age_hours / half_life)

    title = _normalize_inline_text(article.title)
    keyword_score = _title_keyword_bonus(title)
    source_score = priority * 0.6 + quality_score

    return source_score + recency_score + keyword_score


def _rank_articles_by_signal(articles: list[Article]) -> list[Article]:
    if not articles:
        return []

    if not SUMMARY_SIGNAL_RANKING:
        return sorted(articles, key=lambda a: a.published, reverse=True)

    scored = []
    for idx, article in enumerate(articles):
        score = _article_signal_score(article)
        scored.append((score, article.published.timestamp(), -idx, article))

    scored.sort(reverse=True, key=lambda x: (x[0], x[1], x[2]))
    return [row[3] for row in scored]


def _article_host(article: Article) -> str:
    try:
        return urllib.parse.urlsplit(article.link or "").netloc.lower()
    except Exception:
        return ""


def _host_matches(host: str, domains: set[str]) -> bool:
    if not host:
        return False
    for domain in domains:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _is_second_hand_article(article: Article) -> bool:
    host = _article_host(article)
    source_lc = _normalize_inline_text(article.source).lower()
    if _host_matches(host, _SECOND_HAND_HOSTS):
        return True
    if "news.google." in host:
        return True
    return any(keyword in source_lc for keyword in _SECOND_HAND_SOURCE_KEYWORDS)


def _is_primary_source_article(article: Article) -> bool:
    if _is_second_hand_article(article):
        return False

    host = _article_host(article)
    if not host:
        return False

    if _host_matches(host, _PRIMARY_SOURCE_HOSTS):
        return True

    if _host_matches(host, _LOW_SIGNAL_CONTENT_HOSTS):
        return False

    meta = _source_meta_map().get(article.source_key, {})
    quality = str(meta.get("quality", "medium")).lower()
    return quality == "high"


def _filter_primary_source_articles(
    category: str,
    prompt_type: str,
    articles: list[Article],
) -> tuple[list[Article], int, str]:
    if not SUMMARY_PRIMARY_SOURCE_FILTER:
        return articles, 0, "disabled"
    if prompt_type == "ai_practice":
        return articles, 0, "skip-ai-practice"
    if category not in _INVESTMENT_CATEGORIES:
        return articles, 0, "skip-category"

    primary_only = [a for a in articles if _is_primary_source_article(a)]
    if len(primary_only) >= SUMMARY_PRIMARY_SOURCE_MIN_ARTICLES:
        return primary_only, max(0, len(articles) - len(primary_only)), "strict"

    relaxed = [a for a in articles if not _is_second_hand_article(a)]
    if relaxed:
        return relaxed, max(0, len(articles) - len(relaxed)), "relaxed"

    return primary_only or articles, 0, "fallback"


def _load_azure_settings_from_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip()
    ]
    urls = [
        line
        for line in lines
        if line.startswith("http://") or line.startswith("https://")
    ]
    models = [line for line in lines if line.lower().startswith("gpt-")]

    key_candidates = [
        line
        for line in lines
        if " " not in line
        and not line.startswith("http://")
        and not line.startswith("https://")
        and not line.lower().startswith("gpt-")
        and len(line) >= 32
    ]
    key = max(key_candidates, key=len, default="")

    url = ""
    for candidate in urls:
        lc = candidate.lower()
        if "/openai/v1/chat/completions" in lc:
            url = candidate
            break
    if not url:
        for candidate in urls:
            lc = candidate.lower()
            if "/openai/deployments/" in lc and "/chat/completions" in lc:
                url = candidate
                break
    if not url:
        for candidate in urls:
            lc = candidate.lower()
            if "/openai/responses" in lc:
                url = candidate
                break
    if not url and urls:
        first = urls[0].rstrip("/")
        if "openai.azure.com" in first and "/openai/" not in first:
            url = first + "/openai/v1/chat/completions"
        else:
            url = urls[0]

    preferred_models = ["gpt-5-mini", "gpt-5-nano"]
    model = ""
    model_set = {m.lower() for m in models}
    for preferred in preferred_models:
        if preferred in model_set:
            model = preferred
            break
    return {"url": url, "key": key, "model": model}


def _resolve_azure_settings() -> None:
    global AZURE_OPENAI_URL, AZURE_OPENAI_API_KEY, AZURE_OPENAI_MODEL
    if AZURE_OPENAI_URL and AZURE_OPENAI_API_KEY:
        return
    parsed = _load_azure_settings_from_file(AZURE_CONFIG_PATH)
    if not AZURE_OPENAI_URL:
        AZURE_OPENAI_URL = parsed.get("url", "")
    if not AZURE_OPENAI_API_KEY:
        AZURE_OPENAI_API_KEY = parsed.get("key", "")


def _azure_enabled() -> bool:
    _resolve_azure_settings()
    return bool(AZURE_OPENAI_URL and AZURE_OPENAI_API_KEY)


def _summary_provider() -> str:
    if SUMMARY_PROVIDER and SUMMARY_PROVIDER != "azure":
        raise RuntimeError("已鎖定使用 Azure 摘要；請只調整 AZURE_OPENAI_MODEL。")
    if not _azure_enabled():
        raise RuntimeError(
            "SUMMARY_PROVIDER=azure 但缺少 Azure 設定（AZURE_OPENAI_URL / AZURE_OPENAI_API_KEY）。"
        )
    return "azure"


def reset_usage_stats() -> None:
    provider = _summary_provider()
    model = AZURE_OPENAI_MODEL if provider == "azure" else CODEX_MODEL
    with _USAGE_LOCK:
        _USAGE_STATE["provider"] = provider
        _USAGE_STATE["model"] = model
        _USAGE_STATE["input_tokens"] = 0
        _USAGE_STATE["output_tokens"] = 0
        _USAGE_STATE["requests"] = 0


def _record_usage(input_tokens: int, output_tokens: int) -> None:
    with _USAGE_LOCK:
        _USAGE_STATE["input_tokens"] = int(_USAGE_STATE["input_tokens"]) + max(
            0, input_tokens
        )
        _USAGE_STATE["output_tokens"] = int(_USAGE_STATE["output_tokens"]) + max(
            0, output_tokens
        )
        _USAGE_STATE["requests"] = int(_USAGE_STATE["requests"]) + 1


def _extract_usage_tokens(data: dict) -> tuple[int, int]:
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        return 0, 0

    input_tokens = usage.get("input_tokens")
    if input_tokens is None:
        input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens")
    if output_tokens is None:
        output_tokens = usage.get("completion_tokens")

    try:
        in_tok = int(input_tokens or 0)
    except (TypeError, ValueError):
        in_tok = 0
    try:
        out_tok = int(output_tokens or 0)
    except (TypeError, ValueError):
        out_tok = 0
    return max(0, in_tok), max(0, out_tok)


def _normalize_reasoning_effort(value: str | None) -> str | None:
    allowed = {"minimal", "low", "medium", "high"}
    normalized = (value or "").strip().lower()
    return normalized if normalized in allowed else None


def _normalize_verbosity(value: str | None) -> str | None:
    allowed = {"low", "medium", "high"}
    normalized = (value or "").strip().lower()
    return normalized if normalized in allowed else None


def _fetch_azure_model_pricing(model_name: str) -> dict[str, object] | None:
    cache_key = model_name.strip().lower()
    cached = _PRICING_CACHE.get(cache_key)
    if isinstance(cached, dict):
        return cached

    model_map = {
        "gpt-5-nano": {
            "meter_contains": "GPT 5 Nano",
            "input_meter": "GPT 5 Nano Inpt Glbl 1M Tokens",
            "output_meter": "GPT 5 Nano outpt Glbl 1M Tokens",
        },
        "gpt-5-mini": {
            "meter_contains": "GPT 5 Mini",
            "input_meter": "GPT 5 Mini Inpt Glbl 1M Tokens",
            "output_meter": "GPT 5 Mini outpt Glbl 1M Tokens",
        },
    }
    model_info = model_map.get(cache_key)
    if not model_info:
        return None

    meter_contains = str(model_info.get("meter_contains", "")).strip()
    if not meter_contains:
        return None
    flt = (
        "contains(productName,'OpenAI GPT5') "
        f"and contains(meterName,'{meter_contains}')"
    )
    url = f"{AZURE_RETAIL_PRICES_API}?$filter={urllib.parse.quote(flt)}"

    rows = []
    while url:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.load(resp)
        rows.extend(data.get("Items", []))
        url = data.get("NextPageLink")

    input_meter = model_info["input_meter"]
    output_meter = model_info["output_meter"]

    input_rows = [r for r in rows if str(r.get("meterName", "")).strip() == input_meter]
    output_rows = [
        r for r in rows if str(r.get("meterName", "")).strip() == output_meter
    ]
    if not input_rows or not output_rows:
        return None

    def _latest_row(items: list[dict]) -> dict:
        return max(items, key=lambda r: str(r.get("effectiveStartDate", "")))

    input_row = _latest_row(input_rows)
    output_row = _latest_row(output_rows)
    input_price = float(input_row.get("unitPrice", 0))
    output_price = float(output_row.get("unitPrice", 0))
    currency = str(input_row.get("currencyCode", output_row.get("currencyCode", "USD")))
    effective_start = max(
        str(input_row.get("effectiveStartDate", "")),
        str(output_row.get("effectiveStartDate", "")),
    )

    pricing = {
        "input_per_1m_usd": input_price,
        "output_per_1m_usd": output_price,
        "currency": currency,
        "effective_start": effective_start,
        "source": "https://prices.azure.com/api/retail/prices",
        "input_meter": input_meter,
        "output_meter": output_meter,
    }
    _PRICING_CACHE[cache_key] = pricing
    return pricing


def get_usage_summary() -> dict[str, object]:
    with _USAGE_LOCK:
        usage = {
            "provider": _USAGE_STATE.get("provider", ""),
            "model": _USAGE_STATE.get("model", ""),
            "input_tokens": int(_USAGE_STATE.get("input_tokens", 0)),
            "output_tokens": int(_USAGE_STATE.get("output_tokens", 0)),
            "requests": int(_USAGE_STATE.get("requests", 0)),
        }

    total_cost = None
    input_cost = None
    output_cost = None
    pricing = None

    if usage["provider"] == "azure" and usage["model"]:
        try:
            pricing = _fetch_azure_model_pricing(str(usage["model"]))
        except Exception as e:
            pricing = {"error": str(e)}
        if pricing and "input_per_1m_usd" in pricing and "output_per_1m_usd" in pricing:
            input_cost = (
                usage["input_tokens"] / 1_000_000 * float(pricing["input_per_1m_usd"])
            )
            output_cost = (
                usage["output_tokens"] / 1_000_000 * float(pricing["output_per_1m_usd"])
            )
            total_cost = input_cost + output_cost

    usage["input_cost_usd"] = input_cost
    usage["output_cost_usd"] = output_cost
    usage["total_cost_usd"] = total_cost
    usage["pricing"] = pricing
    return usage


def _article_x_group_labels(article: Article) -> list[str]:
    topics = list(getattr(article, "topics", []) or [])
    if not topics:
        meta = _source_meta_map().get(article.source_key, {})
        topics = list(meta.get("topics", []) or [])

    labels: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        label = _X_GROUP_LABELS.get(str(topic).strip())
        if not label or label in seen:
            continue
        labels.append(label)
        seen.add(label)
    return labels


def _article_x_primary_group_key(article: Article) -> str:
    topics = list(getattr(article, "topics", []) or [])
    if not topics:
        meta = _source_meta_map().get(article.source_key, {})
        topics = list(meta.get("topics", []) or [])

    for topic in topics:
        key = str(topic).strip()
        if key in _X_GROUP_LABELS:
            return key
    return ""


def _build_articles_text(
    articles: list[Article],
    limit: int | None = None,
    start_index: int = 1,
    prompt_type: str = "news",
) -> str:
    """將文章列表轉成文字"""
    text = ""
    selected = articles if limit is None else articles[:limit]
    for i, a in enumerate(selected, start_index):
        title_text = _normalize_inline_text(a.title)
        body_text = _article_body_text(a)
        text += f"""
---
[{i}]
來源：{a.source} | 時間：{a.published.strftime("%Y-%m-%d %H:%M")}
標題：{title_text}
內文：{body_text}
"""
        if prompt_type == "x_trends":
            x_group_labels = _article_x_group_labels(a)
            if x_group_labels:
                text += f"群組：{'、'.join(x_group_labels)}\n"
        if a.companies:
            text += f"公司：{'、'.join(a.companies)}\n"
        if a.tickers:
            text += f"代號：{'、'.join(a.tickers)}\n"
        if a.event_type:
            text += f"事件：{a.event_type}\n"
        financial_context = _article_financial_context(a)
        if financial_context:
            text += f"財務重點：{financial_context}\n"
        if SUMMARY_INCLUDE_LINKS_IN_PROMPT:
            text += f"連結：{a.link}\n"
    return text


def _cap_x_articles_per_group(
    articles: list[Article], prompt_type: str
) -> tuple[list[Article], int]:
    if prompt_type != "x_trends" or SUMMARY_X_GROUP_MAX_ARTICLES <= 0:
        return articles, 0

    per_group_count: dict[str, int] = {}
    selected: list[Article] = []
    dropped = 0
    for article in articles:
        group_key = _article_x_primary_group_key(article) or "_ungrouped"
        count = per_group_count.get(group_key, 0)
        if count >= SUMMARY_X_GROUP_MAX_ARTICLES:
            dropped += 1
            continue
        per_group_count[group_key] = count + 1
        selected.append(article)
    return selected, dropped


def _normalize_inline_text(text: str | None) -> str:
    decoded = html_lib.unescape(text or "")
    cleaned = decoded.replace("\xa0", " ")
    return " ".join(cleaned.split()).strip()


def _article_market(article: Article) -> str:
    for ticker in getattr(article, "tickers", []) or []:
        ticker_text = str(ticker).upper()
        if ticker_text.isdigit() or ticker_text.endswith(".TW") or ticker_text.endswith(".TWO"):
            return "tw"
    return "us"


def _article_financial_context(article: Article) -> str:
    tickers = getattr(article, "tickers", []) or []
    if not tickers:
        return ""
    try:
        from financial_reports import (
            format_financial_snapshot_bundle_context,
            get_financial_snapshot_bundle,
        )
    except Exception:
        return ""
    ticker = str(tickers[0]).replace(".TW", "").replace(".TWO", "").upper()
    bundle = get_financial_snapshot_bundle(
        DB_PATH, market=_article_market(article), ticker=ticker
    )
    if not bundle:
        return ""
    return format_financial_snapshot_bundle_context(bundle)


def _title_fingerprint(title: str) -> str:
    normalized = _normalize_inline_text(title).lower()
    if not normalized:
        return ""
    normalized = _SOURCE_TRAIL_RE.sub("", normalized)
    normalized = _TITLE_CLEAN_RE.sub(" ", normalized)
    return _normalize_inline_text(normalized)


def _article_body_text(article: Article) -> str:
    body = _normalize_inline_text(getattr(article, "body_text", "") or article.summary)
    if not body and SUMMARY_TITLE_FALLBACK:
        body = _normalize_inline_text(article.title)
    if len(body) <= SUMMARY_BODY_MAX_CHARS:
        return body
    return body[:SUMMARY_BODY_MAX_CHARS].rstrip() + "…"


def _has_article_body(article: Article) -> bool:
    return len(_article_body_text(article)) >= SUMMARY_MIN_BODY_CHARS


def _dedupe_by_title(articles: list[Article]) -> tuple[list[Article], int]:
    if not SUMMARY_TITLE_DEDUP:
        return articles, 0

    seen_titles: set[str] = set()
    deduped: list[Article] = []
    dropped = 0
    for article in articles:
        fp = _title_fingerprint(article.title)
        if not fp:
            deduped.append(article)
            continue
        if fp in seen_titles:
            dropped += 1
            continue
        seen_titles.add(fp)
        deduped.append(article)
    return deduped, dropped


def _is_low_signal_title(article: Article) -> bool:
    if not SUMMARY_FILTER_LOW_SIGNAL:
        return False

    title = _normalize_inline_text(article.title)
    if not title:
        return False

    for pattern in _LOW_SIGNAL_TITLE_PATTERNS:
        if pattern.search(title):
            return True
    return False


def _filter_low_signal_articles(articles: list[Article]) -> tuple[list[Article], int]:
    if not SUMMARY_FILTER_LOW_SIGNAL:
        return articles, 0

    selected: list[Article] = []
    dropped = 0
    for article in articles:
        if _is_low_signal_title(article):
            dropped += 1
            continue
        selected.append(article)
    return selected, dropped


def _cap_articles_per_source(articles: list[Article]) -> tuple[list[Article], int]:
    if SUMMARY_MAX_PER_SOURCE <= 0:
        return articles, 0

    per_source_count: dict[str, int] = {}
    selected: list[Article] = []
    dropped = 0
    for article in articles:
        source_key = _normalize_inline_text(article.source) or "unknown"
        count = per_source_count.get(source_key, 0)
        if count >= SUMMARY_MAX_PER_SOURCE:
            dropped += 1
            continue
        per_source_count[source_key] = count + 1
        selected.append(article)
    return selected, dropped


def _estimate_article_prompt_chars(article: Article) -> int:
    # Keep this estimate simple and stable. We only need coarse budgeting.
    overhead = 64
    title_len = len(_normalize_inline_text(article.title))
    body_len = len(_article_body_text(article))
    link_len = len(article.link) + 8 if SUMMARY_INCLUDE_LINKS_IN_PROMPT else 0
    return overhead + title_len + body_len + link_len


def _apply_input_char_budget(articles: list[Article]) -> tuple[list[Article], int]:
    if SUMMARY_MAX_INPUT_CHARS <= 0:
        return articles, 0

    selected: list[Article] = []
    used_chars = 0
    for article in articles:
        article_chars = _estimate_article_prompt_chars(article)
        if not selected:
            selected.append(article)
            used_chars += article_chars
            continue
        if used_chars + article_chars > SUMMARY_MAX_INPUT_CHARS:
            break
        selected.append(article)
        used_chars += article_chars

    dropped = max(0, len(articles) - len(selected))
    return selected, dropped


def _min_citations_for_article_count(article_count: int) -> int:
    dynamic_min_citations = 3
    if article_count >= 30:
        dynamic_min_citations = 6
    elif article_count >= 15:
        dynamic_min_citations = 5
    elif article_count >= 8:
        dynamic_min_citations = 4
    return max(2, max(SUMMARY_MIN_CITATIONS, dynamic_min_citations))


def _extract_numeric_citations(text: str) -> list[int]:
    citations: list[int] = []
    for match in _NUMERIC_CITATION_RE.finditer(text or ""):
        try:
            citations.append(int(match.group(1)))
        except ValueError:
            continue
    return citations


def _extract_non_numeric_bracket_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _NON_NUMERIC_BRACKET_RE.finditer(text or ""):
        token = _normalize_inline_text(match.group(1))
        if not token:
            continue
        if token.isdigit():
            continue
        tokens.append(token)
    return tokens


def _sanitize_non_numeric_brackets(text: str) -> str:
    if not text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        token = _normalize_inline_text(match.group(1))
        if token.isdigit():
            return match.group(0)
        return token

    return _NON_NUMERIC_BRACKET_RE.sub(_replace, text)


# ── LLM 輸出後處理：去除常見垃圾 ──
# 正規化 [n(141)] / [n（141）] → [141]
_BRACKET_N_PAREN_RE = re.compile(r"\[n[（(](\d{1,4})[)）]\]")
_TRAILING_CITATION_DUMP_RE = re.compile(r"\n+(?:n\n)?(?:\d{1,4}\n){3,}[\d\s]*$")
# 匹配 "[n]102\n[n]104\n..." 格式的裸引用列表
_TRAILING_BRACKET_CITATION_RE = re.compile(r"\s*(?:\[n\]\d{1,4}\s*){3,}$")
# 匹配 "n 2、3、13" 或 "[n] 101, 102, 106" 格式的裸引用列表
_TRAILING_CITATION_INLINE_RE = re.compile(r"\n+\[?n\]?\s+[\d、,\s]+\s*$")
_LLM_CONVERSATIONAL_CLOSERS = [
    re.compile(r"^若需要.*$", re.MULTILINE),
    re.compile(r"^如需.*$", re.MULTILINE),
    re.compile(r"^注[：:]以上.*$", re.MULTILINE),
    re.compile(r"^以上.*皆基於.*$", re.MULTILINE),
    re.compile(r"^如果.*需要.*整理.*$", re.MULTILINE),
    re.compile(r"^需要.*可以.*$", re.MULTILINE),
    re.compile(r"^---+\s*$", re.MULTILINE),
]
# 移除 LLM 在尾部附加的 "[n] 來源索引對應" 區塊
_TRAILING_SOURCE_INDEX_RE = re.compile(r"\n+\[n\]\s*來源索引.*$", re.DOTALL)
# 移除 "(以上內容整合自..." 結尾段
_TRAILING_INTEGRATION_NOTE_RE = re.compile(r"\n+[（(]以上內容整合自.*$", re.DOTALL)
_DUPLICATE_HEADING_RE = re.compile(
    r"(### .+?今日主軸.*?)(?=### .+?今日主軸)", re.DOTALL
)


def _clean_llm_output(text: str) -> str:
    """清理 LLM 常見的垃圾輸出"""
    if not text:
        return ""
    result = text

    # 0. 正規化異體引用格式：[n(141)] → [141]
    result = _BRACKET_N_PAREN_RE.sub(r"[\1]", result)

    # 1. 移除尾部裸 citation 數字列表（n\n10\n136\n... 或 [n]102\n[n]104 或 n 2、3、13、49）
    result = _TRAILING_CITATION_DUMP_RE.sub("", result)
    result = _TRAILING_BRACKET_CITATION_RE.sub("", result)
    result = _TRAILING_CITATION_INLINE_RE.sub("", result)

    # 2. 移除 LLM 對話式結尾
    for pat in _LLM_CONVERSATIONAL_CLOSERS:
        result = pat.sub("", result)
    result = _TRAILING_SOURCE_INDEX_RE.sub("", result)
    result = _TRAILING_INTEGRATION_NOTE_RE.sub("", result)

    # 3. 偵測重複的 ### 段落標題（chunk merge 失敗），合併為唯一結構
    # 找出所有 ### 標題，如果同一標題出現多次，只保留最長的那段內容
    all_h3 = list(re.finditer(r"^### .+$", result, re.MULTILINE))
    if len(all_h3) >= 2:
        # 拆成 (heading_text, section_content) 對
        sections: list[tuple[str, str]] = []
        for i, m in enumerate(all_h3):
            heading = m.group(0).strip()
            start = m.end()
            end = all_h3[i + 1].start() if i + 1 < len(all_h3) else len(result)
            content = result[start:end].strip()
            sections.append((heading, content))

        # 對相同標題，只保留最長的段落；不同標題按順序保留
        seen_headings: dict[str, int] = {}
        merged: list[tuple[str, str]] = []
        for heading, content in sections:
            # 用正規化 key 比較（移除 emoji 和多餘空白）
            norm_key = re.sub(r"[^\w\s]", "", heading).strip()
            if norm_key in seen_headings:
                idx = seen_headings[norm_key]
                if len(content) > len(merged[idx][1]):
                    merged[idx] = (heading, content)
            else:
                seen_headings[norm_key] = len(merged)
                merged.append((heading, content))

        rebuilt_sections: list[str] = []
        for idx, (heading, content) in enumerate(merged):
            if content:
                rebuilt_sections.append(f"{heading}\n{content}")
            elif idx == 0:
                rebuilt_sections.append(heading)
        result = "\n\n".join(rebuilt_sections)

    # 4. 清理多餘空行
    result = re.sub(r"\n{3,}", "\n\n", result).strip()

    return result


def _validate_summary_citations(
    text: str, max_index: int, min_citations: int
) -> tuple[bool, str]:
    if max_index <= 0:
        return False, "無可引用新聞編號"

    non_numeric_tokens = _extract_non_numeric_bracket_tokens(text)
    if non_numeric_tokens:
        preview = ", ".join(non_numeric_tokens[:3])
        return False, f"含非數字引用標記：{preview}"

    citations = _extract_numeric_citations(text)
    if len(citations) < min_citations:
        return False, f"引用數不足（{len(citations)} < {min_citations}）"

    out_of_range = sorted({c for c in citations if c < 1 or c > max_index})
    if out_of_range:
        preview = ",".join(str(v) for v in out_of_range[:5])
        return False, f"引用編號超出範圍（1..{max_index}）：{preview}"

    return True, ""


def _build_citation_repair_prompt(
    base_prompt: str, invalid_output: str, error: str
) -> str:
    clipped_output = invalid_output.strip()
    if len(clipped_output) > 1500:
        clipped_output = clipped_output[:1500].rstrip() + "…"

    return (
        base_prompt
        + "\n\n### 上一版輸出引用格式不合規，請重寫\n"
        + f"- 錯誤原因：{error}\n"
        + "- 只允許 `[n]` 數字引用，且 n 必須在輸入新聞編號範圍內。\n"
        + "- 禁止任何非數字方括號（例如 `[來源]`、`[分類]`、`[n]` 占位符）。\n"
        + "- 請輸出完整修正版，不要解釋。\n\n"
        + "以下是上一版無效輸出（僅供你避免重複錯誤）：\n"
        + clipped_output
    )


def _summarize_with_citation_guard(
    prompt: str, category: str, max_index: int
) -> str | None:
    min_citations = _min_citations_for_article_count(max_index)

    first_result = _summarize_with_provider(prompt, category)
    if not first_result:
        return None

    valid, error = _validate_summary_citations(first_result, max_index, min_citations)
    if valid:
        return first_result

    sanitized_first = _sanitize_non_numeric_brackets(first_result)
    if sanitized_first != first_result:
        sanitized_valid, sanitized_error = _validate_summary_citations(
            sanitized_first, max_index, min_citations
        )
        if sanitized_valid:
            print(f"  ⚠️ {category} 已自動清理非數字引用標記", flush=True)
            return sanitized_first
        error = sanitized_error

    print(f"  ⚠️ {category} 引用格式不合規，重試一次：{error}", flush=True)
    repair_prompt = _build_citation_repair_prompt(prompt, first_result, error)
    retry_result = _summarize_with_provider(repair_prompt, f"{category} 引用修正")
    if not retry_result:
        return None

    retry_valid, retry_error = _validate_summary_citations(
        retry_result, max_index, min_citations
    )
    if retry_valid:
        return retry_result

    sanitized_retry = _sanitize_non_numeric_brackets(retry_result)
    if sanitized_retry != retry_result:
        sanitized_retry_valid, sanitized_retry_error = _validate_summary_citations(
            sanitized_retry, max_index, min_citations
        )
        if sanitized_retry_valid:
            print(f"  ⚠️ {category} 引用修正版已自動清理非數字標記", flush=True)
            return sanitized_retry
        retry_error = sanitized_retry_error

    print(f"  ⚠️ {category} 引用格式仍不合規：{retry_error}", flush=True)
    raise RuntimeError(f"{category} 引用格式不合規：{retry_error}")


def _extract_repo_slug(text: str) -> str:
    raw = text or ""
    if "github.com" not in raw.lower():
        return ""

    match = _GITHUB_REPO_RE.search(raw)
    if match:
        repo = _normalize_inline_text(match.group(1)).strip("/").lower()
        if repo.count("/") == 1 and re.search(r"[a-zA-Z]", repo):
            return repo
    return ""


def _article_repo_slug(article: Article) -> str:
    slug = _extract_repo_slug(article.link or "")
    if slug:
        return slug

    source_lc = _normalize_inline_text(article.source).lower()
    if "github" in source_lc:
        for candidate in re.findall(
            r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b", article.title or ""
        ):
            repo = _normalize_inline_text(candidate).strip("/").lower()
            if repo.count("/") == 1 and re.search(r"[a-zA-Z]", repo):
                return repo
    return ""


def _format_citation_refs(refs: set[int], max_refs: int = 3) -> str:
    if not refs:
        return ""
    ordered = sorted(refs)[:max_refs]
    return "".join(f"[{idx}]" for idx in ordered)


def _summarize_repo_signal(title: str, repo_slug: str) -> str:
    signal = _normalize_inline_text(title)
    if not signal:
        return "社群討論與實作分享同步上升"
    signal = signal.replace(repo_slug, "").strip(" -:|")
    signal = _normalize_inline_text(signal)
    if not signal:
        return "社群討論與實作分享同步上升"
    if len(signal) > 70:
        return signal[:70].rstrip() + "…"
    return signal


def _shorten_line(text: str, max_len: int = 72) -> str:
    normalized = _normalize_inline_text(text)
    if len(normalized) <= max_len:
        return normalized
    return normalized[:max_len].rstrip() + "…"


def _clean_x_discussion_text(text: str | None) -> str:
    normalized = _normalize_inline_text(text)
    if not normalized:
        return ""
    normalized = _X_URL_RE.sub("", normalized)
    normalized = re.sub(
        r"\s*(?:-|–|—)\s*x\.com\s*$", "", normalized, flags=re.IGNORECASE
    )
    normalized = re.sub(r"\bx\.com\b", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip(" -|;:,")
    return _normalize_inline_text(normalized)


def _is_low_signal_x_discussion(text: str) -> bool:
    normalized = _normalize_inline_text(text)
    if len(normalized) < 20:
        return True
    lowered = normalized.lower()
    if any(
        token in lowered
        for token in (
            "meme",
            "birthday cake",
            "just in",
            "bullish",
            "breaking:",
        )
    ):
        return True
    return False


def _infer_x_discussion_theme(article: Article, text: str) -> str:
    merged = f"{article.source} {text}".lower()
    if any(
        kw in merged
        for kw in ("openai", "anthropic", "claude", "xai", "model", "模型", "api")
    ):
        return "AI 平台與模型"
    if any(
        kw in merged
        for kw in ("mcp", "agent", "workflow", "tool use", "工具鏈", "導入")
    ):
        return "Agent 與工具鏈落地"
    if any(
        kw in merged
        for kw in ("gpu", "hbm", "cowos", "datacenter", "inference", "算力", "成本")
    ):
        return "算力成本與基礎設施"
    if any(kw in merged for kw in ("bitcoin", "btc", "crypto", "ethereum", "eth")):
        return "加密市場與政策"
    if any(
        kw in merged
        for kw in ("oil", "tariff", "bond", "rates", "fomc", "macro", "關稅", "利率")
    ):
        return "宏觀與政策風險"
    if any(kw in merged for kw in ("semiconductor", "nvidia", "tsmc", "samsung")):
        return "半導體供應鏈"
    return "社群討論重點"


def _topic_key(topic: str) -> str:
    return _normalize_inline_text(topic).lower().lstrip("#$")


def _extract_x_topics(text: str) -> tuple[list[str], list[str]]:
    normalized = _normalize_inline_text(text)
    if not normalized:
        return [], []

    tags_map: dict[str, str] = {}
    for raw in _X_HASHTAG_RE.findall(normalized):
        tag = f"#{raw.strip()}"
        key = tag.lower()
        if key not in tags_map:
            tags_map[key] = tag
    for raw in _X_CASHTAG_RE.findall(normalized):
        tag = f"${raw.strip().upper()}"
        key = tag.lower()
        if key not in tags_map:
            tags_map[key] = tag

    keywords_map: dict[str, str] = {}
    domain_suffixes = (".com", ".ai", ".io", ".net", ".org", ".co", ".tw", ".us")
    for token in _X_ENG_TOKEN_RE.findall(normalized):
        token_norm = token.strip().lower()
        if not token_norm or token_norm in _X_TOPIC_STOPWORDS:
            continue
        if token_norm.startswith(("http", "www")):
            continue
        if token_norm.endswith(domain_suffixes):
            continue
        if len(token_norm) < 3:
            continue
        if token_norm not in keywords_map:
            if token.isupper() and len(token) <= 8:
                keywords_map[token_norm] = token
            else:
                keywords_map[token_norm] = token_norm

    for token in _X_CJK_TOKEN_RE.findall(normalized):
        token_norm = token.strip()
        if not token_norm or token_norm in _X_TOPIC_STOPWORDS_ZH or len(token_norm) < 2:
            continue
        key = token_norm.lower()
        if key not in keywords_map:
            keywords_map[key] = token_norm

    return list(tags_map.values()), list(keywords_map.values())


def _build_x_trends_summary(category: str, articles: list[Article]) -> str:
    lines = [f"### {category} AI 導讀"]
    if not articles:
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 主線判讀")
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 今日熱門話題（24h）")
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 可驗證訊號")
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 背後動機")
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 共識與分歧")
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 影響與機會（若有）")
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 代表性貼文（供快速點讀）")
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 48h 行動清單")
        lines.append("- 目前資訊不足以判斷。")
        return "\n".join(lines)

    tag_refs: dict[str, set[int]] = {}
    tag_sources: dict[str, set[str]] = {}
    tag_mentions: dict[str, int] = {}
    keyword_refs: dict[str, set[int]] = {}
    keyword_sources: dict[str, set[str]] = {}
    keyword_mentions: dict[str, int] = {}
    keyword_display: dict[str, str] = {}
    signal_buckets: dict[str, set[int]] = {
        "產品發布 / 模型更新": set(),
        "算力與成本 / 基礎設施": set(),
        "企業導入 / 商業化": set(),
        "治理與政策 / 風險": set(),
    }
    speculative_refs: set[int] = set()

    for idx, article in enumerate(articles, 1):
        source = _normalize_inline_text(article.source) or "unknown"
        text = _normalize_inline_text(f"{article.title} {article.summary}")
        text_lc = text.lower()
        tags, keywords = _extract_x_topics(text)

        for tag in tags[:6]:
            tag_refs.setdefault(tag, set()).add(idx)
            tag_sources.setdefault(tag, set()).add(source)
            tag_mentions[tag] = tag_mentions.get(tag, 0) + 1

        for keyword in keywords[:8]:
            key = _topic_key(keyword)
            if not key:
                continue
            keyword_refs.setdefault(key, set()).add(idx)
            keyword_sources.setdefault(key, set()).add(source)
            keyword_mentions[key] = keyword_mentions.get(key, 0) + 1
            keyword_display.setdefault(key, keyword)

        if any(
            kw in text_lc
            for kw in (
                "launch",
                "release",
                "announc",
                "preview",
                "ship",
                "api",
                "model",
                "open-source",
                "open source",
                "benchmark",
                "推出",
                "發布",
                "上線",
                "模型",
                "開源",
                "版本",
            )
        ):
            signal_buckets["產品發布 / 模型更新"].add(idx)

        if any(
            kw in text_lc
            for kw in (
                "gpu",
                "hbm",
                "cowos",
                "datacenter",
                "data center",
                "inference",
                "latency",
                "throughput",
                "server",
                "cluster",
                "token",
                "capex",
                "成本",
                "算力",
                "推理",
                "伺服器",
                "資料中心",
            )
        ):
            signal_buckets["算力與成本 / 基礎設施"].add(idx)

        if any(
            kw in text_lc
            for kw in (
                "enterprise",
                "customer",
                "partner",
                "integration",
                "deploy",
                "production",
                "adoption",
                "revenue",
                "合同",
                "合作",
                "企業",
                "客戶",
                "導入",
                "商用",
                "上線",
            )
        ):
            signal_buckets["企業導入 / 商業化"].add(idx)

        if any(
            kw in text_lc
            for kw in (
                "policy",
                "regulation",
                "export control",
                "compliance",
                "security",
                "copyright",
                "監管",
                "政策",
                "法規",
                "風險",
                "資安",
                "版權",
            )
        ):
            signal_buckets["治理與政策 / 風險"].add(idx)

        if any(
            kw in text_lc
            for kw in (
                "rumor",
                "speculation",
                "unconfirmed",
                "leak",
                "傳聞",
                "未證實",
                "爆料",
                "可能",
            )
        ):
            speculative_refs.add(idx)

    scored_topics: list[tuple[str, set[int], set[str], int, float]] = []
    for tag, refs in tag_refs.items():
        sources = tag_sources.get(tag, set())
        mentions = tag_mentions.get(tag, 0)
        score = len(refs) * 4.0 + len(sources) * 2.0 + min(mentions, 6) * 0.4
        scored_topics.append((tag, refs, sources, mentions, score))

    tag_keys = {_topic_key(tag) for tag in tag_refs}
    for key, refs in keyword_refs.items():
        if key in tag_keys:
            continue
        if len(refs) < 2 and key not in _X_PRIORITY_KEYWORDS:
            continue
        display = keyword_display.get(key, key)
        sources = keyword_sources.get(key, set())
        mentions = keyword_mentions.get(key, 0)
        score = len(refs) * 3.0 + len(sources) * 1.6 + min(mentions, 6) * 0.3
        if key in _X_PRIORITY_KEYWORDS:
            score += 1.8
        scored_topics.append((display, refs, sources, mentions, score))

    scored_topics.sort(
        key=lambda item: (
            item[4],
            len(item[1]),
            len(item[2]),
            item[3],
            item[0].lower(),
        ),
        reverse=True,
    )

    top_topics: list[tuple[str, set[int], set[str], int]] = []
    seen_keys: set[str] = set()
    for topic, refs, sources, mentions, _score in scored_topics:
        key = _topic_key(topic)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        top_topics.append((topic, refs, sources, mentions))
        if len(top_topics) >= 6:
            break

    lines.append("")
    lines.append("### 主線判讀")
    if top_topics:
        lead_refs: set[int] = set()
        lead_source_set: set[str] = set()
        lead_keys: set[str] = set()
        for topic, refs, sources, _mentions in top_topics[:3]:
            lead_refs.update(refs)
            lead_source_set.update(sources)
            lead_keys.add(_topic_key(topic))

        lead_topics = "、".join(topic for topic, _r, _s, _m in top_topics[:3])
        lead_narratives: list[str] = []
        if lead_keys & {
            "gpu",
            "hbm",
            "cowos",
            "datacenter",
            "inference",
            "算力",
            "成本",
            "推理",
        }:
            lead_narratives.append("算力成本與部署效率")
        if lead_keys & {
            "openai",
            "anthropic",
            "xai",
            "claude",
            "grok",
            "model",
            "模型",
        }:
            lead_narratives.append("模型與平台發布節奏")
        if lead_keys & {
            "mcp",
            "agent",
            "agents",
            "rag",
            "workflow",
            "integration",
            "部署",
            "導入",
        }:
            lead_narratives.append("Agent 工作流與企業導入落地")

        if not lead_narratives:
            lead_narratives.append("平台動態驅動的短期情緒與主題輪動")

        narrative = "、".join(lead_narratives[:2])
        lines.append(
            f"- 今日熱門話題集中在 **{lead_topics}**，核心樣本 {len(lead_refs)} 則、覆蓋 {len(lead_source_set)} 個來源；主軸偏向 **{narrative}**。{_format_citation_refs(lead_refs, max_refs=5)}"
        )
        lines.append(
            f"- 導讀重點：先看「可驗證訊號」是否持續增加，再判斷是否從社群熱度轉為可落地趨勢。{_format_citation_refs(lead_refs, max_refs=4)}"
        )
    else:
        lines.append("- 今日貼文訊號分散，尚未形成明確共識主線。")

    lines.append("")
    lines.append("### 今日熱門話題（24h）")
    if top_topics:
        for topic, refs, sources, mentions in top_topics:
            conviction = "高共識" if len(sources) >= 3 else "早期訊號"
            lines.append(
                f"- **{topic}**：{len(refs)} 則貼文、{mentions} 次提及、跨 {len(sources)} 來源（{conviction}）。{_format_citation_refs(refs, max_refs=4)}"
            )
    else:
        lines.append("- 目前資訊不足以判斷。")

    lines.append("")
    lines.append("### 可驗證訊號")
    ranked_buckets = sorted(
        ((name, refs) for name, refs in signal_buckets.items() if refs),
        key=lambda item: (len(item[1]), item[0]),
        reverse=True,
    )
    if ranked_buckets:
        for bucket_name, refs in ranked_buckets[:4]:
            lines.append(
                f"- **{bucket_name}**：{len(refs)} 則貼文含可驗證關鍵詞，建議優先追蹤官方公告、版本與部署案例。{_format_citation_refs(refs, max_refs=4)}"
            )
    else:
        lines.append("- 尚未看到足夠可驗證訊號，暫以觀察為主。")

    lines.append("")
    lines.append("### 背後動機")
    if top_topics:
        motive_refs: set[int] = set()
        for _topic, refs, _sources, _mentions in top_topics[:3]:
            motive_refs.update(refs)
        motive_topics = "、".join(topic for topic, _r, _s, _m in top_topics[:3])
        lines.append(
            f"- 討論快速升溫的主因是 **{motive_topics}** 同時出現，社群焦點從單一新聞轉向可驗證的部署與採用訊號。{_format_citation_refs(motive_refs, max_refs=5)}"
        )
        if ranked_buckets:
            top_bucket_name, top_bucket_refs = ranked_buckets[0]
            lines.append(
                f"- 目前最強驅動因子是 **{top_bucket_name}**，代表關注點已進入「能否落地、誰先受益、成本是否可控」的階段。{_format_citation_refs(top_bucket_refs, max_refs=4)}"
            )
        else:
            lines.append("- 目前可驗證樣本仍少，背後動機暫以早期討論擴散看待。")
    else:
        lines.append("- 目前資訊不足以判斷。")

    lines.append("")
    lines.append("### 共識與分歧")
    consensus_topics: list[tuple[str, set[int], set[str], int]] = []
    divergence_topics: list[tuple[str, set[int], set[str], int]] = []
    for topic, refs, sources, mentions in top_topics:
        if len(refs) >= 3 and len(sources) >= 3:
            consensus_topics.append((topic, refs, sources, mentions))
        elif len(refs) >= 2 and len(sources) <= 2:
            divergence_topics.append((topic, refs, sources, mentions))

    if consensus_topics:
        refs: set[int] = set()
        topic_names: list[str] = []
        for topic, topic_refs, _sources, _mentions in consensus_topics[:3]:
            refs.update(topic_refs)
            topic_names.append(topic)
        lines.append(
            f"- **共識區**：{'、'.join(topic_names)} 已跨多來源重複出現，短期延續機率較高。{_format_citation_refs(refs, max_refs=5)}"
        )
    else:
        lines.append("- **共識區**：目前尚未形成跨來源的穩定共識。")

    if divergence_topics:
        refs = set()
        topic_names = []
        for topic, topic_refs, _sources, _mentions in divergence_topics[:3]:
            refs.update(topic_refs)
            topic_names.append(topic)
        lines.append(
            f"- **分歧區**：{'、'.join(topic_names)} 目前多集中於少數來源，先當早期訊號，不急著放大解讀。{_format_citation_refs(refs, max_refs=5)}"
        )
    else:
        lines.append("- **分歧區**：目前未見明顯單一來源壟斷議題。")

    if speculative_refs:
        lines.append(
            f"- **噪訊提醒**：{len(speculative_refs)}/{len(articles)} 則貼文帶有傳聞或未證實措辭，建議降權處理。{_format_citation_refs(speculative_refs, max_refs=4)}"
        )

    lines.append("")
    lines.append("### 影響與機會（若有）")
    if ranked_buckets:
        opportunity_lines: list[tuple[str, set[int]]] = []
        risk_lines: list[tuple[str, set[int]]] = []
        for bucket_name, refs in ranked_buckets:
            if bucket_name == "產品發布 / 模型更新":
                opportunity_lines.append(
                    (
                        "- **機會鏈**：模型與平台更新加速，較可能先影響 API 平台、模型服務與生態整合工具。",
                        refs,
                    )
                )
            elif bucket_name == "算力與成本 / 基礎設施":
                opportunity_lines.append(
                    (
                        "- **機會鏈**：算力與成本討論升溫，優先關注 GPU 供應鏈、資料中心電力/散熱與雲推理服務。",
                        refs,
                    )
                )
            elif bucket_name == "企業導入 / 商業化":
                opportunity_lines.append(
                    (
                        "- **影響點**：企業導入訊號增加，可能帶動企業軟體、SI 與治理/觀測工具需求。",
                        refs,
                    )
                )
            elif bucket_name == "治理與政策 / 風險":
                risk_lines.append(
                    (
                        "- **風險鏈**：治理與政策議題升溫，合規與審查成本上升可能延後實際採用時程。",
                        refs,
                    )
                )

        emitted = False
        for text, refs in opportunity_lines[:3]:
            if len(refs) >= 3:
                lines.append(f"{text}{_format_citation_refs(refs, max_refs=4)}")
                emitted = True
        for text, refs in risk_lines[:2]:
            if len(refs) >= 2:
                lines.append(f"{text}{_format_citation_refs(refs, max_refs=4)}")
                emitted = True
        if not emitted:
            lead_refs: set[int] = set()
            for _topic, refs, _sources, _mentions in top_topics[:3]:
                lead_refs.update(refs)
            lines.append(
                f"- **影響判讀**：目前以早期討論為主，先觀察是否出現跨來源、可量化的採用與部署證據，再決定是否提升權重。{_format_citation_refs(lead_refs, max_refs=4)}"
            )
    else:
        lines.append("- 目前資訊不足以判斷。")

    lines.append("")
    lines.append("### 代表性貼文（供快速點讀）")
    ranked_posts: list[tuple[float, int, Article]] = []
    topic_keys = {_topic_key(topic) for topic, _r, _s, _m in top_topics}
    for idx, article in enumerate(articles, 1):
        score = _article_signal_score(article)
        article_text = f"{article.title} {article.summary}".lower()
        overlap = 0
        for topic_key in topic_keys:
            if topic_key and topic_key in article_text:
                overlap += 1
        score += overlap * 2.4
        ranked_posts.append((score, idx, article))
    ranked_posts.sort(
        key=lambda row: (row[0], row[2].published.timestamp(), -row[1]), reverse=True
    )

    for _score, idx, article in ranked_posts[:3]:
        lines.append(
            f"- {_shorten_line(article.title)}（{_normalize_inline_text(article.source)}）[{idx}]"
        )

    lines.append("")
    lines.append("### 48h 行動清單")
    if top_topics:
        for topic, refs, sources, _mentions in top_topics[:3]:
            lines.append(
                f"- 追蹤 **{topic}** 是否在 48h 內新增官方/產品/部署佐證；若討論快速降為單一來源，視為短期噪訊。{_format_citation_refs(refs, max_refs=4)}"
            )
        if speculative_refs:
            lines.append(
                f"- 傳聞型議題需至少 2 個獨立來源或官方帳號確認，再提升決策權重。{_format_citation_refs(speculative_refs, max_refs=4)}"
            )
    else:
        lines.append("- 追蹤是否出現跨來源重複議題，且有可驗證的企業採用訊號。")

    lines.append("")
    lines.append("### 社群在討論什麼（內文）")
    topic_keys = {_topic_key(topic) for topic, _r, _s, _m in top_topics}
    ranked_posts: list[tuple[float, int, Article]] = []
    for idx, article in enumerate(articles, 1):
        score = _article_signal_score(article)
        article_text = f"{article.title} {article.summary}".lower()
        overlap = 0
        for topic_key in topic_keys:
            if topic_key and topic_key in article_text:
                overlap += 1
        score += overlap * 2.4
        ranked_posts.append((score, idx, article))
    ranked_posts.sort(
        key=lambda row: (row[0], row[2].published.timestamp(), -row[1]), reverse=True
    )

    seen_discussion_fp: set[str] = set()
    discussion_lines: list[str] = []
    for _score, idx, article in ranked_posts:
        text = _clean_x_discussion_text(article.summary) or _clean_x_discussion_text(
            article.title
        )
        if not text or _is_low_signal_x_discussion(text):
            continue
        fp = _title_fingerprint(text)
        if fp and fp in seen_discussion_fp:
            continue
        if fp:
            seen_discussion_fp.add(fp)
        theme = _infer_x_discussion_theme(article, text)
        discussion_lines.append(
            f"- **{theme}**：{_shorten_line(text, max_len=100)}[{idx}]"
        )
        if len(discussion_lines) >= 5:
            break

    if discussion_lines:
        lines.extend(discussion_lines)
    else:
        lines.append("- 目前資訊不足以判斷。")

    return "\n".join(lines)


def _build_ai_practice_hotlist_summary(category: str, articles: list[Article]) -> str:
    lines = [f"### {category} 今日可落地訊號", "", "### 熱門開源專案"]
    if not articles:
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 企業採用與產業影響")
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 噪訊過濾")
        lines.append("- 目前資訊不足以判斷。")
        lines.append("")
        lines.append("### 48h 追蹤")
        lines.append("- 目前資訊不足以判斷。")
        return "\n".join(lines)

    repo_scores: dict[str, float] = {}
    repo_mentions: dict[str, int] = {}
    repo_titles: dict[str, list[str]] = {}
    repo_citations: dict[str, set[int]] = {}
    repo_sources: dict[str, set[str]] = {}
    low_signal_refs: set[int] = set()
    adoption_refs: set[int] = set()
    topic_refs: dict[str, set[int]] = {
        "Agent / MCP 工具鏈": set(),
        "RAG / 知識檢索": set(),
        "推理成本與部署": set(),
        "評測與治理": set(),
    }

    for idx, article in enumerate(articles, 1):
        title_lc = f"{article.title} {article.summary}".lower()
        if _is_second_hand_article(article) or _host_matches(
            _article_host(article), _LOW_SIGNAL_CONTENT_HOSTS
        ):
            low_signal_refs.add(idx)

        if any(
            kw in title_lc
            for kw in (
                "deploy",
                "integration",
                "enterprise",
                "production",
                "adoption",
                "pilot",
                "poc",
                "落地",
                "導入",
                "採用",
                "上線",
            )
        ):
            adoption_refs.add(idx)

        if any(
            kw in title_lc for kw in ("agent", "mcp", "copilot", "tool use", "workflow")
        ):
            topic_refs["Agent / MCP 工具鏈"].add(idx)
        if any(
            kw in title_lc
            for kw in ("rag", "retrieval", "vector", "embedding", "knowledge")
        ):
            topic_refs["RAG / 知識檢索"].add(idx)
        if any(
            kw in title_lc
            for kw in (
                "inference",
                "latency",
                "token",
                "deploy",
                "production",
                "on-device",
                "成本",
            )
        ):
            topic_refs["推理成本與部署"].add(idx)
        if any(
            kw in title_lc
            for kw in (
                "eval",
                "benchmark",
                "safety",
                "security",
                "governance",
                "guardrail",
            )
        ):
            topic_refs["評測與治理"].add(idx)

        slug = _article_repo_slug(article)
        if not slug:
            continue

        repo_scores[slug] = repo_scores.get(slug, 0.0) + max(
            1.0, _article_signal_score(article)
        )
        repo_mentions[slug] = repo_mentions.get(slug, 0) + 1
        repo_citations.setdefault(slug, set()).add(idx)
        repo_sources.setdefault(slug, set()).add(_normalize_inline_text(article.source))

        title_bucket = repo_titles.setdefault(slug, [])
        normalized_title = _normalize_inline_text(article.title)
        if normalized_title and len(title_bucket) < 2:
            title_bucket.append(normalized_title)

    ranked_repos = sorted(
        repo_scores.keys(),
        key=lambda slug: (
            repo_scores.get(slug, 0.0),
            repo_mentions.get(slug, 0),
            len(repo_citations.get(slug, set())),
        ),
        reverse=True,
    )
    top_repos = ranked_repos[:6]
    hot_topics = sorted(
        ((topic, refs) for topic, refs in topic_refs.items() if refs),
        key=lambda item: len(item[1]),
        reverse=True,
    )

    if top_repos:
        for slug in top_repos:
            title = (repo_titles.get(slug) or [""])[0]
            mentions = repo_mentions.get(slug, 0)
            source_count = len(repo_sources.get(slug, set()))
            signal = _summarize_repo_signal(title, slug)
            refs = _format_citation_refs(repo_citations.get(slug, set()))
            lines.append(
                f"- **{slug}**：{signal}；24h 內出現 {mentions} 次、跨 {source_count} 個來源。{refs}"
            )
    else:
        if hot_topics:
            for topic, refs in hot_topics[:4]:
                lines.append(
                    f"- **{topic}**：近期討論度上升，優先追蹤可重現案例與部署成本。{_format_citation_refs(refs, max_refs=4)}"
                )
        else:
            lines.append("- 今天未偵測到明確 GitHub repo 熱點，先保留觀察。")

    lines.append("")
    lines.append("### 企業採用與產業影響")

    impact_lines: list[str] = []
    for slug in top_repos[:3]:
        slug_lc = slug.lower()
        refs = _format_citation_refs(repo_citations.get(slug, set()))
        if any(key in slug_lc for key in ("mcp", "agent", "workflow", "orchestr")):
            impact_lines.append(
                f"- Agent/MCP 工具鏈熱度上升，企業採用關鍵在權限治理與可觀測性；受益在 API 平台與 DevTool 生態。{refs}"
            )
        elif any(key in slug_lc for key in ("rag", "retriev", "vector", "embedding")):
            impact_lines.append(
                f"- 檢索與資料連接工具升溫，企業落地重點轉向資料治理與成本控制；受益在資料平台與向量基建。{refs}"
            )
        elif any(
            key in slug_lc for key in ("eval", "benchmark", "guard", "safety", "secure")
        ):
            impact_lines.append(
                f"- 評測與安全治理工具被重視，採購優先序會偏向可稽核與可量測成效的方案。{refs}"
            )
        else:
            impact_lines.append(
                f"- 開發流程工具化持續擴散，企業會優先評估可縮短 PoC 到正式上線時間的解法。{refs}"
            )

    if impact_lines:
        lines.extend(impact_lines)
    elif hot_topics:
        for topic, refs in hot_topics[:3]:
            lines.append(
                f"- {topic} 相關討論升溫，企業採用需確認是否有正式部署與可量化成效。{_format_citation_refs(refs, max_refs=4)}"
            )
    elif adoption_refs:
        lines.append(
            f"- 今日可見初步導入訊號，但案例仍有限，先觀察是否出現連續企業採用公告。{_format_citation_refs(adoption_refs)}"
        )
    else:
        lines.append("- 目前資訊不足以判斷。")

    lines.append("")
    lines.append("### 噪訊過濾")
    if low_signal_refs:
        lines.append(
            f"- 樣本中有 {len(low_signal_refs)}/{len(articles)} 篇來自聚合或個人平台；若缺少程式碼、benchmark、部署細節，先視為觀察訊號。{_format_citation_refs(low_signal_refs, max_refs=4)}"
        )
    else:
        lines.append("- 今日主要來源以原始資訊為主，噪訊相對可控。")

    repeated = [slug for slug in top_repos if repo_mentions.get(slug, 0) >= 2]
    if repeated:
        repeated_refs: set[int] = set()
        for slug in repeated[:3]:
            repeated_refs.update(repo_citations.get(slug, set()))
        lines.append(
            f"- 重複被提及的專案：{', '.join(repeated[:3])}，優先追蹤是否從討論轉向正式版本/企業案例。{_format_citation_refs(repeated_refs, max_refs=4)}"
        )
    else:
        lines.append("- 單點爆紅但無連續證據的條目，暫不視為結構性趨勢。")

    lines.append("")
    lines.append("### 48h 追蹤")
    if top_repos:
        for slug in top_repos[:3]:
            refs = _format_citation_refs(repo_citations.get(slug, set()))
            lines.append(
                f"- 追蹤 **{slug}** 的 star、issue、release 是否連兩天增長；若同步出現企業導入案例，代表熱度轉為採用。{refs}"
            )
    elif hot_topics:
        for topic, refs in hot_topics[:3]:
            lines.append(
                f"- 追蹤 **{topic}** 是否連續兩天被多來源提及，且出現可重現部署案例。{_format_citation_refs(refs, max_refs=4)}"
            )
    else:
        lines.append("- 追蹤 GitHub Trending 是否出現連續兩天重複 repo。")
        lines.append("- 追蹤是否有企業官方部落格公布導入案例。")
        lines.append("- 追蹤是否出現可重現 benchmark 與部署指標。")

    return "\n".join(lines)


_AI_GITHUB_KEYWORDS = (
    "ai",
    "agent",
    "agents",
    "mcp",
    "llm",
    "gpt",
    "claude",
    "openai",
    "anthropic",
    "copilot",
    "prompt",
    "rag",
    "retrieval",
    "embedding",
    "vector",
    "inference",
    "model",
    "models",
    "ml",
    "mlx",
    "audio",
    "tts",
    "stt",
    "sts",
    "speech",
    "voice",
    "sora",
    "diffusion",
)


def _is_ai_github_article(article: Article) -> bool:
    source_lc = _normalize_inline_text(article.source).lower()
    host = _article_host(article)
    if "github" not in source_lc and host != "github.com" and not host.endswith(".github.com"):
        return False

    article_text = _normalize_inline_text(
        f"{article.title} {article.summary} {_article_repo_slug(article)}"
    ).lower()
    return any(keyword in article_text for keyword in _AI_GITHUB_KEYWORDS)


def _prepare_ai_github_digest_articles(articles: list[Article]) -> list[Article]:
    github_articles = [
        article for article in articles if _is_ai_github_article(article) and _has_article_body(article)
    ]
    if not github_articles:
        return []

    ranked_articles = _rank_articles_by_signal(github_articles)
    deduped_articles, _ = _dedupe_by_title(ranked_articles)
    return deduped_articles[:7]


def build_ai_github_digest_prompt(category: str, articles: list[Article]) -> str:
    selected_articles = _prepare_ai_github_digest_articles(articles)
    articles_text = _build_articles_text(selected_articles or articles)
    min_citations = _min_citations_for_article_count(len(selected_articles or articles))
    prompt = f"""你正在整理 [{category}] 裡的 GitHub 熱門 AI 工具清單。

### 任務
只保留最值得看的 GitHub 項目，輸出給使用者快速瀏覽。

### 輸出格式（固定）
### GitHub 熱門 AI 工具
- **保留 GitHub 原始標題**：一句正體中文簡單解釋這個 repo / 工具在做什麼，必要時再補半句「為什麼最近值得看」。[n]

### 規則
- 只挑 5-7 個最值得看的 GitHub 項目。
- 每點只寫 1 句，最長 40 字。
- 保留 GitHub 原始標題，不要改寫成新聞標題。
- 一句正體中文簡單解釋即可，不要寫成新聞分析。
- 不要輸出「今日主軸」「市場影響」「48h 追蹤」「風險」等段落。
- 不要直接貼英文 summary；要改寫成自然的正體中文。
- 若資訊不足，只能根據標題與摘要做保守說明，不可腦補功能。
- 直接輸出內容，不要開場白，不要結尾補充說明。

以下是 GitHub 相關材料：
{articles_text}
"""
    return prompt + "\n\n" + _citation_rules(min_citations)


def _fallback_ai_github_digest(category: str, articles: list[Article]) -> str:
    selected_articles = _prepare_ai_github_digest_articles(articles) or articles[:5]
    lines = ["### GitHub 熱門 AI 工具"]
    if not selected_articles:
        lines.append("- 目前沒有可用的 GitHub AI 項目。")
        return "\n".join(lines)

    for idx, article in enumerate(selected_articles, 1):
        title = _normalize_inline_text(article.title) or _article_repo_slug(article) or "GitHub 項目"
        repo_slug = _article_repo_slug(article)
        if repo_slug:
            explanation = f"{repo_slug} 最近在 GitHub 熱度上升，可先看它在解什麼問題。"
        else:
            explanation = "這是近期 GitHub 熱度上升的 AI 工具，可先點進原始頁面看用途。"
        lines.append(f"- **{title}**：{explanation}[{idx}]")
    return "\n".join(lines)


def summarize_ai_github_digest(
    category: str, articles: list[Article]
) -> tuple[str, dict[int, str]]:
    selected_articles = _prepare_ai_github_digest_articles(articles)
    if not selected_articles:
        return _fallback_ai_github_digest(category, articles), {}

    prompt = build_ai_github_digest_prompt(category, selected_articles)
    result = _summarize_with_citation_guard(prompt, f"{category} GitHub digest", len(selected_articles))
    if result:
        return _clean_llm_output(result), {
            idx: article.link for idx, article in enumerate(selected_articles, 1)
        }

    return _fallback_ai_github_digest(category, selected_articles), {
        idx: article.link for idx, article in enumerate(selected_articles, 1)
    }


def _prepare_summary_articles(
    articles: list[Article],
    category: str,
    prompt_type: str,
) -> tuple[list[Article], list[Article], dict[str, int | bool]]:
    stats: dict[str, int | bool] = {
        "input_total": len(articles),
        "dropped_no_body": 0,
        "dropped_title_dup": 0,
        "dropped_low_signal": 0,
        "dropped_secondary_source": 0,
        "dropped_source_cap": 0,
        "dropped_x_group_cap": 0,
        "dropped_input_budget": 0,
        "dropped_max_articles": 0,
        "selected_total": 0,
        "truncated": False,
        "ranking_enabled": SUMMARY_SIGNAL_RANKING,
        "primary_mode": False,
    }

    body_articles = [a for a in articles if _has_article_body(a)]
    stats["dropped_no_body"] = len(articles) - len(body_articles)

    deduped_articles, dropped_dup = _dedupe_by_title(body_articles)
    stats["dropped_title_dup"] = dropped_dup

    if SUMMARY_FULL_READ_MODE:
        ranked_articles = _rank_articles_by_signal(deduped_articles)
        x_group_capped_articles, dropped_x_group = _cap_x_articles_per_group(
            ranked_articles, prompt_type
        )
        filtered_articles = x_group_capped_articles
        stats["dropped_low_signal"] = 0
        stats["dropped_secondary_source"] = 0
        stats["primary_mode"] = False
        stats["dropped_source_cap"] = 0
        stats["dropped_x_group_cap"] = dropped_x_group
        stats["dropped_input_budget"] = 0
        budgeted_articles = filtered_articles
    else:
        filtered_articles, dropped_low_signal = _filter_low_signal_articles(
            deduped_articles
        )
        stats["dropped_low_signal"] = dropped_low_signal

        ranked_articles = _rank_articles_by_signal(filtered_articles)

        primary_filtered_articles, dropped_secondary, primary_mode = (
            _filter_primary_source_articles(category, prompt_type, ranked_articles)
        )
        stats["dropped_secondary_source"] = dropped_secondary
        stats["primary_mode"] = primary_mode in {"strict", "relaxed"}

        source_capped_articles, dropped_source = _cap_articles_per_source(
            primary_filtered_articles
        )
        stats["dropped_source_cap"] = dropped_source

        x_group_capped_articles, dropped_x_group = _cap_x_articles_per_group(
            source_capped_articles, prompt_type
        )
        stats["dropped_x_group_cap"] = dropped_x_group

        budgeted_articles, dropped_budget = _apply_input_char_budget(
            x_group_capped_articles
        )
        stats["dropped_input_budget"] = dropped_budget

    selected_articles = budgeted_articles
    if (
        not SUMMARY_FULL_READ_MODE
        and SUMMARY_MAX_ARTICLES > 0
        and len(selected_articles) > SUMMARY_MAX_ARTICLES
    ):
        stats["dropped_max_articles"] = len(selected_articles) - SUMMARY_MAX_ARTICLES
        selected_articles = selected_articles[:SUMMARY_MAX_ARTICLES]

    dropped_total = (
        int(stats["dropped_no_body"])
        + int(stats["dropped_title_dup"])
        + int(stats["dropped_low_signal"])
        + int(stats["dropped_secondary_source"])
        + int(stats["dropped_source_cap"])
        + int(stats["dropped_x_group_cap"])
        + int(stats["dropped_input_budget"])
        + int(stats["dropped_max_articles"])
    )
    stats["selected_total"] = len(selected_articles)
    stats["truncated"] = dropped_total > 0 and len(selected_articles) > 0
    return body_articles, selected_articles, stats


def build_citation_link_map(category: str, articles: list[Article]) -> dict[int, str]:
    """建立摘要引用編號 [n] 對應原文連結"""
    prompt_type = _get_prompt_type(category, articles)
    _, selected_articles, _ = _prepare_summary_articles(articles, category, prompt_type)
    return {idx: article.link for idx, article in enumerate(selected_articles, 1)}


def build_all_citation_links(
    all_articles: dict[str, list[Article]],
) -> dict[str, dict[int, str]]:
    return {
        category: build_citation_link_map(category, articles)
        for category, articles in all_articles.items()
    }


def _citation_rules(min_citations: int) -> str:
    citation_count = max(2, min_citations)
    return """
### 事實規範（強制）
- 只能使用「以下是今天的新聞內文」中可見的事實，禁止使用外部知識補齊。
- 關鍵事實句（數字、時間、政策、公司動作）後必須標註來源編號 `[n]`。
- 禁止輸出占位符（例如 `[n]`、`[來源]`）；必須使用真實數字編號（例如 `[3]`）。
- 全文至少放 {citation_count} 個 `[n]`，且 `[n]` 必須對應輸入新聞編號。
- 不可杜撰、不過度延伸；若資訊不足，直接寫「目前資訊不足以判斷」。
- 不要做明確漲跌預測或確定性結論，僅做基於事實的推論。
""".format(citation_count=citation_count)


def _extract_json_error_message(raw_output: str) -> str | None:
    for line in (raw_output or "").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "error":
            message = event.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()

        if event.get("type") == "turn.failed":
            err = event.get("error", {})
            if isinstance(err, dict):
                message = err.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
    return None


def _extract_text_from_azure_response(data: dict) -> str:
    # Responses API
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    # Chat Completions API
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message", {})
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()
                if isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict):
                            text = item.get("text")
                            if isinstance(text, str) and text.strip():
                                text_parts.append(text.strip())
                    if text_parts:
                        return "\n\n".join(text_parts)

    # Fallback for newer schema variants
    output = data.get("output")
    if isinstance(output, list):
        text_parts = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for chunk in content:
                if isinstance(chunk, dict):
                    text = chunk.get("text")
                    if isinstance(text, str) and text.strip():
                        text_parts.append(text.strip())
        if text_parts:
            return "\n\n".join(text_parts)

    return ""


def _summarize_with_azure(prompt: str, category: str) -> str | None:
    import time

    if not _azure_enabled():
        return None

    start_time = time.time()
    print(f"    ⏱️ Calling Azure OpenAI API ({AZURE_OPENAI_MODEL})...", flush=True)

    url = AZURE_OPENAI_URL
    if not url:
        return None
    url_lc = url.lower()
    endpoint = "responses" if "/responses" in url_lc else "chat.completions"
    reasoning_effort = _normalize_reasoning_effort(AZURE_OPENAI_REASONING_EFFORT)
    verbosity = _normalize_verbosity(AZURE_OPENAI_VERBOSITY)
    print(
        "    ⚙️ Azure params: "
        f"endpoint={endpoint} "
        f"reasoning={reasoning_effort or 'default'} "
        f"verbosity={verbosity or 'default'}",
        flush=True,
    )

    if endpoint == "responses":
        payload = {
            "model": AZURE_OPENAI_MODEL,
            "input": prompt,
        }
        if reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}
        if verbosity:
            payload["text"] = {"verbosity": verbosity}
    else:
        payload = {
            "model": AZURE_OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
        }
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if verbosity:
            payload["verbosity"] = verbosity

    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("api-key", AZURE_OPENAI_API_KEY)
    req.add_header("Authorization", f"Bearer {AZURE_OPENAI_API_KEY}")

    max_attempts = AZURE_OPENAI_MAX_RETRIES
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=AZURE_OPENAI_TIMEOUT_SEC) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
            in_tok, out_tok = _extract_usage_tokens(data)
            _record_usage(in_tok, out_tok)
            text = _extract_text_from_azure_response(data)
            elapsed = time.time() - start_time
            print(
                f"    ⏱️ API returned in {elapsed:.1f}s ({AZURE_OPENAI_MODEL}) in={in_tok} out={out_tok}",
                flush=True,
            )
            return text or None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            if e.code == 429 and attempt < max_attempts:
                retry_after = 0.0
                if hasattr(e, "headers") and e.headers:
                    try:
                        retry_after = float(e.headers.get("Retry-After", "0") or 0)
                    except (TypeError, ValueError):
                        retry_after = 0.0
                wait_sec = max(
                    retry_after, AZURE_OPENAI_RETRY_BASE_SEC * (2 ** (attempt - 1))
                )
                print(
                    f"  ⚠️ Azure HTTP 429 ({category})，{wait_sec:.0f}s 後重試 "
                    f"{attempt}/{max_attempts}: {body[:160]}",
                    flush=True,
                )
                time.sleep(wait_sec)
                continue

            print(f"  ⚠️ Azure HTTP {e.code} ({category}): {body[:240]}", flush=True)
            return None
        except Exception as e:
            print(f"  ⚠️ Azure 錯誤 ({category}): {e}", flush=True)
            return None

    return None


def _category_focus(prompt_type: str) -> str:
    p = _load_persona()
    cf = p.get("category_focus", {})
    fallback = {
        "news": "資本支出增減、利率/通膨數據、企業獲利與 guidance。",
        "finance": "資本支出增減、利率/通膨數據、企業獲利與 guidance。",
        "geopolitics": "出口管制、關稅變動、補貼政策、供應鏈重組。",
        "semiconductor": "製程/產能/良率、先進封裝、記憶體、設備訂單。",
        "tech_industry": "大廠策略轉向、產品路線圖、供應鏈連鎖影響。",
        "ai_research": "模型能力突破、推理成本、部署條件、商業化可行性。",
        "ai_practice": "可落地工具、企業採用訊號、成本效益指標。",
        "x_trends": "社群情緒主線、可驗證訊號、分歧點。",
        "deep_analysis": "結構性產業變化、長期趨勢轉折。",
    }
    focus_text = cf.get(prompt_type, fallback.get(prompt_type, fallback["news"]))
    return f"- 本分類關注：{focus_text}"


def _build_category_synthesis_prompt(
    category: str, prompt_type: str, articles_text: str
) -> str:
    if prompt_type == "x_trends":
        return f"""你是AI/LLM 社群情報分析師，追蹤重要 KOL、官方帳號與技術社群討論。

### 任務
讀完所有內文後，先回答「社群在討論什麼」，再整理主線、可驗證訊號與代表性貼文。

### 輸出格式
### {category} AI 導讀

### 社群在討論什麼（內文）

### 主線與背後動機

### 可驗證訊號

### 影響與機會（若有）

### 代表性貼文

### 48h 行動清單

### 規則
- 繁體中文，重要事實附 [n]
- 不可只列來源或連結；必須先講內容。
- 先講討論內容，再講誰在討論。
- 要比較不同觀點群組，不要把所有帳號混成單一聲音。
- 每點要有具體事實支撐，不可空泛形容。
- 直接輸出，不要開場白，不要結尾問話或補充說明

以下是今天的新聞內文：
{articles_text}
"""

    agent_key = _resolve_agent_key(category, prompt_type)
    agents = _load_category_agents()
    agent = agents.get(agent_key, {})
    base = _load_persona()

    persona_text = agent.get("persona", "資深產業研究分析師")
    framework = agent.get("framework", "").strip()
    key_metrics = agent.get("key_metrics", [])
    output_sections = agent.get("output_sections", [])
    agent_anti = agent.get("anti_patterns", [])
    global_anti = base.get("global_anti_patterns", [])

    # 分析框架
    framework_blk = f"\n### 分析框架\n{framework}" if framework else ""

    # 關鍵指標
    metrics_blk = ""
    if key_metrics:
        metrics_lines = "\n".join(f"- {m}" for m in key_metrics)
        metrics_blk = f"\n### 關鍵指標\n{metrics_lines}"

    # 關注板塊（ai_practice 為技術雷達，不顯示投資板塊）
    sectors_blk = ""
    if agent_key != "ai_practice":
        sectors = base.get("focus_sectors", [])
        if sectors:
            sectors_lines = "\n".join(f"- {s}" for s in sectors)
            sectors_blk = f"\n### 關注板塊\n{sectors_lines}"

    # 輸出格式（從 config 的 output_sections 動態生成）
    output_blk = f"### {category} 今日主軸\n2-3 句，概述今天最關鍵的變化。\n"
    for section in output_sections:
        output_blk += f"\n### {section}\n"

    # 禁止事項（agent 專屬 + 全域）
    all_anti = agent_anti + global_anti
    anti_lines = "\n".join(f"- {a}" for a in all_anti)
    anti_blk = f"\n### 禁止事項\n{anti_lines}" if all_anti else ""

    return f"""你是{persona_text}。以下是 [{category}] 的新聞全文。
{sectors_blk}
{framework_blk}
{metrics_blk}

### 任務
讀完所有內文後，根據上述分析框架產出專業級分析報告。

### 輸出格式
{output_blk}
{anti_blk}

### 規則
- 繁體中文，重要事實附 [n]
- 每點要有具體數字或事實支撐
- 直接輸出，不要開場白，不要結尾問話或補充說明

以下是今天的新聞內文：
{articles_text}
"""


def build_prompt(
    category: str,
    articles: list[Article],
    prompt_type: str = "news",
    start_index: int = 1,
) -> str:
    """建立分類摘要 prompt（全量內文綜整）"""
    selected_articles = articles
    if (
        not SUMMARY_FULL_READ_MODE
        and SUMMARY_MAX_ARTICLES > 0
        and len(articles) > SUMMARY_MAX_ARTICLES
    ):
        selected_articles = articles[:SUMMARY_MAX_ARTICLES]
    articles_text = _build_articles_text(
        selected_articles, start_index=start_index, prompt_type=prompt_type
    )
    min_citations = _min_citations_for_article_count(len(selected_articles))
    return (
        _build_category_synthesis_prompt(category, prompt_type, articles_text)
        + "\n\n"
        + _citation_rules(min_citations)
    )


def _chunk_articles(articles: list[Article], chunk_size: int) -> list[list[Article]]:
    if chunk_size <= 0:
        return [articles]
    return [articles[i : i + chunk_size] for i in range(0, len(articles), chunk_size)]


def _build_category_merge_prompt(
    category: str, prompt_type: str, chunk_summaries: list[str], total_articles: int
) -> str:
    agent_key = _resolve_agent_key(category, prompt_type)
    agents = _load_category_agents()
    agent = agents.get(agent_key, {})
    base = _load_persona()

    persona_text = agent.get("persona", "資深產業研究分析師")
    output_sections = agent.get("output_sections", [])
    agent_anti = agent.get("anti_patterns", [])
    global_anti = base.get("global_anti_patterns", [])

    merged_input = ""
    for i, summary in enumerate(chunk_summaries, 1):
        merged_input += f"\n### 分段 {i}\n{summary.strip()}\n"

    # 輸出格式
    output_blk = f"### {category} 今日主軸\n2-3 句概述。\n"
    for section in output_sections:
        output_blk += f"\n### {section}\n"

    # 禁止事項
    all_anti = agent_anti + global_anti
    anti_lines = "\n".join(f"- {a}" for a in all_anti)
    anti_blk = f"\n### 禁止事項\n{anti_lines}" if all_anti else ""

    return f"""你是{persona_text}。以下是 [{category}] 的分段摘要（總計 {total_articles} 篇）。
請整合成一份完整分析報告：合併重複訊號、保留深度分析、強化因果判斷。

### 輸出格式
{output_blk}
{anti_blk}

### 規則
- 繁體中文，引用格式一律用 [數字]（如 [5]、[28]），不可用 [n(5)] 或其他格式，不可杜撰新編號
- 每點要有具體數字或事實支撐
- 直接輸出，不要開場白，不要結尾問話或補充說明
- 重要：只輸出一份摘要，不要重複段落

以下是分段摘要：
{merged_input}
"""


def build_daily_memo_prompt(
    all_articles: dict[str, list[Article]],
    summaries: dict[str, str],
    category_max_chars: int | None = None,
) -> str:
    """建立每日整體 memo prompt（跨分類整合，不挑新聞）"""
    limit_chars = (
        SUMMARY_TOP10_CATEGORY_MAX_CHARS
        if category_max_chars is None
        else max(0, category_max_chars)
    )
    # 去掉各分類摘要中的 [n] 引用，因為跨分類後編號會衝突
    _citation_ref_re = re.compile(r"\s*\[\d+\]")
    context = ""
    for category, summary in summaries.items():
        articles = all_articles.get(category, [])
        body_articles = [a for a in articles if _has_article_body(a)]
        summary_text = (summary or "").strip()
        summary_text = _citation_ref_re.sub("", summary_text)
        if limit_chars > 0 and len(summary_text) > limit_chars:
            summary_text = summary_text[:limit_chars].rstrip() + "…"
        context += f"\n\n### {category}（原始 {len(articles)} 篇；有內文 {len(body_articles)} 篇）\n"
        context += f"{summary_text}\n"

    return f"""你是首席投資策略師兼產業研究總監。以下是今天各分類的深度分析摘要。

你的任務是產出一份單篇「每日整體 memo」。這不是分類彙編，也不是新聞條列，而是一篇有結論、有佐證、有推論脈絡的市場判讀。

### 任務要求
- 只可使用輸入中的事實，不可新增未出現的事件。
- 不可逐分類重述；分類只可作為你內部理解脈絡的材料。
- 每個主要判斷都要有至少 2 個訊號或 2 個來源支撐。
- 每個段落都優先遵守「結論 → 佐證 → 脈絡 → 投資意義」。
- 若證據不足，直接縮短段落，不可硬湊結論。

### 輸出格式（固定）
### 今日主線
4-6 句。
- 先給今天最重要的 1-2 個結論。
- 接著補 2-3 個直接佐證。
- 再交代這些佐證如何串成市場主線。

### 市場怎麼定價
4-6 句。
- 說清楚股市、利率/美元、商品、加密、半導體或台股在交易什麼。
- 必須交代跨資產之間的呼應或背離。

### 關鍵因果鏈
列 3 條。
每條 3-4 句，格式為：
1. 先寫一句結論
2. 再寫觸發事件與直接佐證
3. 再寫第一層影響與第二層影響
4. 最後寫投資意義

### 重要公司 / 資產
3-5 點。
- 只保留今天最值得盯的公司、指數、ETF、商品或貨幣。
- 每點都要說明：為什麼它重要、它證明了什麼。

### 反方與風險
3-4 點。
- 每點都要明寫：若主線錯了，最可能錯在哪。
- 要提出具體反證，而不是抽象風險提醒。

### 48 小時觀察點
4-6 點。
- 每點格式：「觀察 X → 若結果是 A → 主線偏向 Y」。

### 規則
- 用繁體中文。
- 不要使用 [n] 引用標記（輸入中已去除引用編號）。
- 每個判斷要有具體數字、價格、公司、政策或事件支撐。
- 不要插入分類標籤或逐分類逐段重述。
- 不做明確漲跌預測，但要明確列出條件判斷。
- 若同一事件已在多個分類摘要中出現，只在最相關的位置提一次。
- 直接輸出內容，不要開場白，不要結尾問話或補充說明。

以下是今天各分類摘要：
{context}
"""


def _prepare_daily_memo_articles(
    all_articles: dict[str, list[Article]],
) -> tuple[list[tuple[str, Article]], dict[str, int]]:
    prepared: list[tuple[str, Article]] = []
    candidate_rows: list[tuple[float, float, str, Article]] = []
    stats = {
        "input_categories": len(all_articles),
        "input_articles": sum(len(items) for items in all_articles.values()),
        "candidate_articles": 0,
        "selected_articles": 0,
    }

    for category, articles in all_articles.items():
        if not articles:
            continue
        prompt_type = _get_prompt_type(category, articles)
        _, selected_articles, _ = _prepare_summary_articles(articles, category, prompt_type)
        if DAILY_MEMO_MAX_PER_CATEGORY > 0:
            selected_articles = selected_articles[:DAILY_MEMO_MAX_PER_CATEGORY]
        for article in selected_articles:
            candidate_rows.append(
                (
                    _article_signal_score(article),
                    article.published.timestamp(),
                    category,
                    article,
                )
            )

    stats["candidate_articles"] = len(candidate_rows)
    candidate_rows.sort(key=lambda row: (row[0], row[1]), reverse=True)

    seen_keys: set[str] = set()
    used_chars = 0
    for _score, _published_ts, category, article in candidate_rows:
        dedupe_key = article.url_hash or article.link or _title_fingerprint(article.title)
        if dedupe_key and dedupe_key in seen_keys:
            continue

        article_chars = _estimate_article_prompt_chars(article) + len(category) + 48
        if (
            DAILY_MEMO_MAX_INPUT_CHARS > 0
            and prepared
            and used_chars + article_chars > DAILY_MEMO_MAX_INPUT_CHARS
        ):
            break

        prepared.append((category, article))
        used_chars += article_chars
        if dedupe_key:
            seen_keys.add(dedupe_key)
        if DAILY_MEMO_MAX_ARTICLES > 0 and len(prepared) >= DAILY_MEMO_MAX_ARTICLES:
            break

    stats["selected_articles"] = len(prepared)
    return prepared, stats


def _cluster_daily_memo_events(
    prepared_articles: list[tuple[str, Article]],
) -> list[dict[str, object]]:
    clusters: list[dict[str, object]] = []
    cluster_by_key: dict[str, dict[str, object]] = {}

    for idx, (category, article) in enumerate(prepared_articles, 1):
        cluster_key = _normalize_inline_text(getattr(article, "event_key", ""))
        if not cluster_key:
            cluster_key = _title_fingerprint(article.title)
        if not cluster_key:
            cluster_key = article.url_hash or article.link or f"daily-memo-{idx}"

        cluster = cluster_by_key.get(cluster_key)
        if cluster is None:
            cluster = {
                "key": cluster_key,
                "headline": _normalize_inline_text(article.title) or "未命名事件",
                "articles": [],
                "categories": [],
                "sources": [],
                "latest_published": article.published,
                "signal_score": _article_signal_score(article),
            }
            cluster_by_key[cluster_key] = cluster
            clusters.append(cluster)

        cluster_articles = cluster["articles"]
        assert isinstance(cluster_articles, list)
        cluster_articles.append((category, article))

        cluster_categories = cluster["categories"]
        assert isinstance(cluster_categories, list)
        if category not in cluster_categories:
            cluster_categories.append(category)

        cluster_sources = cluster["sources"]
        assert isinstance(cluster_sources, list)
        source_name = _normalize_inline_text(article.source) or "未知來源"
        if source_name not in cluster_sources:
            cluster_sources.append(source_name)

        latest_published = cluster["latest_published"]
        assert isinstance(latest_published, datetime)
        if article.published > latest_published:
            cluster["latest_published"] = article.published

        signal_score = cluster["signal_score"]
        assert isinstance(signal_score, (int, float))
        cluster["signal_score"] = max(signal_score, _article_signal_score(article))

    return clusters


def _build_daily_memo_articles_text(prepared_articles: list[tuple[str, Article]]) -> str:
    lines: list[str] = []
    for idx, cluster in enumerate(_cluster_daily_memo_events(prepared_articles), 1):
        headline = str(cluster["headline"])
        categories = "、".join(cluster["categories"])
        sources = "、".join(cluster["sources"])
        latest_published = cluster["latest_published"]
        assert isinstance(latest_published, datetime)
        cluster_articles = cluster["articles"]
        assert isinstance(cluster_articles, list)

        lines.extend(
            [
                f"### 事件 {idx}",
                f"標題主軸：{headline}",
                f"來源數：{len(cluster_articles)}",
                f"涉及標籤：{categories or '未標記'}",
                f"來源列表：{sources or '未知來源'}",
                f"最新時間：{latest_published.strftime('%Y-%m-%d %H:%M')}",
            ]
        )

        for article_idx, (category, article) in enumerate(cluster_articles, 1):
            body_text = _article_body_text(article)
            lines.append(
                "材料 "
                f"{article_idx} | 來源：{article.source} | 標籤：{category} "
                f"| 時間：{article.published.strftime('%Y-%m-%d %H:%M')}"
            )
            if article.companies:
                lines.append(f"公司：{'、'.join(article.companies)}")
            if article.tickers:
                lines.append(f"代號：{'、'.join(article.tickers)}")
            if article.event_type:
                lines.append(f"事件：{article.event_type}")
            financial_context = _article_financial_context(article)
            if financial_context:
                lines.append(f"財務重點：{financial_context}")
            lines.append(f"摘要：{body_text}")
            if SUMMARY_INCLUDE_LINKS_IN_PROMPT:
                lines.append(f"連結：{article.link}")
        lines.append("")

    return "\n".join(lines).strip()


def build_daily_memo_prompt_from_articles(
    prepared_articles: list[tuple[str, Article]]
) -> str:
    context = _build_daily_memo_articles_text(prepared_articles)
    return f"""你是首席投資策略師兼產業研究總監。以下是今天高訊號、已去重並按事件群組整理的市場材料。

你的任務是產出一份單篇「每日整體 memo」。

### 任務要求
- 只可使用輸入中的事實，不可新增未出現的事件。
- 不可逐分類重述；`涉及標籤` 只用來幫助你理解脈絡，不能當成輸出章節。
- 每個主要判斷都要有至少 2 個事件、價格、政策或公司訊號支撐。
- 每個段落都優先遵守「結論 → 佐證 → 脈絡 → 投資意義」。
- 若證據不足，直接縮短段落，不可硬湊結論。
- 若同一事件下有多條材料，先整合材料再下判斷，不可把同一標題主軸重複當成多個獨立事件。

### 輸出格式（固定）
### 今日主線
4-6 句，先講今天最重要的 1-2 個結論，再補直接佐證與市場主線。

### 市場怎麼定價
4-6 句，說清楚股市、商品、加密、半導體、匯率或台股之間的呼應或背離。

### 關鍵因果鏈
列 3 條。每條都要包含：
1. 一句結論
2. 直接佐證
3. 第一層與第二層影響
4. 投資意義

### 重要公司 / 資產
3-5 點，每點都要說明為什麼它重要、它證明了什麼。

### 反方與風險
3-4 點，每點都要寫清楚：若主線錯了，最可能錯在哪。

### 48 小時觀察點
4-6 點，每點格式：「觀察 X → 若結果是 A → 主線偏向 Y」。

### 規則
- 用繁體中文。
- 不要使用 [n] 引用標記。
- 每個判斷都要帶具體價格、公司、政策、時間或事件。
- 不要插入分類標題，不要逐條新聞重述。
- 不做明確漲跌預測，但要明確列出條件判斷。
- 同一個 `標題主軸` 只能視為一個事件，佐證要寫成跨來源整合，不可重複計數。
- 直接輸出內容，不要開場白，不要結尾問話或補充說明。

以下是今天的高訊號事件材料：
{context}
"""


def build_top10_prompt(
    all_articles: dict[str, list[Article]],
    summaries: dict[str, str],
    category_max_chars: int | None = None,
) -> str:
    """相容舊名稱，實際改走新的 daily memo prompt。"""
    return build_daily_memo_prompt(all_articles, summaries, category_max_chars)


def _fallback_daily_memo_from_summaries(summaries: dict[str, str]) -> str:
    lines = ["### 今日主線"]
    lines.append("整體 memo 生成逾時，先根據已完成的分類摘要整理今日主線。")
    lines.append("")
    lines.append("### 市場怎麼定價")
    lines.append("目前先以跨分類共同出現的價格訊號、政策變數與公司事件作為市場主線。")
    lines.append("")
    lines.append("### 關鍵因果鏈")
    lines.append("1. 若同一事件被多個分類反覆提及，優先視為主線候選。")
    lines.append("2. 若政策、價格、公司三種訊號同時共振，優先提高判讀權重。")
    lines.append("3. 若後續來源彼此矛盾，暫不升級為強結論。")
    lines.append("")
    lines.append("### 重要公司 / 資產")
    lines.append("- 先追蹤被多來源重複提及，且能代表板塊風向的公司與資產。")
    lines.append("")
    lines.append("### 反方與風險")
    lines.append("- 若後續新聞無法形成跨來源共識，需降低主線信心。")
    lines.append("- 若同一事件出現互相矛盾版本，暫不做方向判斷。")
    lines.append("")
    lines.append("### 48 小時觀察點")
    for category, summary in summaries.items():
        short = _normalize_inline_text(summary).replace("\n", " ")
        if len(short) > 120:
            short = short[:120].rstrip() + "…"
        lines.append(f"- {category}：{short or '目前資訊不足以判斷'}")
    return "\n".join(lines)


def _fallback_daily_memo_from_articles(
    prepared_articles: list[tuple[str, Article]]
) -> str:
    event_clusters = _cluster_daily_memo_events(prepared_articles)
    lines = ["### 今日主線"]
    lines.append("整體 memo 生成逾時，先根據高訊號原始新聞整理今天的主線。")
    lines.append("")
    lines.append("### 市場怎麼定價")
    lines.append("先觀察原始新聞中重複出現的政策、價格與公司事件，再決定主線強度。")
    lines.append("")
    lines.append("### 關鍵因果鏈")
    for idx, cluster in enumerate(event_clusters[:3], 1):
        lines.append(f"{idx}. {cluster['headline']}")
    lines.append("")
    lines.append("### 重要公司 / 資產")
    for cluster in event_clusters[:5]:
        lines.append(f"- {cluster['headline']}")
    lines.append("")
    lines.append("### 反方與風險")
    lines.append("- 若高訊號新聞彼此無法形成同一條主線，需降低結論強度。")
    lines.append("")
    lines.append("### 48 小時觀察點")
    for cluster in event_clusters[:4]:
        lines.append(f"- 觀察：{cluster['headline']}")
    return "\n".join(lines)


def generate_daily_memo(
    all_articles: dict[str, list[Article]], summaries: dict[str, str]
) -> str:
    """產生每日整體 memo（跨分類整合）"""
    prompt = build_daily_memo_prompt(all_articles, summaries)

    provider = _summary_provider()
    provider_model = AZURE_OPENAI_MODEL if provider == "azure" else CODEX_MODEL
    print(f"  → Provider: {provider} ({provider_model})", end=" ")
    result = _summarize_with_provider(prompt, "每日整體 memo")
    if result:
        print("✅")
        return _clean_llm_output(_sanitize_non_numeric_brackets(result))

    compact_chars = max(800, SUMMARY_TOP10_CATEGORY_MAX_CHARS // 2)
    retry_prompt = build_daily_memo_prompt(
        all_articles, summaries, category_max_chars=compact_chars
    )
    retry_result = _summarize_with_provider(retry_prompt, "每日整體 memo（重試）")
    if retry_result:
        print("⚠️ 首次失敗，重試成功")
        return _clean_llm_output(_sanitize_non_numeric_brackets(retry_result))

    print("⚠️ 失敗，改用 fallback")
    return _clean_llm_output(
        _sanitize_non_numeric_brackets(_fallback_daily_memo_from_summaries(summaries))
    )


def generate_top10(
    all_articles: dict[str, list[Article]], summaries: dict[str, str]
) -> str:
    """相容舊名稱，實際改走新的 daily memo 生成。"""
    return generate_daily_memo(all_articles, summaries)


def generate_daily_memo_from_articles(all_articles: dict[str, list[Article]]) -> str:
    """直接從原始文章生成每日整體 memo（不先做分類摘要）。"""
    prepared_articles, stats = _prepare_daily_memo_articles(all_articles)
    if not prepared_articles:
        return _fallback_daily_memo_from_summaries({})

    event_clusters = _cluster_daily_memo_events(prepared_articles)
    stats["selected_events"] = len(event_clusters)
    print(
        "  🧭 每日 memo 原文路徑："
        f"候選 {stats['candidate_articles']} 篇 → 使用 {stats['selected_articles']} 篇"
        f" → 事件 {stats['selected_events']} 組"
    )
    prompt = build_daily_memo_prompt_from_articles(prepared_articles)

    provider = _summary_provider()
    provider_model = AZURE_OPENAI_MODEL if provider == "azure" else CODEX_MODEL
    print(f"  → Provider: {provider} ({provider_model})", end=" ")
    result = _summarize_with_provider(prompt, "每日整體 memo")
    if result:
        print("✅")
        return _clean_llm_output(_sanitize_non_numeric_brackets(result))

    retry_articles = prepared_articles[: max(8, len(prepared_articles) // 2)]
    retry_prompt = build_daily_memo_prompt_from_articles(retry_articles)
    retry_result = _summarize_with_provider(retry_prompt, "每日整體 memo（重試）")
    if retry_result:
        print("⚠️ 首次失敗，重試成功")
        return _clean_llm_output(_sanitize_non_numeric_brackets(retry_result))

    print("⚠️ 失敗，改用 fallback")
    return _clean_llm_output(
        _sanitize_non_numeric_brackets(
            _fallback_daily_memo_from_articles(prepared_articles)
        )
    )


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
        models = [CODEX_MODEL] + [m for m in CODEX_FALLBACK_MODELS if m != CODEX_MODEL]
        stderr_output = ""

        for model in models:
            result = subprocess.run(
                [
                    codex_path,
                    "exec",
                    "-m",
                    model,
                    "-c",
                    f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"',
                    "--json",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "-",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=tempfile.gettempdir(),
            )

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
                    elapsed = time.time() - start_time
                    print(f"    ⏱️ API returned in {elapsed:.1f}s ({model})", flush=True)
                    return "\n\n".join(text_parts)

            if result.stderr:
                stderr_output += result.stderr + "\n"

            json_error = _extract_json_error_message(result.stdout or "")
            if json_error:
                stderr_output += json_error + "\n"

            error_text = (result.stderr or "") + "\n" + (result.stdout or "")
            if "not supported" in error_text.lower() and model != models[-1]:
                print(f"    ⚠️ {model} 不可用，改用 fallback model", flush=True)
                continue

            break
        elapsed = time.time() - start_time
        print(f"    ⏱️ API returned in {elapsed:.1f}s", flush=True)

        # fallback: 看 stderr 有沒有有用的資訊
        if stderr_output:
            # 過濾掉 ERROR log 行，只印有意義的
            meaningful = [
                l
                for l in stderr_output.split("\n")
                if l.strip() and "ERROR codex_core::rollout" not in l
            ]
            if meaningful:
                print(f"  ⚠️ stderr: {meaningful[0][:200]}")
        return None

    except subprocess.TimeoutExpired:
        print(f"    ⏱️ ⚠️ {CODEX_MODEL} API timeout after 300s ({category})")
        return None
    except Exception as e:
        print(f"  ⚠️ Codex 錯誤 ({category}): {e}")
        return None


def _summarize_with_provider(prompt: str, category: str) -> str | None:
    provider = _summary_provider()
    if provider == "azure":
        return _summarize_with_azure(prompt, category)
    return _summarize_with_codex(prompt, category)


def _get_prompt_type(category: str, articles: list[Article] | None = None) -> str:
    """根據 config 中的 summary_prompt 決定 prompt 類型"""
    if articles:
        source_prompts = Counter()
        for article in articles:
            if article.summary_prompt:
                source_prompts[article.summary_prompt] += 1

        if source_prompts:
            prompt_candidates = [p for p, c in source_prompts.items() if c > 0]
            if len(prompt_candidates) == 1:
                return prompt_candidates[0]

    config = load_config()
    for feed_key, feed_config in config.get("feeds", {}).items():
        if feed_config.get("category") == category:
            return feed_config.get("summary_prompt", "news")
    return "news"


def summarize_category(category: str, articles: list[Article]) -> str:
    if not articles:
        print(f"  ⏭️ {category}: 無新聞，跳過")
        return f"今天 {category} 無新聞。"

    prompt_type = _get_prompt_type(category, articles)
    body_articles, selected_articles, prepare_stats = _prepare_summary_articles(
        articles, category, prompt_type
    )
    dropped_no_body = int(prepare_stats.get("dropped_no_body", 0))
    dropped_title_dup = int(prepare_stats.get("dropped_title_dup", 0))
    dropped_low_signal = int(prepare_stats.get("dropped_low_signal", 0))
    dropped_secondary_source = int(prepare_stats.get("dropped_secondary_source", 0))
    dropped_source_cap = int(prepare_stats.get("dropped_source_cap", 0))
    dropped_input_budget = int(prepare_stats.get("dropped_input_budget", 0))
    dropped_max_articles = int(prepare_stats.get("dropped_max_articles", 0))
    truncated = bool(prepare_stats.get("truncated", False))
    ranking_enabled = bool(prepare_stats.get("ranking_enabled", False))
    primary_mode = bool(prepare_stats.get("primary_mode", False))

    if SUMMARY_FULL_READ_MODE:
        print(f"  📚 {category} 完整閱讀模式：不做摘要前裁切（僅保留有內文與去重）")

    if dropped_no_body > 0:
        print(f"  ✂️ {category} 跳過 {dropped_no_body} 篇無內文新聞")
    if dropped_title_dup > 0:
        print(f"  🧹 {category} 去重 {dropped_title_dup} 篇標題重複新聞")
    if dropped_low_signal > 0:
        print(f"  🧼 {category} 過濾 {dropped_low_signal} 篇低訊號快訊標題")
    if dropped_secondary_source > 0:
        source_filter_note = "主來源優先" if primary_mode else "來源過濾"
        print(f"  🧭 {category} {source_filter_note}略過 {dropped_secondary_source} 篇")
    if ranking_enabled:
        print(f"  🎯 {category} 依來源權重與時效排序後再抽樣")
    if dropped_source_cap > 0 and SUMMARY_MAX_PER_SOURCE > 0:
        print(
            f"  ⚖️ {category} 每來源上限 {SUMMARY_MAX_PER_SOURCE}，略過 {dropped_source_cap} 篇"
        )
    if dropped_input_budget > 0 and SUMMARY_MAX_INPUT_CHARS > 0:
        print(
            f"  📦 {category} 輸入字元預算 {SUMMARY_MAX_INPUT_CHARS}，略過 {dropped_input_budget} 篇"
        )

    if not body_articles:
        raise RuntimeError(f"{category} 沒有可用內文，無法摘要")

    used_count = len(selected_articles)
    if dropped_max_articles > 0 and SUMMARY_MAX_ARTICLES > 0:
        print(
            f"  ✂️ {category} 文章過多，摘要改取前 {SUMMARY_MAX_ARTICLES}/{len(body_articles)} 篇"
        )
    elif truncated:
        print(
            f"  ✂️ {category} 摘要輸入改取 {used_count}/{len(body_articles)} 篇（聚焦高訊號與多來源）"
        )

    print(
        f"  📝 摘要 {category}（使用 {used_count}/{len(body_articles)} 篇有內文；原始 {len(articles)} 篇）..."
    )

    if SUMMARY_CHUNK_ARTICLES > 0 and len(selected_articles) > SUMMARY_CHUNK_ARTICLES:
        chunks = _chunk_articles(selected_articles, SUMMARY_CHUNK_ARTICLES)
        print(
            f"  📚 {category} 採分段摘要：{len(chunks)} 段（每段最多 {SUMMARY_CHUNK_ARTICLES} 篇）"
        )
        chunk_summaries: list[str] = []
        chunk_offset = 0
        for idx, chunk in enumerate(chunks, 1):
            print(f"    🧩 分段 {idx}/{len(chunks)}（{len(chunk)} 篇）")
            chunk_prompt = build_prompt(
                category,
                chunk,
                prompt_type,
                start_index=chunk_offset + 1,
            )
            chunk_result = _summarize_with_provider(
                chunk_prompt, f"{category} 分段 {idx}/{len(chunks)}"
            )
            if not chunk_result:
                print(f"  ⚠️ {category} 分段 {idx}/{len(chunks)} 摘要失敗，跳過此段")
            else:
                chunk_summaries.append(chunk_result)
            chunk_offset += len(chunk)

        if not chunk_summaries:
            raise RuntimeError(f"{category} 所有分段摘要均失敗（無可用結果）")

        merge_prompt = _build_category_merge_prompt(
            category, prompt_type, chunk_summaries, len(selected_articles)
        )
        merge_result = _summarize_with_provider(merge_prompt, f"{category} 合併")
        if merge_result:
            print(f"    ✅ {category} 摘要完成")
            return _clean_llm_output(merge_result)
        # 合併失敗時，直接串接各段摘要作為 fallback
        print(f"  ⚠️ {category} 合併摘要失敗，改用各段串接")
        fallback = "\n\n".join(chunk_summaries)
        return _clean_llm_output(fallback)

    prompt = build_prompt(category, selected_articles, prompt_type)

    result = _summarize_with_citation_guard(prompt, category, len(selected_articles))
    if result:
        print(f"    ✅ {category} 摘要完成")
        return _clean_llm_output(result)

    print(f"  ⚠️ {category} API 摘要失敗，改用簡單列表 fallback")
    return _simple_summary(category, selected_articles)


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
    items = list(all_articles.items())
    if not items:
        return summaries

    worker_count = (
        len(items)
        if SUMMARY_BATCH_WORKERS <= 0
        else min(SUMMARY_BATCH_WORKERS, len(items))
    )
    if worker_count <= 1:
        for category, articles in items:
            print(f"🧠 摘要 {category} ({len(articles)} 篇)...")
            summaries[category] = summarize_category(category, articles)
        return summaries

    print(f"⚡ 分類摘要並行模式：workers={worker_count}")
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for category, articles in items:
            print(f"🧠 摘要 {category} ({len(articles)} 篇)...")
            futures[category] = executor.submit(summarize_category, category, articles)

        # 保持原本分類順序寫回，避免報告順序跳動
        for category, articles in items:
            summaries[category] = futures[category].result()
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
            source_key="tech:CNBC",
            summary_prompt="news",
            category="🇺🇸 美國財經",
            published=datetime.now(TW_TZ),
        ),
        Article(
            title="Fed 暗示可能延後降息",
            summary="聯準會主席鮑威爾表示通膨仍具黏性，市場降息預期推遲至下半年。",
            link="https://example.com/2",
            source="CNN",
            source_key="finance:CNN",
            summary_prompt="news",
            category="🇺🇸 美國財經",
            published=datetime.now(TW_TZ),
        ),
    ]
    result = summarize_category("🇺🇸 美國財經", test_articles)
    print(result)
