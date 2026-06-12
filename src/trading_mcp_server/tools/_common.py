"""Shared helpers for tool modules."""
from __future__ import annotations

import functools
from typing import Any, Callable

from trading_mcp_server.services import data_provider_service as data
from trading_mcp_server.utils.logger import get_logger

log = get_logger("mcp_tools")


def make_tool(mcp) -> Callable:
    """Returns a decorator that registers fn as an MCP tool with uniform
    error handling (exceptions surface as {'error': ...} to the agent)."""

    def tool(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                log.exception("Tool %s failed", fn.__name__)
                return {"error": f"{type(exc).__name__}: {exc}"}

        return mcp.tool()(wrapper)

    return tool


def fetch_df(symbol: str, interval: str = "ONE_DAY", bars: int = 250):
    """Historical candles as a DataFrame — shared by indicator/strategy tools."""
    return data.fetch_historical_df(symbol, interval, num_intervals=bars)
