# yfinance-mcp-server

yfinance-mcp-server is a Python MCP server that exposes the information-collection parts of the yfinance library as discoverable, type-safe tools for AI hosts.

## Objectives

- expose supported yfinance information APIs as explicit MCP tools
- provide typed request models and validated JSON responses for AI hosts
- support both local stdio mode and remote streamable HTTP mode
- include caching, retry, and rate-limit-aware wrapper behavior

## Features

- explicit MCP tools instead of a generic passthrough interface
- typed request models and validated JSON-serializable responses
- backend-agnostic caching with an in-memory implementation for v1
- retry, timeout, and concurrency controls around upstream calls
- support for both local stdio mode and remote streamable-http mode
- project docs covering scope, API mapping, and user setup

## Use Cases

- retrieve a current quote snapshot for a single ticker such as AAPL, TSLA, or SPY
- compare multiple tickers using recent price history, quote snapshots, and news in one agent workflow
- download historical OHLCV data across one or more symbols for charting or downstream analysis
- fetch company metadata, analyst data, earnings dates, insider activity, and holder data for research prompts
- pull annual or quarterly income statements, balance sheets, and cash flow statements for fundamental analysis
- inspect available options expirations and fetch option chains for a selected date
- access Yahoo market summary, sector, industry, search, and lookup endpoints for discovery-oriented tasks
- support AI hosts that need explicit tool selection instead of relying on a generic Python or HTTP wrapper
- run the same tool set locally over stdio for desktop hosts or remotely over streamable HTTP for shared deployments

## Requirements

- Python 3.11+
- uv recommended, or pip

## Installation

Using uv:

1. Create a virtual environment with uv venv.
2. Activate it with source .venv/bin/activate.
3. Install the project with uv pip install -e .

Using pip:

1. Create a virtual environment with python3 -m venv .venv.
2. Activate it with source .venv/bin/activate.
3. Install the project with python3 -m pip install -e .

## Quick Start

Local stdio mode:

1. Install the project.
2. Run uv run python -m yfinance_mcp.server.

Remote HTTP mode:

1. Install the project.
2. Run YF_TRANSPORT=streamable-http uv run python -m yfinance_mcp.server.

## Current Status

The current implementation includes the core information-retrieval surface for yfinance, including quote and company metadata, history, statements, news, options, earnings and analyst data, holders and insider data, fund data, calendars, market endpoints, sector and industry endpoints, and discovery tools such as search and lookup.

Tool requests use typed request models and validated JSON-safe outputs. Detailed tool coverage and the upstream-to-MCP mapping live in docs/API_MAPPING.md, and the full contract and scope live in docs/PROJECT_SPEC.md.

Not implemented:

- `get_shares` is not implemented because current `yfinance` raises `YFNotImplementedError` for that upstream path.
- `get_earnings` is not implemented because the upstream earnings table path is deprecated and does not reliably return usable tabular data.
- `get_capital_gains` is not implemented because live upstream checks consistently returned no capital gains data across tested fund and ETF symbols.
- `get_sustainability` is not implemented because Yahoo frequently returns no sustainability or ESG fundamentals data for otherwise valid symbols.

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
- YF_BACKOFF_CAP_SECONDS
- YF_RETRY_AFTER_CAP_SECONDS
- YF_THROTTLE_COOLDOWN_THRESHOLD
- YF_THROTTLE_COOLDOWN_SECONDS
- YF_LOG_LEVEL
- YF_HTTP_HOST
- YF_HTTP_PORT

## Documentation

- [docs/USER_GUIDE.md](/Users/emt/Workspace/yfinance-mcp-server/docs/USER_GUIDE.md) for installation and run steps
- [docs/PROJECT_SPEC.md](/Users/emt/Workspace/yfinance-mcp-server/docs/PROJECT_SPEC.md) for requirements and scope
- [docs/API_MAPPING.md](/Users/emt/Workspace/yfinance-mcp-server/docs/API_MAPPING.md) for upstream-to-MCP tool mapping
- [examples/QUERIES.md](/Users/emt/Workspace/yfinance-mcp-server/examples/QUERIES.md) for example prompts

## Remote Mode

Remote streamable-http transport is available in the current slice with basic health and readiness support.

Current remote endpoints:

- /mcp for streamable HTTP MCP traffic
- /healthz for basic liveness
- /readyz for basic readiness and version metadata

## Testing

- offline tests: PYTHONPATH=src pytest
- live integration tests: YF_RUN_LIVE_TESTS=1 PYTHONPATH=src pytest -m live
- transport tests: included in the default pytest run and cover main(), /healthz, /readyz, and /mcp route wiring

## Observability

- tool logs include a request-scoped request_id
- tool completion and failure logs include upstream_call_count
- mapping-style responses use a stable values container instead of arbitrary top-level keys
- retry and throttle logs preserve the same request context across attempts

## Project Layout

- [src/yfinance_mcp/server.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/server.py) contains the MCP server entrypoint and tool registration.
- [src/yfinance_mcp/wrapper.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/wrapper.py) contains the yfinance wrapper, retry policy, and cache usage.
- [src/yfinance_mcp/cache.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/cache.py) defines the cache abstraction and in-memory backend.
- [src/yfinance_mcp/schemas.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/schemas.py) contains request and response schemas.

## Development

See [docs/DEVELOPMENT.md](/Users/emt/Workspace/yfinance-mcp-server/docs/DEVELOPMENT.md).

## License

This project is licensed under the MIT License. See [LICENSE](/Users/emt/Workspace/yfinance-mcp-server/LICENSE).
