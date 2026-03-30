import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


DB_PATH = Path(__file__).parent / "data" / "news.db"
_TW_QUARTER_RE = re.compile(r"(?P<year>\d{3,4})\s*Q(?P<quarter>[1-4])", re.IGNORECASE)


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
    guidance_summary: str = ""
    filing_excerpt: str = ""
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


@dataclass
class FinancialSnapshotBundle:
    market: str
    ticker: str
    company_name: str
    quarterly: FinancialReport | None = None
    monthly_revenue: FinancialReport | None = None


def _connect(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


_FINANCIAL_REPORT_EXTRA_COLUMNS = {
    "guidance_summary": "TEXT NOT NULL DEFAULT ''",
    "filing_excerpt": "TEXT NOT NULL DEFAULT ''",
}


def _ensure_financial_report_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(financial_reports)").fetchall()
    }
    for column_name, column_sql in _FINANCIAL_REPORT_EXTRA_COLUMNS.items():
        if column_name in existing_columns:
            continue
        conn.execute(
            f"ALTER TABLE financial_reports ADD COLUMN {column_name} {column_sql}"
        )


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
            guidance_summary TEXT NOT NULL DEFAULT '',
            filing_excerpt TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT ''
        )
        """
    )
    _ensure_financial_report_columns(conn)
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
            free_cash_flow, guidance_summary, filing_excerpt, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            report.guidance_summary,
            report.filing_excerpt,
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
        guidance_summary=row[25] or "",
        filing_excerpt=row[26] or "",
        payload_json=row[27] or "",
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
               capex, free_cash_flow, guidance_summary, filing_excerpt, payload_json
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


def _get_latest_financial_report_by_kind(
    db_path: str | Path, *, market: str, ticker: str, report_kind: str
) -> FinancialReport | None:
    init_financial_report_store(db_path)
    conn = _connect(db_path)
    rows = conn.execute(
        """
        SELECT report_id, market, ticker, company_name, cik, source_type,
               source_confidence, form_type, fiscal_year, fiscal_period,
               period_end, filed_at, source_url, report_kind, revenue,
               monthly_revenue, net_income, operating_income, gross_profit,
               gross_margin, operating_margin, eps_diluted, operating_cash_flow,
               capex, free_cash_flow, guidance_summary, filing_excerpt, payload_json
          FROM financial_reports
         WHERE market = ? AND ticker = ? AND report_kind = ?
         ORDER BY filed_at DESC, period_end DESC
        """,
        (market, ticker.upper(), report_kind),
    ).fetchall()
    conn.close()
    if not rows:
        return None
    reports = [_row_to_financial_report(row) for row in rows]
    if market == "tw" and report_kind == "quarterly":
        source_priority = {
            "mops-api": 3,
            "tpex-finance-report": 2,
            "twse-openapi-listed-ci": 1,
            "twse-openapi-listed-basi": 1,
            "twse-openapi-listed-bd": 1,
            "twse-openapi-listed-fh": 1,
            "twse-openapi-listed-ins": 1,
            "twse-openapi-listed-mim": 1,
        }

        def _normalize_tw_year(value: int | str | None) -> int:
            if value in (None, ""):
                return 0
            try:
                year = int(str(value).strip())
            except ValueError:
                return 0
            return year + 1911 if year < 1911 else year

        def _extract_tw_quarter_key(report: FinancialReport) -> tuple[int, int]:
            if report.fiscal_year is not None and report.fiscal_period.upper().startswith("Q"):
                try:
                    return _normalize_tw_year(report.fiscal_year), int(report.fiscal_period[1:])
                except ValueError:
                    pass
            for raw_value in (report.period_end, report.filed_at):
                match = _TW_QUARTER_RE.search(str(raw_value or ""))
                if match:
                    return (
                        _normalize_tw_year(match.group("year")),
                        int(match.group("quarter")),
                    )
            return _normalize_tw_year(report.fiscal_year), 0

        reports.sort(
            key=lambda report: (
                *_extract_tw_quarter_key(report),
                source_priority.get(report.source_type, 0),
                str(report.filed_at),
                str(report.period_end),
            ),
            reverse=True,
        )
    return reports[0]


def get_financial_snapshot_bundle(
    db_path: str | Path = DB_PATH, *, market: str, ticker: str
) -> FinancialSnapshotBundle | None:
    quarterly = _get_latest_financial_report_by_kind(
        db_path, market=market, ticker=ticker, report_kind="quarterly"
    )
    monthly = _get_latest_financial_report_by_kind(
        db_path, market=market, ticker=ticker, report_kind="monthly_revenue"
    )
    if not quarterly and not monthly:
        return None
    primary = quarterly or monthly
    assert primary is not None
    return FinancialSnapshotBundle(
        market=market,
        ticker=primary.ticker,
        company_name=primary.company_name,
        quarterly=quarterly,
        monthly_revenue=monthly,
    )


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


def format_financial_snapshot_bundle_context(bundle: FinancialSnapshotBundle) -> str:
    parts: list[str] = []
    if bundle.quarterly:
        quarterly = bundle.quarterly
        quarter_bits = ["官方財報" if bundle.market == "us" else "台股財務資料"]
        if quarterly.form_type:
            quarter_bits.append(quarterly.form_type)
        if quarterly.fiscal_year and quarterly.fiscal_period:
            quarter_bits.append(f"FY{quarterly.fiscal_year} {quarterly.fiscal_period}")
        if quarterly.revenue is not None:
            quarter_bits.append(f"營收 {_format_money(quarterly.revenue, bundle.market)}")
        if quarterly.eps_diluted is not None:
            quarter_bits.append(f"EPS {quarterly.eps_diluted:.2f}")
        if quarterly.free_cash_flow is not None:
            quarter_bits.append(f"FCF {_format_money(quarterly.free_cash_flow, bundle.market)}")
        parts.append(" | ".join(quarter_bits))
    if bundle.monthly_revenue and bundle.monthly_revenue.monthly_revenue is not None:
        monthly = bundle.monthly_revenue
        parts.append(
            f"{monthly.fiscal_period} 月營收 {_format_money(monthly.monthly_revenue, bundle.market)}"
        )
    if bundle.quarterly:
        if bundle.quarterly.guidance_summary:
            parts.append(bundle.quarterly.guidance_summary)
        if bundle.quarterly.filing_excerpt:
            parts.append(bundle.quarterly.filing_excerpt)
    return " ; ".join(parts)


def build_financial_highlight_entries(
    articles_by_category: dict[str, list[object]],
    *,
    db_path: str | Path = DB_PATH,
    max_entries: int = 4,
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for articles in articles_by_category.values():
        for article in articles:
            tickers = getattr(article, "tickers", []) or []
            if not tickers:
                continue
            raw_ticker = str(tickers[0]).replace(".TW", "").replace(".TWO", "").upper()
            market = "tw" if raw_ticker.isdigit() else "us"
            key = (market, raw_ticker)
            if key in seen:
                continue
            seen.add(key)
            bundle = get_financial_snapshot_bundle(db_path, market=market, ticker=raw_ticker)
            if not bundle:
                continue
            summary = format_financial_snapshot_bundle_context(bundle)
            if not summary:
                continue
            entries.append(
                {
                    "market": market,
                    "ticker": bundle.ticker,
                    "company_name": bundle.company_name or raw_ticker,
                    "summary": summary,
                }
            )
            if len(entries) >= max_entries:
                return entries
    return entries
