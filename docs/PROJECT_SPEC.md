# Project Specification: yfinance MCP Server

## Project Description

`yfinance-mcp-server` is a Python 3.11+ MCP server built with the official `FastMCP` SDK. It exposes the information-collection portions of the `yfinance` library API and behavior, as defined by the latest supported upstream release, as discoverable, type-safe tools for local and remote AI hosts.

## Objectives

- Provide coverage of the information-collection `yfinance` API and observable behavior, as defined by the latest supported upstream release, including `Ticker`, `Tickers`, `download`, `Market`, `Calendars`, `Search`, `Lookup`, sector and industry queries, and screener support.
- Expose strongly typed MCP tools with clear docstrings, parameter descriptions, and structured return schemas for strong LLM discoverability.
- Handle data safely and efficiently by converting pandas objects into JSON-serializable payloads or markdown tables where appropriate.
- Include caching and rate-limit awareness to reduce pressure on Yahoo Finance and improve responsiveness.
- Support both local `stdio` transport and remote `streamable-http` transport as first-class deployment modes.
- Keep installation and configuration simple for MCP hosts.
- Provide end-user documentation with clear steps for installing and running the server.
- Preserve an architecture that is easy to extend as `yfinance` evolves.
- Version the MCP API against the supported `yfinance` API version so hosts can reason about compatibility.

## Scope

For this project, "all functions" means the server should cover the information-collection API and behavior exposed by the latest supported `yfinance` release through explicit MCP tools rather than through a generic passthrough tool.

The authoritative source for scope is the latest supported upstream `yfinance` documentation and runtime behavior at the time of implementation. If a public API is added, deprecated, or behavior changes in a newer `yfinance` release, the MCP surface should be updated in a corresponding versioned release of this server.

### Public API Areas

- Core classes: `yf.Ticker`, `yf.Tickers`, `yf.Market`, `yf.Calendars`
- Discovery and screening APIs: `yf.Search`, `yf.Lookup`, sector and industry queries, and screener-related functions
- Top-level functions: `yf.download`, `yf.screen`
- Supported `Ticker` information APIs include:
  - `info`
  - `history`
  - `fast_info`
  - `actions`
  - `dividends`
  - `splits`
  - `capital_gains`
  - `financials`
  - `quarterly_financials`
  - `balance_sheet`
  - `quarterly_balance_sheet`
  - `cashflow`
  - `quarterly_cashflow`
  - `earnings`
  - `quarterly_earnings`
  - `sustainability`
  - analyst price targets and recommendations
  - `calendar`
  - `news`
  - `options`
  - `option_chain`
  - `funds_data` for ETFs and funds

### Tool Exposure Strategy

- Every supported information-collection method or property should be represented as an explicit `@mcp.tool()` function unless it is listed in an explicit exclusions section.
- The server must not rely on a single generic "call anything" tool.
- The core v1 surface should remain focused on read-only request-response data retrieval.
- Helper tools that support information retrieval, such as validated screener query builders, are allowed when they directly enable read-only data access.

### Exclusions and Non-Goals

- Private or undocumented `yfinance` internals are out of scope.
- Streaming and subscription-oriented APIs, including WebSocket and `live(...)` interfaces, are out of scope for the core MCP tool surface.
- Configuration and process-level helper functions are out of scope as end-user MCP tools.
- Any upstream behavior that is unstable, deprecated, or host-incompatible may be wrapped with explicit caveats rather than mirrored blindly.

## Versioning and Compatibility

- The MCP server should track the latest supported `yfinance` release at implementation time.
- MCP API versioning should be derived from the underlying supported `yfinance` API version.
- At minimum, the project should document:
  - the server package version
  - the supported `yfinance` version or version range
  - any known incompatible upstream changes
- Recommended release policy:
  - patch release: internal fixes with no MCP tool contract changes
  - minor release: additive MCP coverage for new upstream `yfinance` APIs
  - major release: breaking changes caused by upstream `yfinance` contract changes or deliberate MCP schema changes
- Recommended compatibility metadata:
  - expose a server metadata tool that returns the MCP server version, supported `yfinance` version, and transport capabilities
  - include the supported `yfinance` version in README, package metadata, and release notes

## Technical Stack

- MCP framework: `mcp[cli]` with `FastMCP`
- Data library: `yfinance` (latest stable version available at implementation time)
- Data handling: `pandas`
- Caching: backend-agnostic cache layer with pluggable implementations
- HTTP transport: `FastAPI` plus MCP `streamable-http` support
- Packaging: `uv` preferred, `pip` acceptable
- Testing: `pytest` and MCP CLI via `mcp dev`
- Logging: `structlog`
- Validation and schemas: `pydantic`

## Proposed Folder Structure

