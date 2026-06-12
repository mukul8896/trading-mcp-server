"""Minimal long-only backtest engine over signal series (1=long, 0=flat).

Entries/exits execute at the NEXT bar's open to avoid look-ahead bias.
"""
from __future__ import annotations

import pandas as pd

from trading_mcp_server.backtest.strategies import STRATEGIES


def run_backtest(
    df: pd.DataFrame,
    strategy_name: str,
    initial_capital: float = 100_000.0,
    strategy_params: dict | None = None,
) -> dict:
    if strategy_name not in STRATEGIES:
        return {"error": f"Unknown strategy '{strategy_name}'. Available: {sorted(STRATEGIES)}"}
    if len(df) < 60:
        return {"error": f"Not enough candles ({len(df)}) — need at least 60."}

    signal = STRATEGIES[strategy_name](df, **(strategy_params or {}))

    trades: list[dict] = []
    in_position = False
    entry_price = 0.0
    entry_date = None
    quantity = 0
    cash = initial_capital

    for i in range(len(df) - 1):
        next_open = float(df["open"].iloc[i + 1])
        next_date = df.index[i + 1]
        want_long = bool(signal.iloc[i])

        if want_long and not in_position:
            quantity = int(cash // next_open)
            if quantity > 0:
                in_position = True
                entry_price = next_open
                entry_date = next_date
                cash -= quantity * next_open
        elif not want_long and in_position:
            cash += quantity * next_open
            trades.append(
                {
                    "entry_date": str(entry_date),
                    "exit_date": str(next_date),
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(next_open, 2),
                    "quantity": quantity,
                    "pnl": round((next_open - entry_price) * quantity, 2),
                    "return_pct": round((next_open / entry_price - 1) * 100, 2),
                }
            )
            in_position = False

    # Close any open position at the final close
    if in_position:
        last_close = float(df["close"].iloc[-1])
        cash += quantity * last_close
        trades.append(
            {
                "entry_date": str(entry_date),
                "exit_date": str(df.index[-1]),
                "entry_price": round(entry_price, 2),
                "exit_price": round(last_close, 2),
                "quantity": quantity,
                "pnl": round((last_close - entry_price) * quantity, 2),
                "return_pct": round((last_close / entry_price - 1) * 100, 2),
                "closed_at_end": True,
            }
        )

    return _metrics(trades, initial_capital, cash, strategy_name, df)


def _metrics(trades: list[dict], initial: float, final: float, strategy: str, df: pd.DataFrame) -> dict:
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    equity, peak, max_dd = initial, initial, 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100 if peak else 0)

    total_return_pct = (final / initial - 1) * 100
    buy_hold_pct = (float(df["close"].iloc[-1]) / float(df["close"].iloc[0]) - 1) * 100

    return {
        "strategy": strategy,
        "period": {"start": str(df.index[0]), "end": str(df.index[-1]), "bars": len(df)},
        "initial_capital": initial,
        "final_capital": round(final, 2),
        "total_return_pct": round(total_return_pct, 2),
        "buy_and_hold_return_pct": round(buy_hold_pct, 2),
        "num_trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else None,
        "total_pnl": round(sum(pnls), 2),
        "avg_pnl_per_trade": round(sum(pnls) / len(trades), 2) if trades else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) else None,
        "max_drawdown_pct": round(max_dd, 2),
        "profitable": total_return_pct > 0,
        "beats_buy_and_hold": total_return_pct > buy_hold_pct,
        "trades": trades[-20:],  # last 20 trades for inspection
    }
