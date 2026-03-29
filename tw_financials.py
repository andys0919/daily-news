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
TW_INCOME_STATEMENT_URLS = [
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci", "source_type": "twse-openapi-listed-ci"},
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_basi", "source_type": "twse-openapi-listed-basi"},
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_bd", "source_type": "twse-openapi-listed-bd"},
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_fh", "source_type": "twse-openapi-listed-fh"},
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ins", "source_type": "twse-openapi-listed-ins"},
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_mim", "source_type": "twse-openapi-listed-mim"},
]
TW_BALANCE_SHEET_URLS = [
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ci", "source_type": "twse-openapi-listed-ci"},
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_basi", "source_type": "twse-openapi-listed-basi"},
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_bd", "source_type": "twse-openapi-listed-bd"},
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_fh", "source_type": "twse-openapi-listed-fh"},
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ins", "source_type": "twse-openapi-listed-ins"},
    {"url": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_mim", "source_type": "twse-openapi-listed-mim"},
]
TW_INCOME_STATEMENT_URL = TW_INCOME_STATEMENT_URLS[0]["url"]
TW_BALANCE_SHEET_URL = TW_BALANCE_SHEET_URLS[0]["url"]
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


def _first_float(row: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = _as_float(row.get(key))
        if value is not None:
            return value
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
    source_type: str = "twse-openapi-listed-ci",
    source_url: str = TW_INCOME_STATEMENT_URL,
) -> FinancialReport | None:
    income_row = next((row for row in income_rows if str(row.get("公司代號", "")).strip() == ticker), None)
    balance_row = next((row for row in balance_rows if str(row.get("公司代號", "")).strip() == ticker), None)
    if not income_row and not balance_row:
        return None
    base_row = income_row or balance_row or {}
    revenue = _first_float(
        income_row or {},
        ["營業收入", "收益", "收入", "利息淨收益"],
    )
    gross_profit = _first_float(
        income_row or {},
        ["營業毛利（毛損）淨額", "營業毛利（毛損）", "收益減除費損淨額"],
    )
    operating_income = _first_float(
        income_row or {},
        ["營業利益（損失）", "繼續營業單位稅前淨利（淨損）", "稅前淨利（淨損）"],
    )
    net_income = _first_float(
        income_row or {},
        [
            "淨利（淨損）歸屬於母公司業主",
            "繼續營業單位本期淨利（淨損）",
            "本期淨利（淨損）",
        ],
    )
    eps_diluted = _first_float(
        income_row or {},
        ["基本每股盈餘（元）", "每股盈餘（元）"],
    )
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
        source_type=source_type,
        source_confidence="official-openapi",
        form_type="TWSE-Q",
        fiscal_year=int(fiscal_year) if fiscal_year not in (None, "") else None,
        fiscal_period=str(fiscal_period or ""),
        period_end=str(base_row.get("出表日期", "")).strip(),
        filed_at=str(base_row.get("出表日期", "")).strip(),
        source_url=source_url,
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
    income_payloads = [
        {
            "config": config,
            "rows": fetch_json(config["url"]),
        }
        for config in TW_INCOME_STATEMENT_URLS
    ]
    balance_payloads = {
        config["source_type"]: fetch_json(config["url"]) for config in TW_BALANCE_SHEET_URLS
    }
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
        for payload in income_payloads:
            source_type = payload["config"]["source_type"]
            quarterly_report = build_tw_quarterly_financial_report(
                ticker=ticker,
                income_rows=payload["rows"],
                balance_rows=balance_payloads.get(source_type, []),
                source_type=source_type,
                source_url=payload["config"]["url"],
            )
            if not quarterly_report:
                continue
            save_financial_report(db_path, quarterly_report)
            reports.append(quarterly_report)
            break
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
