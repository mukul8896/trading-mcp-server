"""Position sizing and risk-rule calculations driven by the central config."""
from __future__ import annotations

from trading_mcp_server.config import get_config


def calculate_position_size(
    capital: float, risk_percent: float, entry_price: float, stop_loss: float
) -> dict:
    """Quantity such that loss at stop equals risk_percent of capital."""
    if entry_price <= 0 or stop_loss <= 0:
        return {"error": "entry_price and stop_loss must be positive"}
    risk_per_share = abs(entry_price - stop_loss)
    if risk_per_share == 0:
        return {"error": "stop_loss must differ from entry_price"}
    risk_amount = capital * risk_percent / 100
    quantity = int(risk_amount / risk_per_share)

    cfg = get_config()
    max_position_value = capital * cfg.max_position_size_percent / 100
    capped_by_position_limit = quantity * entry_price > max_position_value
    if capped_by_position_limit:
        quantity = int(max_position_value / entry_price)

    return {
        "quantity": max(quantity, 0),
        "risk_amount": round(risk_amount, 2),
        "risk_per_share": round(risk_per_share, 2),
        "position_value": round(quantity * entry_price, 2),
        "capped_by_max_position_size": capped_by_position_limit,
        "max_position_value": round(max_position_value, 2),
    }


def calculate_stop_loss(entry_price: float, atr_value: float, side: str = "BUY", multiplier: float = 1.5) -> dict:
    """ATR-based stop suggestion."""
    offset = atr_value * multiplier
    stop = entry_price - offset if side.upper() == "BUY" else entry_price + offset
    return {
        "entry_price": entry_price,
        "suggested_stop_loss": round(stop, 2),
        "atr": atr_value,
        "atr_multiplier": multiplier,
        "side": side.upper(),
    }


def calculate_target_price(entry_price: float, stop_loss: float, risk_reward_ratio: float = 2.0) -> dict:
    risk = abs(entry_price - stop_loss)
    direction = 1 if entry_price > stop_loss else -1  # long if stop below entry
    target = entry_price + direction * risk * risk_reward_ratio
    return {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "risk_reward_ratio": risk_reward_ratio,
        "target_price": round(target, 2),
    }


def risk_reward_ratio(entry_price: float, stop_loss: float, target: float) -> float | None:
    risk = abs(entry_price - stop_loss)
    if risk == 0:
        return None
    return round(abs(target - entry_price) / risk, 2)


def check_max_daily_loss(todays_pnl: float, capital: float) -> dict:
    cfg = get_config()
    limit = capital * cfg.max_daily_loss_percent / 100
    breached = todays_pnl <= -limit
    return {
        "todays_realized_pnl": round(todays_pnl, 2),
        "max_daily_loss_amount": round(limit, 2),
        "max_daily_loss_percent": cfg.max_daily_loss_percent,
        "limit_breached": breached,
        "trading_allowed": not breached,
    }


def check_portfolio_concentration(positions: list[dict], capital: float) -> dict:
    """Per-symbol exposure as % of capital vs MAX_POSITION_SIZE_PERCENT."""
    cfg = get_config()
    exposures = []
    for pos in positions:
        value = pos["quantity"] * pos.get("avg_price", pos.get("averageprice", 0) or 0)
        pct = value / capital * 100 if capital else 0
        exposures.append(
            {
                "symbol": pos.get("symbol") or pos.get("tradingsymbol"),
                "value": round(value, 2),
                "percent_of_capital": round(pct, 2),
                "exceeds_limit": pct > cfg.max_position_size_percent,
            }
        )
    return {
        "max_position_size_percent": cfg.max_position_size_percent,
        "positions": exposures,
        "any_exceeds_limit": any(e["exceeds_limit"] for e in exposures),
    }
