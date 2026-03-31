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

## Run Locally with stdio

Start the server for local MCP hosts such as Claude Desktop:

- with uv: uv run python -m yfinance_mcp.server
- with pip or a virtualenv: python -m yfinance_mcp.server

## Run in Remote HTTP Mode

Start the streamable HTTP server:

- YF_TRANSPORT=streamable-http uv run python -m yfinance_mcp.server

To bind a host and port explicitly:

- YF_TRANSPORT=streamable-http YF_HTTP_HOST=127.0.0.1 YF_HTTP_PORT=8000 uv run python -m yfinance_mcp.server

## Claude Desktop Example

An example Claude Desktop MCP config is available in [examples/claude_config.json.example](/Users/emt/Workspace/yfinance-mcp-server/examples/claude_config.json.example).

## Verify

After starting the server:

- local mode should start without errors and wait on stdio
- remote mode should start an HTTP listener on the configured host and port

## Notes

- The package expects Python `3.11+`, even if some local smoke checks were done with an older interpreter.
- If dependencies such as the MCP SDK are missing, install the project again in a fresh Python `3.11+` environment.
