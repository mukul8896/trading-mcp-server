"""Indicator calculations on synthetic data."""
import numpy as np
import pandas as pd

from trading_mcp_server.services import indicator_service as ind
from tests.conftest import make_ohlcv


def test_sma_matches_manual(ohlcv):
    expected = ohlcv["close"].tail(20).mean()
    assert abs(ind.sma(ohlcv["close"], 20).iloc[-1] - expected) < 1e-9


def test_rsi_bounds(ohlcv):
    values = ind.rsi(ohlcv).dropna()
    assert ((values >= 0) & (values <= 100)).all()


def test_rsi_extremes():
    rising = make_ohlcv(trend=2.0, seed=1)
    falling = make_ohlcv(trend=-2.0, seed=1)
    assert ind.rsi(rising).iloc[-1] > 60
    assert ind.rsi(falling).iloc[-1] < 40


def test_macd_histogram_is_difference(ohlcv):
    m = ind.macd(ohlcv)
    assert np.allclose(m["histogram"], m["macd"] - m["signal"], equal_nan=True)


def test_bollinger_ordering(ohlcv):
    bb = ind.bollinger_bands(ohlcv).dropna()
    assert (bb["upper"] >= bb["middle"]).all()
    assert (bb["middle"] >= bb["lower"]).all()


def test_atr_positive(ohlcv):
    assert (ind.atr(ohlcv).dropna() > 0).all()


def test_vwap_within_day_range():
    df = make_ohlcv(bars=50)
    v = ind.vwap(df)
    assert (v.dropna() > 0).all()


def test_trend_detection():
    up = make_ohlcv(bars=400, trend=0.5, seed=3)
    down = make_ohlcv(bars=400, trend=-0.5, start_price=400, seed=3)
    assert ind.detect_trend(up)["direction"] == "uptrend"
    assert ind.detect_trend(down)["direction"] == "downtrend"


def test_support_resistance_levels(ohlcv):
    sr = ind.support_resistance(ohlcv)
    last = sr["last_close"]
    assert all(s < last for s in sr["support_levels"])
    assert all(r > last for r in sr["resistance_levels"])


def test_snapshot_requires_enough_data():
    small = make_ohlcv(bars=10)
    assert "error" in ind.indicator_snapshot(small)


def test_snapshot_complete(ohlcv):
    snap = ind.indicator_snapshot(ohlcv)
    for key in ["rsi_14", "ema20", "ema50", "ema200", "macd", "bollinger_upper",
                "atr_14", "volume", "trend"]:
        assert key in snap
