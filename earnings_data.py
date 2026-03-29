import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from bs4 import BeautifulSoup

from financial_reports import (
    DB_PATH,
    FinancialReport,
    cache_sec_issuer,
    get_cached_sec_issuer,
    init_financial_report_store,
    save_financial_report,
)


SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_USER_AGENT = os.getenv(
    "SEC_API_USER_AGENT", "daily-news-bot contact@example.com"
).strip()
US_FINANCIAL_MAX_ISSUERS = max(1, int(os.getenv("US_FINANCIAL_MAX_ISSUERS", "8")))

_PRIMARY_FORMS = ("10-Q", "10-K", "20-F", "40-F", "6-K", "8-K")
_FORM_PRIORITY = {form: idx for idx, form in enumerate(_PRIMARY_FORMS)}
_USD_FACTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
    "net_income": ["NetIncomeLoss"],
    "operating_income": ["OperatingIncomeLoss"],
    "gross_profit": ["GrossProfit"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpendituresIncurredButNotYetPaid",
    ],
}
_EPS_FACTS = ["DilutedEarningsPerShare", "EarningsPerShareDiluted"]
_FILING_GUIDANCE_KEYWORDS = (
    "guidance",
    "outlook",
    "expects",
    "expect",
    "forecast",
    "sees",
    "projects",
)
_FILING_HIGHLIGHT_KEYWORDS = (
    "capital expenditure",
    "capital expenditures",
    "capex",
    "data center",
    "ai demand",
    "share repurchase",
    "dividend",
)
_TABLE_LIKE_PREFIXES = (
    "three months ended",
    "nine months ended",
    "as of ",
    "total shareholders",
    "net sales",
)


def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", SEC_USER_AGENT)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", SEC_USER_AGENT)
    req.add_header("Accept", "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _clean_visible_text(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split()).strip()


def extract_sec_filing_highlights(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html or "", "html.parser")
    paragraphs = [
        _clean_visible_text(tag.get_text(" ", strip=True))
        for tag in soup.find_all(["p", "div", "li"])
    ]
    paragraphs = [p for p in paragraphs if len(p) >= 40]
    sentences: list[str] = []
    for paragraph in paragraphs:
        chunks = re.split(r"(?<=[.!?])\s+", paragraph)
        if len(chunks) == 1:
            chunks = [paragraph]
        for chunk in chunks:
            sentence = _clean_visible_text(chunk)
            if len(sentence) < 40:
                continue
            sentence_lc = sentence.lower()
            alpha_count = sum(1 for ch in sentence if ch.isalpha())
            digit_count = sum(1 for ch in sentence if ch.isdigit())
            if alpha_count and digit_count > alpha_count * 0.8:
                continue
            if sentence_lc.startswith(_TABLE_LIKE_PREFIXES):
                continue
            sentences.append(sentence)

    guidance_summary = ""
    filing_excerpt = ""
    highlight_candidates: list[str] = []
    for sentence in sentences:
        sentence_lc = sentence.lower()
        if not guidance_summary and any(
            keyword in sentence_lc for keyword in _FILING_GUIDANCE_KEYWORDS
        ):
            guidance_summary = sentence[:240]
        if any(keyword in sentence_lc for keyword in _FILING_HIGHLIGHT_KEYWORDS):
            highlight_candidates.append(sentence[:240])
    if highlight_candidates:
        filing_excerpt = highlight_candidates[0]
    if not filing_excerpt and guidance_summary:
        filing_excerpt = guidance_summary
    return {
        "guidance_summary": guidance_summary,
        "filing_excerpt": filing_excerpt,
    }


def _normalize_cik(raw: str | int) -> str:
    digits = str(raw).strip()
    if digits.isdigit():
        return digits.zfill(10)
    return digits


def resolve_sec_issuer(
    ticker: str,
    mapping_payload: Any,
    db_path: str | Path = DB_PATH,
) -> dict[str, str] | None:
    cached = get_cached_sec_issuer(db_path, ticker)
    if cached:
        return cached

    payload = mapping_payload if isinstance(mapping_payload, dict) else {}
    ticker_upper = ticker.upper()
    for item in payload.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("ticker", "")).upper() != ticker_upper:
            continue
        resolved = {
            "ticker": ticker_upper,
            "cik": _normalize_cik(item.get("cik_str", "")),
            "company_name": str(item.get("title", ticker_upper)),
        }
        cache_sec_issuer(
            db_path,
            ticker=ticker_upper,
            cik=resolved["cik"],
            company_name=resolved["company_name"],
        )
        return resolved
    return None


