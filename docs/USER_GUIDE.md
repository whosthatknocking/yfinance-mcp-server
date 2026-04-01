# User Guide

This guide explains how to install and run `yfinance-mcp-server`.

## Requirements

- Python `3.11+`
- `uv` recommended, or `pip`

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

Optional environment variables can be copied from [.env.example](/Users/emt/Workspace/yfinance-mcp-server/.env.example).

Common settings:

- YF_TRANSPORT=stdio for local MCP hosts
- YF_TRANSPORT=streamable-http for remote HTTP mode
- YF_HTTP_HOST and YF_HTTP_PORT for remote mode
- YF_CACHE_BACKEND, YF_CACHE_TTL, and related cache settings
- YF_UPSTREAM_CONCURRENCY for upstream request concurrency limits
- YF_READ_TIMEOUT, YF_TOTAL_TIMEOUT, YF_MAX_RETRIES, YF_BACKOFF_CAP_SECONDS, YF_RETRY_AFTER_CAP_SECONDS, YF_THROTTLE_COOLDOWN_THRESHOLD, and YF_THROTTLE_COOLDOWN_SECONDS for upstream retry and throttling behavior
- YF_LOG_LEVEL to control stderr log verbosity

## Run Locally with stdio

Start the server for local MCP hosts such as Claude Desktop:

- with uv: uv run python -m yfinance_mcp.server
- with pip or a virtualenv: python -m yfinance_mcp.server

## Run in Remote HTTP Mode

Start the streamable HTTP server:

- YF_TRANSPORT=streamable-http uv run python -m yfinance_mcp.server

To bind a host and port explicitly:

- YF_TRANSPORT=streamable-http YF_HTTP_HOST=127.0.0.1 YF_HTTP_PORT=8000 uv run python -m yfinance_mcp.server

## Examples

Configuration and prompt examples are available in:

- [examples/claude_config.json.example](/Users/emt/Workspace/yfinance-mcp-server/examples/claude_config.json.example) for Claude Desktop
- [examples/lmstudio_config.json.example](/Users/emt/Workspace/yfinance-mcp-server/examples/lmstudio_config.json.example) for LM Studio with `uv`
- [examples/lmstudio_config.venv.json.example](/Users/emt/Workspace/yfinance-mcp-server/examples/lmstudio_config.venv.json.example) for LM Studio with an explicit virtualenv Python path
- [examples/QUERIES.md](/Users/emt/Workspace/yfinance-mcp-server/examples/QUERIES.md) for example prompts and tool-oriented queries

For LM Studio, make sure the config uses the project directory as `cwd`. If LM Studio launches the system Python without the project environment, it will fail to import `yfinance_mcp`.

## Verify

After starting the server:

- local mode should start without errors and wait on stdio
- remote mode should start an HTTP listener on the configured host and port
- remote mode exposes `/healthz` for liveness and `/readyz` for readiness
- MCP streamable HTTP traffic is served at `/mcp`

## Notes

- The package expects Python `3.11+`, even if some local smoke checks were done with an older interpreter.
- If dependencies such as the MCP SDK are missing, install the project again in a fresh Python `3.11+` environment.
