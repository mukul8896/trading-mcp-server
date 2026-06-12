"""Tool registration for the trading MCP server."""
from __future__ import annotations

from trading_mcp_server.tools import (
    broker,
    config_tools,
    indicators,
    market_data,
    news,
    paper_trading,
    portfolio,
    risk,
    strategy,
)

ALL_TOOL_MODULES = [
    config_tools,
    market_data,
    indicators,
    news,
    portfolio,
    risk,
    strategy,
    paper_trading,
    broker,
]


def register_all(mcp) -> None:
    for module in ALL_TOOL_MODULES:
        module.register(mcp)
