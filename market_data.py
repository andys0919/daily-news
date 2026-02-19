"""市場數據模組 — 抓取大盤指數和市場情緒"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

CONFIG_PATH = Path(__file__).parent / "config.yaml"
MARKET_CACHE_PATH = Path(__file__).parent / "data" / "market_overview_cache.json"
TW_TZ = timezone(timedelta(hours=8))
MARKET_CACHE_TTL_SEC = max(0, int(os.getenv("MARKET_CACHE_TTL_SEC", "900")))

# 龍頭股名稱對照（避免額外 API 呼叫）
LEADER_NAMES = {
    # XLK 科技
    "NVDA": "NVIDIA", "AAPL": "Apple", "MSFT": "Microsoft",
    # XLF 金融
    "BRK-B": "Berkshire", "JPM": "JPMorgan", "V": "Visa",
    # XLV 醫療
    "LLY": "Eli Lilly", "JNJ": "J&J", "ABBV": "AbbVie",
    # XLE 能源
    "XOM": "ExxonMobil", "CVX": "Chevron", "COP": "ConocoPhilips",
    # XLI 工業
    "GE": "GE Aero", "CAT": "Caterpillar", "RTX": "RTX",
    # XLY 非必需消費
    "AMZN": "Amazon", "TSLA": "Tesla", "HD": "Home Depot",
    # XLC 通訊
    "META": "Meta", "GOOGL": "Alphabet", "NFLX": "Netflix",
    # XLU 公用事業
    "NEE": "NextEra", "SO": "Southern Co", "DUK": "Duke Energy",
    # XLRE 房地產
    "WELL": "Welltower", "PLD": "Prologis", "AMT": "AMT",
    # XLP 民生消費
    "WMT": "Walmart", "COST": "Costco", "PG": "P&G",
    # XLB 原物料
    "LIN": "Linde", "NEM": "Newmont", "FCX": "Freeport",
    # 台股
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科",
}


@dataclass
class LeaderStock:
    """產業龍頭個股"""
    symbol: str
    name: str           # 公司短名
    price: float
    change_pct: float
    week_pct: float
    ytd_pct: float


@dataclass
class IndexData:
    """大盤指數數據"""
    name: str
    symbol: str
    price: float
    change: float
    change_pct: float
    prev_close: float
    group: str = ""         # us, sector, tw_asia, europe, sentiment, forex
    week_pct: float = 0.0   # 近一週漲跌幅
    ytd_pct: float = 0.0    # 今年以來漲跌幅
    leaders: list = field(default_factory=list)  # list[LeaderStock]


@dataclass
class MarketOverview:
    """市場概覽"""
    indices: list[IndexData]
    timestamp: datetime
    fear_greed: str = "N/A"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_single(symbol: str) -> dict:
    """抓取單一指數數據，帶 retry 機制"""
    ticker = yf.Ticker(symbol)
    info = ticker.fast_info

    price = info.get("lastPrice", 0) or info.get("regularMarketPrice", 0)
    prev = info.get("previousClose", 0) or info.get("regularMarketPreviousClose", 0)

    if not (price and prev):
        # fallback: 用 history
        hist = ticker.history(period="2d")
        if len(hist) >= 2:
            price = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2]
        else:
            return {"price": 0, "prev": 0, "week_pct": 0, "ytd_pct": 0}

    # 抓近一週數據
    week_pct = 0.0
    try:
        hist_5d = ticker.history(period="5d")
        if len(hist_5d) >= 2:
            week_start = hist_5d["Close"].iloc[0]
            week_end = hist_5d["Close"].iloc[-1]
            week_pct = (week_end - week_start) / week_start * 100
    except Exception:
        pass

    # 抓 YTD 數據
    ytd_pct = 0.0
    try:
        hist_ytd = ticker.history(period="ytd")
        if len(hist_ytd) >= 2:
            ytd_start = hist_ytd["Close"].iloc[0]
            ytd_end = hist_ytd["Close"].iloc[-1]
            ytd_pct = (ytd_end - ytd_start) / ytd_start * 100
    except Exception:
        pass

    return {"price": price, "prev": prev, "week_pct": week_pct, "ytd_pct": ytd_pct}


def fetch_indices() -> list[IndexData]:
    """抓取所有設定的大盤指數"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    indices = []
    symbols_config = config["market"]["indices"]

    print("📈 抓取市場數據...")

    for sym_config in symbols_config:
        symbol = sym_config["symbol"]
        name = sym_config["name"]
        group = sym_config.get("group", "")

        try:
            data = _fetch_single(symbol)
            price = data["price"]
            prev = data["prev"]
            week_pct = data.get("week_pct", 0.0)
            ytd_pct = data.get("ytd_pct", 0.0)

            if price and prev:
                change = price - prev
                change_pct = (change / prev) * 100
            else:
                price = change = change_pct = prev = 0

            # 抓龍頭個股
            leader_list = []
            leader_symbols = sym_config.get("leaders", [])
            if leader_symbols:
                for ldr_sym in leader_symbols:
                    try:
                        ldr_data = _fetch_single(ldr_sym)
                        ldr_price = ldr_data["price"]
                        ldr_prev = ldr_data["prev"]
                        ldr_chg_pct = ((ldr_price - ldr_prev) / ldr_prev * 100) if ldr_prev else 0
                        ldr_name = LEADER_NAMES.get(ldr_sym, ldr_sym)
                        leader = LeaderStock(
                            symbol=ldr_sym,
                            name=ldr_name,
                            price=round(ldr_price, 2),
                            change_pct=round(ldr_chg_pct, 2),
                            week_pct=round(ldr_data.get("week_pct", 0), 2),
                            ytd_pct=round(ldr_data.get("ytd_pct", 0), 2),
                        )
                        leader_list.append(leader)
                        l_arrow = "🟢" if ldr_chg_pct >= 0 else "🔴"
                        print(f"    {l_arrow} {ldr_name} ({ldr_sym}): {ldr_price:,.2f} 日{ldr_chg_pct:+.2f}%")
                    except Exception as e:
                        print(f"    ⚠️ Leader {ldr_sym}: {e}")
                    time.sleep(0.3)

            idx = IndexData(
                name=name,
                symbol=symbol,
                price=round(price, 2),
                change=round(change, 2),
                change_pct=round(change_pct, 2),
                prev_close=round(prev, 2),
                group=group,
                week_pct=round(week_pct, 2),
                ytd_pct=round(ytd_pct, 2),
                leaders=leader_list,
            )
            indices.append(idx)
            arrow = "🟢" if change >= 0 else "🔴"
            print(f"  {arrow} {name}: {price:,.2f} (日{change_pct:+.2f}% | 週{week_pct:+.2f}% | YTD{ytd_pct:+.2f}%)")

        except Exception as e:
            print(f"  ⚠️ {name} ({symbol}): {e}")
            indices.append(
                IndexData(name=name, symbol=symbol, price=0, change=0, change_pct=0,
                          prev_close=0, group=group, week_pct=0, ytd_pct=0)
            )

        # 每次請求間隔 0.5 秒，避免 yfinance 429
        time.sleep(0.5)

    return indices


