import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from financial_reports import DB_PATH, FinancialReport, init_financial_report_store, save_financial_report


MOPS_API_BASE = "https://mops.twse.com.tw/mops/api"
MOPS_INCOME_URL = f"{MOPS_API_BASE}/t164sb04"
MOPS_BALANCE_URL = f"{MOPS_API_BASE}/t164sb03"
MOPS_CASHFLOW_URL = f"{MOPS_API_BASE}/t164sb05"
MOPS_QUERY_REFERER = "https://mops.twse.com.tw/mops/#/web/t164sb00"


def _fetch_json(url: str, payload: dict[str, Any]) -> Any:
    req = urllib.request.Request(url, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    )
    req.add_header("Origin", "https://mops.twse.com.tw")
    req.add_header("Referer", MOPS_QUERY_REFERER)
    req.add_header("Accept", "*/*")
    body = json.dumps(payload).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=body, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        host = urlsplit(url).netloc.lower()
        if host != "mops.twse.com.tw" or not isinstance(
            reason, ssl.SSLCertVerificationError
        ):
            raise
        insecure_ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, data=body, timeout=20, context=insecure_ctx) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _parse_amount(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _row_map(payload: dict[str, Any]) -> dict[str, float]:
    rows = payload.get("result", {}).get("reportList", [])
    result: dict[str, float] = {}
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        label = str(row[0]).strip()
        value = _parse_amount(row[1] if len(row) > 1 else None)
        if not label or value is None:
            continue
        result[label] = value
    return result


def _row_value(rows: dict[str, float], *labels: str) -> float | None:
    normalized = {key.replace("　", "").strip(): value for key, value in rows.items()}
    for label in labels:
        key = label.replace("　", "").strip()
        if key in normalized:
            return normalized[key]
    return None


def build_mops_financial_report(
    *,
    ticker: str,
    income_payload: dict[str, Any],
    balance_payload: dict[str, Any],
    cashflow_payload: dict[str, Any],
) -> FinancialReport:
    income_map = _row_map(income_payload)
    balance_map = _row_map(balance_payload)
    cashflow_map = _row_map(cashflow_payload)
    meta = income_payload.get("result", {})
    fiscal_year = meta.get("year")
    season = meta.get("season")
    company_name = str(meta.get("companyAbbreviation", ticker))
    return FinancialReport(
        market="tw",
        ticker=ticker,
        company_name=company_name,
        source_type="mops-api",
        source_confidence="official-mops",
        form_type="MOPS-Q",
        fiscal_year=int(fiscal_year) if fiscal_year not in (None, "") else None,
        fiscal_period=f"Q{season}" if season else "",
        period_end=f"{fiscal_year}Q{season}" if fiscal_year and season else "",
        filed_at=f"{fiscal_year}Q{season}" if fiscal_year and season else "",
        source_url=MOPS_INCOME_URL,
        report_kind="quarterly",
        revenue=_row_value(income_map, "營業收入合計"),
        net_income=_row_value(income_map, "本期淨利（淨損）"),
        operating_income=_row_value(income_map, "營業利益（損失）"),
        eps_diluted=_row_value(income_map, "基本每股盈餘", "稀釋每股盈餘"),
        operating_cash_flow=_row_value(cashflow_map, "營業活動之淨現金流入（流出）"),
        capex=abs(_row_value(cashflow_map, "取得不動產、廠房及設備")) if _row_value(cashflow_map, "取得不動產、廠房及設備") is not None else None,
        filing_excerpt=(
            f"資產總額 {balance_map.get('　資產總額'):,.0f}、負債總額 {balance_map.get('　負債總額'):,.0f}"
            if balance_map.get("　資產總額") is not None and balance_map.get("　負債總額") is not None
            else ""
        ),
        payload_json=json.dumps(
            {
                "income": income_payload,
                "balance": balance_payload,
                "cashflow": cashflow_payload,
            },
            ensure_ascii=False,
        ),
    )


def refresh_mops_financial_reports(
    tickers: list[str],
    *,
    db_path: str | Path = DB_PATH,
    fetch_json: Callable[[str, dict[str, Any]], Any] = _fetch_json,
) -> list[FinancialReport]:
    init_financial_report_store(db_path)
    reports: list[FinancialReport] = []
    for ticker in tickers:
        payload = {
            "companyId": ticker,
            "dataType": "1",
            "season": "",
            "year": "",
            "subsidiaryCompanyId": "",
        }
        income_payload = fetch_json(MOPS_INCOME_URL, payload)
        balance_payload = fetch_json(MOPS_BALANCE_URL, payload)
        cashflow_payload = fetch_json(MOPS_CASHFLOW_URL, payload)
        report = build_mops_financial_report(
            ticker=ticker,
            income_payload=income_payload,
            balance_payload=balance_payload,
            cashflow_payload=cashflow_payload,
        )
        save_financial_report(db_path, report)
        reports.append(report)
    return reports


def refresh_mops_financial_reports_for_articles(
    all_articles: dict[str, list[Any]],
    *,
    db_path: str | Path = DB_PATH,
    fetch_json: Callable[[str, dict[str, Any]], Any] = _fetch_json,
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
    if not candidates:
        return []
    return refresh_mops_financial_reports(candidates, db_path=db_path, fetch_json=fetch_json)
