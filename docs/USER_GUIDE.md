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

- `YF_TRANSPORT=stdio` by default. Selects the server transport. Set `YF_TRANSPORT=streamable-http` for remote HTTP mode.
- `YF_HTTP_HOST=127.0.0.1` by default. Sets the bind host for remote HTTP mode. In Docker, override `YF_HTTP_HOST=0.0.0.0`.
- `YF_HTTP_PORT=8000` by default. Sets the bind port for remote HTTP mode.
- `YF_CACHE_BACKEND=memory` by default. The current implementation uses the in-memory cache backend; this variable is reserved for future backend selection and is reported in server metadata.
- `YF_CACHE_TTL=900` by default. Sets the general cache lifetime in seconds.
- `YF_CACHE_TTL_QUOTE=60` by default. Sets the cache lifetime for quote-style responses in seconds.
- `YF_CACHE_TTL_REFERENCE=3600` by default. Sets the cache lifetime for reference-style metadata responses in seconds.
- `YF_CACHE_TTL_HISTORY=900` by default. Sets the cache lifetime for historical data responses in seconds.
- `YF_UPSTREAM_CONCURRENCY=4` by default. Caps concurrent upstream Yahoo Finance work per process.
- `YF_READ_TIMEOUT=20` by default. Sets the upstream read timeout in seconds.
- `YF_TOTAL_TIMEOUT=30` by default. Sets the total deadline for an upstream call in seconds.
- `YF_MAX_RETRIES=3` by default. Sets the maximum number of retry attempts for transient upstream failures.
- `YF_BACKOFF_CAP_SECONDS=4` by default. Caps exponential backoff delay between retries.
- `YF_RETRY_AFTER_CAP_SECONDS=30` by default. Caps server-directed `Retry-After` delays.
- `YF_THROTTLE_COOLDOWN_THRESHOLD=3` by default. Sets how many consecutive throttle-like failures trigger cooldown behavior.
- `YF_THROTTLE_COOLDOWN_SECONDS=10` by default. Sets how long the server pauses upstream work after repeated throttle failures.
- `YF_LOG_LEVEL` defaults to `WARNING` in `stdio` mode and `INFO` in `streamable-http` mode unless explicitly set. Controls stderr log verbosity.

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
- For current unsupported or intentionally excluded upstream surfaces, see [docs/API_MAPPING.md](API_MAPPING.md) and [docs/PROJECT_SPEC.md](PROJECT_SPEC.md).
