"""Technical indicators on OHLCV DataFrames.

Pure-pandas implementations ported from legacy inidcators/ — Wilder RSI/ATR,
EMA, MACD, Bollinger, VWAP, volume spike — plus trend and support/resistance
detection. Every function takes a DataFrame with columns
open/high/low/close/volume and a DatetimeIndex.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    change = df["close"].diff()
    gain = change.clip(lower=0.0)
    loss = -change.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(df["close"], fast) - ema(df["close"], slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "histogram": line - sig})


def bollinger_bands(df: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std(ddof=0)
    return pd.DataFrame({"middle": mid, "upper": mid + num_std * std, "lower": mid - num_std * std})


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP (resets each calendar day — meaningful for intraday data)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical * df["volume"]
    grouped = pd.Series(df.index.date, index=df.index)
    return pv.groupby(grouped).cumsum() / df["volume"].groupby(grouped).cumsum()


def volume_analysis(df: pd.DataFrame, span: int = 20, spike_multiplier: float = 2.0) -> dict:
    vol_ema = df["volume"].ewm(span=span, adjust=False).mean()
    latest_vol = float(df["volume"].iloc[-1])
    latest_ema = float(vol_ema.iloc[-1])
    return {
        "latest_volume": latest_vol,
        "volume_ema": round(latest_ema, 2),
        "volume_ratio": round(latest_vol / latest_ema, 2) if latest_ema else None,
        "is_spike": bool(latest_vol > latest_ema * spike_multiplier),
        "avg_volume_20": round(float(df["volume"].tail(20).mean()), 2),
    }


def support_resistance(df: pd.DataFrame, window: int = 10, max_levels: int = 4) -> dict:
    """Swing-high/low pivots clustered into support and resistance levels."""
    highs, lows = df["high"], df["low"]
    pivot_highs = highs[(highs == highs.rolling(2 * window + 1, center=True).max())].dropna()
    pivot_lows = lows[(lows == lows.rolling(2 * window + 1, center=True).min())].dropna()
    last_close = float(df["close"].iloc[-1])

    def cluster(levels: list[float]) -> list[float]:
        out: list[float] = []
        for lv in sorted(levels):
            if out and abs(lv - out[-1]) / out[-1] < 0.01:  # merge within 1%
                out[-1] = (out[-1] + lv) / 2
            else:
                out.append(lv)
        return [round(x, 2) for x in out]

    supports = [lv for lv in cluster(pivot_lows.tolist()) if lv < last_close]
    resistances = [lv for lv in cluster(pivot_highs.tolist()) if lv > last_close]
    return {
        "last_close": round(last_close, 2),
        "support_levels": supports[-max_levels:],
        "resistance_levels": resistances[:max_levels],
    }


def detect_trend(df: pd.DataFrame) -> dict:
    """Trend via EMA stack + linear-regression slope of the last 50 closes."""
    closes = df["close"]
    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    tail = closes.tail(50)
    x = np.arange(len(tail))
    slope = float(np.polyfit(x, tail.values, 1)[0]) if len(tail) >= 2 else 0.0
    slope_pct = slope / float(tail.mean()) * 100 if float(tail.mean()) else 0.0

    last = -1
    if e20.iloc[last] > e50.iloc[last] > e200.iloc[last] and slope > 0:
        direction = "uptrend"
    elif e20.iloc[last] < e50.iloc[last] < e200.iloc[last] and slope < 0:
        direction = "downtrend"
    else:
        direction = "sideways"
    return {
        "direction": direction,
        "slope_pct_per_bar": round(slope_pct, 4),
        "ema20": round(float(e20.iloc[last]), 2),
        "ema50": round(float(e50.iloc[last]), 2),
        "ema200": round(float(e200.iloc[last]), 2),
        "close": round(float(closes.iloc[last]), 2),
    }


def indicator_snapshot(df: pd.DataFrame, interval: str = "ONE_DAY") -> dict:
    """Latest values of all standard indicators — the agent's one-call summary."""
    if len(df) < 30:
        return {"error": f"Not enough candles ({len(df)}) to compute indicators (need 30+)."}
    out: dict = {
        "close": round(float(df["close"].iloc[-1]), 2),
        "rsi_14": round(float(rsi(df).iloc[-1]), 2),
        "atr_14": round(float(atr(df).iloc[-1]), 2),
        "ema20": round(float(ema(df["close"], 20).iloc[-1]), 2),
        "ema50": round(float(ema(df["close"], 50).iloc[-1]), 2),
        "ema200": round(float(ema(df["close"], 200).iloc[-1]), 2),
        "sma20": round(float(sma(df["close"], 20).iloc[-1]), 2),
    }
    m = macd(df)
    out["macd"] = round(float(m["macd"].iloc[-1]), 2)
    out["macd_signal"] = round(float(m["signal"].iloc[-1]), 2)
    out["macd_histogram"] = round(float(m["histogram"].iloc[-1]), 2)
    bb = bollinger_bands(df)
    out["bollinger_upper"] = round(float(bb["upper"].iloc[-1]), 2)
    out["bollinger_lower"] = round(float(bb["lower"].iloc[-1]), 2)
    if interval != "ONE_DAY":
        out["vwap"] = round(float(vwap(df).iloc[-1]), 2)
    out["volume"] = volume_analysis(df)
    out["trend"] = detect_trend(df)
    return out
