"""Permission gates and the full validation checklist — the safety core."""
from datetime import datetime

import pytest

from trading_mcp_server.services import order_validation_service as ovs
from trading_mcp_server.services.order_validation_service import check_permissions, validate_order


def _order(**overrides):
    base = {
        "symbol": "TCS", "side": "BUY", "quantity": 10, "entry_price": 100.0,
        "stop_loss": 95.0, "target": 110.0, "product_type": "INTRADAY",
    }
    base.update(overrides)
    return base


def _failed_checks(result: dict) -> set[str]:
    return {c["check"] for c in result["checks"] if not c["passed"]}


# ---------------- permission gates ----------------

def test_delivery_sell_blocked_by_default(temp_env, paper):
    result = check_permissions(_order(side="SELL", product_type="DELIVERY")).to_dict()
    assert result["approved"] is False
    assert any("Delivery sell is blocked" in r for r in result["blocking_reasons"])


def test_delivery_sell_allowed_only_when_configured(temp_env, paper):
    temp_env.write_text("ALLOW_DELIVERY_SELL=true\n")
    from trading_mcp_server.config import get_config
    get_config(reload=True)
    result = check_permissions(_order(side="SELL", product_type="DELIVERY")).to_dict()
    assert "delivery_sell_allowed" not in _failed_checks(result)


def test_delivery_buy_allowed_in_paper(temp_env, paper):
    result = check_permissions(_order(side="BUY", product_type="DELIVERY")).to_dict()
    assert result["approved"] is True


def test_live_mode_without_master_switch_blocks(temp_env, paper):
    temp_env.write_text("TRADING_MODE=live\nALLOW_LIVE_TRADING=false\n")
    from trading_mcp_server.config import get_config
    get_config(reload=True)
    result = check_permissions(_order()).to_dict()
    assert "live_trading_master_switch" in _failed_checks(result)


def test_live_mode_requires_credentials(temp_env, paper):
    temp_env.write_text("TRADING_MODE=live\nALLOW_LIVE_TRADING=true\n")
    from trading_mcp_server.config import get_config
    get_config(reload=True)
    result = check_permissions(_order()).to_dict()
    assert "broker_credentials_present" in _failed_checks(result)


@pytest.mark.parametrize("side,product,flag,check", [
    ("BUY", "INTRADAY", "ALLOW_INTRADAY_BUY", "intraday_buy_allowed"),
    ("SELL", "INTRADAY", "ALLOW_INTRADAY_SELL", "intraday_sell_allowed"),
    ("BUY", "DELIVERY", "ALLOW_DELIVERY_BUY", "delivery_buy_allowed"),
])
def test_per_action_live_permissions(temp_env, paper, side, product, flag, check):
    temp_env.write_text(f"TRADING_MODE=live\nALLOW_LIVE_TRADING=true\n{flag}=false\n")
    from trading_mcp_server.config import get_config
    get_config(reload=True)
    result = check_permissions(_order(side=side, product_type=product)).to_dict()
    assert check in _failed_checks(result)


def test_invalid_side_rejected(temp_env, paper):
    result = check_permissions(_order(side="SHORT")).to_dict()
    assert result["approved"] is False


# ---------------- full validation ----------------

def test_missing_stop_loss_blocks(temp_env, paper):
    result = validate_order(_order(stop_loss=None))
    assert "stop_loss_present" in _failed_checks(result)


def test_missing_target_blocks_entry(temp_env, paper):
    result = validate_order(_order(target=None))
    assert "target_present" in _failed_checks(result)


def test_poor_risk_reward_blocks(temp_env, paper):
    # risk 5, reward 2 -> rr 0.4 < default 1.5
    result = validate_order(_order(stop_loss=95.0, target=102.0))
    assert "risk_reward_acceptable" in _failed_checks(result)


def test_oversized_position_blocks(temp_env, paper):
    # 20% of 1,000,000 = 200,000 max; this is 500,000
    result = validate_order(_order(quantity=5000, entry_price=100.0, stop_loss=99.0, target=103.0))
    assert "position_size_ok" in _failed_checks(result)


def test_excess_risk_per_trade_blocks(temp_env, paper):
    # risk = 1500 * 10 = 15,000 > 1% of 1,000,000
    result = validate_order(_order(quantity=1500, entry_price=100.0, stop_loss=90.0, target=120.0))
    assert "risk_per_trade_ok" in _failed_checks(result)


def test_max_open_positions_blocks(temp_env, paper):
    temp_env.write_text("MAX_OPEN_POSITIONS=1\n")
    from trading_mcp_server.config import get_config
    get_config(reload=True)
    paper.place_order("INFY", "BUY", 1, 100.0, "DELIVERY")
    result = validate_order(_order())
    assert "max_open_positions_ok" in _failed_checks(result)


def test_daily_loss_limit_blocks(temp_env, paper):
    # Realize a loss beyond 2% of 1,000,000 (=20,000)
    paper.place_order("X", "BUY", 100, 1000.0, "INTRADAY")
    paper.place_order("X", "SELL", 100, 750.0, "INTRADAY")  # -25,000 today
    result = validate_order(_order())
    assert "daily_loss_limit_ok" in _failed_checks(result)


def test_market_closed_blocks(temp_env, paper, monkeypatch):
    from trading_mcp_server.utils import time_utils
    closed = datetime(2026, 6, 13, 20, 0)  # Saturday evening
    monkeypatch.setattr(
        ovs, "market_status", lambda: time_utils.market_status(closed)
    )
    result = validate_order(_order())
    assert "market_open" in _failed_checks(result)


def test_exit_of_existing_position_relaxes_entry_checks(temp_env, paper):
    paper.place_order("TCS", "BUY", 10, 100.0, "INTRADAY")
    result = validate_order(_order(side="SELL", stop_loss=99.0, target=None))
    assert "target_present" not in _failed_checks(result)
    assert "max_open_positions_ok" not in _failed_checks(result)
