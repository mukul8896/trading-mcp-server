"""Portfolio tools — mode-aware (paper portfolio vs broker account)."""
from __future__ import annotations

from trading_mcp_server.config import get_config
from trading_mcp_server.services import risk_service as risk
from trading_mcp_server.services.paper_trading_service import get_paper_service
from trading_mcp_server.tools._common import make_tool


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def fetch_portfolio() -> dict:
        """Portfolio for the EFFECTIVE mode: paper portfolio in paper mode, broker
        holdings+positions in live mode."""
        cfg = get_config(reload=True)
        if cfg.is_paper:
            return get_paper_service().get_portfolio()
        from trading_mcp_server.broker.smartapi_adapter import get_broker_adapter
        adapter = get_broker_adapter()
        return {"mode": "live", "holdings": adapter.get_holdings(),
                "positions": adapter.get_positions()}

    @tool
    def fetch_order_history() -> dict:
        """Order history for the effective mode (paper orders, or broker order book)."""
        cfg = get_config(reload=True)
        if cfg.is_paper:
            return {"mode": "paper", "orders": get_paper_service().get_orders()}
        from trading_mcp_server.broker.smartapi_adapter import get_broker_adapter
        return {"mode": "live", "orders": get_broker_adapter().get_order_book()}

    @tool
    def calculate_portfolio_exposure() -> dict:
        """Per-position exposure vs MAX_POSITION_SIZE_PERCENT (paper portfolio)."""
        paper = get_paper_service()
        positions = list(paper.state["positions"].values())
        return risk.check_portfolio_concentration(positions, paper.state["starting_capital"])

    @tool
    def calculate_unrealized_pnl(live_prices: dict | None = None) -> dict:
        """Paper portfolio P&L. Pass live_prices as {symbol: ltp} (e.g. from
        fetch_live_price) to include unrealized P&L."""
        return get_paper_service().get_portfolio(live_prices)
