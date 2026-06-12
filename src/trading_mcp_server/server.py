"""trading-mcp-server — local MCP server exposing safe trading tools.

Run (stdio transport):
    trading-mcp-server            # console script after pip install
    python -m trading_mcp_server.server

The server resolves its .env and storage/ from TRADING_MCP_HOME (or the
current working directory), so the same installed package serves any
trading project.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from trading_mcp_server import prompts, resources, tools
from trading_mcp_server.config import get_env_file, get_home_dir
from trading_mcp_server.utils.logger import get_logger

log = get_logger("trading_mcp_server")

INSTRUCTIONS = (
    "Local trading-agent toolbox (NSE / Angel One). SAFETY RULES: the system is "
    "paper-mode by default; never claim an order was executed unless a tool returned "
    "status='executed' or 'filled'; every trade needs a stop-loss and must pass "
    "validate_trade_against_risk_rules; delivery sells are blocked and may only be "
    "given as recommendations; live orders additionally require an approval token "
    "confirmed by the human. Always state the trading mode in your analysis, and "
    "always include a 'not financial advice' disclaimer."
)


def create_server() -> FastMCP:
    mcp = FastMCP("trading-agent", instructions=INSTRUCTIONS)
    tools.register_all(mcp)
    resources.register_all(mcp)
    prompts.register_all(mcp)
    return mcp


def main() -> None:
    log.info("Starting trading-mcp-server (home=%s, env=%s)", get_home_dir(), get_env_file())
    create_server().run()


if __name__ == "__main__":
    main()
