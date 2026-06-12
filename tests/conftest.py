"""Shared fixtures: isolated home dir (env + storage) per test, synthetic OHLCV."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# make `tests.conftest` importable from test modules
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading_mcp_server import config as settings
from trading_mcp_server.services import paper_trading_service as pts


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    """Point TRADING_MCP_HOME at a temp dir and reset the config singleton."""
    monkeypatch.setenv("TRADING_MCP_HOME", str(tmp_path))
    settings._config = None
    yield tmp_path / ".env"
    settings._config = None


@pytest.fixture
def paper(tmp_path, temp_env):
    """Fresh paper trading service with isolated state file."""
    service = pts.PaperTradingService(state_file=tmp_path / "paper_state.json",
                                      starting_capital=1_000_000)
    pts._service = service
    yield service
    pts._service = None


def make_ohlcv(bars: int = 300, start_price: float = 100.0, trend: float = 0.1, seed: int = 7) -> pd.DataFrame:
    """Synthetic daily OHLCV with a mild uptrend."""
    rng = np.random.default_rng(seed)
    closes = start_price + np.cumsum(rng.normal(trend, 1.0, bars))
    closes = np.maximum(closes, 5.0)
    opens = np.concatenate([[start_price], closes[:-1]])
    highs = np.maximum(opens, closes) + rng.uniform(0, 1, bars)
    lows = np.minimum(opens, closes) - rng.uniform(0, 1, bars)
    volume = rng.integers(100_000, 1_000_000, bars).astype(float)
    index = pd.bdate_range(end="2026-06-12", periods=bars)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volume},
        index=index,
    )


@pytest.fixture
def ohlcv():
    return make_ohlcv()
