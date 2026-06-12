"""MCP prompts: reusable analysis workflows for the trading agent.

Adapted from the legacy OpenAI-era prompts; the agent (Claude Code /
Copilot CLI) executes these workflows using the server's tools.
"""
from __future__ import annotations

RESPONSE_FORMAT = """\
Structure your final answer with:
- Trading mode (paper/live) and trading type (intraday/swing)
- Market summary, indicator summary, news/sentiment summary
- Portfolio impact and risk assessment
- Entry price, stop-loss, target, position size, risk-reward ratio
- Suggested action with confidence level and invalidating conditions
- Whether any order was simulated, prepared, executed, or blocked
- A disclaimer that this is not financial advice
"""


def register_all(mcp) -> None:
    @mcp.prompt()
    def intraday_trade_analysis(symbol: str) -> str:
        """Disciplined intraday analysis workflow for one symbol."""
        return f"""\
Analyze {symbol} for an intraday trade. Follow this workflow strictly:
1. get_current_trading_mode and fetch_market_status — stop if the market is closed.
2. evaluate_intraday_trade_setup("{symbol}") for multi-timeframe indicators.
3. fetch_latest_news("{symbol}") and weigh sentiment against the technicals.
4. Check fetch_paper_portfolio and check_max_daily_loss before sizing.
5. If (and only if) the setup is convincing, run validate_trade_against_risk_rules.
6. In paper mode place the trade with place_paper_order (include stop_loss and
   target). In live mode use prepare_order and wait for my approval.
Avoid the trade entirely if data is incomplete or confidence is low.
{RESPONSE_FORMAT}"""

    @mcp.prompt()
    def swing_trade_analysis(symbol: str) -> str:
        """Swing/delivery analysis workflow for one symbol."""
        return f"""\
Analyze {symbol} for a swing/delivery trade (days to weeks):
1. get_current_trading_mode, then evaluate_swing_trade_setup("{symbol}").
2. Check support/resistance placement of the suggested stop and target.
3. fetch_latest_news("{symbol}") and analyze_news_sentiment("{symbol}").
4. Review portfolio concentration with calculate_portfolio_exposure.
5. Validate with validate_trade_against_risk_rules before any order.
6. Remember: delivery BUY can be simulated or prepared; delivery SELL is always
   blocked — only give a recommendation.
{RESPONSE_FORMAT}"""

    @mcp.prompt()
    def paper_trading_review() -> str:
        """Review paper-trading performance and judge strategy profitability."""
        return f"""\
Review my paper trading performance:
1. generate_paper_trading_report and calculate_paper_trading_performance.
2. Compare intraday vs delivery results, and per-strategy results.
3. Identify what is working, what is losing money, and why (win rate vs
   average win/loss, drawdown).
4. Recommend concrete adjustments (risk %, strategy selection, filters) and
   whether the system looks profitable enough to even consider live mode.
{RESPONSE_FORMAT}"""
