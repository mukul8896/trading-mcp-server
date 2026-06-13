"""Outbound notification tools (Telegram).

These tools send a MESSAGE ONLY — they never place, validate, or modify an
order. They exist so the agent can hand an actionable trade to the human for
manual placement (the "notify only" execution mode).
"""
from __future__ import annotations

from trading_mcp_server.services import notification_service as notify
from trading_mcp_server.tools._common import make_tool


def register(mcp) -> None:
    tool = make_tool(mcp)

    @tool
    def send_telegram_notification(message: str, parse_mode: str = "HTML") -> dict:
        """Send a free-text message to the configured Telegram chat.

        Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env; if either is
        missing, returns {'sent': False, 'reason': 'telegram_not_configured'}
        without raising. parse_mode: HTML | Markdown | none. This sends a
        MESSAGE ONLY and never places an order.
        """
        return notify.send_message(message, parse_mode=parse_mode)

    @tool
    def send_trade_alert(
        symbol: str,
        side: str,
        quantity: int,
        trade_type: str,
        mode: str,
        entry: float,
        stop_loss: float,
        target: float,
        rationale: str = "",
        validity: str = "",
    ) -> dict:
        """Format an 'ACTION REQUIRED' trade recommendation and send it to
        Telegram for the human to place manually (used in notify-only mode).

        side: BUY | SELL; trade_type: intraday | delivery; mode: paper | live.
        Sends a RECOMMENDATION ONLY — it does NOT place any order. The returned
        dict always includes 'preview' (the message text) so the agent can also
        surface it inline even when Telegram is not configured.
        """
        text = notify.format_trade_alert(
            symbol=symbol,
            side=side,
            quantity=quantity,
            trade_type=trade_type,
            mode=mode,
            entry=entry,
            stop_loss=stop_loss,
            target=target,
            rationale=rationale,
            validity=validity,
        )
        # Plain-text alert -> parse_mode 'none' so arbitrary symbols/rationale
        # can never break Telegram's markup parser.
        result = notify.send_message(text, parse_mode="none")
        result["preview"] = text
        return result
