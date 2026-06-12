"""Broker tools — every path to a real order goes through the safety layer."""
from __future__ import annotations

from trading_mcp_server.services.broker_service import (
    cancel_pending_order,
    execute_prepared_order,
    list_pending_orders,
    prepare_order as _prepare_order,
)
from trading_mcp_server.services.order_validation_service import (
    DELIVERY_SELL_BLOCK_MESSAGE,
    validate_order,
)
from trading_mcp_server.tools._common import make_tool
from trading_mcp_server.utils.logger import log_trade_event


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def prepare_order(
        symbol: str, side: str, quantity: int, entry_price: float,
        stop_loss: float | None = None, target: float | None = None,
        product_type: str = "INTRADAY", order_type: str = "MARKET",
    ) -> dict:
        """Validate and STAGE an order. Never executes. In live mode returns an
        approval_token; the human must approve before execution. Delivery sells
        are blocked and returned as recommendation-only."""
        return _prepare_order(symbol, side, quantity, entry_price, stop_loss,
                              target, product_type, order_type)

    @tool
    def validate_order_before_execution(
        symbol: str, side: str, quantity: int, entry_price: float,
        stop_loss: float | None = None, target: float | None = None,
        product_type: str = "INTRADAY",
    ) -> dict:
        """Re-run the full validation checklist for an order without staging it."""
        return validate_order({
            "symbol": symbol, "side": side, "quantity": quantity,
            "entry_price": entry_price, "stop_loss": stop_loss, "target": target,
            "product_type": product_type,
        })

    @tool
    def execute_intraday_order_after_validation(approval_token: str) -> dict:
        """Execute a prepared INTRADAY live order. Only call after the human has
        explicitly approved the prepared order shown to them."""
        return execute_prepared_order(approval_token, expected_product="INTRADAY")

    @tool
    def execute_delivery_buy_after_validation(approval_token: str) -> dict:
        """Execute a prepared DELIVERY BUY live order. Only call after the human
        has explicitly approved. Delivery SELL can never be executed through this
        system."""
        pending = list_pending_orders().get(approval_token)
        if pending and pending.get("side") == "SELL":
            return {"status": "blocked", "reason": DELIVERY_SELL_BLOCK_MESSAGE}
        return execute_prepared_order(approval_token, expected_product="DELIVERY")

    @tool
    def block_delivery_sell_order(symbol: str, quantity: int, reason: str = "") -> dict:
        """Record a delivery-sell RECOMMENDATION. The order is never sent to the
        broker — delivery sells require manual verification by the user."""
        rec = {"symbol": symbol.upper(), "quantity": quantity, "side": "SELL",
               "product_type": "DELIVERY", "agent_reasoning": reason}
        log_trade_event("delivery_sell_recommendation", rec)
        return {"status": "blocked", "recommendation_recorded": True,
                "message": DELIVERY_SELL_BLOCK_MESSAGE, "recommendation": rec}

    @tool
    def list_pending_live_orders() -> dict:
        """Prepared live orders awaiting human approval."""
        return {"pending": list_pending_orders()}

    @tool
    def cancel_pending_live_order(approval_token: str) -> dict:
        """Cancel a prepared live order before execution."""
        return cancel_pending_order(approval_token)

    @tool
    def fetch_broker_funds() -> dict:
        """Available funds/margins from the broker (requires credentials)."""
        from trading_mcp_server.broker.smartapi_adapter import get_broker_adapter
        return get_broker_adapter().get_funds()

    @tool
    def fetch_broker_positions() -> dict:
        """Today's positions from the broker."""
        from trading_mcp_server.broker.smartapi_adapter import get_broker_adapter
        return {"positions": get_broker_adapter().get_positions()}

    @tool
    def fetch_broker_holdings() -> dict:
        """Delivery holdings from the broker."""
        from trading_mcp_server.broker.smartapi_adapter import get_broker_adapter
        return {"holdings": get_broker_adapter().get_holdings()}

    @tool
    def fetch_broker_order_status(order_id: str) -> dict:
        """Status of a broker order by id."""
        from trading_mcp_server.broker.smartapi_adapter import get_broker_adapter
        status = get_broker_adapter().get_order_status(order_id)
        return status or {"error": f"Order {order_id} not found in order book"}
