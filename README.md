# yfinance-mcp-server

`yfinance-mcp-server` is a Python MCP server that exposes the read-only, information-collection surface of `yfinance` as explicit, typed, JSON-serializable tools for AI hosts that need tool discovery instead of a generic wrapper. It supports quote snapshots, company metadata, historical prices, options, analyst and holder data, market summaries, and search-oriented workflows with consistent behavior across `stdio` and `streamable-http`.

## Why This Project

- explicit MCP tools are easier for AI hosts to discover and select than arbitrary `yfinance` passthrough calls
- typed, stable response shapes are easier to integrate than raw upstream objects and ad hoc payloads
- read-only, retrieval-oriented scope keeps the server focused on information access instead of account or trading actions
- wrapper-level caching, retries, timeouts, and normalization make upstream Yahoo Finance behavior more usable in repeated agent workflows
- transport parity across `stdio` and `streamable-http` makes the same tool surface usable in both local and remote deployments

## Quick Start

Requirements:

- Python 3.11+
- `uv` recommended, or `pip`

Install:

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

Run in local `stdio` mode:

```bash
uv run python -m yfinance_mcp.server
```

Run in remote `streamable-http` mode:

```bash
YF_TRANSPORT=streamable-http uv run python -m yfinance_mcp.server
```

Remote endpoints:

- `/mcp`
- `/healthz`
- `/readyz`

## Documentation

The docs are split by purpose so the README stays brief:

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md): installation, configuration, transports, Docker, and host examples
- [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md): scope, architecture, tool contract rules, and non-goals
- [docs/API_MAPPING.md](docs/API_MAPPING.md): upstream `yfinance` to MCP tool mapping
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): development workflow, tests, and benchmark notes
- [examples/QUERIES.md](examples/QUERIES.md): example prompts and query patterns

Scope, exclusions, and contract rules live in [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md) and [docs/API_MAPPING.md](docs/API_MAPPING.md).

Development setup, testing, and benchmark guidance live in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
