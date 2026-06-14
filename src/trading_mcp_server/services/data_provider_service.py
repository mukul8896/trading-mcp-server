"""Market data: historical candles, live prices, scanners, news.

Data comes from the broker API (Angel One) for candles/LTP, Chartink for
watchlist scans, and Tradient/NewsAPI for news. All functions return plain
JSON-serializable structures for MCP tools.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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

# NewsAPI has no country filter on /v2/everything, so we bias toward Indian
# market coverage by restricting to Indian financial-news domains.
INDIAN_NEWS_DOMAINS = [
    "economictimes.indiatimes.com",
    "moneycontrol.com",
    "livemint.com",
    "business-standard.com",
    "financialexpress.com",
    "thehindubusinessline.com",
    "ndtvprofit.com",
    "zeebiz.com",
    "businesstoday.in",
]

# Broad Indian-market query used when no specific search term is given, so the
# domain-restricted NewsAPI feed still returns macro/market news (vs. empty).
INDIAN_MARKET_QUERY = (
    "NSE OR BSE OR Nifty OR Sensex OR \"Indian stock market\" OR \"Indian economy\" "
    "OR FII OR DII OR RBI OR \"repo rate\" OR inflation OR GDP OR rupee"
)

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


def _fetch_tradient_news() -> list[dict]:
    """Raw Tradient news feed (list of article objects). Free, no key needed."""
    response = requests.get(TRADIENT_NEWS_URL, timeout=10)
    response.raise_for_status()
    return response.json().get("data", {}).get("latest_news", []) or []


def _normalize_news_item(item: dict) -> dict:
    """Flatten one raw Tradient article into the agent-facing shape."""
    news_obj = item.get("news_object") or {}
    metadata = item.get("metadata") or {}
    return {
        "symbol": (item.get("sm_symbol") or "").strip().upper(),
        "stock_name": item.get("stock_name") or "",
        "title": news_obj.get("title") or "",
        "text": news_obj.get("text") or "",
        "sentiment": (news_obj.get("overall_sentiment") or "neutral").lower(),
        "category": (item.get("category") or "").lower(),
        "sub_category": (item.get("sub_category") or "").lower(),
        "sector": metadata.get("sector_name") or "",
        "publish_date": item.get("publish_date"),
    }


def fetch_market_news(category: str = "all", sentiment: str = "all", symbol: str | None = None) -> list[dict]:
    """Latest Indian-market news from Tradient (free, no key needed).

    Filtering is permissive so real feed values match:
    - ``category`` matches against EITHER the article category (e.g. "companies")
      OR its sub_category (e.g. "earnings-financial-results", "corporate-actions").
    - ``symbol`` matches the exact ticker OR a substring of the company name,
      so common names ("RELIANCE") still hit even when the feed uses a variant.
    """
    results = []
    for item in _fetch_tradient_news():
        record = _normalize_news_item(item)
        if category != "all" and category.lower() not in (record["category"], record["sub_category"]):
            continue
        if sentiment != "all" and record["sentiment"] != sentiment.lower():
            continue
        if symbol:
            sym = symbol.strip().upper()
            if sym != record["symbol"] and sym not in record["stock_name"].upper():
                continue
        results.append(record)
    return results


def summarize_market_sentiment() -> dict:
    """Aggregate the whole news feed into an overall market mood + active themes.

    Returns sentiment tally/percentages, an overall mood label, the most active
    sub-category themes, and a few representative positive/negative headlines.
    """
    items = [_normalize_news_item(i) for i in _fetch_tradient_news()]
    total = len(items)
    tally = {"positive": 0, "negative": 0, "neutral": 0}
    themes: dict[str, int] = {}
    for record in items:
        key = record["sentiment"] if record["sentiment"] in tally else "neutral"
        tally[key] += 1
        sub = record["sub_category"] or "uncategorized"
        themes[sub] = themes.get(sub, 0) + 1

    def pct(n: int) -> float:
        return round(100 * n / total, 1) if total else 0.0

    top_themes = sorted(themes.items(), key=lambda kv: kv[1], reverse=True)[:5]
    headline = lambda r: {"symbol": r["symbol"], "title": r["title"], "sub_category": r["sub_category"]}
    return {
        "total_items": total,
        "tally": tally,
        "percent": {k: pct(v) for k, v in tally.items()},
        "overall_mood": _mood_from_tally(tally),
        "top_themes": [{"theme": t, "count": c} for t, c in top_themes],
        "top_positive": [headline(r) for r in items if r["sentiment"] == "positive"][:5],
        "top_negative": [headline(r) for r in items if r["sentiment"] == "negative"][:5],
    }


def summarize_sector_sentiment() -> dict:
    """Sentiment broken down by sector, derived from the Tradient feed's
    ``sector_name`` tags. Each sector gets a tally and a mood label, sorted by
    news volume — a quick read of which sectors are in the news and how."""
    items = [_normalize_news_item(i) for i in _fetch_tradient_news()]
    by_sector: dict[str, dict[str, int]] = {}
    for record in items:
        sector = record["sector"] or "Unknown"
        tally = by_sector.setdefault(sector, {"positive": 0, "negative": 0, "neutral": 0})
        key = record["sentiment"] if record["sentiment"] in tally else "neutral"
        tally[key] += 1

    sectors = [
        {
            "sector": sector,
            "items": sum(tally.values()),
            "tally": tally,
            "mood": _mood_from_tally(tally),
        }
        for sector, tally in by_sector.items()
    ]
    sectors.sort(key=lambda s: s["items"], reverse=True)
    return {"total_items": len(items), "sectors": sectors}


def _mood_from_tally(tally: dict) -> str:
    """Map a positive/negative/neutral tally to bullish|bearish|neutral|no_news."""
    if sum(tally.values()) == 0:
        return "no_news"
    if tally["positive"] > tally["negative"] * 1.5:
        return "bullish"
    if tally["negative"] > tally["positive"] * 1.5:
        return "bearish"
    return "neutral"


def fetch_article_text(url: str, max_chars: int = 4000) -> str:
    """Best-effort extraction of an article's body text (lazy bs4). Returns ""
    on any failure — never raises, so one bad URL can't break a batch fetch."""
    if not url:
        return ""
    try:
        from bs4 import BeautifulSoup

        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = "\n".join(p.get_text() for p in soup.find_all("p")).strip()
        return text[:max_chars]
    except Exception as exc:
        log.warning("Article fetch failed for %s: %s", url, exc)
        return ""