def _overview_to_dict(overview: MarketOverview) -> dict:
    return {
        "timestamp": overview.timestamp.isoformat(),
        "fear_greed": overview.fear_greed,
        "indices": [
            {
                "name": idx.name,
                "symbol": idx.symbol,
                "price": idx.price,
                "change": idx.change,
                "change_pct": idx.change_pct,
                "prev_close": idx.prev_close,
                "group": idx.group,
                "week_pct": idx.week_pct,
                "ytd_pct": idx.ytd_pct,
                "leaders": [
                    {
                        "symbol": leader.symbol,
                        "name": leader.name,
                        "price": leader.price,
                        "change_pct": leader.change_pct,
                        "week_pct": leader.week_pct,
                        "ytd_pct": leader.ytd_pct,
                    }
                    for leader in idx.leaders
                ],
            }
            for idx in overview.indices
        ],
    }


def _overview_from_dict(payload: dict) -> MarketOverview | None:
    try:
        ts_raw = str(payload.get("timestamp", ""))
        timestamp = datetime.fromisoformat(ts_raw)
        indices_payload = payload.get("indices", [])
        if not isinstance(indices_payload, list):
            return None

        indices: list[IndexData] = []
        for raw_idx in indices_payload:
            if not isinstance(raw_idx, dict):
                continue
            leaders_payload = raw_idx.get("leaders", [])
            leader_list: list[LeaderStock] = []
            if isinstance(leaders_payload, list):
                for raw_leader in leaders_payload:
                    if not isinstance(raw_leader, dict):
                        continue
                    leader_list.append(
                        LeaderStock(
                            symbol=str(raw_leader.get("symbol", "")),
                            name=str(raw_leader.get("name", "")),
                            price=float(raw_leader.get("price", 0.0) or 0.0),
                            change_pct=float(raw_leader.get("change_pct", 0.0) or 0.0),
                            week_pct=float(raw_leader.get("week_pct", 0.0) or 0.0),
                            ytd_pct=float(raw_leader.get("ytd_pct", 0.0) or 0.0),
                        )
                    )

            indices.append(
                IndexData(
                    name=str(raw_idx.get("name", "")),
                    symbol=str(raw_idx.get("symbol", "")),
                    price=float(raw_idx.get("price", 0.0) or 0.0),
                    change=float(raw_idx.get("change", 0.0) or 0.0),
                    change_pct=float(raw_idx.get("change_pct", 0.0) or 0.0),
                    prev_close=float(raw_idx.get("prev_close", 0.0) or 0.0),
                    group=str(raw_idx.get("group", "")),
                    week_pct=float(raw_idx.get("week_pct", 0.0) or 0.0),
                    ytd_pct=float(raw_idx.get("ytd_pct", 0.0) or 0.0),
                    leaders=leader_list,
                )
            )

        return MarketOverview(
            indices=indices,
            timestamp=timestamp,
            fear_greed=str(payload.get("fear_greed", "N/A")),
        )
    except Exception:
        return None


