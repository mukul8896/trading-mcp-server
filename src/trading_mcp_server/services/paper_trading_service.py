"""Paper trading engine — simulated orders, positions, P&L, performance.

State is persisted to <home>/storage/paper_state.json. Intraday and delivery
trades are tracked separately so strategy profitability can be evaluated
per trading style. No broker interaction happens anywhere in this module.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from trading_mcp_server.config import get_config, get_storage_dir
from trading_mcp_server.utils.logger import get_logger, log_trade_event

log = get_logger("paper_trading")

VALID_SIDES = {"BUY", "SELL"}
VALID_PRODUCTS = {"INTRADAY", "DELIVERY"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class PaperTradingService:
    def __init__(self, state_file: Path | None = None, starting_capital: float | None = None):
        self.state_file = state_file if state_file is not None else get_storage_dir() / "paper_state.json"
        self._starting_capital = starting_capital
        self.state = self._load()

    # ---------------- persistence ----------------
    def _default_state(self) -> dict:
        capital = (
            self._starting_capital
            if self._starting_capital is not None
            else get_config().paper_starting_capital
        )
        return {
            "starting_capital": capital,
            "cash": capital,
            "positions": {},  # key: f"{symbol}:{product_type}"
            "orders": [],
            "closed_trades": [],
        }

    def _load(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        return self._default_state()

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def reset(self) -> dict:
        self.state = self._default_state()
        self._save()
        return {"status": "reset", "cash": self.state["cash"]}

    # ---------------- orders ----------------
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        product_type: str = "DELIVERY",
        order_type: str = "MARKET",
        stop_loss: float | None = None,
        target: float | None = None,
        strategy: str | None = None,
    ) -> dict:
        """Simulate an immediate fill at `price`. Returns the order record."""
        symbol = symbol.upper()
        side = side.upper()
        product_type = product_type.upper()
        if side not in VALID_SIDES:
            return {"status": "rejected", "reason": f"Invalid side '{side}'"}
        if product_type not in VALID_PRODUCTS:
            return {"status": "rejected", "reason": f"Invalid product_type '{product_type}'"}
        if quantity <= 0:
            return {"status": "rejected", "reason": "Quantity must be positive"}
        if price <= 0:
            return {"status": "rejected", "reason": "A positive fill price is required"}

        key = f"{symbol}:{product_type}"
        position = self.state["positions"].get(key)
        cost = quantity * price

        if side == "BUY":
            if cost > self.state["cash"]:
                return {
                    "status": "rejected",
                    "reason": f"Insufficient paper cash ({self.state['cash']:.2f}) for cost {cost:.2f}",
                }
            self.state["cash"] -= cost
            if position:
                total_qty = position["quantity"] + quantity
                position["avg_price"] = (
                    position["avg_price"] * position["quantity"] + cost
                ) / total_qty
                position["quantity"] = total_qty
            else:
                self.state["positions"][key] = position = {
                    "symbol": symbol,
                    "product_type": product_type,
                    "quantity": quantity,
                    "avg_price": price,
                    "stop_loss": stop_loss,
                    "target": target,
                    "strategy": strategy,
                    "opened_at": _now(),
                }
        else:  # SELL — only against an existing long position (no shorting in v1)
            if not position or position["quantity"] < quantity:
                held = position["quantity"] if position else 0
                return {
                    "status": "rejected",
                    "reason": f"Cannot sell {quantity} {symbol} ({product_type}): only {held} held. "
                    "Short selling is not supported in the paper engine.",
                }
            pnl = (price - position["avg_price"]) * quantity
            self.state["cash"] += quantity * price
            self.state["closed_trades"].append(
                {
                    "symbol": symbol,
                    "product_type": product_type,
                    "quantity": quantity,
                    "entry_price": position["avg_price"],
                    "exit_price": price,
                    "pnl": round(pnl, 2),
                    "strategy": position.get("strategy") or strategy,
                    "opened_at": position.get("opened_at"),
                    "closed_at": _now(),
                }
            )
            position["quantity"] -= quantity
            if position["quantity"] == 0:
                del self.state["positions"][key]

        order = {
            "order_id": f"PAPER-{uuid.uuid4().hex[:10]}",
            "status": "filled",
            "simulated": True,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "fill_price": price,
            "product_type": product_type,
            "order_type": order_type,
            "stop_loss": stop_loss,
            "target": target,
            "strategy": strategy,
            "timestamp": _now(),
        }
        self.state["orders"].append(order)
        self._save()
        log_trade_event("paper_order_filled", order)
        return order

    def close_position(self, symbol: str, price: float, product_type: str = "DELIVERY") -> dict:
        key = f"{symbol.upper()}:{product_type.upper()}"
        position = self.state["positions"].get(key)
        if not position:
            return {"status": "rejected", "reason": f"No open paper position for {key}"}
        return self.place_order(
            symbol, "SELL", position["quantity"], price, product_type=product_type
        )

    # ---------------- views ----------------
    def get_portfolio(self, live_prices: dict[str, float] | None = None) -> dict:
        live_prices = {k.upper(): v for k, v in (live_prices or {}).items()}
        positions = []
        unrealized = 0.0
        invested = 0.0
        for pos in self.state["positions"].values():
            entry_value = pos["quantity"] * pos["avg_price"]
            invested += entry_value
            ltp = live_prices.get(pos["symbol"])
            row = {**pos}
            if ltp:
                row["ltp"] = ltp
                row["unrealized_pnl"] = round((ltp - pos["avg_price"]) * pos["quantity"], 2)
                unrealized += row["unrealized_pnl"]
            positions.append(row)
        realized = sum(t["pnl"] for t in self.state["closed_trades"])
        return {
            "mode": "paper",
            "starting_capital": self.state["starting_capital"],
            "cash": round(self.state["cash"], 2),
            "invested_value_at_cost": round(invested, 2),
            "open_positions": positions,
            "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unrealized, 2) if live_prices else None,
            "total_orders": len(self.state["orders"]),
            "closed_trades": len(self.state["closed_trades"]),
        }

    def get_trades(self, product_type: str | None = None) -> list[dict]:
        trades = self.state["closed_trades"]
        if product_type:
            trades = [t for t in trades if t["product_type"] == product_type.upper()]
        return trades

    def get_orders(self) -> list[dict]:
        return self.state["orders"]

    def todays_realized_pnl(self) -> float:
        today = datetime.now().date().isoformat()
        return sum(
            t["pnl"] for t in self.state["closed_trades"] if (t.get("closed_at") or "").startswith(today)
        )

    def open_position_count(self) -> int:
        return len(self.state["positions"])

    # ---------------- analytics ----------------
    def performance_report(self) -> dict:
        report = {"overall": self._performance(self.state["closed_trades"])}
        for product in sorted(VALID_PRODUCTS):
            trades = self.get_trades(product)
            if trades:
                report[product.lower()] = self._performance(trades)
        by_strategy = {}
        for trade in self.state["closed_trades"]:
            by_strategy.setdefault(trade.get("strategy") or "unspecified", []).append(trade)
        report["by_strategy"] = {name: self._performance(ts) for name, ts in by_strategy.items()}
        report["current"] = self.get_portfolio()
        return report

    @staticmethod
    def _performance(trades: list[dict]) -> dict:
        if not trades:
            return {"trades": 0, "note": "No closed trades yet"}
        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        equity, peak, max_dd = 0.0, 0.0, 0.0
        for p in pnls:
            equity += p
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        return {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(trades) * 100, 1),
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl_per_trade": round(sum(pnls) / len(trades), 2),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
            "max_drawdown": round(max_dd, 2),
            "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else None,
        }


_service: PaperTradingService | None = None


def get_paper_service() -> PaperTradingService:
    global _service
    if _service is None:
        _service = PaperTradingService()
    return _service
