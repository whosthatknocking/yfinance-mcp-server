# AGENTS.md

This file gives project-specific guidance to AI agents working in this repository.

## Project Context

- Project: `yfinance-mcp-server`
- Purpose: expose the read-only, information-collection surface of `yfinance` as explicit MCP tools for AI hosts
- Runtime: Python 3.11+
- Primary transports:
  - `stdio` for local MCP hosts
  - `streamable-http` for remote deployments
- Packaging:
  - install with `uv pip install -e .`
  - dev install with `uv pip install -e .[dev]`

## Source of Truth

When behavior, naming, or scope is unclear, use these files in this order:

1. `docs/PROJECT_SPEC.md`
2. `docs/API_MAPPING.md`
3. `README.md`
4. `docs/USER_GUIDE.md`

Keep those files aligned with the implementation. If you change tool names, behavior, configuration, or transport behavior, update the docs in the same task.

## Architecture Map

- `src/yfinance_mcp/server.py`
  - FastMCP entrypoint
  - tool registration
  - transport dispatch
  - async MCP wrappers that offload blocking sync tool bodies to Starlette's threadpool
  - `/healthz`, `/readyz`, and `/mcp` wiring for HTTP mode
- `src/yfinance_mcp/wrapper.py`
  - all upstream `yfinance` access
  - retries, timeout handling, throttling, caching, and normalization
- `src/yfinance_mcp/schemas.py`
  - request and response models
  - canonical MCP response contracts
- `src/yfinance_mcp/utils.py`
  - normalization and serialization helpers
- `src/yfinance_mcp/cache.py`
  - cache abstraction and in-memory implementation
- `src/yfinance_mcp/logging_utils.py`
  - request-scoped logging context and counters

## Non-Negotiable Design Rules

- Expose explicit MCP tools. Do not add a generic passthrough tool for arbitrary `yfinance` calls.
- Keep the server read-only. This project is for information retrieval, not trading or account actions.
- Return JSON-serializable payloads only.
- Prefer stable typed schemas over ad hoc dictionaries.
- Keep one canonical response shape per tool.
- For mapping-style responses, use stable containers such as `values` or documented result objects rather than arbitrary dynamic top-level keys.
- Normalize host-generated input conservatively. Fix common symbol formatting issues, but do not silently reinterpret materially different user intent.
- Preserve transport parity. Tool behavior and payloads should stay consistent between `stdio` and `streamable-http`.

## Tool and Wrapper Conventions

- Add or change MCP tools in `src/yfinance_mcp/server.py`.
- Keep tool docstrings precise and retrieval-oriented. Tool descriptions matter for LLM tool selection.
- Route upstream calls through `YFinanceWrapper`; do not duplicate `yfinance` access in server tools.
- Validate non-trivial outputs through Pydantic models before returning them.
- Use `_run_tool(...)` for request context, logging, and error normalization.
- Preserve the async tool registration pattern so blocking `yfinance` calls stay off the HTTP event loop.
- Prefer `get_quote_snapshot` for current quote-style requests and `get_info` for broader company metadata.
- When adding a batch tool, enforce bounded concurrency and avoid unbounded fan-out.

## Error Handling and Stability

- Raise project-appropriate validation or wrapper errors instead of leaking raw upstream exceptions.
- Respect existing timeout, retry, throttle, and cache behavior in `YFinanceWrapper`.
- Do not remove cache usage or request-scoped logging without a strong reason.
- If an upstream `yfinance` surface is deprecated, unstable, or consistently empty, document that caveat clearly instead of pretending it is reliable.

## Testing Expectations

Run the smallest relevant test set first, then broaden if needed.

- Main suite: `PYTHONPATH=src pytest`
- Live tests: `YF_RUN_LIVE_TESTS=1 PYTHONPATH=src pytest -m live`

Testing guidance:

- Add or update tests for any behavior change in tools, serialization, normalization, transport wiring, or wrapper logic.
- Prefer offline tests by default.
- Use live tests only when the change depends on current Yahoo or `yfinance` behavior.
- If live testing is skipped, say so explicitly in your summary.

## Documentation Expectations

Update docs when any of these change:

- tool names or parameters
- response shapes
- environment variables
- supported or unsupported upstream APIs
- run instructions
- transport endpoints

Common files to update:

- `README.md`
- `docs/API_MAPPING.md`
- `docs/USER_GUIDE.md`
- `examples/QUERIES.md`

## Practical Workflow

1. Read the affected code and the matching contract docs first.
2. Make the smallest coherent change.
3. Update tests with the code change.
4. Update docs if user-facing behavior changed.
5. Run targeted tests, then broader tests if warranted.

## Commit and PR Guidance

- Use imperative commit subjects, for example `docs: add selective tool arg guidance`.
- Keep commits small, single-purpose, and easy to review.
- Include tests with behavior changes in the same commit when practical.
- Avoid mixing unrelated refactors, docs updates, and behavior changes unless they are tightly coupled.
- In PRs, summarize intent in 1-3 sentences.
- In PRs, list the validation steps actually run.
- If validation was skipped or limited, say so explicitly.

## Repository-Specific Notes

- The package version is defined in `pyproject.toml` and exposed by the package.
- Remote mode exposes:
  - `/mcp`
  - `/healthz`
  - `/readyz`
- The current implementation intentionally excludes some upstream surfaces when they are not reliable, including `get_shares`, `get_earnings`, `get_capital_gains`, and `get_sustainability`. Do not reintroduce them casually.
- This repo uses `structlog`, `pydantic`, `pytest`, `starlette`, `uvicorn`, and `yfinance`. Match the existing style and dependencies before introducing new ones.

## Good Changes

- adding a new explicit tool that maps cleanly to a stable upstream information API
- tightening a schema while preserving backward-compatible fields
- improving symbol normalization with tests
- fixing serialization edge cases for pandas objects
- updating docs to reflect the actual implemented MCP surface

## Bad Changes

- adding a catch-all tool that can invoke arbitrary `yfinance` methods
- returning raw pandas objects or non-JSON types
- changing response shapes without updating schemas and docs
- bypassing the wrapper from MCP tools
- adding network-dependent tests to the default suite unless they are explicitly marked live
