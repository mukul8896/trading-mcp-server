# Agent register — trading-mcp-server

## A. MCP Server Agent

**Role:** Maintains the MCP server package.

**Responsibilities:**
- Create and maintain MCP tools, resources, and prompts under
  `src/trading_mcp_server/` (tools in `tools/`, one module per category).
- Keep the MCP server independent from any consuming trading repo — paths
  resolve via `TRADING_MCP_HOME`/cwd, never a hardcoded repo location.
- Ensure the package always installs with `pip install -e .` and the console
  script `trading-mcp-server` keeps working.
- Keep the code ready for future PyPI publishing (pyproject metadata, src/
  layout, version sync between `pyproject.toml` and `__init__.py`).
- Maintain clean package structure under `src/trading_mcp_server/`.
- Add tests for MCP tools and services (`tests/`, pytest, network-free);
  preserve the safety test suite (paper default, delivery-sell block,
  approval flow, risk limits).

**Restrictions:**
- Do not add main trading app business logic into the MCP server — it is a
  generic, reusable toolbox.
- Do not hardcode broker secrets, API keys, tokens, or account numbers.
- Do not make the MCP server dependent on one specific repo path.
- Do not break future pip packaging compatibility (src/ layout, extras,
  lazy optional imports).
- Do not weaken the safety invariants listed in CLAUDE.md.

**When to use:** modifying MCP tools/resources/prompts, server startup,
package metadata, `pyproject.toml`, services, the broker safety layer, or
reusable trading utilities.
