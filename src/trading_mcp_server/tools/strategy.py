"""Strategy tools: trade-setup evaluation, watchlist scans, backtesting."""
from __future__ import annotations

from trading_mcp_server.backtest.engine import run_backtest
from trading_mcp_server.config import get_config
from trading_mcp_server.services import data_provider_service as data
from trading_mcp_server.services import indicator_service as ind
from trading_mcp_server.services import risk_service as risk
from trading_mcp_server.services.paper_trading_service import get_paper_service
from trading_mcp_server.tools._common import fetch_df, make_tool


def _trade_setup(symbol: str, style: str) -> dict:
    """Shared evaluation: multi-timeframe snapshot + mechanical trade plan."""
    cfg = get_config()
    daily = ind.indicator_snapshot(fetch_df(symbol, "ONE_DAY"), "ONE_DAY")
    if "error" in daily:
        return {"symbol": symbol.upper(), **daily}
    setup: dict = {"symbol": symbol.upper(), "style": style, "daily": daily}

    if style == "intraday":
        setup["hourly"] = ind.indicator_snapshot(fetch_df(symbol, "ONE_HOUR", 150), "ONE_HOUR")
        setup["fifteen_minute"] = ind.indicator_snapshot(
            fetch_df(symbol, "FIFTEEN_MINUTE", 150), "FIFTEEN_MINUTE"
        )
        atr_value = setup["fifteen_minute"].get("atr_14") or daily["atr_14"]
        sl_mult, rr = 1.0, 1.5
    else:
        setup["support_resistance"] = ind.support_resistance(fetch_df(symbol, "ONE_DAY"))
        atr_value, sl_mult, rr = daily["atr_14"], 1.5, 2.0

    entry = daily["close"]
    stop = round(entry - atr_value * sl_mult, 2)
    target = risk.calculate_target_price(entry, stop, rr)["target_price"]
    sizing = risk.calculate_position_size(
        get_paper_service().state["starting_capital"],
        cfg.max_risk_per_trade_percent, entry, stop,
    )

    trend_dir = daily["trend"]["direction"]
    rsi_value = daily["rsi_14"]
    score = 0
    score += 30 if trend_dir == "uptrend" else (10 if trend_dir == "sideways" else 0)
    score += 25 if 45 <= rsi_value <= 65 else (10 if 35 <= rsi_value <= 70 else 0)
    score += 20 if daily["macd_histogram"] > 0 else 0
    score += 15 if daily["volume"]["volume_ratio"] and daily["volume"]["volume_ratio"] > 1 else 5
    score += 10 if entry > daily["ema50"] else 0

    setup["suggested_plan"] = {
        "direction": "BUY" if trend_dir != "downtrend" else "AVOID",
        "entry_price": entry,
        "stop_loss": stop,
        "target": target,
        "risk_reward_ratio": rr,
        "position_sizing": sizing,
        "confidence_score": score,
        "confidence": "high" if score >= 70 else ("medium" if score >= 50 else "low"),
        "note": (
            "Mechanical setup from indicators only. The agent must overlay news, "
            "market context and its own judgment, then run "
            "validate_trade_against_risk_rules before any order. Not financial advice."
        ),
    }
    return setup


def _scan_watchlist(style: str, max_symbols: int) -> dict:
    watchlist = data.fetch_watchlist()
    results = []
    for sym in watchlist["symbols"][:max_symbols]:
        try:
            setup = _trade_setup(sym, style)
            plan = setup.get("suggested_plan", {})
            results.append({
                "symbol": sym,
                "direction": plan.get("direction"),
                "confidence_score": plan.get("confidence_score", 0),
                "entry_price": plan.get("entry_price"),
                "stop_loss": plan.get("stop_loss"),
                "target": plan.get("target"),
            })
        except Exception as exc:
            results.append({"symbol": sym, "error": str(exc)})
    ranked = sorted(results, key=lambda r: r.get("confidence_score") or 0, reverse=True)
    return {"style": style, "source": watchlist["source"],
            "scanned": len(ranked), "results": ranked}


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def evaluate_intraday_trade_setup(symbol: str) -> dict:
        """Multi-timeframe (daily/1h/15m) intraday setup with a mechanical trade
        plan and confidence score."""
        return _trade_setup(symbol, "intraday")

    @tool
    def evaluate_swing_trade_setup(symbol: str) -> dict:
        """Daily-timeframe swing/delivery setup with support/resistance and a
        mechanical trade plan."""
        return _trade_setup(symbol, "swing")

    @tool
    def compare_multiple_symbols(symbols: list[str], timeframe: str = "ONE_DAY") -> dict:
        """Side-by-side indicator snapshots for up to 10 symbols."""
        out = {}
        for sym in symbols[:10]:
            try:
                out[sym.upper()] = ind.indicator_snapshot(fetch_df(sym, timeframe), timeframe)
            except Exception as exc:
                out[sym.upper()] = {"error": str(exc)}
        return {"timeframe": timeframe, "symbols": out}

    @tool
    def scan_watchlist_for_swing_opportunities(max_symbols: int = 8) -> dict:
        """Evaluate the watchlist for swing setups, ranked by confidence score."""
        return _scan_watchlist("swing", max_symbols)

    @tool
    def scan_watchlist_for_intraday_opportunities(max_symbols: int = 5) -> dict:
        """Evaluate the watchlist for intraday setups, ranked by confidence score.
        Slow: fetches three timeframes per symbol."""
        return _scan_watchlist("intraday", max_symbols)

    @tool
    def run_strategy_backtest(
        strategy_name: str, symbol: str, timeframe: str = "ONE_DAY",
        start_date: str | None = None, end_date: str | None = None,
        initial_capital: float = 100000,
    ) -> dict:
        """Backtest a built-in strategy (ma_crossover | rsi_reversal | macd_trend |
        breakout_volume) on historical data. Returns trades, win rate, P&L, drawdown."""
        from datetime import datetime
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None
        df = data.fetch_historical_df(symbol, timeframe, start, end, num_intervals=500)
        result = run_backtest(df, strategy_name, initial_capital)
        result["symbol"] = symbol.upper()
        return result
