# Development

## Development Setup

1. Use Python 3.11+.
2. Create and activate a virtual environment.
3. Install the project in editable mode with development dependencies.

Recommended setup:

- uv venv
- source .venv/bin/activate
- uv pip install -e .[dev]

## Development Workflow

- make changes in src/yfinance_mcp/
- keep tool contracts aligned with [docs/API_MAPPING.md](/Users/emt/Workspace/yfinance-mcp-server/docs/API_MAPPING.md)
- keep implementation aligned with [docs/PROJECT_SPEC.md](/Users/emt/Workspace/yfinance-mcp-server/docs/PROJECT_SPEC.md)
- keep README and user docs aligned with the currently implemented tool names and config variables
- preserve the async MCP tool registration pattern that offloads blocking `yfinance` work to Starlette's threadpool
- add or update tests under tests/
- update user-facing docs when behavior changes

## Testing

- run tests with PYTHONPATH=src pytest
- run live integration tests with YF_RUN_LIVE_TESTS=1 PYTHONPATH=src pytest -m live
- run perf tests with PYTHONPATH=src pytest -m perf
- run the benchmark baseline snapshot with PYTHONPATH=src .venv/bin/python scripts/benchmark_baseline.py
- transport tests run with the default pytest suite and cover the HTTP app plus main() transport dispatch
- when changing tool registration or server execution behavior, verify the registered MCP tools remain async so HTTP mode does not block the event loop on synchronous `yfinance` calls
- use perf tests for cache warm-path, serialization-cost, and non-blocking execution checks without putting timing-sensitive assertions in the default suite
- keep direct tests around public server tool functions in addition to wrapper and serialization tests
- for local smoke checks, validate imports and basic wrapper behavior before opening a PR

## Performance Baseline

Use `scripts/benchmark_baseline.py` for a quick, repeatable snapshot of representative behavior. The benchmark is intentionally mock-based so it stays stable across runs and does not depend on Yahoo Finance latency.

Current baseline snapshot:

- Run date: 2026-04-01 local time / 2026-04-02T03:54:14Z
- Command: `PYTHONPATH=src .venv/bin/python scripts/benchmark_baseline.py`
- Python: `3.11.15`

Reference results from that run:

| Benchmark | Median | Min | Max | Notes |
| --- | ---: | ---: | ---: | --- |
| `get_info_cold_cache` | 32.593 ms | 30.318 ms | 35.230 ms | One uncached `get_info` call with a mocked 30 ms upstream property. |
| `get_info_warm_cache` | 0.002 ms | 0.001 ms | 0.003 ms | Warm-cache `get_info` after one priming request. |
| `get_quote_snapshot_tool_concurrent_x3` | 102.895 ms | 101.278 ms | 106.124 ms | Three concurrent MCP tool invocations backed by mocked 100 ms blocking upstream work. |
| `serialize_dataframe_2000x6` | 4.763 ms | 4.648 ms | 4.885 ms | Serialize a representative 2,000-row by 6-column DataFrame payload. |

How to use this baseline:

- Compare future runs against the same command and Python version when possible.
- Treat these numbers as directional, not as hard pass/fail budgets across different machines.
- Look for material regressions in warm-cache latency, serialization time, or concurrent tool completion time.
- Update this section when benchmark methodology changes or when a new baseline should replace the old one.

## Pull Requests

- keep changes scoped and reviewable
- use imperative commit subjects
- keep commits small and focused
- include tests with behavior changes when practical
- include documentation updates when tool signatures, setup, or behavior changes
- summarize PR intent briefly
- list validation steps actually run
- mention skipped validation explicitly when relevant
- mention any live-network testing limitations in the PR description