def fetch_newsapi_articles(
    query: str | None = None,
    days: int = 1,
    page_size: int = 20,
    full_text: bool = False,
    indian_only: bool = True,
) -> list[dict]:
    """Free-text news search via NewsAPI (newsapi.org). Requires NEWS_API_KEY.

    Returns raw articles (title, description, source, published_at, url, and
    optionally article_text). NewsAPI does NOT classify sentiment — the caller
    reads the text and judges. Best for stock-specific or thematic news that the
    Tradient feed doesn't cover.

    query: a search term (e.g. "Reliance Q1 results"). When omitted, a broad
    Indian-market query (INDIAN_MARKET_QUERY: NSE/BSE/Nifty/FII/GDP/RBI...) is
    used so the domain-restricted feed still returns macro/market news.
    indian_only (default True) restricts results to Indian financial-news
    domains (INDIAN_NEWS_DOMAINS), since /v2/everything has no country filter.
    Pass indian_only=False for global coverage.
    """
    api_key = get_config().news_api_key
    if not api_key:
        raise ValueError("NEWS_API_KEY is not configured; set it in your .env to use NewsAPI tools.")

    params = {
        "q": query or INDIAN_MARKET_QUERY,
        "language": "en",
        "from": (datetime.now(timezone.utc) - timedelta(days=max(days, 1))).strftime("%Y-%m-%d"),
        "sortBy": "publishedAt",
        "pageSize": min(max(page_size, 1), 100),
        "apiKey": api_key,
    }
    if indian_only:
        params["domains"] = ",".join(INDIAN_NEWS_DOMAINS)
    response = requests.get(NEWS_API_URL, params=params, timeout=15)
    payload = response.json()
    if payload.get("status") != "ok":
        # message is safe to surface; it never echoes the key
        raise RuntimeError(f"NewsAPI error: {payload.get('message') or payload.get('code') or 'unknown'}")

    articles = []
    for article in payload.get("articles", []):
        url = article.get("url")
        articles.append(
            {
                "title": article.get("title"),
                "description": article.get("description"),
                "source": (article.get("source") or {}).get("name"),
                "published_at": article.get("publishedAt"),
                "url": url,
                "article_text": fetch_article_text(url) if full_text else "",
            }
        )
    return articles