def _recent_primary_filing(submissions_payload: dict[str, Any]) -> dict[str, str]:
    recent = submissions_payload.get("filings", {}).get("recent", {})
    forms = list(recent.get("form", []))
    filing_dates = list(recent.get("filingDate", []))
    report_dates = list(recent.get("reportDate", []))
    accessions = list(recent.get("accessionNumber", []))
    documents = list(recent.get("primaryDocument", []))
    candidates: list[tuple[int, str, int]] = []
    for idx, form in enumerate(forms):
        if form not in _FORM_PRIORITY:
            continue
        filing_date = str(filing_dates[idx] if idx < len(filing_dates) else "")
        candidates.append((_FORM_PRIORITY[form], filing_date, idx))
    if not candidates:
        return {"form_type": "", "filed_at": "", "period_end": "", "source_url": ""}

    best_priority = min(item[0] for item in candidates)
    priority_candidates = [item for item in candidates if item[0] == best_priority]
    priority_candidates.sort(key=lambda item: item[1], reverse=True)
    _, _, idx = priority_candidates[0]
    form = forms[idx]
    accession = str(accessions[idx] if idx < len(accessions) else "")
    accession_nodash = accession.replace("-", "")
    return {
        "form_type": form,
        "filed_at": str(filing_dates[idx] if idx < len(filing_dates) else ""),
        "period_end": str(report_dates[idx] if idx < len(report_dates) else ""),
        "source_url": (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(submissions_payload.get('cik', '0') or 0)}/"
            f"{accession_nodash}/"
            f"{documents[idx] if idx < len(documents) else ''}"
        ),
    }


def _recent_text_filing(submissions_payload: dict[str, Any]) -> dict[str, str]:
    recent = submissions_payload.get("filings", {}).get("recent", {})
    forms = list(recent.get("form", []))
    filing_dates = list(recent.get("filingDate", []))
    accessions = list(recent.get("accessionNumber", []))
    documents = list(recent.get("primaryDocument", []))
    cik = int(submissions_payload.get("cik", "0") or 0)

    candidates: list[tuple[str, str, str, str]] = []
    for idx, form in enumerate(forms):
        if form not in {"8-K", "6-K", "10-Q", "10-K", "20-F", "40-F"}:
            continue
        accession = str(accessions[idx] if idx < len(accessions) else "")
        document = str(documents[idx] if idx < len(documents) else "")
        if not accession or not document:
            continue
        accession_nodash = accession.replace("-", "")
        source_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{document}"
        )
        candidates.append((form, str(filing_dates[idx] if idx < len(filing_dates) else ""), accession, source_url))

    preferred_forms = ("8-K", "6-K", "10-Q", "10-K", "20-F", "40-F")
    for preferred_form in preferred_forms:
        filtered = [item for item in candidates if item[0] == preferred_form]
        if not filtered:
            continue
        filtered.sort(key=lambda item: item[1], reverse=True)
        form, filed_at, _accession, source_url = filtered[0]
        return {"form_type": form, "filed_at": filed_at, "source_url": source_url}
    return {"form_type": "", "filed_at": "", "source_url": ""}


def _fact_candidates(
    companyfacts_payload: dict[str, Any], names: list[str], unit_fragments: list[str]
) -> list[dict[str, Any]]:
    us_gaap = companyfacts_payload.get("facts", {}).get("us-gaap", {})
    candidates: list[dict[str, Any]] = []
    for name in names:
        fact = us_gaap.get(name, {})
        units = fact.get("units", {})
        for unit_name, values in units.items():
            if unit_fragments and not any(fragment in unit_name for fragment in unit_fragments):
                continue
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, dict):
                        candidates.append(item)
    return candidates


