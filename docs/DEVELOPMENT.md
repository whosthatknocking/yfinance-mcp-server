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
- transport tests run with the default pytest suite and cover the HTTP app plus main() transport dispatch
- when changing tool registration or server execution behavior, verify the registered MCP tools remain async so HTTP mode does not block the event loop on synchronous `yfinance` calls
- keep direct tests around public server tool functions in addition to wrapper and serialization tests
- for local smoke checks, validate imports and basic wrapper behavior before opening a PR

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