- `pyproject.toml`
- `README.md`
- `LICENSE`
- `.env.example`
- `src/yfinance_mcp/__init__.py`
- `src/yfinance_mcp/server.py`
- `src/yfinance_mcp/wrapper.py`
- `src/yfinance_mcp/schemas.py`
- `src/yfinance_mcp/utils.py`
- `tests/test_tools.py`
- `tests/test_serialization.py`
- `examples/claude_config.json.example`
- `docs/PROJECT_SPEC.md`
- `docs/API_MAPPING.md`

## Architecture

### `server.py`

- Create a `FastMCP` server instance.
- Register all MCP tools in one place.
- Instantiate a shared `YFinanceWrapper` for caching, serialization, and error handling.
- Support both `stdio` and `streamable-http` execution modes.
- Expose metadata about the server version and supported `yfinance` version.
- Example structure:
  - instantiate `FastMCP` with a server name such as `yfinance`
  - create a shared wrapper instance
  - register explicit tools such as `get_info(symbol: str) -> dict`
  - start the server with either `stdio` or `streamable-http` transport

### `wrapper.py`

- Instantiate `yf.Ticker(symbol)` and `yf.Tickers(...)` lazily on demand.
- Normalize `pandas.DataFrame`, `Series`, and other non-JSON types into JSON-safe structures.
- Apply caching to read-heavy operations through an abstract cache interface.
- Centralize retries, backoff, rate-limit handling, and user-friendly errors.
- Enforce upstream timeout, concurrency, and resource-limiting policies.

### Cache Layer

- Define a cache abstraction so storage can be swapped without changing tool or wrapper logic.
- Support an in-memory cache as the default implementation for v1.
- Allow future cache backends such as SQLite, Redis, disk-backed caches, or other persistent stores.
- Keep cache key generation, TTL policy, and serialization rules independent from the backing store.
- Avoid coupling the public MCP contract to any specific cache technology.

### `schemas.py`

- Define Pydantic models for tool inputs and outputs wherever the payload is non-trivial or externally exposed.
- Use models for complex payloads such as options chains, market summaries, search results, screeners, and aggregate tool responses.
- Prefer explicit typed response models over unstructured dictionaries for stable MCP contracts.
- Serialize MCP responses from validated model instances or schema-checked structures rather than ad hoc dictionaries.

### Tool Naming and Contract Recommendations

- Use stable, explicit names such as `get_info`, `get_quote_snapshot`, `get_history`, and `download_history`.
- Prefer one tool per upstream concept instead of large polymorphic tools with many mutually exclusive parameters.
- Keep return contracts stable across transports.
- Avoid switching between JSON objects and markdown strings as the primary return type for the same tool.
- If display-friendly output is needed, return it in an auxiliary field such as `markdown_preview` while preserving a canonical structured payload.

### `utils.py`

- House serialization helpers, datetime normalization, markdown table helpers, and shared error formatting utilities.

## API Mapping Requirements

The implementation should maintain an exhaustive mapping of information-collection `yfinance` functionality to MCP tool names in `docs/API_MAPPING.md`.

### Example Mapping

| yfinance Call | MCP Tool Name | Key Parameters | Return Type |
| --- | --- | --- | --- |
| `Ticker(symbol).info` | `get_info` | `symbol: str` | `dict` |
| latest quote-style ticker snapshot | `get_quote_snapshot` | `symbol: str` | `dict` |
| `Ticker(symbol).history(...)` | `get_history` | `symbol`, `period`, `interval`, `start`, `end` | `dict` |
| `Ticker(symbol).financials` | `get_income_stmt` | `symbol`, `freq` | `dict` |
| `Ticker(symbol).balance_sheet` | `get_balance_sheet` | `symbol`, `freq` | `dict` |
| `yf.download(...)` | `download_history` | `tickers: list[str]`, `period`, others | `dict` |
| `yf.Tickers(...).tickers[...].info` | `get_batch_info` | `symbols: list[str]` | `dict` |
| `Ticker(symbol).news` | `get_news` | `symbol: str` | `list[dict]` |
| `Ticker(symbol).option_chain(...)` | `get_option_chain` | `symbol`, `date: str` | `dict` |
| `yf.Market(market).summary` | `get_market_summary` | `market: str` | `dict` |
| `yf.screen(query, ...)` | `screen` | `query`, `count`, `offset` | `dict` |

The final `API_MAPPING.md` should be exhaustive and maintained against the official `yfinance` reference.

## Data Serialization

- All tools must return JSON-serializable `dict` or `list` payloads.
- Each tool should have one canonical primary response schema.
- Canonical tool schemas should be defined and validated before serialization, preferably through Pydantic models or equivalent schema-checked structures.
- `DataFrame` values should default to a structured object with `columns`, `data`, and `index` keys.