def _pick_fact(
    companyfacts_payload: dict[str, Any],
    names: list[str],
    unit_fragments: list[str],
    form_type: str,
) -> dict[str, Any] | None:
    candidates = _fact_candidates(companyfacts_payload, names, unit_fragments)
    candidates = [item for item in candidates if str(item.get("form", "")) == form_type]
    if not candidates:
        candidates = _fact_candidates(companyfacts_payload, names, unit_fragments)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            str(item.get("filed", "")),
            str(item.get("end", "")),
            str(item.get("fy", "")),
            str(item.get("fp", "")),
        ),
        reverse=True,
    )
    return candidates[0]


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_us_financial_report(
    *,
    ticker: str,
    cik: str,
    submissions_payload: dict[str, Any],
    companyfacts_payload: dict[str, Any],
) -> FinancialReport | None:
    filing = _recent_primary_filing(submissions_payload)
    form_type = filing["form_type"]
    if not form_type:
        return None

    revenue_fact = _pick_fact(companyfacts_payload, _USD_FACTS["revenue"], ["USD"], form_type)
    net_income_fact = _pick_fact(companyfacts_payload, _USD_FACTS["net_income"], ["USD"], form_type)
    operating_income_fact = _pick_fact(companyfacts_payload, _USD_FACTS["operating_income"], ["USD"], form_type)
    gross_profit_fact = _pick_fact(companyfacts_payload, _USD_FACTS["gross_profit"], ["USD"], form_type)
    eps_fact = _pick_fact(companyfacts_payload, _EPS_FACTS, ["USD"], form_type)
    ocf_fact = _pick_fact(companyfacts_payload, _USD_FACTS["operating_cash_flow"], ["USD"], form_type)
    capex_fact = _pick_fact(companyfacts_payload, _USD_FACTS["capex"], ["USD"], form_type)
    anchor_fact = revenue_fact or net_income_fact or eps_fact or ocf_fact
    if not anchor_fact:
        return None

    revenue = _as_float(revenue_fact.get("val") if revenue_fact else None)
    net_income = _as_float(net_income_fact.get("val") if net_income_fact else None)
    operating_income = _as_float(operating_income_fact.get("val") if operating_income_fact else None)
    gross_profit = _as_float(gross_profit_fact.get("val") if gross_profit_fact else None)
    eps_diluted = _as_float(eps_fact.get("val") if eps_fact else None)
    operating_cash_flow = _as_float(ocf_fact.get("val") if ocf_fact else None)
    capex = _as_float(capex_fact.get("val") if capex_fact else None)
    free_cash_flow = None
    if operating_cash_flow is not None and capex is not None:
        free_cash_flow = operating_cash_flow - abs(capex)

    gross_margin = (gross_profit / revenue) if (gross_profit is not None and revenue) else None
    operating_margin = (
        operating_income / revenue if (operating_income is not None and revenue) else None
    )
    fiscal_year = anchor_fact.get("fy")
    fiscal_period = str(anchor_fact.get("fp", ""))
    period_end = str(anchor_fact.get("end") or filing["period_end"])
    filed_at = str(anchor_fact.get("filed") or filing["filed_at"])

    return FinancialReport(
        market="us",
        ticker=ticker.upper(),
        company_name=str(submissions_payload.get("name", ticker.upper())),
        cik=_normalize_cik(cik),
        source_type="sec-companyfacts",
        source_confidence="official",
        form_type=form_type,
        fiscal_year=int(fiscal_year) if fiscal_year is not None else None,
        fiscal_period=fiscal_period,
        period_end=period_end,
        filed_at=filed_at,
        source_url=filing["source_url"] or SEC_SUBMISSIONS_URL.format(cik=_normalize_cik(cik)),
        revenue=revenue,
        net_income=net_income,
        operating_income=operating_income,
        gross_profit=gross_profit,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        eps_diluted=eps_diluted,
        operating_cash_flow=operating_cash_flow,
        capex=capex,
        free_cash_flow=free_cash_flow,
        payload_json=json.dumps(
            {"submissions": filing, "anchor_fact": anchor_fact}, ensure_ascii=False
        ),
    )


def refresh_us_financial_reports(
    tickers: list[str],
    *,
    db_path: str | Path = DB_PATH,
    fetch_json: Callable[[str], Any] = _fetch_json,
    fetch_text: Callable[[str], str] = _fetch_text,
    sleep_sec: float = 0.2,
) -> list[FinancialReport]:
    init_financial_report_store(db_path)
    mapping_payload = fetch_json(SEC_TICKER_URL)
    reports: list[FinancialReport] = []
    for ticker in tickers:
        issuer = resolve_sec_issuer(ticker, mapping_payload, db_path=db_path)
        if not issuer:
            continue
        cik = issuer["cik"]
        try:
            submissions_payload = fetch_json(SEC_SUBMISSIONS_URL.format(cik=cik))
            companyfacts_payload = fetch_json(SEC_COMPANYFACTS_URL.format(cik=cik))
        except urllib.error.HTTPError:
            continue
        report = build_us_financial_report(
            ticker=ticker,
            cik=cik,
            submissions_payload=submissions_payload,
            companyfacts_payload=companyfacts_payload,
        )
        if not report:
            continue
        text_filing = _recent_text_filing(submissions_payload)
        text_source_url = text_filing.get("source_url") or report.source_url
        if text_source_url:
            try:
                filing_html = fetch_text(text_source_url)
            except Exception:
                filing_html = ""
            if filing_html:
                filing_highlights = extract_sec_filing_highlights(filing_html)
                report.guidance_summary = filing_highlights.get("guidance_summary", "")
                report.filing_excerpt = filing_highlights.get("filing_excerpt", "")
        save_financial_report(db_path, report)
        reports.append(report)
        if sleep_sec > 0:
            time.sleep(sleep_sec)
    return reports


def refresh_us_financial_reports_for_articles(
    all_articles: dict[str, list[Any]],
    *,
    max_issuers: int = US_FINANCIAL_MAX_ISSUERS,
    refresh_fn: Callable[..., list[FinancialReport]] | None = None,
    db_path: str | Path = DB_PATH,
) -> list[FinancialReport]:
    candidates: list[str] = []
    seen: set[str] = set()
    for articles in all_articles.values():
        for article in articles:
            for ticker in getattr(article, "tickers", []) or []:
                ticker_text = str(ticker).upper()
                if not ticker_text.isalpha():
                    continue
                if ticker_text in seen:
                    continue
                seen.add(ticker_text)
                candidates.append(ticker_text)
                if len(candidates) >= max_issuers:
                    break
            if len(candidates) >= max_issuers:
                break
        if len(candidates) >= max_issuers:
            break
    if not candidates:
        return []
    fn = refresh_fn or refresh_us_financial_reports
    return fn(candidates, db_path=db_path)
