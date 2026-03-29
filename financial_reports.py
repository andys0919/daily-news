import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


DB_PATH = Path(__file__).parent / "data" / "news.db"


@dataclass
class FinancialReport:
    market: str
    ticker: str
    company_name: str
    cik: str = ""
    source_type: str = ""
    source_confidence: str = ""
    form_type: str = ""
    fiscal_year: int | None = None
    fiscal_period: str = ""
    period_end: str = ""
    filed_at: str = ""
    source_url: str = ""
    report_kind: str = "quarterly"
    revenue: float | None = None
    monthly_revenue: float | None = None
    net_income: float | None = None
    operating_income: float | None = None
    gross_profit: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    eps_diluted: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None
    payload_json: str = ""

    @property
    def report_id(self) -> str:
        raw = "|".join(
            [
                self.market,
                self.ticker.upper(),
                self.report_kind,
                self.form_type,
                str(self.fiscal_year or ""),
                self.fiscal_period,
                self.period_end,
                self.filed_at,
            ]
        )
        return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _connect(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def init_financial_report_store(db_path: str | Path = DB_PATH) -> None:
    conn = _connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS financial_reports (
            report_id TEXT PRIMARY KEY,
            market TEXT NOT NULL,
            ticker TEXT NOT NULL,
            company_name TEXT NOT NULL,
            cik TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT '',
            source_confidence TEXT NOT NULL DEFAULT '',
            form_type TEXT NOT NULL DEFAULT '',
            fiscal_year INTEGER,
            fiscal_period TEXT NOT NULL DEFAULT '',
            period_end TEXT NOT NULL DEFAULT '',
            filed_at TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            report_kind TEXT NOT NULL DEFAULT 'quarterly',
            revenue REAL,
            monthly_revenue REAL,
            net_income REAL,
            operating_income REAL,
            gross_profit REAL,
            gross_margin REAL,
            operating_margin REAL,
            eps_diluted REAL,
            operating_cash_flow REAL,
            capex REAL,
            free_cash_flow REAL,
            payload_json TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_financial_reports_lookup
        ON financial_reports(market, ticker, filed_at DESC)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sec_issuer_cache (
            ticker TEXT PRIMARY KEY,
            cik TEXT NOT NULL,
            company_name TEXT NOT NULL,
            cached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def cache_sec_issuer(
    db_path: str | Path,
    *,
    ticker: str,
    cik: str,
    company_name: str,
) -> None:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT OR REPLACE INTO sec_issuer_cache (ticker, cik, company_name, cached_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (ticker.upper(), cik, company_name),
    )
    conn.commit()
    conn.close()


def get_cached_sec_issuer(db_path: str | Path, ticker: str) -> dict[str, str] | None:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT ticker, cik, company_name FROM sec_issuer_cache WHERE ticker = ?",
        (ticker.upper(),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"ticker": row[0], "cik": row[1], "company_name": row[2]}


def save_financial_report(db_path: str | Path, report: FinancialReport) -> None:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT OR REPLACE INTO financial_reports (
            report_id, market, ticker, company_name, cik, source_type,
            source_confidence, form_type, fiscal_year, fiscal_period, period_end,
            filed_at, source_url, report_kind, revenue, monthly_revenue,
            net_income, operating_income, gross_profit, gross_margin,
            operating_margin, eps_diluted, operating_cash_flow, capex,
            free_cash_flow, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report.report_id,
            report.market,
            report.ticker.upper(),
            report.company_name,
            report.cik,
            report.source_type,
            report.source_confidence,
            report.form_type,
            report.fiscal_year,
            report.fiscal_period,
            report.period_end,
            report.filed_at,
            report.source_url,
            report.report_kind,
            report.revenue,
            report.monthly_revenue,
            report.net_income,
            report.operating_income,
            report.gross_profit,
            report.gross_margin,
            report.operating_margin,
            report.eps_diluted,
            report.operating_cash_flow,
            report.capex,
            report.free_cash_flow,
            report.payload_json,
        ),
    )
    conn.commit()
    conn.close()


def _row_to_financial_report(row: sqlite3.Row | tuple) -> FinancialReport:
    return FinancialReport(
        market=row[1],
        ticker=row[2],
        company_name=row[3],
        cik=row[4],
        source_type=row[5],
        source_confidence=row[6],
        form_type=row[7],
        fiscal_year=row[8],
        fiscal_period=row[9],
        period_end=row[10],
        filed_at=row[11],
        source_url=row[12],
        report_kind=row[13],
        revenue=row[14],
        monthly_revenue=row[15],
        net_income=row[16],
        operating_income=row[17],
        gross_profit=row[18],
        gross_margin=row[19],
        operating_margin=row[20],
        eps_diluted=row[21],
        operating_cash_flow=row[22],
        capex=row[23],
        free_cash_flow=row[24],
        payload_json=row[25] or "",
    )


def get_latest_financial_report(
    db_path: str | Path = DB_PATH, *, market: str, ticker: str
) -> FinancialReport | None:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    row = conn.execute(
        """
        SELECT report_id, market, ticker, company_name, cik, source_type,
               source_confidence, form_type, fiscal_year, fiscal_period,
               period_end, filed_at, source_url, report_kind, revenue,
               monthly_revenue, net_income, operating_income, gross_profit,
               gross_margin, operating_margin, eps_diluted, operating_cash_flow,
               capex, free_cash_flow, payload_json
          FROM financial_reports
         WHERE market = ? AND ticker = ?
         ORDER BY filed_at DESC, period_end DESC
         LIMIT 1
        """,
        (market, ticker.upper()),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_financial_report(row)


def _format_money(value: float | None, market: str) -> str:
    if value is None:
        return ""
    unit = "億美元" if market == "us" else "億元"
    return f"{value / 100_000_000:.1f} {unit}"


def format_financial_report_context(report: FinancialReport) -> str:
    label = "官方財報" if report.market == "us" else "台股財務資料"
    parts = [label]
    if report.form_type:
        parts.append(report.form_type)
    if report.fiscal_year and report.fiscal_period:
        parts.append(f"FY{report.fiscal_year} {report.fiscal_period}")
    if report.revenue is not None:
        parts.append(f"營收 {_format_money(report.revenue, report.market)}")
    elif report.monthly_revenue is not None:
        parts.append(f"月營收 {_format_money(report.monthly_revenue, report.market)}")
    if report.eps_diluted is not None:
        parts.append(f"EPS {report.eps_diluted:.2f}")
    if report.free_cash_flow is not None:
        parts.append(f"FCF {_format_money(report.free_cash_flow, report.market)}")
    return " | ".join(parts)
