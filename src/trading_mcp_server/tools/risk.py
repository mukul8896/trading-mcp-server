"""Risk-management tools."""
from __future__ import annotations

from trading_mcp_server.services import indicator_service as ind
from trading_mcp_server.services import risk_service as risk
from trading_mcp_server.services.order_validation_service import validate_order
from trading_mcp_server.services.paper_trading_service import get_paper_service
from trading_mcp_server.tools._common import fetch_df, make_tool


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def calculate_position_size(capital: float, risk_percent: float,
                                entry_price: float, stop_loss: float) -> dict:
        """Quantity so the stop-loss loss equals risk_percent of capital, capped by
        MAX_POSITION_SIZE_PERCENT."""
        return risk.calculate_position_size(capital, risk_percent, entry_price, stop_loss)

    @tool
    def calculate_stop_loss(symbol: str, side: str = "BUY", atr_multiplier: float = 1.5,
                            timeframe: str = "ONE_DAY") -> dict:
        """ATR-based stop-loss suggestion from current price."""
        df = fetch_df(symbol, timeframe)
        entry = float(df["close"].iloc[-1])
        atr_value = round(float(ind.atr(df).iloc[-1]), 2)
        return {"symbol": symbol.upper(),
                **risk.calculate_stop_loss(entry, atr_value, side, atr_multiplier)}

    @tool
    def calculate_target_price(entry_price: float, stop_loss: float,
                               risk_reward_ratio: float = 2.0) -> dict:
        """Target price for a desired risk:reward given entry and stop."""
        return risk.calculate_target_price(entry_price, stop_loss, risk_reward_ratio)

    @tool
    def check_max_daily_loss() -> dict:
        """Whether today's realized paper P&L has hit MAX_DAILY_LOSS_PERCENT."""
        paper = get_paper_service()
        return risk.check_max_daily_loss(paper.todays_realized_pnl(),
                                         paper.state["starting_capital"])

    @tool
    def check_portfolio_concentration() -> dict:
        """Concentration check across open paper positions."""
        paper = get_paper_service()
        return risk.check_portfolio_concentration(
            list(paper.state["positions"].values()), paper.state["starting_capital"]
        )

    @tool
    def validate_trade_against_risk_rules(
        symbol: str, side: str, quantity: int, entry_price: float,
        stop_loss: float | None = None, target: float | None = None,
        product_type: str = "INTRADAY",
    ) -> dict:
        """Full pre-trade validation checklist: permissions, market status, risk
        limits, stop/target presence, risk:reward, position size, daily loss, open
        positions. Run this BEFORE any paper or live order."""
        return validate_order({
            "symbol": symbol, "side": side, "quantity": quantity,
            "entry_price": entry_price, "stop_loss": stop_loss, "target": target,
            "product_type": product_type,
        })
