# trading-mcp-server

A local **MCP (Model Context Protocol) server** that exposes safe trading tools for AI agents such as **Claude Code** and **Copilot CLI**. The agent does the reasoning; this server provides market data, technical indicators, news, risk management, a paper-trading engine, backtesting, and a heavily guarded broker layer (Angel One SmartAPI, NSE).

**Safety model (non-negotiable):**

- Paper trading is the default. Real orders require `TRADING_MODE=live` **and** `ALLOW_LIVE_TRADING=true` (the latter can only be set by a human editing `.env` — no tool can change it).
- Every order passes a full validation checklist (stop-loss required, risk:reward minimum, position-size / daily-loss / open-position limits, market-hours check).
- Live orders use a **prepare → human approval → execute** token flow.
- **Delivery (CNC) sell orders are always blocked** — the server only records a recommendation.
- Every decision is appended to an audit log (`storage/trade_logs.jsonl`).

> Nothing produced by this server is financial advice.

## Installation

```bash
# local development (editable, from a sibling checkout)
pip install -e ../trading-mcp-server

# with broker + scanner extras (needed for live data / Chartink watchlist)
pip install -e "../trading-mcp-server[broker,scanners]"

# future, once published to PyPI
pip install trading-mcp-server
```

Requires Python 3.10+.

## Running the server

The server speaks MCP over stdio:

```bash
trading-mcp-server
# or
python -m trading_mcp_server.server
```

It resolves its configuration and state from a **home directory**:

1. `TRADING_MCP_HOME` environment variable, if set
2. otherwise the current working directory

There it reads `<home>/.env` (trading mode, permissions, risk limits, broker credentials) and writes `<home>/storage/` (paper-trading state, pending orders, audit log). This keeps the package independent of any repo path — point `TRADING_MCP_HOME` at your trading project.

Register in a client (e.g. `.mcp.json` for Claude Code):

```json
{
  "mcpServers": {
    "trading-agent": {
      "command": "trading-mcp-server",
      "env": { "TRADING_MCP_HOME": "C:\\path\\to\\your\\trading-repo" }
    }
  }
}
```

## What it exposes

### Tools (by category)

| Category | Tools |
|---|---|
| Config | `get_trading_config`, `get_current_trading_mode`, `update_trading_config`, `switch_to_paper_mode`, `switch_to_live_mode`, `validate_trading_permissions` |
| Market data | `fetch_live_price`, `fetch_historical_data`, `fetch_market_status`, `fetch_symbol_metadata`, `fetch_watchlist` |
| Indicators | `calculate_sma/ema/rsi/macd/bollinger_bands/atr/volume_analysis`, `detect_support_resistance`, `detect_trend`, `get_indicator_snapshot` |
| News | `fetch_latest_news`, `fetch_market_news`, `analyze_news_sentiment` |
| Portfolio | `fetch_portfolio`, `fetch_order_history`, `calculate_portfolio_exposure`, `calculate_unrealized_pnl` |
| Risk | `calculate_position_size`, `calculate_stop_loss`, `calculate_target_price`, `check_max_daily_loss`, `check_portfolio_concentration`, `validate_trade_against_risk_rules` |
| Strategy | `evaluate_intraday_trade_setup`, `evaluate_swing_trade_setup`, `compare_multiple_symbols`, `scan_watchlist_for_intraday_opportunities`, `scan_watchlist_for_swing_opportunities`, `run_strategy_backtest` |
| Paper trading | `place_paper_order`, `close_paper_position`, `fetch_paper_trades`, `fetch_paper_portfolio`, `calculate_paper_trading_performance`, `generate_paper_trading_report`, `reset_paper_account` |
| Broker (guarded) | `prepare_order`, `validate_order_before_execution`, `execute_intraday_order_after_validation`, `execute_delivery_buy_after_validation`, `block_delivery_sell_order`, `list_pending_live_orders`, `cancel_pending_live_order`, `fetch_broker_funds/positions/holdings/order_status` |

### Resources

- `trading://config` — current configuration (secrets redacted)
- `trading://safety-rules` — the safety rules the server enforces

### Prompts

- `intraday_trade_analysis(symbol)` — disciplined intraday workflow
- `swing_trade_analysis(symbol)` — swing/delivery workflow
- `paper_trading_review()` — profitability review workflow

Backtest strategies built in: `ma_crossover`, `rsi_reversal`, `macd_trend`, `breakout_volume`.

## Package structure

```
src/trading_mcp_server/
├── server.py        # FastMCP entry point (create_server, main)
├── config.py        # .env-backed TradingConfig — single source of truth
├── tools/           # MCP tool modules (one per category, register(mcp))
├── resources/       # MCP resources
├── prompts/         # MCP prompts
├── services/        # data provider, indicators, risk, validation, paper engine, broker safety layer
├── broker/          # SmartAPI adapter — the ONLY module talking to the real broker
├── backtest/        # engine + built-in strategies
└── utils/           # logging/audit, market hours, instrument lookup
tests/               # pytest suite (config, safety, paper engine, indicators, backtest)
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests -q          # run tests (no network, no broker needed)
python -m trading_mcp_server.server  # run server from source
```

## Configuration reference

See `.env.example` in the consuming repo. Key flags: `TRADING_MODE` (paper|live), `ALLOW_LIVE_TRADING`, `REQUIRE_MANUAL_APPROVAL_FOR_LIVE_ORDERS`, `ALLOW_INTRADAY_BUY/SELL`, `ALLOW_DELIVERY_BUY`, `ALLOW_DELIVERY_SELL` (keep `false`), `MAX_RISK_PER_TRADE_PERCENT`, `MAX_DAILY_LOSS_PERCENT`, `MAX_OPEN_POSITIONS`, `MAX_POSITION_SIZE_PERCENT`, `MIN_RISK_REWARD_RATIO`, `PAPER_STARTING_CAPITAL`, `BROKER_*` credentials.

## Publishing to PyPI (future)

1. Bump `version` in `pyproject.toml` and `src/trading_mcp_server/__init__.py`.
2. `python -m build` (requires `pip install build`).
3. `python -m twine upload dist/*` (requires a PyPI account + API token).
4. Consumers then switch from `pip install -e ../trading-mcp-server` to `pip install trading-mcp-server` — no other change needed.

## License

MIT
