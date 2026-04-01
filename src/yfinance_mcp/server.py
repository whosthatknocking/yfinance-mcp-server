from __future__ import annotations

import contextlib
import os
import time
from typing import Dict, List, Optional

import structlog
import yfinance as yf
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
import uvicorn

from . import __version__
from .logging_utils import configure_logging
from .schemas import (
    DownloadHistoryResult,
    DownloadRequest,
    HistoryRequest,
    HistoryResult,
    InfoResult,
    LookupRequest,
    LookupResult,
    MarketRequest,
    MarketSummaryResult,
    NewsListResult,
    NewsRequest,
    OptionChainResult,
    OptionChainRequest,
    QuoteSnapshotResult,
    SearchRequest,
    SearchResult,
    StatementRequest,
    StatementResult,
    StringListResult,
    ToolMetadata,
)
from mcp.server.fastmcp import FastMCP

configure_logging()
logger = structlog.get_logger(__name__)

from .wrapper import YFinanceError, YFinanceWrapper


wrapper = YFinanceWrapper()
mcp = FastMCP("yfinance")


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, ValidationError):
        raise ValueError(exc.errors()) from exc
    if isinstance(exc, YFinanceError):
        raise ValueError({"category": exc.category, "message": str(exc), "details": exc.details}) from exc
    raise


def _run_tool(tool_name: str, operation):
    started_at = time.perf_counter()
    try:
        result = operation()
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        if isinstance(exc, YFinanceError) and exc.category == "timeout":
            logger.warning("tool_timeout", tool_name=tool_name, elapsed_ms=elapsed_ms, details=exc.details)
        else:
            logger.warning("tool_failed", tool_name=tool_name, elapsed_ms=elapsed_ms, error_type=type(exc).__name__)
        _handle_error(exc)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info("tool_completed", tool_name=tool_name, elapsed_ms=elapsed_ms)
    return result


async def _healthz(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def _readyz(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ready",
            "server_name": "yfinance",
            "server_version": __version__,
            "supported_yfinance_version": getattr(yf, "__version__", "unknown"),
            "cache_backend": wrapper.cache_backend_name,
        }
    )


