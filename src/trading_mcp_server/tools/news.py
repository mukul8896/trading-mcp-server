"""News and sentiment tools."""
from __future__ import annotations

from trading_mcp_server.services import data_provider_service as data
from trading_mcp_server.tools._common import make_tool


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def fetch_latest_news(symbol: str) -> dict:
        """Latest news items for one symbol with per-item sentiment."""
        items = data.fetch_market_news(symbol=symbol)
        return {"symbol": symbol.upper(), "count": len(items), "news": items}

    @tool
    def fetch_market_news(category: str = "all", sentiment: str = "all") -> dict:
        """Broad market news. category: all|stock|sectoral|global; sentiment:
        all|positive|negative|neutral."""
        items = data.fetch_market_news(category=category, sentiment=sentiment)
        return {"count": len(items), "news": items[:40]}

    @tool
    def analyze_news_sentiment(symbol: str) -> dict:
        """Aggregate sentiment counts for a symbol's recent news. The agent should
        read the texts (fetch_latest_news) for nuance — this is just the tally."""
        items = data.fetch_market_news(symbol=symbol)
        tally = {"positive": 0, "negative": 0, "neutral": 0}
        for item in items:
            key = item.get("sentiment") or "neutral"
            tally[key if key in tally else "neutral"] += 1
        overall = max(tally, key=tally.get) if items else "no_news"
        return {"symbol": symbol.upper(), "items": len(items), "tally": tally, "overall": overall}
