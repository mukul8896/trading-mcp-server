"""News and sentiment tools."""
from __future__ import annotations

from trading_mcp_server.services import data_provider_service as data
from trading_mcp_server.tools._common import make_tool


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def fetch_latest_news(symbol: str) -> dict:
        """Latest news items for one symbol with per-item sentiment. Matches the
        exact ticker OR a substring of the company name. The feed is the broad
        Indian-market stream (often small/mid-caps), so a given symbol may have no
        items right now — an empty list is a valid 'no recent news' answer."""
        items = data.fetch_market_news(symbol=symbol)
        return {"symbol": symbol.upper(), "count": len(items), "news": items}

    @tool
    def fetch_market_news(category: str = "all", sentiment: str = "all") -> dict:
        """Broad Indian-market news feed (Tradient, free).

        category: all | companies | <sub_category>, where sub_category is one of
          earnings-financial-results | corporate-actions | operational-updates |
          management-leadership | legal-compliance | product-launches-innovation |
          others. Matched against both category and sub_category.
        sentiment: all | positive | negative | neutral.

        Each item: symbol, stock_name, title, text, sentiment, category,
        sub_category, sector, publish_date (epoch ms)."""
        items = data.fetch_market_news(category=category, sentiment=sentiment)
        return {"count": len(items), "news": items[:40]}

    @tool
    def get_market_sentiment() -> dict:
        """Overall market sentiment and trends from the whole news feed. Returns a
        sentiment tally + percentages, an overall mood (bullish|bearish|neutral),
        the most active themes (sub-categories), and representative positive/
        negative headlines. Use this for a top-down read of market mood before
        drilling into a specific symbol."""
        return data.summarize_market_sentiment()

    @tool
    def get_sector_sentiment() -> dict:
        """Sentiment broken down by sector (from the Tradient feed). Returns each
        sector with a positive/negative/neutral tally and a mood label, sorted by
        news volume. Use to see which sectors are active and how the mood skews."""
        return data.summarize_sector_sentiment()

    @tool
    def fetch_news_articles(
        query: str = "", days: int = 1, full_text: bool = False, indian_only: bool = True
    ) -> dict:
        """Free-text news search via NewsAPI (newsapi.org). Requires NEWS_API_KEY
        in the env. Best for stock-specific or thematic news the Tradient feed
        misses (e.g. 'Reliance Q1 results', 'RBI rate decision'). Leave query
        empty for broad Indian-market news (NSE/BSE/Nifty/FII/GDP/RBI...) — useful
        for a general market read. NewsAPI provides NO sentiment label — read
        article_text to judge. Set full_text=True to also fetch each article's
        body (slower). days = lookback window in days (default 1). indian_only
        (default True) restricts results to Indian financial-news sources; set
        False for global coverage. Returns raw articles."""
        items = data.fetch_newsapi_articles(
            query=query or None, days=days, full_text=full_text, indian_only=indian_only
        )
        return {"query": query or "indian_market_default", "count": len(items), "articles": items}

    @tool
    def analyze_news_sentiment(symbol: str) -> dict:
        """Aggregate sentiment counts for a symbol's recent news. The agent should
        read the texts (fetch_latest_news) for nuance — this is just the tally.
        For a market-wide read use get_market_sentiment instead."""
        items = data.fetch_market_news(symbol=symbol)
        tally = {"positive": 0, "negative": 0, "neutral": 0}
        for item in items:
            key = item.get("sentiment") or "neutral"
            tally[key if key in tally else "neutral"] += 1
        overall = max(tally, key=tally.get) if items else "no_news"
        return {"symbol": symbol.upper(), "items": len(items), "tally": tally, "overall": overall}
