"""NSE market-hours helpers (ported from legacy utils/commonutils.py)."""
from __future__ import annotations

from datetime import datetime, time, timedelta

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
INTRADAY_SQUARE_OFF = time(15, 15)

INTERVAL_MINUTES = {
    "ONE_MINUTE": 1,
    "FIVE_MINUTE": 5,
    "TEN_MINUTE": 10,
    "FIFTEEN_MINUTE": 15,
    "THIRTY_MINUTE": 30,
    "ONE_HOUR": 60,
    "ONE_DAY": 375,  # one trading day worth of minutes
}


def is_market_open(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE

def is_near_square_off(now: datetime | None = None) -> bool:
    """True when intraday positions should already be closed (after 15:15)."""
    now = now or datetime.now()
    return now.weekday() < 5 and now.time() >= INTRADAY_SQUARE_OFF


def market_status(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    if now.weekday() >= 5:
        state = "closed_weekend"
    elif now.time() < MARKET_OPEN:
        state = "pre_open"
    elif now.time() > MARKET_CLOSE:
        state = "closed"
    else:
        state = "open"
    return {
        "exchange": "NSE",
        "status": state,
        "is_open": state == "open",
        "market_open": "09:15",
        "market_close": "15:30",
        "intraday_square_off": "15:15",
        "checked_at": now.isoformat(timespec="seconds"),
        "note": "Exchange holidays are not checked — verify on a holiday calendar.",
    }


def get_start_date(interval: str, num_intervals: int = 250, now: datetime | None = None) -> datetime:
    """Past datetime such that roughly num_intervals trading candles exist until now."""
    now = now or datetime.now()
    if interval not in INTERVAL_MINUTES:
        raise ValueError(f"Unsupported interval: {interval}. Use one of {sorted(INTERVAL_MINUTES)}")

    if interval == "ONE_DAY":
        count, dt = 0, now
        while count < num_intervals:
            dt -= timedelta(days=1)
            if dt.weekday() < 5:
                count += 1
        return datetime(dt.year, dt.month, dt.day, MARKET_OPEN.hour, MARKET_OPEN.minute)

    minutes = INTERVAL_MINUTES[interval]
    count, dt = 0, now
    while count < num_intervals:
        dt -= timedelta(minutes=minutes)
        if dt.weekday() < 5 and MARKET_OPEN <= dt.time() <= MARKET_CLOSE:
            count += 1
    return dt
