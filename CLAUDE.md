# CLAUDE.md — trading-mcp-server

## Project context

This repo is a **standalone, pip-installable Python package** that implements
a local MCP with safe trading tools (NSE / Angel One). It is consumed
by trading workspaces (e.g. the sibling `TradingAgent` repo) but must never
depend on them. The agent using the tools lives elsewhere — this package only
provides data, validation, simulation, and a guarded broker layer.

## Package structure rules

- `src/` layout, import package `trading_mcp_server`, distribution name
  `trading-mcp-server`. Do not break this naming or move out of `src/`.
- `server.py` only wires things together (`create_server()`); logic lives in
  `services/`, tool registration in `tools/` (one module per category, each
  exposing `register(mcp)`), MCP resources/prompts in their packages.
- `broker/smartapi_adapter.py` is the ONLY module that talks to the real
  broker, and `services/broker_service.py` is the ONLY caller of its order
  methods. Keep it that way — that's what makes the safety layer auditable.
- All filesystem state goes under `get_storage_dir()`; all config through
  `config.get_config()`. Both resolve from `TRADING_MCP_HOME` (or cwd).
  **Never hardcode a repo path, user path, or absolute path.**
- Heavy/optional imports (SmartApi, bs4) stay lazy so paper-mode users and
  tests run without the `[broker,scanners]` extras.

## MCP tool design rules

- Tools return plain JSON-serializable dicts; errors as `{"error": ...}` via
  `tools/_common.make_tool` — never let raw tracebacks reach the agent.
- Docstrings are the agent-facing contract: state what the tool does, its
  enums (e.g. timeframes), and any safety behavior.
- Every order path — paper or live — must pass
  `order_validation_service.validate_order`. Never add a tool that bypasses it.
- Tools must never return secrets; config goes out via `to_safe_dict()` only.
- Logs go to stderr (`utils/logger.py`); stdout belongs to the MCP transport.

## Safety invariants (do not weaken)

1. Paper mode is the default; live requires `TRADING_MODE=live` AND
   `ALLOW_LIVE_TRADING=true`, and the latter is not runtime-updatable.
2. Delivery sell is hard-blocked at prepare time, at execute time, and in the
   permission checks. Three layers — keep all three.
3. Live execution requires the prepare → approval-token → execute flow.
4. Every order decision is audited via `log_trade_event`.
5. No main-trading-app business logic in this package — keep it a generic,
   reusable toolbox.
6. No hardcoded broker secrets, API keys, tokens, or account numbers — ever,
   including in tests and docs.

## Testing

```bash
pip install -e ".[dev]"
python -m pytest tests -q
```

- Tests are network-free and broker-free; keep them that way (the safety tests
  prove the broker is never reached — that's the point).
- Safety behaviors are covered in `test_broker_safety.py`,
  `test_order_validation.py`, `test_config.py`. Never delete or weaken these
  to make a change pass. New tools need tests where logic is non-trivial.

## Packaging expectations

- `pyproject.toml` (hatchling) is the build source of truth; console script
  `trading-mcp-server` must keep working.
- Keep the package importable on a clean `pip install trading-mcp-server`
  (core deps only). Broker/scanner deps stay in extras.
- Version lives in `pyproject.toml` + `trading_mcp_server.__version__` — bump
  both together. Future publish: `python -m build` + `twine upload`.
