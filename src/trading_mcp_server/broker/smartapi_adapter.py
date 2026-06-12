"""Angel One SmartAPI adapter — the ONLY module that talks to the real broker.

Ported from legacy smartapi/SmartApiActions.py. The session is created
lazily so paper-mode users without credentials never hit the broker, and
order-placing methods exist only here so the safety layer in
services/broker_service.py is the single entry point for real orders.
"""
from __future__ import annotations

import time
from datetime import datetime

from trading_mcp_server.config import get_config
from trading_mcp_server.utils.instruments import refresh_instrument_list, token_lookup
from trading_mcp_server.utils.logger import get_logger

log = get_logger("smartapi_adapter")


class BrokerCredentialsMissing(RuntimeError):
    pass


class SmartApiAdapter:
    """Thin wrapper around SmartConnect. Heavy imports happen lazily."""

    def __init__(self) -> None:
        self._session = None

    # ---------------- session ----------------
    def _connect(self):
        if self._session is not None:
            return self._session
        cfg = get_config()
        if not cfg.has_broker_credentials():
            raise BrokerCredentialsMissing(
                "Broker credentials are not configured. Set BROKER_API_KEY, "
                "BROKER_CLIENT_CODE, BROKER_PASSWORD and BROKER_TOTP_SECRET in .env."
            )
        from SmartApi import SmartConnect  # lazy: only needed with credentials
        from pyotp import TOTP

        session = SmartConnect(api_key=cfg.broker_api_key)
        session.generateSession(
            cfg.broker_client_code, cfg.broker_password, TOTP(cfg.broker_totp_secret).now()
        )
        try:
            refresh_instrument_list()
        except Exception as exc:  # cache may already exist
            log.warning("Instrument list refresh failed: %s", exc)
        self._session = session
        log.info("SmartAPI session established")
        return session

    def is_available(self) -> bool:
        try:
            self._connect()
            return True
        except Exception:
            return False

    # ---------------- market data ----------------
    def get_ltp(self, ticker: str) -> float:
        session = self._connect()
        token, exchange = token_lookup(ticker)
        time.sleep(1)  # broker rate limit
        response = session.ltpData(exchange, f"{ticker}-EQ", token)
        return float(response["data"]["ltp"])

    def get_candle_data(
        self, ticker: str, start: datetime, end: datetime, interval: str
    ) -> list:
        session = self._connect()
        token, exchange = token_lookup(ticker)
        params = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": interval,
            "fromdate": start.strftime("%Y-%m-%d %H:%M"),
            "todate": end.strftime("%Y-%m-%d %H:%M"),
        }
        time.sleep(1)
        response = session.getCandleData(params)
        return response.get("data") or []

    # ---------------- account ----------------
    def get_funds(self) -> dict:
        session = self._connect()
        time.sleep(1)
        response = session.rmsLimit()
        return response.get("data") or {}

    def get_positions(self) -> list:
        session = self._connect()
        time.sleep(1)
        response = session.position()
        return response.get("data") or []

    def get_holdings(self) -> dict:
        session = self._connect()
        time.sleep(1)
        response = session.allholding()
        return response.get("data") or {}

    def get_order_book(self) -> list:
        session = self._connect()
        time.sleep(1)
        response = session.orderBook()
        return response.get("data") or []

    def get_order_status(self, order_id: str) -> dict | None:
        for order in self.get_order_book():
            if str(order.get("orderid")) == str(order_id):
                return order
        return None

    def get_margin_required(self, ticker: str, side: str, quantity: int, product_type: str) -> float:
        session = self._connect()
        token, exchange = token_lookup(ticker)
        params = {
            "positions": [
                {
                    "exchange": exchange,
                    "qty": quantity,
                    "price": 0,
                    "productType": product_type,
                    "token": token,
                    "tradeType": side,
                }
            ]
        }
        time.sleep(1)
        response = session.getMarginApi(params)
        return float(response["data"]["totalMarginRequired"])

    # ---------------- orders (called ONLY by BrokerService after validation) ----------------
    def place_order(
        self,
        ticker: str,
        side: str,
        quantity: int,
        product_type: str,
        order_type: str = "MARKET",
        price: float = 0,
    ) -> dict:
        session = self._connect()
        token, exchange = token_lookup(ticker)
        params = {
            "variety": "NORMAL",
            "tradingsymbol": f"{ticker}-EQ",
            "symboltoken": token,
            "transactiontype": side,
            "exchange": exchange,
            "ordertype": order_type,
            "producttype": product_type,
            "duration": "DAY",
            "price": price if order_type == "LIMIT" else 0,
            "quantity": quantity,
        }
        time.sleep(1)
        response = session.placeOrder(params)
        return {"order_id": response} if isinstance(response, str) else response

    def cancel_order(self, order_id: str) -> dict:
        session = self._connect()
        return session.cancelOrder(order_id, "NORMAL")


_adapter: SmartApiAdapter | None = None


def get_broker_adapter() -> SmartApiAdapter:
    global _adapter
    if _adapter is None:
        _adapter = SmartApiAdapter()
    return _adapter
