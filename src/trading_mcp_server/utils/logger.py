"""Structured logging for the trading system.

Every order decision (validated, blocked, simulated, prepared, executed) is
appended to <home>/storage/trade_logs.jsonl as a permanent audit trail.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from trading_mcp_server.config import get_storage_dir

# MCP servers communicate over stdout — logs MUST go to stderr.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_trade_event(event_type: str, payload: dict) -> None:
    """Append an audit record for any trading decision or order action."""
    storage = get_storage_dir()
    storage.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **payload,
    }
    with (storage / "trade_logs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
