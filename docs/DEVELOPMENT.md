# Development

## Development Setup

1. Use Python `3.11+`.
2. Create and activate a virtual environment.
3. Install the project in editable mode with development dependencies.

Recommended setup:

- uv venv
- source .venv/bin/activate
- uv pip install -e .[dev]

## Development Workflow

- make changes in `src/yfinance_mcp/`
- keep tool contracts aligned with [docs/API_MAPPING.md](/Users/emt/Workspace/yfinance-mcp-server/docs/API_MAPPING.md)
- keep implementation aligned with [docs/PROJECT_SPEC.md](/Users/emt/Workspace/yfinance-mcp-server/docs/PROJECT_SPEC.md)
- add or update tests under `tests/`
- update user-facing docs when behavior changes

## Testing

- run tests with PYTHONPATH=src pytest
- for local smoke checks, validate imports and basic wrapper behavior before opening a PR

## Pull Requests

- keep changes scoped and reviewable
- include documentation updates when tool signatures, setup, or behavior changes
- mention any live-network testing limitations in the PR description