- Where useful, the server may offer markdown table output as a fallback or optional display-oriented format.
- Large responses should support truncation, summarization, or chunking where necessary without changing the top-level schema for a tool.
- Recommended conventions:
  - use ISO 8601 for datetimes
  - preserve timezone information where available
  - represent missing numeric data as `null`
  - include paging or truncation metadata when a payload is intentionally limited

## Concurrency and Resource Limits

- The server must define bounded concurrency for upstream `yfinance` and Yahoo Finance requests.
- Shared components such as wrapper instances, HTTP clients, and cache adapters must be safe for the selected concurrency model.
- The implementation should support configurable worker and concurrency limits for batch and multi-symbol operations.
- Batch tools should avoid unbounded parallel fan-out and should degrade gracefully under constrained resources.
- Recommended controls:
  - maximum concurrent upstream requests per process
  - maximum concurrent upstream requests per MCP call
  - bounded worker pools for batch tools
  - protection against duplicate in-flight work for identical cache keys where practical

## Timeouts, Retries, and Stability

- Every upstream request path must have explicit timeout behavior.
- Retries must be bounded and limited to transient failures.
- The server should fail fast on persistent upstream errors rather than hang indefinitely.
- Cancellation and timeout behavior should leave shared state and caches consistent.
- Retry policy should distinguish between retryable and non-retryable failures.
- Recommended controls:
  - connect timeout
  - read timeout
  - total request deadline
  - bounded exponential backoff with jitter
  - optional stale-cache fallback on transient upstream failure for cacheable tools
  - explicit no-retry behavior for invalid input, unsupported symbols, and permanent upstream failures

## Error Handling and Operational Practices

- Detect and report invalid ticker symbols cleanly.
- Handle Yahoo Finance throttling, temporary blocking, and transient network failures gracefully.
- Return user-facing errors that are useful to MCP hosts and LLMs.
- Respect Yahoo Finance terms and practical usage limits through caching and conservative request behavior.
- Expose runtime configuration through environment variables such as:
  - `YF_CACHE_BACKEND`
  - `YF_CACHE_TTL`
  - `YF_CACHE_TTL_QUOTE`
  - `YF_CACHE_TTL_REFERENCE`
  - `YF_CACHE_TTL_HISTORY`
  - `YF_CACHE_PATH`
  - `YF_MAX_WORKERS`
  - `YF_TRANSPORT`
  - `YF_LOG_LEVEL`
- Recommended cache policy:
  - short TTL for quote-like and market summary data
  - medium TTL for options, news, and search results
  - longer TTL for company profile, sector, industry, and financial statement data
- Recommended operational behavior:
  - normalize cache keys so equivalent requests hit the same cache entry
  - use bounded retries with exponential backoff for transient upstream failures
  - surface upstream failures with MCP-friendly error messages that preserve context without leaking internals
  - keep cache backend selection and backend-specific settings separate from tool definitions
  - classify errors into categories such as invalid input, upstream temporary failure, upstream permanent failure, timeout, and internal server error
  - treat rate-limit and throttling responses as first-class error conditions with dedicated handling rules
  - honor upstream retry hints such as `Retry-After` when available
  - avoid retry storms by combining backoff with concurrency controls and temporary cool-down behavior

## Rate Limiting and Throttling Protection

- The server should include explicit protection against Yahoo Finance throttling and temporary blocking.
- Rate-limit handling should work together with caching, concurrency control, and retry policy.
- The implementation should distinguish between:
  - request bursts caused by one MCP call
  - sustained process-level traffic
  - repeated failures that indicate temporary upstream blocking
- Recommended protections:
  - per-process concurrency caps for upstream calls
  - per-request fan-out limits for batch operations
  - temporary cool-down or circuit-breaker behavior after repeated throttle responses
  - honoring `Retry-After` or equivalent upstream hints when present
  - serving stale cache entries for selected cacheable tools when upstream access is temporarily blocked
  - clear classification and logging of throttle, timeout, and block events
- Recommended retry policy for throttling:
  - retry only a small bounded number of times
  - apply exponential backoff with jitter between attempts
  - stop retrying when the total request deadline is exceeded
  - stop retrying on permanent failures or invalid user input

## Cache Semantics

- Cacheability rules should be defined per tool family or data category.
- Cache entries should include enough metadata to support expiration, invalidation, and optional stale fallback behavior.
- Cache serialization must be backend-independent so in-memory and persistent backends behave consistently.
- The cache interface should support future invalidation and inspection operations even if v1 uses only simple get/set semantics.
- Recommended cache behavior:
  - deterministic cache keys based on normalized tool inputs
  - TTL enforcement independent of backend implementation
  - optional stale-on-error behavior for selected cacheable tools
  - clear treatment of non-cacheable or highly volatile endpoints
  - explicit rules for which tool families may serve stale data and which must fail closed
  - quote-like and other highly time-sensitive tools should default to fail closed rather than serve stale responses unless explicitly configured otherwise

