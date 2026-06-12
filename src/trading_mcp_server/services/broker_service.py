"""Broker order safety layer — the ONLY path to a real order.

Flow for live orders:
  1. prepare_order()   -> validates, stores a pending order, returns approval token
  2. (human approves)
  3. execute_prepared_order(token) -> re-validates, places via the adapter

Guarantees:
  - TRADING_MODE=paper          -> never touches the broker; routes to paper engine
  - ALLOW_LIVE_TRADING=false    -> live execution impossible
  - DELIVERY SELL               -> hard-blocked unless ALLOW_DELIVERY_SELL=true
  - every action audited via log_trade_event
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from trading_mcp_server.config import get_config
from trading_mcp_server.services.order_validation_service import (
    DELIVERY_SELL_BLOCK_MESSAGE,
    validate_order,
)
from trading_mcp_server.services.paper_trading_service import get_paper_service
from trading_mcp_server.config import get_storage_dir
from trading_mcp_server.utils.logger import get_logger, log_trade_event

log = get_logger("broker_service")

# Overridable for tests; None -> resolved from TRADING_MCP_HOME at call time.
PENDING_ORDERS_FILE: Path | None = None


def _pending_file() -> Path:
    return PENDING_ORDERS_FILE if PENDING_ORDERS_FILE is not None else get_storage_dir() / "pending_orders.json"


def _load_pending() -> dict:
    path = _pending_file()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_pending(pending: dict) -> None:
    path = _pending_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pending, indent=2), encoding="utf-8")


def _delivery_sell_block(order: dict) -> dict:
    log_trade_event("delivery_sell_blocked", order)
    return {
        "status": "blocked",
        "reason": DELIVERY_SELL_BLOCK_MESSAGE,
        "recommendation_only": True,
        "order": order,
    }


def prepare_order(
    symbol: str,
    side: str,
    quantity: int,
    entry_price: float,
    stop_loss: float | None = None,
    target: float | None = None,
    product_type: str = "INTRADAY",
    order_type: str = "MARKET",
) -> dict:
    """Validate an order and stage it. Never executes anything.

    Paper mode: returns the validation result and tells the agent to use
    place_paper_order. Live mode: stages the order for approval.
    """
    cfg = get_config()
    order = {
        "symbol": symbol.upper(),
        "side": side.upper(),
        "quantity": int(quantity),
        "entry_price": float(entry_price),
        "stop_loss": stop_loss,
        "target": target,
        "product_type": product_type.upper(),
        "order_type": order_type.upper(),
    }

    if order["product_type"] == "DELIVERY" and order["side"] == "SELL" and not cfg.allow_delivery_sell:
        return _delivery_sell_block(order)

    validation = validate_order(order)
    # 'manual_approval' is expected to fail at the prepare stage — that's the point.
    hard_failures = [
        r for r in validation["blocking_reasons"] if not r.startswith("manual_approval")
    ]

    if cfg.is_paper:
        return {
            "status": "validated" if not hard_failures else "blocked",
            "mode": "paper",
            "validation": validation,
            "next_step": "Use place_paper_order to simulate this trade."
            if not hard_failures
            else "Resolve the blocking reasons before retrying.",
        }

    if hard_failures:
        log_trade_event("live_order_blocked", {**order, "reasons": hard_failures})
        return {"status": "blocked", "mode": "live", "validation": validation}

    token = f"APPROVE-{uuid.uuid4().hex[:12]}"
    pending = _load_pending()
    pending[token] = {**order, "prepared_at": datetime.now().isoformat(timespec="seconds")}
    _save_pending(pending)
    log_trade_event("live_order_prepared", {**order, "approval_token": token})
    return {
        "status": "prepared",
        "mode": "live",
        "approval_token": token,
        "validation": validation,
        "next_step": (
            "Show this order to the user and ask for explicit approval. Only after the "
            f"user confirms, call execute_intraday_order_after_validation or "
            f"execute_delivery_buy_after_validation with approval_token='{token}'."
        ),
    }


def execute_prepared_order(approval_token: str, expected_product: str | None = None) -> dict:
    """Execute a previously prepared + human-approved live order."""
    cfg = get_config()
    pending = _load_pending()
    order = pending.get(approval_token)
    if not order:
        return {"status": "rejected", "reason": f"No pending order for token '{approval_token}'"}

    if expected_product and order["product_type"] != expected_product.upper():
        return {
            "status": "rejected",
            "reason": f"Token belongs to a {order['product_type']} order, not {expected_product}",
        }

    # Re-check the hard gates at execution time — config may have changed.
    if not cfg.is_live:
        return {
            "status": "blocked",
            "reason": "Live trading is not enabled (TRADING_MODE must be 'live' AND "
            "ALLOW_LIVE_TRADING=true). The prepared order was NOT executed.",
        }
    if order["product_type"] == "DELIVERY" and order["side"] == "SELL" and not cfg.allow_delivery_sell:
        return _delivery_sell_block(order)

    validation = validate_order({**order, "manual_approval_token": approval_token})
    if not validation["approved"]:
        log_trade_event("live_order_blocked_at_execution", {**order, "validation": validation})
        return {"status": "blocked", "validation": validation}

    from trading_mcp_server.broker.smartapi_adapter import get_broker_adapter

    try:
        response = get_broker_adapter().place_order(
            ticker=order["symbol"],
            side=order["side"],
            quantity=order["quantity"],
            product_type=order["product_type"],
            order_type=order["order_type"],
            price=order["entry_price"] if order["order_type"] == "LIMIT" else 0,
        )
    except Exception as exc:
        log_trade_event("live_order_failed", {**order, "error": str(exc)})
        return {"status": "error", "reason": f"Broker rejected/failed: {exc}", "order": order}

    del pending[approval_token]
    _save_pending(pending)
    log_trade_event("live_order_executed", {**order, "broker_response": response})
    return {"status": "executed", "mode": "live", "order": order, "broker_response": response}


def list_pending_orders() -> dict:
    return _load_pending()


def cancel_pending_order(approval_token: str) -> dict:
    pending = _load_pending()
    if approval_token in pending:
        order = pending.pop(approval_token)
        _save_pending(pending)
        log_trade_event("pending_order_cancelled", order)
        return {"status": "cancelled", "order": order}
    return {"status": "not_found", "approval_token": approval_token}
