"""Angel One instrument master list and token lookup (ported from legacy)."""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

INSTRUMENT_LIST_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)
CACHE_DIR = Path.home() / "hist_data"
CACHE_FILE = CACHE_DIR / "instrumentList.json"
CACHE_MAX_AGE_SECONDS = 24 * 3600

_instruments: list[dict] | None = None


def refresh_instrument_list() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(urllib.request.urlopen(INSTRUMENT_LIST_URL).read())
    CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
    global _instruments
    _instruments = data


def get_instrument_list() -> list[dict]:
    global _instruments
    if _instruments is not None:
        return _instruments
    if CACHE_FILE.exists() and (time.time() - CACHE_FILE.stat().st_mtime) < CACHE_MAX_AGE_SECONDS:
        _instruments = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    else:
        refresh_instrument_list()
    return _instruments


def normalize_symbol(ticker: str) -> str:
    return ticker.replace("-EQ", "").replace("-SM", "").upper().strip()


def token_lookup(ticker: str, exchange: str = "NSE") -> tuple[str, str] | None:
    """Return (token, exchange) for a ticker, trying NSE first then BSE."""
    ticker = normalize_symbol(ticker)
    instruments = get_instrument_list()
    for exch in ([exchange, "BSE"] if exchange.upper() == "NSE" else [exchange]):
        for inst in instruments:
            if (
                inst.get("name", "").upper().strip() == ticker
                and inst.get("exch_seg", "").upper() == exch.upper()
            ):
                return inst["token"], exch.upper()
    return None


def symbol_metadata(ticker: str) -> dict | None:
    ticker = normalize_symbol(ticker)
    for inst in get_instrument_list():
        if inst.get("name", "").upper().strip() == ticker and inst.get("exch_seg") in ("NSE", "BSE"):
            return {
                "symbol": ticker,
                "tradingsymbol": inst.get("symbol"),
                "token": inst.get("token"),
                "exchange": inst.get("exch_seg"),
                "lot_size": inst.get("lotsize"),
                "tick_size": inst.get("tick_size"),
                "instrument_type": inst.get("instrumenttype") or "EQ",
            }
    return None
