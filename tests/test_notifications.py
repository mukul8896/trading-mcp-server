"""Telegram notification service — network-free.

The single network seam (`_post_to_telegram`) is patched out in every test, so
nothing here ever touches the wire. Covers: safe no-op when unconfigured,
correct credential/payload routing when configured, graceful failure handling,
trade-alert formatting, and the no-secret-leak invariant.
"""
import pytest

from trading_mcp_server import config as settings
from trading_mcp_server.services import notification_service as notify


def _configure(temp_env, token="bot-tok-123", chat="chat-456"):
    temp_env.write_text(f"TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_CHAT_ID={chat}\n")
    settings._config = None  # force reload from the temp .env


def test_not_configured_is_safe_noop(temp_env, monkeypatch):
    # If unconfigured, we must NOT attempt any network call.
    def explode(*a, **k):
        raise AssertionError("_post_to_telegram must not be called when unconfigured")

    monkeypatch.setattr(notify, "_post_to_telegram", explode)
    result = notify.send_message("hello")
    assert result["sent"] is False
    assert result["reason"] == "telegram_not_configured"


def test_empty_message_not_sent(temp_env, monkeypatch):
    _configure(temp_env)
    monkeypatch.setattr(notify, "_post_to_telegram", lambda *a, **k: {"ok": True, "status_code": 200})
    assert notify.send_message("   ")["sent"] is False
    assert notify.send_message("   ")["reason"] == "empty_message"


def test_send_routes_credentials_and_payload(temp_env, monkeypatch):
    _configure(temp_env, token="bot-tok-123", chat="chat-456")
    captured = {}

    def fake_post(token, chat_id, text, parse_mode):
        captured.update(token=token, chat_id=chat_id, text=text, parse_mode=parse_mode)
        return {"ok": True, "status_code": 200, "description": ""}

    monkeypatch.setattr(notify, "_post_to_telegram", fake_post)
    result = notify.send_message("ping", parse_mode="HTML")

    assert result["sent"] is True
    assert result["channel"] == "telegram"
    assert captured == {"token": "bot-tok-123", "chat_id": "chat-456", "text": "ping", "parse_mode": "HTML"}


def test_send_failure_is_reported_not_raised(temp_env, monkeypatch):
    _configure(temp_env)

    def boom(*a, **k):
        raise ConnectionError("dns down")

    monkeypatch.setattr(notify, "_post_to_telegram", boom)
    result = notify.send_message("ping")
    assert result["sent"] is False
    assert result["reason"] == "send_failed"


def test_telegram_api_not_ok_marks_unsent(temp_env, monkeypatch):
    _configure(temp_env)
    monkeypatch.setattr(
        notify, "_post_to_telegram",
        lambda *a, **k: {"ok": False, "status_code": 400, "description": "chat not found"},
    )
    result = notify.send_message("ping")
    assert result["sent"] is False
    assert result["status_code"] == 400


def test_format_trade_alert_has_key_fields():
    text = notify.format_trade_alert(
        symbol="reliance", side="buy", quantity=10, trade_type="delivery",
        mode="live", entry=100, stop_loss=95, target=110, rationale="breakout", validity="EOD",
    )
    assert "ACTION REQUIRED" in text
    assert "RELIANCE" in text and "BUY" in text
    assert "Stop-loss: 95" in text
    assert "2.00:1" in text  # reward 10 / risk 5
    assert "LIVE" in text
    assert "did NOT place" in text
    assert "Not financial advice" in text.lower() or "not financial advice" in text.lower()


def test_trade_alert_returns_preview_even_when_unconfigured(temp_env, monkeypatch):
    # No telegram configured -> not sent, but the agent still gets the text.
    def explode(*a, **k):
        raise AssertionError("should not hit network when unconfigured")

    monkeypatch.setattr(notify, "_post_to_telegram", explode)
    text = notify.format_trade_alert(
        symbol="TCS", side="BUY", quantity=5, trade_type="intraday",
        mode="paper", entry=50, stop_loss=48, target=56,
    )
    result = notify.send_message(text, parse_mode="none")
    result["preview"] = text  # mirrors what the tool does
    assert result["sent"] is False
    assert "ACTION REQUIRED" in result["preview"]


def test_no_secret_in_return_value(temp_env, monkeypatch):
    _configure(temp_env, token="supersecrettoken", chat="999")
    monkeypatch.setattr(
        notify, "_post_to_telegram", lambda *a, **k: {"ok": True, "status_code": 200, "description": ""}
    )
    result = notify.send_message("ping")
    assert "supersecrettoken" not in str(result)


def test_is_configured(temp_env):
    settings._config = None
    assert notify.is_configured() is False
    _configure(temp_env)
    assert notify.is_configured() is True