def _load_market_cache() -> MarketOverview | None:
    if MARKET_CACHE_TTL_SEC <= 0 or not MARKET_CACHE_PATH.exists():
        return None

    try:
        payload = json.loads(MARKET_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

    overview = _overview_from_dict(payload)
    if not overview:
        return None

    age_sec = (datetime.now(TW_TZ) - overview.timestamp).total_seconds()
    if age_sec < 0:
        return None
    if age_sec > MARKET_CACHE_TTL_SEC:
        return None

    print(f"♻️ 使用市場快取（{int(age_sec)} 秒前）")
    return overview


def _save_market_cache(overview: MarketOverview) -> None:
    if MARKET_CACHE_TTL_SEC <= 0:
        return

    try:
        MARKET_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        MARKET_CACHE_PATH.write_text(
            json.dumps(_overview_to_dict(overview), ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        # 快取失敗不應中斷主流程
        return


def get_market_overview() -> MarketOverview:
    """取得市場概覽"""
    cached = _load_market_cache()
    if cached:
        return cached

    indices = fetch_indices()
    overview = MarketOverview(
        indices=indices,
        timestamp=datetime.now(TW_TZ),
    )
    _save_market_cache(overview)
    return overview


if __name__ == "__main__":
    overview = get_market_overview()
    print(f"\n📊 市場概覽 — {overview.timestamp.strftime('%Y-%m-%d %H:%M')}")
    for idx in overview.indices:
        arrow = "↑" if idx.change >= 0 else "↓"
        group_tag = f"[{idx.group}]" if idx.group else ""
        print(f"  {group_tag} {idx.name}: {idx.price:,.2f} {arrow} 日{idx.change_pct:+.2f}% | 週{idx.week_pct:+.2f}% | YTD{idx.ytd_pct:+.2f}%")
