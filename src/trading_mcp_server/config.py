"""Central trading configuration loaded from .env — the single source of truth.

Every safety-relevant flag defaults to the SAFE value: paper mode, live
trading disabled, delivery sell blocked, manual approval required.

Path resolution (keeps the package independent of any repo layout):
  - TRADING_MCP_HOME env var, if set, is the home directory, else the
    current working directory of the server process.
  - .env lives at <home>/.env, runtime state at <home>/storage/.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path


def get_home_dir() -> Path:
    return Path(os.environ.get("TRADING_MCP_HOME") or Path.cwd())


def get_env_file() -> Path:
    return get_home_dir() / ".env"


def get_storage_dir() -> Path:
    return get_home_dir() / "storage"


# Keys the agent is allowed to update at runtime via update_trading_config.
# Credentials and the live-trading master switches are deliberately excluded:
# those must be edited by a human in the .env file.
RUNTIME_UPDATABLE_KEYS = {
    "ENABLE_INTRADAY_TRADING",
    "ENABLE_SWING_TRADING",
    "ALLOW_INTRADAY_BUY",
    "ALLOW_INTRADAY_SELL",
    "ALLOW_DELIVERY_BUY",
    "MAX_RISK_PER_TRADE_PERCENT",
    "MAX_DAILY_LOSS_PERCENT",
    "MAX_OPEN_POSITIONS",
    "MAX_POSITION_SIZE_PERCENT",
    "MIN_RISK_REWARD_RATIO",
}

SECRET_KEYS = {
    "BROKER_API_KEY",
    "BROKER_CLIENT_CODE",
    "BROKER_PASSWORD",
    "BROKER_TOTP_SECRET",
    "NEWS_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
}


def _to_bool(value: str | bool | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_float(value: str | float | None, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: str | int | None, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """Parse a .env file into a dict. Missing file -> empty dict."""
    path = path if path is not None else get_env_file()
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


@dataclass
class TradingConfig:
    # Mode
    trading_mode: str = "paper"  # "paper" | "live"
    enable_intraday_trading: bool = True
    enable_swing_trading: bool = True

    # Live-trading master switches
    allow_live_trading: bool = False
    require_manual_approval_for_live_orders: bool = True

    # Per-action permissions
    allow_intraday_buy: bool = True
    allow_intraday_sell: bool = True
    allow_delivery_buy: bool = True
    allow_delivery_sell: bool = False  # manual verification required — safe default

    # Risk rules
    max_risk_per_trade_percent: float = 1.0
    max_daily_loss_percent: float = 2.0
    max_open_positions: int = 5
    max_position_size_percent: float = 20.0
    min_risk_reward_ratio: float = 1.5

    # Paper trading
    paper_starting_capital: float = 1_000_000.0

    # Broker credentials (never returned by MCP tools)
    broker_name: str = "angelone"
    broker_api_key: str = ""
    broker_client_code: str = ""
    broker_password: str = ""
    broker_totp_secret: str = ""

    # Optional integrations
    news_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ---------------- derived helpers ----------------
    @property
    def is_live(self) -> bool:
        """Live orders are possible only when BOTH switches agree."""
        return self.trading_mode == "live" and self.allow_live_trading

    @property
    def is_paper(self) -> bool:
        return not self.is_live

    def has_broker_credentials(self) -> bool:
        return all(
            [
                self.broker_api_key,
                self.broker_client_code,
                self.broker_password,
                self.broker_totp_secret,
            ]
        )

    def to_safe_dict(self) -> dict:
        """Config as a dict with secrets redacted — what MCP tools return."""
        data = asdict(self)
        for key in list(data):
            if key.upper() in SECRET_KEYS:
                data[key] = "***set***" if data[key] else ""
        data["effective_mode"] = "live" if self.is_live else "paper"
        return data

    # ---------------- loading / persistence ----------------
    @classmethod
    def load(cls, env_path: Path | None = None) -> "TradingConfig":
        """Load from .env file, with OS environment as fallback."""
        raw = load_env_file(env_path)

        def get(key: str) -> str | None:
            return raw.get(key, os.environ.get(key))

        mode = (get("TRADING_MODE") or "paper").strip().lower()
        if mode not in {"paper", "live"}:
            mode = "paper"

        return cls(
            trading_mode=mode,
            enable_intraday_trading=_to_bool(get("ENABLE_INTRADAY_TRADING"), True),
            enable_swing_trading=_to_bool(get("ENABLE_SWING_TRADING"), True),
            allow_live_trading=_to_bool(get("ALLOW_LIVE_TRADING"), False),
            require_manual_approval_for_live_orders=_to_bool(
                get("REQUIRE_MANUAL_APPROVAL_FOR_LIVE_ORDERS"), True
            ),
            allow_intraday_buy=_to_bool(get("ALLOW_INTRADAY_BUY"), True),
            allow_intraday_sell=_to_bool(get("ALLOW_INTRADAY_SELL"), True),
            allow_delivery_buy=_to_bool(get("ALLOW_DELIVERY_BUY"), True),
            allow_delivery_sell=_to_bool(get("ALLOW_DELIVERY_SELL"), False),
            max_risk_per_trade_percent=_to_float(get("MAX_RISK_PER_TRADE_PERCENT"), 1.0),
            max_daily_loss_percent=_to_float(get("MAX_DAILY_LOSS_PERCENT"), 2.0),
            max_open_positions=_to_int(get("MAX_OPEN_POSITIONS"), 5),
            max_position_size_percent=_to_float(get("MAX_POSITION_SIZE_PERCENT"), 20.0),
            min_risk_reward_ratio=_to_float(get("MIN_RISK_REWARD_RATIO"), 1.5),
            paper_starting_capital=_to_float(get("PAPER_STARTING_CAPITAL"), 1_000_000.0),
            broker_name=get("BROKER_NAME") or "angelone",
            broker_api_key=get("BROKER_API_KEY") or "",
            broker_client_code=get("BROKER_CLIENT_CODE") or "",
            broker_password=get("BROKER_PASSWORD") or "",
            broker_totp_secret=get("BROKER_TOTP_SECRET") or "",
            news_api_key=get("NEWS_API_KEY") or "",
            telegram_bot_token=get("TELEGRAM_BOT_TOKEN") or "",
            telegram_chat_id=get("TELEGRAM_CHAT_ID") or "",
        )

    def update_env_values(self, updates: dict[str, str], env_path: Path | None = None) -> list[str]:
        """Persist allowed updates to the .env file. Returns list of applied keys.

        Only RUNTIME_UPDATABLE_KEYS may be changed here; TRADING_MODE is
        handled by the explicit switch_to_* tools and ALLOW_LIVE_TRADING /
        ALLOW_DELIVERY_SELL can only be changed by a human editing .env.
        """
        env_path = env_path if env_path is not None else get_env_file()
        normalized = {k.upper(): str(v) for k, v in updates.items()}
        for key in normalized:
            if key not in RUNTIME_UPDATABLE_KEYS:
                raise PermissionError(
                    f"Config key '{key}' cannot be changed at runtime. "
                    "Live-trading switches, delivery-sell permission, and "
                    "credentials must be edited manually in the .env file."
                )
        current = load_env_file(env_path)
        current.update(normalized)
        _write_env(current, env_path)
        return list(normalized)

    def set_trading_mode(self, mode: str, env_path: Path | None = None) -> str:
        """Switch between paper and live in the .env file.

        Switching to live does NOT enable real orders by itself —
        ALLOW_LIVE_TRADING must already be true (human-edited).
        """
        env_path = env_path if env_path is not None else get_env_file()
        mode = mode.strip().lower()
        if mode not in {"paper", "live"}:
            raise ValueError("mode must be 'paper' or 'live'")
        current = load_env_file(env_path)
        current["TRADING_MODE"] = mode
        _write_env(current, env_path)
        return mode


def _write_env(values: dict[str, str], env_path: Path) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in values.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_config: TradingConfig | None = None


def get_config(reload: bool = False) -> TradingConfig:
    """Process-wide config accessor. Reload re-reads the .env file."""
    global _config
    if _config is None or reload:
        _config = TradingConfig.load()
    return _config
