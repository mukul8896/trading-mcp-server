"""Market data tools: prices, candles, market status, metadata, watchlist."""
from __future__ import annotations

from trading_mcp_server.services import data_provider_service as data
from trading_mcp_server.tools._common import make_tool
from trading_mcp_server.utils import time_utils
from trading_mcp_server.utils.instruments import symbol_metadata


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def fetch_live_price(symbol: str) -> dict:
        """Last traded price for an NSE symbol (requires broker credentials)."""
        return data.fetch_live_price(symbol)

    @tool
    def fetch_historical_data(
        symbol: str,
        timeframe: str = "ONE_DAY",
        start_date: str | None = None,
        end_date: str | None = None,
        max_rows: int = 100,
    ) -> dict:
        """Historical OHLCV candles. timeframe: ONE_MINUTE|FIVE_MINUTE|FIFTEEN_MINUTE|
        THIRTY_MINUTE|ONE_HOUR|ONE_DAY. Dates ISO format (optional)."""
        return data.fetch_historical_data(symbol, timeframe, start_date, end_date, max_rows)

    @tool
    def fetch_market_status(exchange: str = "NSE") -> dict:
        """Whether the market is open, pre-open or closed right now (IST)."""
        return time_utils.market_status()

    @tool
    def fetch_symbol_metadata(symbol: str) -> dict:
        """Instrument metadata: token, exchange, lot size, tick size."""
        meta = symbol_metadata(symbol)
        return meta or {"error": f"Symbol '{symbol}' not found in instrument master"}

    @tool
    def fetch_watchlist() -> dict:
        """Watchlist symbols: Chartink monthly-uptrend + RSI>50 scan, falling back
        to a static NIFTY list when the scan is unavailable."""
        return data.fetch_watchlist()
