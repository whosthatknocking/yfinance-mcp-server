# yfinance-mcp-server

`yfinance-mcp-server` is a Python MCP server that exposes the information-collection parts of the `yfinance` library as discoverable, type-safe tools for AI hosts.

## Overview

The project provides a production-oriented MCP server that maps supported `yfinance` data APIs into explicit read-only tools for local and remote MCP clients. It is designed for AI hosts that need direct access to market data, company information, financial statements, analyst signals, options data, search results, and related financial reference data through stable structured tool contracts.

## Features

- explicit MCP tools instead of a generic passthrough interface
- typed request models and schema-stable JSON responses
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

## Configuration

Environment settings are documented in [.env.example](/Users/emt/Workspace/yfinance-mcp-server/.env.example).

Common settings:

- YF_TRANSPORT
- YF_CACHE_BACKEND
- YF_CACHE_TTL
- YF_HTTP_HOST
- YF_HTTP_PORT
- YF_MAX_WORKERS

## Documentation

- [docs/USER_GUIDE.md](/Users/emt/Workspace/yfinance-mcp-server/docs/USER_GUIDE.md) for installation and run steps
- [docs/PROJECT_SPEC.md](/Users/emt/Workspace/yfinance-mcp-server/docs/PROJECT_SPEC.md) for requirements and scope
- [docs/API_MAPPING.md](/Users/emt/Workspace/yfinance-mcp-server/docs/API_MAPPING.md) for upstream-to-MCP tool mapping

## Project Layout

- [src/yfinance_mcp/server.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/server.py) contains the MCP server entrypoint and tool registration.
- [src/yfinance_mcp/wrapper.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/wrapper.py) contains the yfinance wrapper, retry policy, and cache usage.
- [src/yfinance_mcp/cache.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/cache.py) defines the cache abstraction and in-memory backend.
- [src/yfinance_mcp/schemas.py](/Users/emt/Workspace/yfinance-mcp-server/src/yfinance_mcp/schemas.py) contains request and response schemas.

## Development

- install development dependencies with uv pip install -e .[dev]
- run tests with PYTHONPATH=src pytest
- keep changes aligned with the spec and API mapping docs

## Development

See [docs/DEVELOPMENT.md](/Users/emt/Workspace/yfinance-mcp-server/docs/DEVELOPMENT.md).

## License

This project is licensed under the MIT License. See [LICENSE](/Users/emt/Workspace/yfinance-mcp-server/LICENSE).