## Observability

- The server should emit structured logs for startup, tool execution, upstream request outcomes, and failures.
- Remote mode should expose sufficient health and readiness information for deployment environments.
- Logging and metrics should make it possible to diagnose latency, rate-limit issues, cache behavior, and schema failures.
- Recommended observability data:
  - request or invocation identifier
  - tool name
  - execution duration
  - upstream call count
  - cache hit or miss status
  - error category
  - transport mode

## Setup and Run

Example developer workflow:

- initialize the project with `uv init yfinance-mcp-server`
- add dependencies including `mcp[cli]`, `yfinance`, `pandas`, `cachetools`, and `structlog`
- run the server with `uv run python -m yfinance_mcp.server`

For Claude Desktop or similar MCP hosts, provide an example config using `uv run` or an absolute Python path in `examples/claude_config.json.example`.

Recommended packaging behavior:

- Use a `src/` layout with a proper console entry point or module entry point.
- Prefer `uv run python -m yfinance_mcp.server` over direct path execution to avoid import issues.
- Document both local `stdio` startup and remote `streamable-http` startup commands.
- Ensure user-facing documentation includes step-by-step instructions for installing dependencies, starting the server locally, and running the remote HTTP mode.

## Testing Strategy

- Use `mcp dev` for local inspection and manual tool validation.
- Add unit tests for serialization helpers and wrapper behavior.
- Add contract tests for each exposed tool family and shared wrapper behavior.
- Include integration coverage against known symbols such as `AAPL` and `TSLA`.
- Separate offline tests from live-network tests where possible.
- Recommended test split:
  - deterministic unit tests for serialization, schema validation, and error mapping
  - contract tests for tool signatures and response shapes
  - opt-in live tests for upstream `yfinance` behavior against known symbols

## Deployment Options

### Local

- Default transport: `stdio`
- Primary use case: local desktop MCP hosts
- This mode is required for v1.

### Remote

- Transport: `streamable-http`
- Candidate platforms:
  - Fly.io
  - Railway
  - container-based hosting platforms with long-lived Python support
- This mode is also required for v1, but initial recommendations should prioritize Python-native hosting over edge runtimes with incompatible execution models.
- Remote deployments should include health and readiness checks appropriate for the hosting platform.

### Authentication

- For remote deployments, plan for MCP-compatible OAuth or API-key-based protection where supported.

### Remote Security and Reliability

- Remote deployments should terminate TLS at a trusted layer.
- The server should define request size and concurrency limits appropriate for public or semi-public exposure.
- Health and readiness endpoints should avoid leaking sensitive runtime details.
- Proxy and forwarded-header handling should be explicit when deployed behind load balancers or ingress layers.
- If cross-origin browser access is supported, CORS behavior should be configured deliberately rather than left open by default.

## Risks and Mitigations

- Yahoo rate limits:
  - Use caching, retries, and exponential backoff.
- Upstream API changes:
  - Keep a thin wrapper layer so updates are isolated.
  - Tie MCP release versioning and compatibility notes to upstream `yfinance` releases.
- Data quality limitations:
  - Document that `yfinance` is unofficial and data may be incomplete or delayed.
- Security:
  - Keep the server read-only and avoid storing credentials.
- Transport differences:
  - keep tool contracts transport-agnostic so local and remote hosts see identical behavior

## Suggested Delivery Plan

- Week 1: Project skeleton, packaging, and core tools such as `info`, `history`, and financial statements
- Week 2: Complete API mapping, wrapper coverage, serialization, and caching
- Week 3: Tests, examples, README, and remote HTTP support
- Week 4: Documentation polish and open-source release preparation

## Future Extensions

- MCP resources for raw CSV or JSON exports
- MCP prompts for common financial analysis workflows
- Advanced screener and `EquityQuery` builder tools

## Acceptance Criteria

- The server exposes explicit MCP tools for the supported information-collection `yfinance` API surface defined by the latest supported upstream release.
- Helper tools that directly enable read-only information retrieval, such as screener query builders, are explicitly documented and versioned as part of the MCP surface when included.
- Tool signatures are typed and documented well enough for LLM host discovery.
- Returned values are consistently JSON-serializable and schema-stable.
- Local `stdio` transport works end to end.
- Remote `streamable-http` transport works end to end.
- Caching and rate-limit mitigation are built into the wrapper layer.
- Concurrency, timeout, and retry behavior are defined and enforced.
- Structured logging and basic health or readiness support exist for remote operation.
- The repository includes tests, examples, and API mapping documentation.
- The repository includes user documentation with clear run instructions for the server.
- The repository documents the supported `yfinance` version and how MCP versioning maps to it.
