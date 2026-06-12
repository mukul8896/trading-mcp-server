"""Broker service: prepare/approve/execute flow and hard delivery-sell block.

No test here ever touches the real broker — that is itself the guarantee
being tested (paper mode + blocks must short-circuit before the adapter).
"""
import pytest

from trading_mcp_server.config import get_config
from trading_mcp_server.services import broker_service
from trading_mcp_server.services.broker_service import (
    cancel_pending_order,
    execute_prepared_order,
    list_pending_orders,
    prepare_order,
)


@pytest.fixture(autouse=True)
def pending_file(tmp_path, monkeypatch):
    monkeypatch.setattr(broker_service, "PENDING_ORDERS_FILE", tmp_path / "pending.json")


def test_delivery_sell_blocked_in_prepare(temp_env, paper):
    result = prepare_order("TCS", "SELL", 10, 100.0, stop_loss=95, product_type="DELIVERY")
    assert result["status"] == "blocked"
    assert result["recommendation_only"] is True
    assert "manual verification" in result["reason"]


def test_paper_mode_never_stages_live_orders(temp_env, paper):
    result = prepare_order("TCS", "BUY", 10, 100.0, stop_loss=95, target=110)
    assert result["mode"] == "paper"
    assert "approval_token" not in result
    assert list_pending_orders() == {}


def test_execute_with_unknown_token_rejected(temp_env, paper):
    result = execute_prepared_order("APPROVE-nope")
    assert result["status"] == "rejected"


def test_execute_blocked_when_not_live(temp_env, paper, monkeypatch):
    """Even a staged order must not execute if config reverted to paper."""
    broker_service._save_pending({
        "APPROVE-test": {"symbol": "TCS", "side": "BUY", "quantity": 1,
                         "entry_price": 100.0, "stop_loss": 95.0, "target": 110.0,
                         "product_type": "INTRADAY", "order_type": "MARKET"}
    })
    result = execute_prepared_order("APPROVE-test")
    assert result["status"] == "blocked"
    assert "NOT executed" in result["reason"]


def test_execute_delivery_sell_blocked_even_if_staged(temp_env, paper):
    """Defense in depth: a SELL+DELIVERY that somehow got staged is still blocked."""
    temp_env.write_text("TRADING_MODE=live\nALLOW_LIVE_TRADING=true\n")
    get_config(reload=True)
    broker_service._save_pending({
        "APPROVE-ds": {"symbol": "TCS", "side": "SELL", "quantity": 1,
                       "entry_price": 100.0, "stop_loss": 105.0, "target": 90.0,
                       "product_type": "DELIVERY", "order_type": "MARKET"}
    })
    result = execute_prepared_order("APPROVE-ds")
    assert result["status"] == "blocked"


def test_product_type_mismatch_rejected(temp_env, paper):
    broker_service._save_pending({
        "APPROVE-x": {"symbol": "TCS", "side": "BUY", "quantity": 1,
                      "entry_price": 100.0, "stop_loss": 95.0, "target": 110.0,
                      "product_type": "DELIVERY", "order_type": "MARKET"}
    })
    result = execute_prepared_order("APPROVE-x", expected_product="INTRADAY")
    assert result["status"] == "rejected"


def test_cancel_pending(temp_env, paper):
    broker_service._save_pending({"APPROVE-c": {"symbol": "TCS", "side": "BUY"}})
    assert cancel_pending_order("APPROVE-c")["status"] == "cancelled"
    assert list_pending_orders() == {}
