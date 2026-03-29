import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup


_EVENT_KEY_RE = re.compile(r"[^0-9a-zA-Z_.-]+")
_QUARTER_RE = re.compile(r"\b(?:q([1-4])|([1-4])q|first[- ]quarter|second[- ]quarter|third[- ]quarter|fourth[- ]quarter)\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_TICKER_EXCHANGE_RE = re.compile(
    r"\((?:NASDAQ|NYSE|AMEX|OTC|TWSE|TPE)[:\s]+([A-Z0-9.]{1,10})\)"
)
_DOLLAR_TICKER_RE = re.compile(r"(?<!\w)\$([A-Z]{1,6})(?!\w)")
_TW_TICKER_RE = re.compile(r"\b(\d{4})(?:\.(?:TW|TWO))?\b")

_COMPANY_ALIASES = {
    "APPLE": ("Apple", "AAPL"),
    "MICROSOFT": ("Microsoft", "MSFT"),
    "ALPHABET": ("Alphabet", "GOOGL"),
    "GOOGLE": ("Google", "GOOGL"),
    "META": ("Meta", "META"),
    "AMAZON": ("Amazon", "AMZN"),
    "NVIDIA": ("NVIDIA", "NVDA"),
    "TESLA": ("Tesla", "TSLA"),
    "TSMC": ("TSMC", "TSM"),
    "TAIWAN SEMICONDUCTOR": ("TSMC", "TSM"),
    "台積電": ("台積電", "2330"),
    "鴻海": ("鴻海", "2317"),
    "聯發科": ("聯發科", "2454"),
}

_EARNINGS_KEYWORDS = (
    "earnings",
    "results",
    "revenue",
    "eps",
    "guidance",
    "quarter",
    "quarterly",
    "財報",
    "營收",
    "每股盈餘",
)
_CAPEX_KEYWORDS = ("capex", "capital expenditure", "capital spending", "資本支出")
_POLICY_KEYWORDS = ("tariff", "sanction", "export control", "關稅", "出口管制", "制裁")
_BODY_MIN_CHARS = 120


def _clean_text(text: str | None) -> str:
    return " ".join(unescape(text or "").replace("\xa0", " ").split()).strip()


def _safe_json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return None


def _iter_json_ld_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(" ", strip=True)
        payload = _safe_json_loads(raw)
        if isinstance(payload, list):
            objects.extend(item for item in payload if isinstance(item, dict))
        elif isinstance(payload, dict):
            objects.append(payload)
    return objects


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _clean_text(value if isinstance(value, str) else "")
        if text:
            return text
    return ""


def extract_article_page_metadata(html: str, source_url: str) -> dict[str, str]:
    soup = BeautifulSoup(html or "", "html.parser")
    json_ld_objects = _iter_json_ld_objects(soup)

    canonical_tag = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    canonical_url = ""
    if canonical_tag and canonical_tag.get("href"):
        canonical_url = urljoin(source_url, canonical_tag.get("href", ""))

    publisher = ""
    author = ""
    published_raw = ""
    for obj in json_ld_objects:
        publisher = publisher or _clean_text(
            (obj.get("publisher") or {}).get("name")
            if isinstance(obj.get("publisher"), dict)
            else ""
        )
        author_obj = obj.get("author")
        if isinstance(author_obj, dict):
            author = author or _clean_text(author_obj.get("name"))
        elif isinstance(author_obj, list):
            for item in author_obj:
                if isinstance(item, dict):
                    author = author or _clean_text(item.get("name"))
                    if author:
                        break
        published_raw = published_raw or _clean_text(obj.get("datePublished"))

    publisher = publisher or _first_non_empty(
        soup.find("meta", attrs={"property": "og:site_name"}).get("content")
        if soup.find("meta", attrs={"property": "og:site_name"})
        else "",
    )
    author = author or _first_non_empty(
        soup.find("meta", attrs={"name": "author"}).get("content")
        if soup.find("meta", attrs={"name": "author"})
        else "",
    )
    published_raw = published_raw or _first_non_empty(
        soup.find("meta", attrs={"property": "article:published_time"}).get("content")
        if soup.find("meta", attrs={"property": "article:published_time"})
        else "",
        soup.find("meta", attrs={"name": "pubdate"}).get("content")
        if soup.find("meta", attrs={"name": "pubdate"})
        else "",
        soup.find("time").get("datetime") if soup.find("time") else "",
    )

    body_text = ""
    body_source = ""
    article_tag = soup.find("article")
    if article_tag:
        paragraphs = [_clean_text(tag.get_text(" ", strip=True)) for tag in article_tag.find_all("p")]
        paragraphs = [paragraph for paragraph in paragraphs if paragraph]
        if paragraphs:
            body_text = "\n".join(paragraphs)
            body_source = "article"

    if not body_text:
        paragraphs = [_clean_text(tag.get_text(" ", strip=True)) for tag in soup.find_all("p")]
        paragraphs = [paragraph for paragraph in paragraphs if len(paragraph) >= 40]
        if paragraphs:
            body_text = "\n".join(paragraphs[:12])
            body_source = "paragraphs"

    extraction_status = "success" if len(body_text) >= _BODY_MIN_CHARS else "failed"
    return {
        "canonical_url": canonical_url or source_url,
        "publisher": publisher,
        "author": author,
        "published_raw": published_raw,
        "body_text": body_text,
        "body_source": body_source,
        "extraction_status": extraction_status,
    }


