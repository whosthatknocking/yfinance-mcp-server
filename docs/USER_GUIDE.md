# User Guide

This guide explains how to install and run yfinance-mcp-server.

## Requirements

- Python 3.11+
- uv recommended, or pip

## Install

1. Clone the repository.
2. Change into the project directory.
3. Install the package and dependencies.

Using uv:

- create a virtual environment with uv venv
- activate it with source .venv/bin/activate
- install the project with uv pip install -e .

Using pip:

- create a virtual environment with python3 -m venv .venv
- activate it with source .venv/bin/activate
- install the project with python3 -m pip install -e .

## Configure

Optional environment variables can be copied from [.env.example](../.env.example).

If you do not set these variables, the server uses the defaults shown below.

Common settings:

- `YF_TRANSPORT=stdio` by default for local MCP hosts. Set `YF_TRANSPORT=streamable-http` for remote HTTP mode.
- `YF_HTTP_HOST=127.0.0.1` and `YF_HTTP_PORT=8000` by default for remote mode. In Docker, override `YF_HTTP_HOST=0.0.0.0`.
- `YF_CACHE_BACKEND=memory` by default.
- `YF_CACHE_TTL=900`, `YF_CACHE_TTL_QUOTE=60`, `YF_CACHE_TTL_REFERENCE=3600`, and `YF_CACHE_TTL_HISTORY=900` by default.
- `YF_UPSTREAM_CONCURRENCY=4` by default for upstream request concurrency limits.
- `YF_READ_TIMEOUT=20`, `YF_TOTAL_TIMEOUT=30`, `YF_MAX_RETRIES=3`, `YF_BACKOFF_CAP_SECONDS=4`, `YF_RETRY_AFTER_CAP_SECONDS=30`, `YF_THROTTLE_COOLDOWN_THRESHOLD=3`, and `YF_THROTTLE_COOLDOWN_SECONDS=10` by default for upstream retry and throttling behavior.
- `YF_LOG_LEVEL` defaults to `WARNING` in `stdio` mode and `INFO` in `streamable-http` mode unless explicitly set.

## Run Locally with stdio

Start the server for local MCP hosts such as Claude Desktop:

- with uv: uv run python -m yfinance_mcp.server
- with pip or a virtualenv: python -m yfinance_mcp.server

## Run in Remote HTTP Mode

Start the streamable HTTP server:

- YF_TRANSPORT=streamable-http uv run python -m yfinance_mcp.server

To bind a host and port explicitly:

- YF_TRANSPORT=streamable-http YF_HTTP_HOST=127.0.0.1 YF_HTTP_PORT=8000 uv run python -m yfinance_mcp.server

In remote HTTP mode, blocking `yfinance` work is offloaded to Starlette's threadpool so individual tool calls do not execute directly on the event loop.

## Run with Docker

Docker is the preferred containerized path for remote HTTP deployments. It is less suitable for local `stdio` desktop-host workflows.

Build the image:

- `docker build -t yfinance-mcp-server .`

Run the container:

- `docker run --rm -p 8000:8000 yfinance-mcp-server`

Run with explicit environment overrides:

- `docker run --rm -p 8000:8000 -e YF_LOG_LEVEL=INFO -e YF_UPSTREAM_CONCURRENCY=4 yfinance-mcp-server`

Run with Docker Compose:

- `docker compose up --build`

The container image starts in `streamable-http` mode, binds to `0.0.0.0`, exposes port `8000`, and includes a `/healthz` health check.

## Examples

Configuration and prompt examples are available in:

- [examples/claude_config.json.example](../examples/claude_config.json.example) for Claude Desktop
- [examples/lmstudio_config.json.example](../examples/lmstudio_config.json.example) for LM Studio with uv
- [examples/lmstudio_config.venv.json.example](../examples/lmstudio_config.venv.json.example) for LM Studio with an explicit virtualenv Python path
- [examples/QUERIES.md](../examples/QUERIES.md) for example prompts and tool-oriented queries

For LM Studio, make sure the config uses the project directory as cwd. If LM Studio launches the system Python without the project environment, it will fail to import yfinance_mcp.

## Verify

After starting the server:

- local mode should start without errors and wait on stdio
- remote mode should start an HTTP listener on the configured host and port
- Docker mode should publish port `8000` by default unless overridden
- remote mode should remain responsive while blocking upstream `yfinance` calls are running because tool execution is offloaded to worker threads
- remote mode exposes /healthz for liveness and /readyz for readiness
- MCP streamable HTTP traffic is served at /mcp

## Notes

- The package expects Python 3.11+, even if some local smoke checks were done with an older interpreter.
- If dependencies such as the MCP SDK are missing, install the project again in a fresh Python 3.11+ environment.
- Not implemented:
- `get_shares` is not implemented because current `yfinance` does not implement the upstream shares call reliably.
- `get_earnings` is not implemented because the upstream earnings table path is deprecated and unstable.
- `get_capital_gains` is not implemented because live upstream checks consistently returned no capital gains data.
- `get_sustainability` is not implemented because Yahoo frequently returns no sustainability or ESG fundamentals data.
