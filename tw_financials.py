import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from financial_reports import DB_PATH, FinancialReport, init_financial_report_store, save_financial_report


TW_MONTHLY_REVENUE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
TW_INCOME_STATEMENT_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci"
TW_BALANCE_SHEET_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ci"
TW_FINANCIAL_MAX_ISSUERS = max(1, int(os.getenv("TW_FINANCIAL_MAX_ISSUERS", "8")))


def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        host = urlsplit(url).netloc.lower()
        if host != "openapi.twse.com.tw" or not isinstance(
            reason, ssl.SSLCertVerificationError
        ):
            raise
        insecure_ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=20, context=insecure_ctx) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def map_tw_monthly_revenue_row(row: dict[str, Any]) -> FinancialReport:
    return FinancialReport(
        market="tw",
        ticker=str(row.get("公司代號", "")).strip(),
        company_name=str(row.get("公司名稱", "")).strip(),
        source_type="twse-openapi",
        source_confidence="official-openapi",
        form_type="TWSE-MONTHLY",
        fiscal_year=None,
        fiscal_period=str(row.get("資料年月", "")).strip(),
        period_end=str(row.get("資料年月", "")).strip(),
        filed_at=str(row.get("出表日期", "")).strip(),
        source_url=TW_MONTHLY_REVENUE_URL,
        report_kind="monthly_revenue",
        monthly_revenue=_as_float(row.get("營業收入-當月營收")),
        payload_json=json.dumps(row, ensure_ascii=False),
    )


def build_tw_quarterly_financial_report(
    *,
    ticker: str,
    income_rows: list[dict[str, Any]],
    balance_rows: list[dict[str, Any]],
) -> FinancialReport | None:
    income_row = next((row for row in income_rows if str(row.get("公司代號", "")).strip() == ticker), None)
    balance_row = next((row for row in balance_rows if str(row.get("公司代號", "")).strip() == ticker), None)
    if not income_row and not balance_row:
        return None
    base_row = income_row or balance_row or {}
    revenue = _as_float((income_row or {}).get("營業收入"))
    gross_profit = _as_float((income_row or {}).get("營業毛利（毛損）淨額"))
    operating_income = _as_float((income_row or {}).get("營業利益（損失）"))
    net_income = _as_float((income_row or {}).get("淨利（淨損）歸屬於母公司業主"))
    eps_diluted = _as_float((income_row or {}).get("基本每股盈餘（元）"))
    gross_margin = (gross_profit / revenue) if (gross_profit is not None and revenue) else None
    operating_margin = (operating_income / revenue) if (operating_income is not None and revenue) else None
    fiscal_year = base_row.get("年度")
    fiscal_period = base_row.get("季別")
    if fiscal_period:
        fiscal_period = f"Q{fiscal_period}"
    return FinancialReport(
        market="tw",
        ticker=ticker,
        company_name=str(base_row.get("公司名稱", "")).strip(),
        source_type="twse-openapi",
        source_confidence="official-openapi",
        form_type="TWSE-Q",
        fiscal_year=int(fiscal_year) if fiscal_year not in (None, "") else None,
        fiscal_period=str(fiscal_period or ""),
        period_end=str(base_row.get("出表日期", "")).strip(),
        filed_at=str(base_row.get("出表日期", "")).strip(),
        source_url=TW_INCOME_STATEMENT_URL,
        report_kind="quarterly",
        revenue=revenue,
        net_income=net_income,
        operating_income=operating_income,
        gross_profit=gross_profit,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        eps_diluted=eps_diluted,
        payload_json=json.dumps(
            {"income": income_row or {}, "balance": balance_row or {}},
            ensure_ascii=False,
        ),
    )


def refresh_tw_financial_reports(
    tickers: list[str],
    *,
    db_path: str | Path = DB_PATH,
    fetch_json: Callable[[str], Any] = _fetch_json,
) -> list[FinancialReport]:
    init_financial_report_store(db_path)
    monthly_rows = fetch_json(TW_MONTHLY_REVENUE_URL)
    income_rows = fetch_json(TW_INCOME_STATEMENT_URL)
    balance_rows = fetch_json(TW_BALANCE_SHEET_URL)
    reports: list[FinancialReport] = []
    for ticker in tickers:
        monthly_row = next(
            (row for row in monthly_rows if str(row.get("公司代號", "")).strip() == ticker),
            None,
        )
        if monthly_row:
            monthly_report = map_tw_monthly_revenue_row(monthly_row)
            save_financial_report(db_path, monthly_report)
            reports.append(monthly_report)
        quarterly_report = build_tw_quarterly_financial_report(
            ticker=ticker,
            income_rows=income_rows,
            balance_rows=balance_rows,
        )
        if quarterly_report:
            save_financial_report(db_path, quarterly_report)
            reports.append(quarterly_report)
    return reports


def refresh_tw_financial_reports_for_articles(
    all_articles: dict[str, list[Any]],
    *,
    max_issuers: int = TW_FINANCIAL_MAX_ISSUERS,
    refresh_fn: Callable[..., list[FinancialReport]] | None = None,
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
    fn = refresh_fn or refresh_tw_financial_reports
    return fn(candidates, db_path=db_path)
