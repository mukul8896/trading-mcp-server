"""Paper trading tools — simulated orders and performance reporting."""
from __future__ import annotations

from trading_mcp_server.services import data_provider_service as data
from trading_mcp_server.services.order_validation_service import validate_order
from trading_mcp_server.services.paper_trading_service import get_paper_service
from trading_mcp_server.tools._common import make_tool


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def place_paper_order(
        symbol: str, side: str, quantity: int, price: float | None = None,
        order_type: str = "MARKET", product_type: str = "DELIVERY",
        stop_loss: float | None = None, target: float | None = None,
        strategy: str | None = None,
    ) -> dict:
        """Place a SIMULATED order in the paper account. If price is omitted the
        live LTP is used (requires broker credentials). The full validation
        checklist is enforced here too."""
        if price is None:
            price = data.fetch_live_price(symbol)["ltp"]
        validation = validate_order({
            "symbol": symbol, "side": side, "quantity": quantity,
            "entry_price": price, "stop_loss": stop_loss, "target": target,
            "product_type": product_type,
        })
        if not validation["approved"]:
            return {"status": "blocked", "simulated": True, "validation": validation}
        order = get_paper_service().place_order(
            symbol, side, quantity, price, product_type, order_type,
            stop_loss, target, strategy,
        )
        return {**order, "validation": {"approved": True}}

    @tool
    def close_paper_position(symbol: str, product_type: str = "DELIVERY",
                             price: float | None = None) -> dict:
        """Close an open paper position at the given price (or live LTP)."""
        if price is None:
            price = data.fetch_live_price(symbol)["ltp"]
        return get_paper_service().close_position(symbol, price, product_type)

    @tool
    def fetch_paper_trades(product_type: str | None = None) -> dict:
        """Closed paper trades, optionally filtered by INTRADAY or DELIVERY."""
        trades = get_paper_service().get_trades(product_type)
        return {"count": len(trades), "trades": trades}

    @tool
    def fetch_paper_portfolio() -> dict:
        """Paper account: cash, open positions, realized P&L."""
        return get_paper_service().get_portfolio()

    @tool
    def calculate_paper_trading_performance() -> dict:
        """Performance metrics: win rate, P&L, drawdown — overall, per product type,
        and per strategy. Use this to judge profitability before considering live mode."""
        return get_paper_service().performance_report()

    @tool
    def generate_paper_trading_report() -> dict:
        """Full paper-trading report (performance + portfolio + recent trades)."""
        service = get_paper_service()
        report = service.performance_report()
        report["recent_trades"] = service.get_trades()[-15:]
        report["disclaimer"] = (
            "Simulated results. Past performance does not guarantee future results."
        )
        return report

    @tool
    def reset_paper_account(confirm: bool = False) -> dict:
        """Reset the paper account to starting capital, erasing simulated history.
        Requires confirm=true."""
        if not confirm:
            return {"status": "not_reset",
                    "reason": "Pass confirm=true to reset (destructive for paper history)."}
        return get_paper_service().reset()
