import json
import os
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from financial_reports import DB_PATH, FinancialReport, init_financial_report_store, save_financial_report


TPEX_COMPANY_PAGE_URL = "https://ic.tpex.org.tw/company_basic.php?stk_code={ticker}"
TPEX_COMPANY_BASIC_ENDPOINT_RE = re.compile(
    r'https://dsp\.tpex\.org\.tw/storage/company_basic/company_basic\.php\?s=\d+&m=\d+'
)
TPEX_FINANCE_ENDPOINT_RE = re.compile(
    r'https://dsp\.tpex\.org\.tw/storage/finance_report/company_finance_report\.php\?s=\d+&m=\d+'
)
TPEX_FINANCIAL_MAX_ISSUERS = max(1, int(os.getenv("TPEX_FINANCIAL_MAX_ISSUERS", "8")))
_AUDIT_TYPE_MAP = {
    "3": "標準式無保留核閱報告",
    "4": "修正式無保留核閱報告",
    "5": "保留式核閱報告",
    "6": "否定式核閱報告",
    "7": "拒絕式核閱報告",
    "8": "保留(附加其他事項說明段)",
    "9": "不適用(未經會計師查核(核閱))",
}


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url)
    req.add_header("Accept", "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        host = urlsplit(url).netloc.lower()
        if host not in {"ic.tpex.org.tw", "dsp.tpex.org.tw"} or not isinstance(
            reason, ssl.SSLCertVerificationError
        ):
            raise
        insecure_ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=20, context=insecure_ctx) as resp:
            return resp.read().decode("utf-8", errors="ignore")


def parse_tpex_company_endpoints(html: str) -> dict[str, str]:
    company_basic = TPEX_COMPANY_BASIC_ENDPOINT_RE.search(html or "")
    finance_report = TPEX_FINANCE_ENDPOINT_RE.search(html or "")
    return {
        "company_basic": company_basic.group(0) if company_basic else "",
        "finance_report": finance_report.group(0) if finance_report else "",
    }


