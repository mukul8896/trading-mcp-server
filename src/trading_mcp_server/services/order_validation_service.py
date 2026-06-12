"""Order validation — EVERY order (paper or live) passes through here.

validate_order() runs the full checklist and returns a structured result
listing every check with pass/fail. An order may proceed only when
result["approved"] is True. Blocking reasons are explicit so the agent can
explain them to the user.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from trading_mcp_server.config import TradingConfig, get_config
from trading_mcp_server.services import risk_service
from trading_mcp_server.services.paper_trading_service import get_paper_service
from trading_mcp_server.utils.logger import log_trade_event
from trading_mcp_server.utils.time_utils import is_near_square_off, market_status

VALID_SIDES = {"BUY", "SELL"}
VALID_PRODUCTS = {"INTRADAY", "DELIVERY"}

DELIVERY_SELL_BLOCK_MESSAGE = (
    "Delivery sell is blocked by configuration and requires manual verification. "
    "The system will only produce a sell recommendation/alert; place the order "
    "manually after verifying your holdings."
)


@dataclass
class ValidationResult:
    approved: bool = True
    checks: list[dict] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "passed": passed, "detail": detail})
        if not passed:
            self.approved = False
            self.blocking_reasons.append(f"{name}: {detail}" if detail else name)

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "blocking_reasons": self.blocking_reasons,
            "checks": self.checks,
        }


def check_permissions(order: dict, cfg: TradingConfig | None = None) -> ValidationResult:
    """Config-permission checks only (no market/risk state). Used by
    validate_trading_permissions tool and as the first stage of full validation."""
    cfg = cfg or get_config()
    result = ValidationResult()

    side = str(order.get("side", "")).upper()
    product = str(order.get("product_type", "")).upper()

    result.add("valid_side", side in VALID_SIDES, f"side must be BUY or SELL, got '{side}'")
    result.add(
        "valid_product_type",
        product in VALID_PRODUCTS,
        f"product_type must be INTRADAY or DELIVERY, got '{product}'",
    )
    if not result.approved:
        return result

    result.add(
        "trading_mode_configured",
        cfg.trading_mode in {"paper", "live"},
        f"TRADING_MODE='{cfg.trading_mode}' is invalid",
    )

    if product == "INTRADAY":
        result.add(
            "intraday_trading_enabled",
            cfg.enable_intraday_trading,
            "ENABLE_INTRADAY_TRADING is false",
        )
    else:
        result.add(
            "swing_trading_enabled",
            cfg.enable_swing_trading,
            "ENABLE_SWING_TRADING is false",
        )

    # Hard delivery-sell block applies in EVERY mode unless explicitly allowed.
    if product == "DELIVERY" and side == "SELL" and not cfg.allow_delivery_sell:
        result.add("delivery_sell_allowed", False, DELIVERY_SELL_BLOCK_MESSAGE)

    # Live-only permission gates
    if cfg.is_live:
        if product == "INTRADAY" and side == "BUY":
            result.add("intraday_buy_allowed", cfg.allow_intraday_buy, "ALLOW_INTRADAY_BUY is false")
        elif product == "INTRADAY" and side == "SELL":
            result.add("intraday_sell_allowed", cfg.allow_intraday_sell, "ALLOW_INTRADAY_SELL is false")
        elif product == "DELIVERY" and side == "BUY":
            result.add("delivery_buy_allowed", cfg.allow_delivery_buy, "ALLOW_DELIVERY_BUY is false")
        result.add(
            "broker_credentials_present",
            cfg.has_broker_credentials(),
            "Broker credentials missing in .env — cannot trade live",
        )
    elif cfg.trading_mode == "live" and not cfg.allow_live_trading:
        result.add(
            "live_trading_master_switch",
            False,
            "TRADING_MODE=live but ALLOW_LIVE_TRADING=false. Real orders are disabled; "
            "a human must set ALLOW_LIVE_TRADING=true in .env.",
        )

    return result


def validate_order(order: dict, capital: float | None = None) -> dict:
    """Full pre-trade checklist: permissions + market + risk + order quality.

    order = {symbol, side, quantity, entry_price, stop_loss, target,
             product_type, order_type?}
    """
    cfg = get_config()
    result = check_permissions(order, cfg)

    side = str(order.get("side", "")).upper()
    product = str(order.get("product_type", "")).upper()
    quantity = int(order.get("quantity") or 0)
    entry = float(order.get("entry_price") or 0)
    stop = order.get("stop_loss")
    target = order.get("target")

    # ---- order quality ----
    result.add("positive_quantity", quantity > 0, "quantity must be a positive integer")
    result.add("entry_price_present", entry > 0, "entry_price is required for validation")
    result.add(
        "stop_loss_present",
        stop is not None and float(stop) > 0,
        "Every trade must have a stop-loss",
    )
    is_exit = _is_position_exit(order, cfg)
    if not is_exit:
        # Entries need a target and acceptable risk:reward; exits don't.
        result.add(
            "target_present",
            target is not None and float(target) > 0,
            "Entry orders must define a target price",
        )
        if stop and target and entry:
            rr = risk_service.risk_reward_ratio(entry, float(stop), float(target))
            result.add(
                "risk_reward_acceptable",
                rr is not None and rr >= cfg.min_risk_reward_ratio,
                f"risk:reward {rr} is below minimum {cfg.min_risk_reward_ratio}",
            )

    # ---- market status ----
    status = market_status()
    result.add(
        "market_open",
        status["is_open"],
        f"Market is {status['status']} — orders can only be placed during market hours",
    )
    if product == "INTRADAY" and not is_exit:
        result.add(
            "before_square_off_window",
            not is_near_square_off(),
            "Past 15:15 IST — no new intraday entries; close open intraday positions",
        )

    # ---- risk rules (computed against paper or provided capital) ----
    paper = get_paper_service()
    capital = capital or paper.state["starting_capital"]

    daily = risk_service.check_max_daily_loss(paper.todays_realized_pnl(), capital)
    result.add(
        "daily_loss_limit_ok",
        daily["trading_allowed"],
        f"Daily loss limit reached ({daily['todays_realized_pnl']} vs -{daily['max_daily_loss_amount']})",
    )

    if not is_exit:
        result.add(
            "max_open_positions_ok",
            paper.open_position_count() < cfg.max_open_positions,
            f"Already at MAX_OPEN_POSITIONS={cfg.max_open_positions}",
        )

        position_value = quantity * entry
        max_value = capital * cfg.max_position_size_percent / 100
        result.add(
            "position_size_ok",
            position_value <= max_value,
            f"Position value {position_value:.2f} exceeds {cfg.max_position_size_percent}% of capital ({max_value:.2f})",
        )

        if stop and entry and quantity:
            risk_amount = abs(entry - float(stop)) * quantity
            max_risk = capital * cfg.max_risk_per_trade_percent / 100
            result.add(
                "risk_per_trade_ok",
                risk_amount <= max_risk,
                f"Risk {risk_amount:.2f} exceeds {cfg.max_risk_per_trade_percent}% of capital ({max_risk:.2f})",
            )

    # ---- manual approval requirement (live only) ----
    if cfg.is_live and cfg.require_manual_approval_for_live_orders:
        approved_manually = bool(order.get("manual_approval_token"))
        result.add(
            "manual_approval",
            approved_manually,
            "REQUIRE_MANUAL_APPROVAL_FOR_LIVE_ORDERS=true — prepare the order with "
            "prepare_order(), show it to the user, and execute only with the returned "
            "approval token after the user explicitly confirms.",
        )

    outcome = result.to_dict()
    outcome["effective_mode"] = "live" if cfg.is_live else "paper"
    outcome["order"] = {
        "symbol": order.get("symbol"), "side": side, "quantity": quantity,
        "entry_price": entry, "stop_loss": stop, "target": target, "product_type": product,
    }
    log_trade_event("order_validated", {"approved": outcome["approved"], **outcome["order"]})
    return outcome


def _is_position_exit(order: dict, cfg: TradingConfig) -> bool:
    """SELL of an existing long paper position counts as an exit (relaxed checks)."""
    if str(order.get("side", "")).upper() != "SELL":
        return False
    key = f"{str(order.get('symbol','')).upper()}:{str(order.get('product_type','')).upper()}"
    return key in get_paper_service().state["positions"]