def _extract_companies(text: str) -> list[str]:
    companies: list[str] = []
    upper_text = text.upper()
    for alias, (company_name, _ticker) in _COMPANY_ALIASES.items():
        if alias in upper_text and company_name not in companies:
            companies.append(company_name)
    return companies


def _extract_tickers(text: str) -> list[str]:
    tickers: list[str] = []
    for pattern in (_TICKER_EXCHANGE_RE, _DOLLAR_TICKER_RE):
        for match in pattern.findall(text):
            ticker = str(match).upper()
            if ticker not in tickers:
                tickers.append(ticker)
    for match in _TW_TICKER_RE.findall(text):
        if match not in tickers:
            tickers.append(match)
    upper_text = text.upper()
    for alias, (_company_name, ticker) in _COMPANY_ALIASES.items():
        if alias in upper_text and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def _classify_event_type(text: str) -> str:
    text_lc = text.lower()
    if any(keyword in text_lc for keyword in _EARNINGS_KEYWORDS):
        return "earnings"
    if any(keyword in text_lc for keyword in _CAPEX_KEYWORDS):
        return "capex"
    if any(keyword in text_lc for keyword in _POLICY_KEYWORDS):
        return "policy"
    if "10-q" in text_lc or "10-k" in text_lc or "8-k" in text_lc:
        return "filing"
    return "news"


def _extract_period(text: str, published) -> str:
    quarter_match = _QUARTER_RE.search(text)
    year_match = _YEAR_RE.search(text)
    year_value = year_match.group(1) if year_match else str(getattr(published, "year", ""))
    if not quarter_match:
        return year_value or getattr(published, "date", lambda: None)().isoformat()

    normalized_quarter = ""
    raw_match = quarter_match.group(0).lower()
    if quarter_match.group(1):
        normalized_quarter = f"q{quarter_match.group(1)}"
    elif quarter_match.group(2):
        normalized_quarter = f"q{quarter_match.group(2)}"
    elif "first" in raw_match:
        normalized_quarter = "q1"
    elif "second" in raw_match:
        normalized_quarter = "q2"
    elif "third" in raw_match:
        normalized_quarter = "q3"
    elif "fourth" in raw_match:
        normalized_quarter = "q4"
    return f"{year_value}{normalized_quarter}" if year_value else normalized_quarter


def build_article_event_metadata(article: Any) -> dict[str, Any]:
    title = _clean_text(getattr(article, "title", ""))
    body = _clean_text(getattr(article, "body_text", "") or getattr(article, "summary", ""))
    combined = f"{title}\n{body}"
    event_type = _classify_event_type(combined)
    companies = _extract_companies(combined)
    tickers = _extract_tickers(combined)
    primary_token = (tickers[0] if tickers else (companies[0].lower() if companies else "headline")).lower()
    market = "tw" if tickers and tickers[0].isdigit() else "us"
    period = _extract_period(combined, getattr(article, "published", None))
    raw_key = f"{market}:{primary_token}:{event_type}:{period}"
    event_key = _EVENT_KEY_RE.sub("-", raw_key).strip("-")
    return {
        "companies": companies,
        "tickers": tickers,
        "event_type": event_type,
        "event_key": event_key,
    }


def apply_article_event_metadata(article: Any) -> Any:
    metadata = build_article_event_metadata(article)
    article.companies = metadata["companies"]
    article.tickers = metadata["tickers"]
    article.event_type = metadata["event_type"]
    article.event_key = metadata["event_key"]
    return article


def should_enrich_article(article: Any, min_priority: int = 8) -> bool:
    source_priority = int(getattr(article, "source_priority", 0) or 0)
    if source_priority >= min_priority:
        return True
    text = _clean_text(getattr(article, "title", "")) + " " + _clean_text(
        getattr(article, "summary", "")
    )
    return _classify_event_type(text) in {"earnings", "capex", "policy", "filing"}
