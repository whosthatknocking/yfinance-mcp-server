# yfinance-mcp-server

`yfinance-mcp-server` is a Python MCP server that exposes the information-collection parts of the `yfinance` library as discoverable, type-safe tools for AI hosts.

## Objectives

- expose supported `yfinance` information APIs as explicit MCP tools
- provide typed request models and validated JSON responses for AI hosts
- support both local stdio mode and remote streamable HTTP mode
- include caching, retry, and rate-limit-aware wrapper behavior

## Features

- explicit MCP tools instead of a generic passthrough interface
- typed request models and validated JSON-serializable responses
- backend-agnostic caching with an in-memory implementation for v1
- retry, timeout, and concurrency controls around upstream calls
- support for both local `stdio` mode and remote `streamable-http` mode
- project docs covering scope, API mapping, and user setup

## Requirements

- Python `3.11+`
- `uv` recommended, or `pip`

## Installation

Using uv:

1. Create a virtual environment with `uv venv`.
2. Activate it with `source .venv/bin/activate`.
3. Install the project with uv pip install -e .

Using pip:

1. Create a virtual environment with `python3 -m venv .venv`.
2. Activate it with `source .venv/bin/activate`.
3. Install the project with python3 -m pip install -e .

## Quick Start

Local stdio mode:

1. Install the project.
2. Run uv run python -m yfinance_mcp.server.

Remote HTTP mode:

1. Install the project.
2. Run YF_TRANSPORT=streamable-http uv run python -m yfinance_mcp.server.

## Current Status

The initial implementation scaffolds the package, abstract cache layer, serialization utilities, MCP entrypoint, and a first working tool slice:

- `get_server_metadata`
- `get_info`
- `get_quote_snapshot`
- `get_batch_info`
- `get_batch_quote_snapshot`
- `get_history`
- `download_history`
- `get_news`
- `get_option_expirations`
- `get_option_chain`
- `get_actions`
- `get_dividends`
- `get_splits`
- `get_income_stmt`
- `get_balance_sheet`
- `get_cashflow`
- `get_earnings_dates`
- `get_ticker_calendar`
- `get_earnings`
- `get_recommendations`
- `get_recommendations_summary`
- `get_upgrades_downgrades`
- `get_analyst_price_targets`
- `get_earnings_estimate`
- `get_revenue_estimate`
- `get_earnings_history`
- `get_eps_trend`
- `get_eps_revisions`
- `get_growth_estimates`
- `get_sustainability`
- `get_major_holders`
- `get_institutional_holders`
- `get_mutualfund_holders`
- `get_insider_purchases`
- `get_insider_transactions`
- `get_insider_roster_holders`
- `get_funds_data`
- `get_fund_asset_classes`
- `get_fund_bond_holdings`
- `get_fund_bond_ratings`
- `get_fund_description`
- `get_fund_equity_holdings`
- `get_fund_operations`
- `get_fund_overview`
- `get_fund_sector_weightings`
- `get_fund_top_holdings`
- `get_fund_quote_type`
- `get_calendars`
- `get_earnings_calendar`
- `get_economic_events_calendar`
- `get_ipo_calendar`
- `get_splits_calendar`
- `get_market_summary`
- `search`
- `lookup`

The current slice uses typed request models and validated JSON-safe outputs. History, download, statement, option chain, list-style outputs, and the current metadata, info, quote snapshot, and market summary tools all use named response models. The broadest upstream payloads still allow extra fields where `yfinance` is less stable.

## Configuration

Environment settings are documented in [.env.example](/Users/emt/Workspace/yfinance-mcp-server/.env.example).

Common settings:

- YF_TRANSPORT
- YF_CACHE_BACKEND
- YF_CACHE_TTL
- YF_UPSTREAM_CONCURRENCY
- YF_READ_TIMEOUT
- YF_TOTAL_TIMEOUT
- YF_MAX_RETRIES
- YF_LOG_LEVEL
- YF_HTTP_HOST
- YF_HTTP_PORT

## Documentation

- [docs/USER_GUIDE.md](/Users/emt/Workspace/yfinance-mcp-server/docs/USER_GUIDE.md) for installation and run steps
- [docs/PROJECT_SPEC.md](/Users/emt/Workspace/yfinance-mcp-server/docs/PROJECT_SPEC.md) for requirements and scope
- [docs/API_MAPPING.md](/Users/emt/Workspace/yfinance-mcp-server/docs/API_MAPPING.md) for upstream-to-MCP tool mapping

## Remote Mode

Remote `streamable-http` transport is available in the current slice with basic health and readiness support.

Current remote endpoints:

- `/mcp` for streamable HTTP MCP traffic
- `/healthz` for basic liveness
- `/readyz` for basic readiness and version metadata

## Project Layout

- [src/yfinance_mcp/server.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/server.py) contains the MCP server entrypoint and tool registration.
- [src/yfinance_mcp/wrapper.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/wrapper.py) contains the yfinance wrapper, retry policy, and cache usage.
- [src/yfinance_mcp/cache.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/cache.py) defines the cache abstraction and in-memory backend.
- [src/yfinance_mcp/schemas.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/schemas.py) contains request and response schemas.

## Development

See [docs/DEVELOPMENT.md](/Users/emt/Workspace/yfinance-mcp-server/docs/DEVELOPMENT.md).

## License

This project is licensed under the MIT License. See [LICENSE](/Users/emt/Workspace/yfinance-mcp-server/LICENSE).
