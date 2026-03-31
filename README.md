# yfinance-mcp-server

`yfinance-mcp-server` is a Python MCP server that exposes the information-collection parts of the `yfinance` library as discoverable, type-safe tools for AI hosts.

## Objective

The objective is to provide a production-ready MCP server that maps the latest supported `yfinance` data APIs into explicit read-only tools for local and remote MCP clients. This allows AI hosts to retrieve market data, company information, financial statements, analyst signals, options data, search results, calendars, and related financial reference data through stable structured tool contracts.

## Current Status

The initial implementation scaffolds the package, abstract cache layer, serialization utilities, MCP entrypoint, and a first working tool slice:

- `yfinance_get_server_metadata`
- `yfinance_get_info`
- `yfinance_get_fast_info`
- `yfinance_get_history`
- `yfinance_download`
- `yfinance_get_news`
- `yfinance_get_option_expirations`
- `yfinance_get_option_chain`
- `yfinance_get_income_stmt`
- `yfinance_get_balance_sheet`
- `yfinance_get_cashflow`
- `yfinance_get_market_summary`

## Run

1. Use Python `3.11+`.
2. Install dependencies with `pip install -e .` or `uv pip install -e .`.
3. Start local stdio mode with `uv run python -m yfinance_mcp.server`.
4. Start remote HTTP mode with `YF_TRANSPORT=streamable-http uv run python -m yfinance_mcp.server`.

## Layout

- [src/yfinance_mcp/server.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/server.py) contains the MCP server entrypoint and tool registration.
- [src/yfinance_mcp/wrapper.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/wrapper.py) contains the yfinance wrapper, retry policy, and cache usage.
- [src/yfinance_mcp/cache.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/cache.py) defines the cache abstraction and in-memory backend.
- [src/yfinance_mcp/schemas.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/schemas.py) contains request and response schemas.