def _build_http_app() -> Starlette:
    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp.session_manager.run():
            yield

    return Starlette(
        routes=[
            Route("/healthz", _healthz, methods=["GET"]),
            Route("/readyz", _readyz, methods=["GET"]),
            Mount("/mcp", app=mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )


@mcp.tool()
def get_server_metadata() -> Dict[str, object]:
    """Return server metadata.

    Use this tool to inspect the MCP server version, supported yfinance version,
    transport modes, and active cache backend. It is useful for environment
    checks and compatibility debugging.
    """
    def operation() -> Dict[str, object]:
        metadata = ToolMetadata(**wrapper.get_metadata())
        return metadata.model_dump()
    return _run_tool("get_server_metadata", operation)


@mcp.tool()
def get_info(symbol: str) -> Dict[str, object]:
    """Get detailed company and profile information for a single ticker.

    Use this tool for reference-style data such as company profile fields,
    exchange metadata, business summary information, and other broad ticker
    details. For a lighter quote snapshot, use `get_quote_snapshot` instead.
    """
    def operation() -> Dict[str, object]:
        result = wrapper.get_info(symbol)
        return InfoResult.model_validate(result).model_dump()
    return _run_tool("get_info", operation)


@mcp.tool()
def get_quote_snapshot(symbol: str) -> Dict[str, object]:
    """Get the latest quote-oriented snapshot for a single ticker.

    Use this tool when the request is about the latest stock information, latest
    stock price, current trading context, or a quick symbol overview for an
    individual ticker such as AAPL or TSLA. This tool is intended for
    quote-style stock lookups such as latest price, market cap, and recent
    trading context. It is the right tool for ticker-specific price questions,
    not `get_market_summary`. For richer company profile information, use
    `get_info`.
    """
    def operation() -> Dict[str, object]:
        result = wrapper.get_fast_info(symbol)
        return QuoteSnapshotResult.model_validate(result).model_dump()
    return _run_tool("get_quote_snapshot", operation)


@mcp.tool()
def get_history(
    symbol: str,
    period: Optional[str] = None,
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    prepost: bool = False,
    auto_adjust: bool = True,
    actions: bool = True,
) -> Dict[str, object]:
    """Get historical price candles for a single ticker.

    Use this tool for charting, trend analysis, and recent performance review.
    It supports either a named lookback period or an explicit start/end date
    range. For multi-ticker historical retrieval, use `download_history`.
    """
    def operation() -> Dict[str, object]:
        request = HistoryRequest(
            symbol=symbol,
            period=period,
            interval=interval,
            start=start,
            end=end,
            prepost=prepost,
            auto_adjust=auto_adjust,
            actions=actions,
        )
        result = wrapper.get_history(**request.model_dump())
        return HistoryResult.model_validate(result).model_dump()
    return _run_tool("get_history", operation)


@mcp.tool()
def download_history(
    tickers: List[str],
    period: Optional[str] = None,
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    auto_adjust: bool = True,
    prepost: bool = False,
    actions: bool = False,
) -> Dict[str, object]:
    """Download historical price data for one or more tickers.

    Use this tool when you need a batch historical dataset across multiple
    symbols. For a single ticker history request, `get_history` is usually the
    better fit.
    """
    def operation() -> Dict[str, object]:
        request = DownloadRequest(
            tickers=tickers,
            period=period,
            interval=interval,
            start=start,
            end=end,
            auto_adjust=auto_adjust,
            prepost=prepost,
            actions=actions,
        )
        result = wrapper.download(**request.model_dump())
        return DownloadHistoryResult.model_validate(result).model_dump()
    return _run_tool("download_history", operation)


@mcp.tool()
def get_news(symbol: str, count: int = 10, tab: str = "news") -> List[Dict[str, object]]:
    """Get recent Yahoo Finance news for a ticker.

    Use this tool to retrieve recent article metadata tied to a symbol. It is
    useful for event-driven analysis, sentiment review, and contextualizing
    recent market moves.
    """
    def operation() -> List[Dict[str, object]]:
        request = NewsRequest(symbol=symbol, count=count, tab=tab)
        result = wrapper.get_news(**request.model_dump())
        return NewsListResult(items=result).model_dump()["items"]
    return _run_tool("get_news", operation)


@mcp.tool()
def get_option_expirations(symbol: str) -> List[str]:
    """Get available option expiration dates for a ticker.

    Use this tool before `get_option_chain` when you need to discover which
    option expiration dates are available for a symbol.
    """
    def operation() -> List[str]:
        result = wrapper.get_option_expirations(symbol)
        return StringListResult(items=result).items
    return _run_tool("get_option_expirations", operation)


@mcp.tool()
def get_option_chain(symbol: str, date: Optional[str] = None) -> Dict[str, object]:
    """Get calls and puts for a ticker option chain.

    Use this tool for options analysis after you know the desired expiration
    date. Pair it with `get_option_expirations` when you need to discover valid
    dates first.
    """
    def operation() -> Dict[str, object]:
        request = OptionChainRequest(symbol=symbol, date=date)
        result = wrapper.get_option_chain(**request.model_dump())
        return OptionChainResult.model_validate(result).model_dump()
    return _run_tool("get_option_chain", operation)


@mcp.tool()
def get_income_stmt(symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, object]:
    """Get income statement data for a ticker.

    Use this tool for annual, quarterly, or trailing income statement analysis.
    It is best suited for revenue, margin, and profitability review.
    """
    def operation() -> Dict[str, object]:
        request = StatementRequest(symbol=symbol, freq=freq, pretty=pretty)
        result = wrapper.get_income_stmt(**request.model_dump())
        return StatementResult.model_validate(result).model_dump()
    return _run_tool("get_income_stmt", operation)


@mcp.tool()
def get_balance_sheet(symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, object]:
    """Get balance sheet data for a ticker.

    Use this tool for annual or quarterly balance sheet analysis such as assets,
    liabilities, and capital structure review.
    """
    def operation() -> Dict[str, object]:
        request = StatementRequest(symbol=symbol, freq=freq, pretty=pretty)
        result = wrapper.get_balance_sheet(**request.model_dump())
        return StatementResult.model_validate(result).model_dump()
    return _run_tool("get_balance_sheet", operation)


@mcp.tool()
def get_cashflow(symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, object]:
    """Get cashflow statement data for a ticker.

    Use this tool for annual, quarterly, or trailing cashflow analysis,
    including operating cashflow, investing activity, and free-cash-flow style
    review.
    """
    def operation() -> Dict[str, object]:
        request = StatementRequest(symbol=symbol, freq=freq, pretty=pretty)
        result = wrapper.get_cashflow(**request.model_dump())
        return StatementResult.model_validate(result).model_dump()
    return _run_tool("get_cashflow", operation)


@mcp.tool()
def get_market_summary(market: str) -> Dict[str, object]:
    """Get Yahoo Finance market summary data for a market code.

    Use this tool when you need a market-level overview rather than a
    single-ticker lookup. The `market` argument must be a Yahoo Finance market
    code such as `us` or `ca`, not a ticker symbol like AAPL or TSLA. For
    ticker-specific quote or price questions, use `get_quote_snapshot`.
    """
    def operation() -> Dict[str, object]:
        request = MarketRequest(market=market)
        result = wrapper.get_market_summary(**request.model_dump())
        return MarketSummaryResult.model_validate(result).model_dump()
    return _run_tool("get_market_summary", operation)


@mcp.tool()
def search(
    query: str,
    max_results: int = 8,
    news_count: int = 8,
    lists_count: int = 8,
    include_cb: bool = True,
    include_nav_links: bool = False,
    include_research: bool = False,
    include_cultural_assets: bool = False,
    enable_fuzzy_query: bool = False,
    recommended: int = 8,
) -> Dict[str, object]:
    """Search Yahoo Finance for companies, tickers, and related news.

    Use this tool when the user provides a company name, ambiguous symbol, or
    discovery-oriented prompt and you need quote matches plus related news or
    navigation results. This is the best starting point when you do not yet have
    a specific ticker symbol.
    """

    def operation() -> Dict[str, object]:
        request = SearchRequest(
            query=query,
            max_results=max_results,
            news_count=news_count,
            lists_count=lists_count,
            include_cb=include_cb,
            include_nav_links=include_nav_links,
            include_research=include_research,
            include_cultural_assets=include_cultural_assets,
            enable_fuzzy_query=enable_fuzzy_query,
            recommended=recommended,
        )
        result = wrapper.search(**request.model_dump())
        return SearchResult.model_validate(result).model_dump()

    return _run_tool("search", operation)


@mcp.tool()
def lookup(query: str, count: int = 25) -> Dict[str, object]:
    """Look up matching financial instruments grouped by instrument type.

    Use this tool when you need categorized discovery results such as stocks,
    ETFs, mutual funds, indices, futures, currencies, or cryptocurrencies for a
    query like a company name, symbol, or asset keyword.
    """

    def operation() -> Dict[str, object]:
        request = LookupRequest(query=query, count=count)
        result = wrapper.lookup(**request.model_dump())
        return LookupResult.model_validate(result).model_dump()

    return _run_tool("lookup", operation)


def main() -> None:
    transport = os.getenv("YF_TRANSPORT", "stdio")
    logger.info(
        "starting_server",
        transport=transport,
        server_version=__version__,
        yfinance_version=getattr(yf, "__version__", "unknown"),
    )
    if transport == "streamable-http":
        app = _build_http_app()
        uvicorn.run(
            app,
            host=os.getenv("YF_HTTP_HOST", "127.0.0.1"),
            port=int(os.getenv("YF_HTTP_PORT", "8000")),
            log_level=os.getenv("YF_UVICORN_LOG_LEVEL", "info").lower(),
        )
        return
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
