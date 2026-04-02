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
- keep tool contracts aligned with [docs/API_MAPPING.md](API_MAPPING.md)
- keep implementation aligned with [docs/PROJECT_SPEC.md](PROJECT_SPEC.md)
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

## Release Process

Releases are created by the GitHub Actions workflow in [.github/workflows/release.yml](../.github/workflows/release.yml).

Current release behavior:

- the workflow runs on pushes of tags that match `v*`
- the tag must exactly match the package version in `pyproject.toml`
- the workflow builds both the source distribution and wheel
- the workflow creates a GitHub release with generated release notes and uploads the build artifacts

Recommended release steps:

1. Update the version in `pyproject.toml`.
2. Make sure the docs and implementation reflect the release contents.
3. Run the relevant validation locally:
   - `PYTHONPATH=src pytest`
   - optional: `YF_RUN_LIVE_TESTS=1 PYTHONPATH=src pytest -m live`
   - optional: `python -m build`
4. Commit the version and release-related changes.
5. Create an annotated tag that matches the package version, for example `v0.2.1`.
6. Push the commit and tag to GitHub.

Example:

- `git tag -a v0.2.1 -m "Release v0.2.1"`
- `git push origin main --follow-tags`

Important constraints:

- do not push a release tag that does not match `project.version` in `pyproject.toml`
- if the tag and package version differ, the release workflow fails
- if the release changes the supported upstream `yfinance` version or the public MCP surface, update [docs/API_MAPPING.md](API_MAPPING.md), [docs/PROJECT_SPEC.md](PROJECT_SPEC.md), and the user-facing docs in the same change

## Performance Baseline

Use `scripts/benchmark_baseline.py` for a quick, repeatable snapshot of representative behavior. The benchmark is intentionally mock-based so it stays stable across runs and does not depend on Yahoo Finance latency.

Current baseline snapshot:

- Run date: 2026-04-01 local time / 2026-04-02T04:00:43Z
- Command: `PYTHONPATH=src .venv/bin/python scripts/benchmark_baseline.py`
- Python: `3.11.15`

Reference results from that run:

| Benchmark | Median | Min | Max | Notes |
| --- | ---: | ---: | ---: | --- |
| `get_info_cold_cache` | 34.287 ms | 31.723 ms | 35.285 ms | One uncached `get_info` call with a mocked 30 ms upstream property. |
| `get_info_warm_cache` | 0.002 ms | 0.001 ms | 0.004 ms | Warm-cache `get_info` after one priming request. |
| `get_batch_info_uncached_x4` | 35.359 ms | 31.203 ms | 35.457 ms | Four-symbol uncached batch info call with bounded parallel fan-out and mocked 30 ms per-symbol work. |
| `get_batch_quote_snapshot_uncached_x4` | 33.810 ms | 31.690 ms | 35.444 ms | Four-symbol uncached batch quote snapshot call with bounded parallel fan-out and mocked 30 ms per-symbol work. |
| `get_quote_snapshot_tool_concurrent_x3` | 104.151 ms | 102.060 ms | 106.069 ms | Three concurrent MCP tool invocations backed by mocked 100 ms blocking upstream work. |
| `serialize_dataframe_2000x6` | 4.688 ms | 4.538 ms | 4.956 ms | Serialize a representative 2,000-row by 6-column DataFrame payload. |

How to use this baseline:

- Compare future runs against the same command and Python version when possible.
- Treat these numbers as directional, not as hard pass/fail budgets across different machines.
- Look for material regressions in warm-cache latency, serialization time, or concurrent tool completion time.
- Update this section when benchmark methodology changes or when a new baseline should replace the old one.
