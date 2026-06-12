"""Risk-management math and the backtest engine."""
from trading_mcp_server.backtest.engine import run_backtest
from trading_mcp_server.services import risk_service as risk
from tests.conftest import make_ohlcv


# ---------------- risk service ----------------

def test_position_size_basic(temp_env):
    # capital 100k, risk 1% = 1000; risk/share 10 -> 100 shares...
    # but 100 * 100 = 10,000 < 20% cap, so no capping
    result = risk.calculate_position_size(100_000, 1.0, 100.0, 90.0)
    assert result["quantity"] == 100
    assert result["capped_by_max_position_size"] is False


def test_position_size_capped(temp_env):
    # tight stop -> huge qty -> capped at 20% of capital
    result = risk.calculate_position_size(100_000, 1.0, 100.0, 99.9)
    assert result["capped_by_max_position_size"] is True
    assert result["quantity"] * 100.0 <= 20_000 + 100


def test_position_size_invalid_inputs(temp_env):
    assert "error" in risk.calculate_position_size(100_000, 1.0, 100.0, 100.0)
    assert "error" in risk.calculate_position_size(100_000, 1.0, 0, 90.0)


def test_target_price_long_and_short(temp_env):
    long = risk.calculate_target_price(100.0, 95.0, 2.0)
    assert long["target_price"] == 110.0
    short = risk.calculate_target_price(100.0, 105.0, 2.0)
    assert short["target_price"] == 90.0


def test_risk_reward(temp_env):
    assert risk.risk_reward_ratio(100, 95, 110) == 2.0
    assert risk.risk_reward_ratio(100, 100, 110) is None


def test_daily_loss_check(temp_env):
    ok = risk.check_max_daily_loss(-100, 100_000)  # limit 2% = 2000
    assert ok["trading_allowed"] is True
    breached = risk.check_max_daily_loss(-2500, 100_000)
    assert breached["limit_breached"] is True


# ---------------- backtest engine ----------------

def test_backtest_unknown_strategy(temp_env):
    assert "error" in run_backtest(make_ohlcv(), "nonexistent")


def test_backtest_insufficient_data(temp_env):
    assert "error" in run_backtest(make_ohlcv(bars=30), "ma_crossover")


def test_backtest_produces_metrics(temp_env):
    result = run_backtest(make_ohlcv(bars=400, trend=0.3), "ma_crossover")
    for key in ["num_trades", "win_rate_pct", "total_pnl", "max_drawdown_pct",
                "avg_pnl_per_trade", "profitable", "buy_and_hold_return_pct"]:
        assert key in result
    assert result["num_trades"] >= 1


def test_backtest_all_strategies_run(temp_env):
    df = make_ohlcv(bars=400, trend=0.2)
    for name in ["ma_crossover", "rsi_reversal", "macd_trend", "breakout_volume"]:
        result = run_backtest(df, name)
        assert "error" not in result, f"{name} failed"


def test_backtest_capital_conservation(temp_env):
    """final = initial + total_pnl (no money invented)."""
    result = run_backtest(make_ohlcv(bars=400), "ma_crossover", initial_capital=100_000)
    assert abs(result["final_capital"] - (100_000 + result["total_pnl"])) < 1.0
