"""Market data: historical candles, live prices, scanners, news.

Data comes from the broker API (Angel One) for candles/LTP, Chartink for
watchlist scans, and Tradient/NewsAPI for news. All functions return plain
JSON-serializable structures for MCP tools.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import requests

from trading_mcp_server.broker.smartapi_adapter import get_broker_adapter
from trading_mcp_server.config import get_config
from trading_mcp_server.utils.logger import get_logger
from trading_mcp_server.utils.time_utils import get_start_date

log = get_logger("data_provider")

CHARTINK_SCAN_URL = "https://chartink.com/screener/process"
TRADIENT_NEWS_URL = "https://api.tradient.org/v1/api/market/news"
NEWS_API_URL = "https://newsapi.org/v2/everything"

# Default watchlist scan: monthly uptrend + daily RSI > 50 (from legacy chartink_queries)
MONTHLY_SWING_RSI_50_QUERY = {
    "scan_clause": "( {57960} ( monthly high > 1 month ago high and 1 month ago high > "
    "2 months ago high and 2 months ago high > 3 months ago high and monthly low > "
    "1 month ago low and 1 month ago low > 2 months ago low and 2 months ago low > "
    "3 months ago low and monthly close > 1 month ago close and 1 month ago close > "
    "2 months ago close and 2 months ago close > 3 months ago close and monthly close > "
    "monthly high * 0.618 and daily rsi( 14 ) > 50 ) )"
}

STATIC_WATCHLIST = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
]


def fetch_live_price(symbol: str) -> dict:
    ltp = get_broker_adapter().get_ltp(symbol.upper())
    return {
        "symbol": symbol.upper(),
        "ltp": ltp,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def fetch_historical_df(
    symbol: str,
    interval: str = "ONE_DAY",
    start: datetime | None = None,
    end: datetime | None = None,
    num_intervals: int = 250,
) -> pd.DataFrame:
    """Historical OHLCV as DataFrame indexed by datetime (paginates broker API)."""
    adapter = get_broker_adapter()
    end = end or datetime.now()
    start = start or get_start_date(interval, num_intervals, now=end)

    frames: list[pd.DataFrame] = []
    cursor_end = end
    while start < cursor_end:
        rows = adapter.get_candle_data(symbol.upper(), start, cursor_end, interval)
        if not rows:
            break
        chunk = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        frames.append(chunk)
        if len(rows) <= 1:
            break
        cursor_end = datetime.strptime(chunk["date"].iloc[0][:16], "%Y-%m-%dT%H:%M")

    if not frames:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.concat(frames)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.drop_duplicates(subset="date").set_index("date").sort_index()
    return df.astype(float)


def fetch_historical_data(
    symbol: str,
    interval: str = "ONE_DAY",
    start_date: str | None = None,
    end_date: str | None = None,
    max_rows: int = 250,
) -> dict:
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None
    df = fetch_historical_df(symbol, interval, start, end)
    df = df.tail(max_rows).round(2)
    records = [
        {"date": idx.isoformat(), **row}
        for idx, row in zip(df.index, df.to_dict(orient="records"))
    ]
    return {"symbol": symbol.upper(), "interval": interval, "candles": records}


def chartink_scan(query: dict | None = None) -> list[dict]:
    """Run a Chartink screener query, return [{'tradingsymbol': ...}, ...]."""
    from bs4 import BeautifulSoup

    query = query or MONTHLY_SWING_RSI_50_QUERY
    with requests.session() as s:
        page = s.get(CHARTINK_SCAN_URL, timeout=15)
        soup = BeautifulSoup(page.content, "lxml")
        token = soup.find("meta", {"name": "csrf-token"})["content"]
        data = s.post(CHARTINK_SCAN_URL, headers={"x-csrf-token": token}, data=query, timeout=30).json()
    rows = data.get("data") or []
    return [{"tradingsymbol": r["nsecode"]} for r in rows if r.get("nsecode")]


def fetch_watchlist() -> dict:
    """Dynamic Chartink momentum scan, with a static NIFTY fallback."""
    try:
        scanned = [s["tradingsymbol"] for s in chartink_scan()]
        if scanned:
            return {"source": "chartink_monthly_swing_rsi50", "symbols": scanned}
    except Exception as exc:
        log.warning("Chartink scan failed: %s", exc)
    return {"source": "static_nifty", "symbols": STATIC_WATCHLIST}


def fetch_market_news(category: str = "all", sentiment: str = "all", symbol: str | None = None) -> list[dict]:
    """Latest market news from Tradient (free, no key needed)."""
    response = requests.get(TRADIENT_NEWS_URL, timeout=10)
    response.raise_for_status()
    items = response.json().get("data", {}).get("latest_news", [])

    results = []
    for item in items:
        news_obj = item.get("news_object") or {}
        item_sentiment = (news_obj.get("overall_sentiment") or "").lower()
        item_category = (item.get("category") or "").lower()
        item_symbol = (item.get("sm_symbol") or "").strip().upper()
        if category != "all" and item_category != category.lower():
            continue
        if sentiment != "all" and item_sentiment != sentiment.lower():
            continue
        if symbol and item_symbol != symbol.upper():
            continue
        results.append(
            {
                "symbol": item_symbol,
                "text": news_obj.get("text") or "",
                "sentiment": item_sentiment,
                "category": item_category,
            }
        )
    return results
