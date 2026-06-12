"""Config loading, safe defaults, mode switching, runtime-update restrictions."""
import pytest

from trading_mcp_server import config as settings
from trading_mcp_server.config import TradingConfig


def test_defaults_are_safe(temp_env):
    cfg = TradingConfig.load(temp_env)  # no .env at all
    assert cfg.trading_mode == "paper"
    assert cfg.allow_live_trading is False
    assert cfg.allow_delivery_sell is False
    assert cfg.require_manual_approval_for_live_orders is True
    assert cfg.is_paper and not cfg.is_live


def test_invalid_mode_falls_back_to_paper(temp_env):
    temp_env.write_text("TRADING_MODE=yolo\n")
    assert TradingConfig.load(temp_env).trading_mode == "paper"


def test_live_requires_both_switches(temp_env):
    temp_env.write_text("TRADING_MODE=live\nALLOW_LIVE_TRADING=false\n")
    cfg = TradingConfig.load(temp_env)
    assert cfg.is_live is False  # master switch off -> still paper

    temp_env.write_text("TRADING_MODE=live\nALLOW_LIVE_TRADING=true\n")
    assert TradingConfig.load(temp_env).is_live is True


def test_switch_modes_persists(temp_env):
    cfg = TradingConfig.load(temp_env)
    cfg.set_trading_mode("live", temp_env)
    assert settings.load_env_file(temp_env)["TRADING_MODE"] == "live"
    cfg.set_trading_mode("paper", temp_env)
    assert settings.load_env_file(temp_env)["TRADING_MODE"] == "paper"
    with pytest.raises(ValueError):
        cfg.set_trading_mode("hybrid", temp_env)


def test_runtime_update_allows_risk_keys(temp_env):
    cfg = TradingConfig.load(temp_env)
    applied = cfg.update_env_values({"MAX_OPEN_POSITIONS": "3"}, temp_env)
    assert applied == ["MAX_OPEN_POSITIONS"]
    assert TradingConfig.load(temp_env).max_open_positions == 3


@pytest.mark.parametrize("key", ["ALLOW_LIVE_TRADING", "ALLOW_DELIVERY_SELL", "TRADING_MODE", "BROKER_API_KEY"])
def test_runtime_update_blocks_protected_keys(temp_env, key):
    cfg = TradingConfig.load(temp_env)
    with pytest.raises(PermissionError):
        cfg.update_env_values({key: "true"}, temp_env)


def test_secrets_redacted(temp_env):
    temp_env.write_text("BROKER_API_KEY=supersecret\n")
    safe = TradingConfig.load(temp_env).to_safe_dict()
    assert "supersecret" not in str(safe)
    assert safe["broker_api_key"] == "***set***"