def _parse_jsonp_payload(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    start = raw.find("(")
    end = raw.rfind(")")
    if start < 0 or end <= start:
        return {}
    payload = raw[start + 1 : end]
    try:
        parsed = json.loads(payload)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _detail_map(entries: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for entry in entries:
        key = str(entry.get("Account_ID_X", "")).strip()
        value = _as_float(entry.get("Amont"))
        if not key or value is None:
            continue
        result[key] = value
    return result


def _latest_report_by_kind(rows: list[dict[str, Any]], report_kind: str) -> dict[str, Any] | None:
    filtered = [row for row in rows if str(row.get("ReportKind", "")) == report_kind]
    if not filtered:
        return None
    filtered.sort(key=lambda row: (int(row.get("year", 0)), int(row.get("Season", 0))), reverse=True)
    return filtered[0]


def _audit_summary(payload: dict[str, Any]) -> str:
    acc_rows = payload.get("AccOp", [])
    if not acc_rows:
        return ""
    latest = acc_rows[0]
    type_rows = latest.get("accType", [])
    if not type_rows:
        return ""
    type_code = str(type_rows[0].get("type1", "")).strip()
    summary = _AUDIT_TYPE_MAP.get(type_code, "")
    if not summary:
        return ""
    year = latest.get("accYear")
    season = latest.get("accSeason")
    if year and season:
        return f"會計師意見：{summary}（{year}Q{season}）"
    return f"會計師意見：{summary}"


def build_tpex_financial_reports(
    *,
    ticker: str,
    company_payload: dict[str, Any],
    finance_payload: dict[str, Any],
) -> list[FinancialReport]:
    rows = finance_payload.get("Data", [])
    if not isinstance(rows, list):
        return []
    balance_row = _latest_report_by_kind(rows, "A")
    income_row = _latest_report_by_kind(rows, "B")
    cashflow_row = _latest_report_by_kind(rows, "C")
    if not balance_row and not income_row and not cashflow_row:
        return []

    balance_map = _detail_map(balance_row.get("detail", []) if balance_row else [])
    income_map = _detail_map(income_row.get("detail", []) if income_row else [])
    cashflow_map = _detail_map(cashflow_row.get("detail", []) if cashflow_row else [])
    year = max(
        int((row or {}).get("year", 0))
        for row in [balance_row, income_row, cashflow_row]
        if row
    )
    season = max(
        int((row or {}).get("Season", 0))
        for row in [balance_row, income_row, cashflow_row]
        if row and int((row or {}).get("year", 0)) == year
    )
    revenue = income_map.get("4000")
    net_income = income_map.get("8200") or income_map.get("8000")
    pretax_income = income_map.get("7900")
    eps = income_map.get("9750")
    report = FinancialReport(
        market="tw",
        ticker=ticker,
        company_name=str(company_payload.get("COMPANY_NAME", ticker)),
        source_type="tpex-finance-report",
        source_confidence="official-tpex",
        form_type="TPEX-Q",
        fiscal_year=year or None,
        fiscal_period=f"Q{season}" if season else "",
        period_end=f"{year}Q{season}" if year and season else "",
        filed_at=f"{year}Q{season}" if year and season else "",
        source_url="https://dsp.tpex.org.tw/storage/finance_report/company_finance_report.php",
        report_kind="quarterly",
        revenue=revenue,
        net_income=net_income or pretax_income,
        eps_diluted=eps,
        operating_cash_flow=cashflow_map.get("AAAA"),
        filing_excerpt=(
            f"投資活動現金流量 {cashflow_map.get('BBBB'):,.0f}、籌資活動現金流量 {cashflow_map.get('CCCC'):,.0f}"
            if cashflow_map.get("BBBB") is not None and cashflow_map.get("CCCC") is not None
            else ""
        ),
        guidance_summary=_audit_summary(finance_payload),
        payload_json=json.dumps(
            {"company": company_payload, "finance": finance_payload},
            ensure_ascii=False,
        ),
    )
    return [report]


def refresh_tpex_financial_reports(
    tickers: list[str],
    *,
    db_path: str | Path = DB_PATH,
    fetch_text: Callable[[str], str] = _fetch_text,
) -> list[FinancialReport]:
    init_financial_report_store(db_path)
    reports: list[FinancialReport] = []
    for ticker in tickers:
        company_page = fetch_text(TPEX_COMPANY_PAGE_URL.format(ticker=ticker))
        endpoints = parse_tpex_company_endpoints(company_page)
        if not endpoints["company_basic"] or not endpoints["finance_report"]:
            continue
        company_payload = _parse_jsonp_payload(fetch_text(endpoints["company_basic"]))
        finance_payload = _parse_jsonp_payload(fetch_text(endpoints["finance_report"]))
        built_reports = build_tpex_financial_reports(
            ticker=ticker,
            company_payload=company_payload,
            finance_payload=finance_payload,
        )
        for report in built_reports:
            save_financial_report(db_path, report)
            reports.append(report)
    return reports


def refresh_tpex_financial_reports_for_articles(
    all_articles: dict[str, list[Any]],
    *,
    max_issuers: int = TPEX_FINANCIAL_MAX_ISSUERS,
    fetch_text: Callable[[str], str] = _fetch_text,
    db_path: str | Path = DB_PATH,
) -> list[FinancialReport]:
    candidates: list[str] = []
    seen: set[str] = set()
    for articles in all_articles.values():
        for article in articles:
            for ticker in getattr(article, "tickers", []) or []:
                ticker_text = str(ticker).replace(".TW", "").replace(".TWO", "").strip()
                if not ticker_text.isdigit():
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
    return refresh_tpex_financial_reports(
        candidates,
        db_path=db_path,
        fetch_text=fetch_text,
    )
