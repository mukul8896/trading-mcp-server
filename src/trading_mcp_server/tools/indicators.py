"""Technical indicator tools."""
from __future__ import annotations

from trading_mcp_server.services import indicator_service as ind
from trading_mcp_server.tools._common import fetch_df, make_tool


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def calculate_sma(symbol: str, period: int = 20, timeframe: str = "ONE_DAY") -> dict:
        """Simple moving average (latest value)."""
        df = fetch_df(symbol, timeframe)
        return {"symbol": symbol.upper(), "period": period,
                "sma": round(float(ind.sma(df["close"], period).iloc[-1]), 2)}

    @tool
    def calculate_ema(symbol: str, period: int = 20, timeframe: str = "ONE_DAY") -> dict:
        """Exponential moving average (latest value)."""
        df = fetch_df(symbol, timeframe)
        return {"symbol": symbol.upper(), "period": period,
                "ema": round(float(ind.ema(df["close"], period).iloc[-1]), 2)}

    @tool
    def calculate_rsi(symbol: str, period: int = 14, timeframe: str = "ONE_DAY") -> dict:
        """Wilder RSI (latest value)."""
        df = fetch_df(symbol, timeframe)
        return {"symbol": symbol.upper(), "period": period,
                "rsi": round(float(ind.rsi(df, period).iloc[-1]), 2)}

    @tool
    def calculate_macd(symbol: str, timeframe: str = "ONE_DAY") -> dict:
        """MACD line, signal and histogram (latest values)."""
        df = fetch_df(symbol, timeframe)
        m = ind.macd(df).iloc[-1]
        return {"symbol": symbol.upper(), "macd": round(float(m["macd"]), 2),
                "signal": round(float(m["signal"]), 2),
                "histogram": round(float(m["histogram"]), 2)}

    @tool
    def calculate_bollinger_bands(symbol: str, period: int = 20, timeframe: str = "ONE_DAY") -> dict:
        """Bollinger bands (latest values)."""
        df = fetch_df(symbol, timeframe)
        bb = ind.bollinger_bands(df, period).iloc[-1]
        return {"symbol": symbol.upper(), "period": period,
                "upper": round(float(bb["upper"]), 2),
                "middle": round(float(bb["middle"]), 2),
                "lower": round(float(bb["lower"]), 2)}

    @tool
    def calculate_atr(symbol: str, period: int = 14, timeframe: str = "ONE_DAY") -> dict:
        """Average True Range — useful for stop-loss placement."""
        df = fetch_df(symbol, timeframe)
        return {"symbol": symbol.upper(), "period": period,
                "atr": round(float(ind.atr(df, period).iloc[-1]), 2)}

    @tool
    def calculate_volume_analysis(symbol: str, timeframe: str = "ONE_DAY") -> dict:
        """Volume vs its EMA, spike detection, 20-bar average."""
        return {"symbol": symbol.upper(), **ind.volume_analysis(fetch_df(symbol, timeframe))}

    @tool
    def detect_support_resistance(symbol: str, timeframe: str = "ONE_DAY") -> dict:
        """Support/resistance levels from clustered swing pivots."""
        return {"symbol": symbol.upper(), **ind.support_resistance(fetch_df(symbol, timeframe))}

    @tool
    def detect_trend(symbol: str, timeframe: str = "ONE_DAY") -> dict:
        """Trend direction from EMA stack + regression slope."""
        return {"symbol": symbol.upper(), **ind.detect_trend(fetch_df(symbol, timeframe))}

    @tool
    def get_indicator_snapshot(symbol: str, timeframe: str = "ONE_DAY") -> dict:
        """All standard indicators in one call (RSI, EMAs, MACD, Bollinger, ATR,
        volume, trend, VWAP on intraday timeframes). Prefer this over many single calls."""
        return {"symbol": symbol.upper(), "timeframe": timeframe,
                **ind.indicator_snapshot(fetch_df(symbol, timeframe), timeframe)}
