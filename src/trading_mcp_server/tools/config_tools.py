"""Config tools: read/update configuration and switch trading modes."""
from __future__ import annotations

from trading_mcp_server.config import get_config
from trading_mcp_server.services.order_validation_service import check_permissions
from trading_mcp_server.tools._common import make_tool


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def get_trading_config() -> dict:
        """Current trading configuration (secrets redacted). The single source of
        truth for mode, permissions and risk limits."""
        return get_config(reload=True).to_safe_dict()

    @tool
    def get_current_trading_mode() -> dict:
        """Effective trading mode. 'live' only when TRADING_MODE=live AND
        ALLOW_LIVE_TRADING=true."""
        cfg = get_config(reload=True)
        return {
            "trading_mode": cfg.trading_mode,
            "allow_live_trading": cfg.allow_live_trading,
            "effective_mode": "live" if cfg.is_live else "paper",
            "manual_approval_required_for_live": cfg.require_manual_approval_for_live_orders,
        }

    @tool
    def update_trading_config(updates: dict) -> dict:
        """Update runtime-updatable config keys in .env (risk limits, intraday/swing
        enable flags). Live-trading switches, ALLOW_DELIVERY_SELL and credentials
        can NOT be changed here — a human must edit .env."""
        applied = get_config().update_env_values(updates)
        return {"applied": applied, "config": get_config(reload=True).to_safe_dict()}

    @tool
    def switch_to_paper_mode() -> dict:
        """Set TRADING_MODE=paper (always safe)."""
        get_config().set_trading_mode("paper")
        return get_config(reload=True).to_safe_dict()

    @tool
    def switch_to_live_mode() -> dict:
        """Set TRADING_MODE=live. NOTE: real orders remain impossible until a human
        also sets ALLOW_LIVE_TRADING=true in .env."""
        get_config().set_trading_mode("live")
        cfg = get_config(reload=True)
        result = cfg.to_safe_dict()
        if not cfg.allow_live_trading:
            result["warning"] = (
                "TRADING_MODE is now 'live' but ALLOW_LIVE_TRADING=false, so the "
                "effective mode is still paper. A human must edit .env to enable real orders."
            )
        return result

    @tool
    def validate_trading_permissions(symbol: str, side: str, product_type: str) -> dict:
        """Check config permissions for a prospective order (no market/risk checks).
        side: BUY|SELL, product_type: INTRADAY|DELIVERY."""
        return check_permissions(
            {"symbol": symbol, "side": side, "product_type": product_type}
        ).to_dict()
