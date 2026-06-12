"""Built-in backtest strategies. Each returns a Series of signals per bar:
1 = enter/hold long, 0 = flat. The engine trades the transitions."""
from __future__ import annotations

import pandas as pd

from trading_mcp_server.services import indicator_service as ind


def ma_crossover(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    fast_ma = ind.sma(df["close"], fast)
    slow_ma = ind.sma(df["close"], slow)
    return (fast_ma > slow_ma).astype(int)


def rsi_reversal(df: pd.DataFrame, period: int = 14, oversold: int = 30, exit_level: int = 60) -> pd.Series:
    rsi = ind.rsi(df, period)
    signal = pd.Series(0, index=df.index)
    holding = False
    for i in range(len(df)):
        value = rsi.iloc[i]
        if not holding and value < oversold:
            holding = True
        elif holding and value > exit_level:
            holding = False
        signal.iloc[i] = int(holding)
    return signal


def macd_trend(df: pd.DataFrame) -> pd.Series:
    m = ind.macd(df)
    above_ema200 = df["close"] > ind.ema(df["close"], 200)
    return ((m["macd"] > m["signal"]) & above_ema200).astype(int)


def breakout_volume(df: pd.DataFrame, lookback: int = 20, volume_mult: float = 2.0) -> pd.Series:
    rolling_high = df["high"].rolling(lookback).max().shift(1)
    vol_ema = df["volume"].ewm(span=20, adjust=False).mean()
    entry = (df["close"] > rolling_high) & (df["volume"] > vol_ema * volume_mult)
    exit_ = df["close"] < ind.ema(df["close"], 20)
    signal = pd.Series(0, index=df.index)
    holding = False
    for i in range(len(df)):
        if not holding and bool(entry.iloc[i]):
            holding = True
        elif holding and bool(exit_.iloc[i]):
            holding = False
        signal.iloc[i] = int(holding)
    return signal


STRATEGIES = {
    "ma_crossover": ma_crossover,
    "rsi_reversal": rsi_reversal,
    "macd_trend": macd_trend,
    "breakout_volume": breakout_volume,
}
