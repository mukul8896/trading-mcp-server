"""MCP resources: read-only context documents the agent can load."""
from __future__ import annotations

import json

from trading_mcp_server.config import get_config

SAFETY_RULES = """\
# Trading safety rules (enforced by this MCP server)

1. Paper mode is the default. Real orders require TRADING_MODE=live AND
   ALLOW_LIVE_TRADING=true (the latter only editable by a human in .env).
2. Every order — paper or live — must pass the full validation checklist
   (validate_trade_against_risk_rules): permissions, market open, stop-loss
   present, target present, risk:reward >= minimum, position size, risk per
   trade, daily loss limit, max open positions.
3. Live orders additionally require a prepare -> human approval -> execute
   flow using an approval token. Never execute without explicit user consent.
4. DELIVERY SELL is blocked by configuration: the server only records a
   recommendation. It must never be executed automatically.
5. Intraday entries are refused after 15:15 IST (square-off window).
6. All order decisions are appended to storage/trade_logs.jsonl.
7. Nothing this system produces is financial advice.
"""


def register_all(mcp) -> None:
    @mcp.resource("trading://config")
    def trading_config() -> str:
        """Current trading configuration (secrets redacted)."""
        return json.dumps(get_config(reload=True).to_safe_dict(), indent=2)

    @mcp.resource("trading://safety-rules")
    def safety_rules() -> str:
        """The non-negotiable safety rules this server enforces."""
        return SAFETY_RULES
