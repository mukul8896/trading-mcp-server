"""Paper trading engine: fills, position math, P&L, performance, persistence."""
from trading_mcp_server.services.paper_trading_service import PaperTradingService


def test_buy_then_sell_realizes_pnl(paper):
    buy = paper.place_order("TCS", "BUY", 10, 100.0, "DELIVERY", stop_loss=95, target=110)
    assert buy["status"] == "filled" and buy["simulated"] is True
    assert paper.state["cash"] == 1_000_000 - 1000

    sell = paper.place_order("TCS", "SELL", 10, 110.0, "DELIVERY")
    assert sell["status"] == "filled"
    assert paper.state["cash"] == 1_000_000 + 100
    assert paper.get_trades()[0]["pnl"] == 100.0
    assert paper.open_position_count() == 0


def test_averaging_up(paper):
    paper.place_order("INFY", "BUY", 10, 100.0, "DELIVERY")
    paper.place_order("INFY", "BUY", 10, 120.0, "DELIVERY")
    pos = paper.state["positions"]["INFY:DELIVERY"]
    assert pos["quantity"] == 20 and pos["avg_price"] == 110.0


def test_cannot_sell_more_than_held(paper):
    paper.place_order("SBIN", "BUY", 5, 50.0, "DELIVERY")
    result = paper.place_order("SBIN", "SELL", 10, 55.0, "DELIVERY")
    assert result["status"] == "rejected"
    assert "Short selling" in result["reason"]


def test_cannot_overspend_cash(paper):
    result = paper.place_order("RELIANCE", "BUY", 1_000_000, 100.0, "DELIVERY")
    assert result["status"] == "rejected"
    assert "Insufficient" in result["reason"]


def test_intraday_and_delivery_tracked_separately(paper):
    paper.place_order("TCS", "BUY", 5, 100.0, "INTRADAY")
    paper.place_order("TCS", "BUY", 5, 100.0, "DELIVERY")
    assert paper.open_position_count() == 2
    paper.place_order("TCS", "SELL", 5, 105.0, "INTRADAY")
    assert len(paper.get_trades("INTRADAY")) == 1
    assert len(paper.get_trades("DELIVERY")) == 0


def test_performance_report(paper):
    paper.place_order("A", "BUY", 10, 100.0, "INTRADAY", strategy="ma_crossover")
    paper.place_order("A", "SELL", 10, 110.0, "INTRADAY")
    paper.place_order("B", "BUY", 10, 100.0, "DELIVERY", strategy="rsi_reversal")
    paper.place_order("B", "SELL", 10, 95.0, "DELIVERY")

    report = paper.performance_report()
    assert report["overall"]["trades"] == 2
    assert report["overall"]["wins"] == 1
    assert report["overall"]["win_rate_pct"] == 50.0
    assert report["overall"]["total_pnl"] == 50.0
    assert report["intraday"]["total_pnl"] == 100.0
    assert report["by_strategy"]["ma_crossover"]["total_pnl"] == 100.0


def test_state_persists_across_instances(paper, tmp_path):
    paper.place_order("ITC", "BUY", 10, 100.0, "DELIVERY")
    reloaded = PaperTradingService(state_file=paper.state_file)
    assert "ITC:DELIVERY" in reloaded.state["positions"]


def test_reset(paper):
    paper.place_order("ITC", "BUY", 10, 100.0, "DELIVERY")
    paper.reset()
    assert paper.state["cash"] == paper.state["starting_capital"]
    assert paper.open_position_count() == 0
