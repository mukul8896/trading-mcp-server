"""Outbound notifications (Telegram).

Side-effect only: this service sends MESSAGES. It never places, validates, or
mutates an order, and it never returns or logs secrets. It is used by the agent
in "notify only" mode to hand an actionable trade to the human for manual
placement.

Configured via TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env. When either is
missing the service is a safe no-op that reports it is not configured rather
than raising.
"""
from __future__ import annotations

from trading_mcp_server.config import get_config
from trading_mcp_server.utils.logger import get_logger, log_trade_event

log = get_logger("notifications")

_TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"


def is_configured() -> bool:
    """True only when both the bot token and chat id are present in config."""
    cfg = get_config()
    return bool(cfg.telegram_bot_token and cfg.telegram_chat_id)


def _post_to_telegram(token: str, chat_id: str, text: str, parse_mode: str) -> dict:
    """The ONLY function here that performs network I/O.

    Isolated so tests can patch it out and stay network-free. Returns a small
    dict describing the outcome; never raises for an HTTP error status.
    """
    import requests  # core dependency; imported lazily to keep this patchable

    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode and parse_mode.lower() != "none":
        payload["parse_mode"] = parse_mode

    resp = requests.post(_TELEGRAM_SEND_URL.format(token=token), json=payload, timeout=10)
    try:
        body = resp.json()
    except ValueError:
        body = {}
    return {
        "ok": bool(body.get("ok")) if body else bool(resp.ok),
        "status_code": resp.status_code,
        "description": body.get("description", ""),
    }


def send_message(text: str, parse_mode: str = "HTML") -> dict:
    """Send a free-text message to the configured Telegram chat.

    Returns {'sent': bool, ...}. Reasons for not sending are surfaced
    explicitly (never raised): 'telegram_not_configured', 'empty_message',
    'send_failed'. Secrets are never included in the return value.
    """
    cfg = get_config()
    if not (cfg.telegram_bot_token and cfg.telegram_chat_id):
        return {
            "sent": False,
            "reason": "telegram_not_configured",
            "detail": "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env to enable Telegram notifications.",
        }
    if not text or not text.strip():
        return {"sent": False, "reason": "empty_message"}

    try:
        result = _post_to_telegram(cfg.telegram_bot_token, cfg.telegram_chat_id, text, parse_mode)
    except Exception as exc:  # network/DNS/timeout — report, don't crash the agent
        log.exception("Telegram send failed")
        return {"sent": False, "reason": "send_failed", "detail": f"{type(exc).__name__}: {exc}"}

    sent = bool(result.get("ok"))
    # Audit the fact of a notification — not its content, not any secret.
    log_trade_event(
        "notification_sent",
        {"channel": "telegram", "sent": sent, "status_code": result.get("status_code"), "chars": len(text)},
    )
    return {
        "sent": sent,
        "channel": "telegram",
        "status_code": result.get("status_code"),
        "detail": result.get("description", ""),
    }


def format_trade_alert(
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
) -> str:
    """Build a plain-text 'ACTION REQUIRED' trade recommendation.

    Plain text (no markup) so it is safe to send with any parse_mode and never
    breaks on symbols or free-text rationale.
    """
    reward = abs(target - entry)
    risk = abs(entry - stop_loss)
    rr = f"{reward / risk:.2f}:1" if risk else "n/a"

    lines = [
        "ACTION REQUIRED — place this order manually",
        "",
        f"Mode: {str(mode).upper()}",
        f"{str(side).upper()} {symbol.upper()}  ({str(trade_type).lower()})",
        f"Quantity: {quantity}",
        f"Entry: {entry}",
        f"Stop-loss: {stop_loss}",
        f"Target: {target}",
        f"Reward:Risk: {rr}",
    ]
    if validity:
        lines.append(f"Validity: {validity}")
    if rationale:
        lines += ["", f"Why: {rationale}"]
    lines += [
        "",
        "This is a recommendation only — the agent did NOT place this order.",
        "Not financial advice. Trading involves risk of loss.",
    ]
    return "\n".join(lines)
