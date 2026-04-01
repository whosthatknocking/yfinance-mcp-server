from __future__ import annotations

import contextlib
import os
import time
from typing import Dict, List, Optional

import structlog
import yfinance as yf
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
import uvicorn

from . import __version__
from .logging_utils import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_upstream_call_count,
    next_request_id,
)
from .schemas import (
    DownloadHistoryResult,
    DownloadRequest,
    ActionSeriesResult,
    AnalysisTableResult,
    AnalystPriceTargetsResult,
    BatchInfoResult,
    BatchQuoteSnapshotResult,
    CalendarsResult,
    CalendarResult,
    CalendarRangeRequest,
    EarningsCalendarRequest,
    EarningsDatesRequest,
    FundsDataResult,
    HistoryRequest,
    HistoryResult,
    InfoResult,
    LookupRequest,
    LookupResult,
    KeyRequest,
    MarketStatusResult,
    MarketRequest,
    MarketSummaryResult,
    MappingResult,
    NewsListResult,
    NewsRequest,
    OptionChainResult,
    OptionChainRequest,
    PeriodRequest,
    QuoteSnapshotResult,
    SearchRequest,
    SearchResult,
    SharesFullRequest,
    SectorResult,
    StatementRequest,
    StatementResult,
    StringListResult,
    SymbolRequest,
    SymbolsRequest,
    TextValueResult,
    ToolMetadata,
    IndustryResult,
)
from .wrapper import YFinanceError, YFinanceWrapper

configure_logging()
logger = structlog.get_logger(__name__)


wrapper = YFinanceWrapper()
mcp = FastMCP("yfinance")

def _run_tool(tool_name: str, operation):
    request_id = next_request_id()
    bind_request_context(request_id=request_id, tool_name=tool_name)
    started_at = time.perf_counter()
    try:
        result = operation()
    except ValidationError as exc:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.warning(
            "tool_failed",
            tool_name=tool_name,
            elapsed_ms=elapsed_ms,
            upstream_call_count=get_upstream_call_count(),
            error_type=type(exc).__name__,
        )
        clear_request_context()
        raise ValueError(exc.errors()) from exc
    except YFinanceError as exc:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        if exc.category == "timeout":
            logger.warning(
                "tool_timeout",
                tool_name=tool_name,
                elapsed_ms=elapsed_ms,
                upstream_call_count=get_upstream_call_count(),
                details=exc.details,
            )
        else:
            logger.warning(
                "tool_failed",
                tool_name=tool_name,
                elapsed_ms=elapsed_ms,
                upstream_call_count=get_upstream_call_count(),
                error_type=type(exc).__name__,
            )
        clear_request_context()
        raise ValueError(
            {"category": exc.category, "message": str(exc), "details": exc.details}
        ) from exc
    except Exception:
        clear_request_context()
        raise
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    try:
        logger.info(
            "tool_completed",
            tool_name=tool_name,
            elapsed_ms=elapsed_ms,
            upstream_call_count=get_upstream_call_count(),
        )
        return result
    finally:
        clear_request_context()


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
    http_mcp = _build_http_mcp()
    streamable_http_app = http_mcp.streamable_http_app()

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with http_mcp.session_manager.run():
            yield

    return Starlette(
        routes=[
            Route("/healthz", _healthz, methods=["GET"]),
            Route("/readyz", _readyz, methods=["GET"]),
            Mount("/mcp", app=streamable_http_app),
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
        return InfoResult.model_validate(result).model_dump(exclude_none=True)
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
        return QuoteSnapshotResult.model_validate(result).model_dump(exclude_none=True)
    return _run_tool("get_quote_snapshot", operation)


@mcp.tool()
def get_batch_info(symbols: List[str]) -> Dict[str, object]:
    """Get detailed reference information for multiple tickers.

    Use this tool for comparison workflows when you need company and profile
    metadata across several symbols in one call. For the latest quote-style
    market snapshot across multiple symbols, use `get_batch_quote_snapshot`.
    """

    def operation() -> Dict[str, object]:
        request = SymbolsRequest(symbols=symbols)
        result = wrapper.get_batch_info(**request.model_dump())
        return BatchInfoResult.model_validate(result).model_dump(exclude_none=True)

    return _run_tool("get_batch_info", operation)


@mcp.tool()
def get_batch_quote_snapshot(symbols: List[str]) -> Dict[str, object]:
    """Get the latest quote-oriented snapshot for multiple tickers.

    Use this tool for multi-symbol comparison of recent market context such as
    latest price, previous close, open, day range, and market cap. For broader
    company or profile metadata across several symbols, use `get_batch_info`.
    """

    def operation() -> Dict[str, object]:
        request = SymbolsRequest(symbols=symbols)
        result = wrapper.get_batch_quote_snapshot(**request.model_dump())
        return BatchQuoteSnapshotResult.model_validate(result).model_dump(exclude_none=True)

    return _run_tool("get_batch_quote_snapshot", operation)


@mcp.tool()
def get_batch_news(symbols: List[str]) -> List[Dict[str, object]]:
    """Get recent Yahoo Finance news across multiple tickers."""

    def operation() -> List[Dict[str, object]]:
        request = SymbolsRequest(symbols=symbols)
        result = wrapper.get_batch_news(**request.model_dump())
        return NewsListResult(items=result).model_dump(exclude_none=True)["items"]

    return _run_tool("get_batch_news", operation)


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
def get_history_metadata(symbol: str) -> Dict[str, object]:
    """Get Yahoo Finance history metadata for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_history_metadata(**request.model_dump())
        return MappingResult(values=result).model_dump()

    return _run_tool("get_history_metadata", operation)


@mcp.tool()
def get_isin(symbol: str) -> Dict[str, object]:
    """Get the ISIN for a ticker when available."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_isin(**request.model_dump())
        return TextValueResult.model_validate(result).model_dump()

    return _run_tool("get_isin", operation)


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
        return NewsListResult(items=result).model_dump(exclude_none=True)["items"]
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
def get_actions(symbol: str, period: str = "max") -> Dict[str, object]:
    """Get combined corporate actions for a ticker.

    Use this tool to retrieve the combined actions series, including dividends
    and splits where available, over a named period.
    """

    def operation() -> Dict[str, object]:
        request = PeriodRequest(symbol=symbol, period=period)
        result = wrapper.get_actions(**request.model_dump())
        return ActionSeriesResult.model_validate(result).model_dump()

    return _run_tool("get_actions", operation)


@mcp.tool()
def get_dividends(symbol: str, period: str = "max") -> Dict[str, object]:
    """Get dividend history for a ticker over a named period."""

    def operation() -> Dict[str, object]:
        request = PeriodRequest(symbol=symbol, period=period)
        result = wrapper.get_dividends(**request.model_dump())
        return ActionSeriesResult.model_validate(result).model_dump()

    return _run_tool("get_dividends", operation)


@mcp.tool()
def get_splits(symbol: str, period: str = "max") -> Dict[str, object]:
    """Get stock split history for a ticker over a named period."""

    def operation() -> Dict[str, object]:
        request = PeriodRequest(symbol=symbol, period=period)
        result = wrapper.get_splits(**request.model_dump())
        return ActionSeriesResult.model_validate(result).model_dump()

    return _run_tool("get_splits", operation)


@mcp.tool()
def get_capital_gains(symbol: str, period: str = "max") -> Dict[str, object]:
    """Get capital gains history for a fund ticker over a named period."""

    def operation() -> Dict[str, object]:
        request = PeriodRequest(symbol=symbol, period=period)
        result = wrapper.get_capital_gains(**request.model_dump())
        return ActionSeriesResult.model_validate(result).model_dump()

    return _run_tool("get_capital_gains", operation)


@mcp.tool()
def get_shares_full(symbol: str, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, object]:
    """Get extended share-count history for a ticker."""

    def operation() -> Dict[str, object]:
        request = SharesFullRequest(symbol=symbol, start=start, end=end)
        result = wrapper.get_shares_full(**request.model_dump())
        return ActionSeriesResult.model_validate(result).model_dump()

    return _run_tool("get_shares_full", operation)


@mcp.tool()
def get_sec_filings(symbol: str) -> List[Dict[str, object]]:
    """Get SEC filings metadata for a ticker."""

    def operation() -> List[Dict[str, object]]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_sec_filings(**request.model_dump())
        return NewsListResult(items=result).model_dump(exclude_none=True)["items"]

    return _run_tool("get_sec_filings", operation)


@mcp.tool()
def get_earnings_dates(symbol: str, limit: int = 12, offset: int = 0) -> Dict[str, object]:
    """Get historical and upcoming earnings dates for a ticker.

    Use this tool when the user asks about earnings events, earnings timing, or
    recent earnings history for a specific symbol.
    """

    def operation() -> Dict[str, object]:
        request = EarningsDatesRequest(symbol=symbol, limit=limit, offset=offset)
        result = wrapper.get_earnings_dates(**request.model_dump())
        return HistoryResult.model_validate(result).model_dump()

    return _run_tool("get_earnings_dates", operation)


@mcp.tool()
def get_ticker_calendar(symbol: str) -> Dict[str, object]:
    """Get calendar and event summary data for a ticker.

    Use this tool for earnings-event context, dividend dates, and related
    calendar-style company event fields for a single ticker.
    """

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_ticker_calendar(**request.model_dump())
        return CalendarResult.model_validate(result).model_dump(exclude_none=True)

    return _run_tool("get_ticker_calendar", operation)


@mcp.tool()
def get_recommendations(symbol: str) -> Dict[str, object]:
    """Get analyst recommendation summary data for a ticker.

    Use this tool when the user asks for recommendation trends, buy/hold/sell
    counts, or recent analyst sentiment for a symbol.
    """

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_recommendations(**request.model_dump())
        return HistoryResult.model_validate(result).model_dump()

    return _run_tool("get_recommendations", operation)


@mcp.tool()
def get_analyst_price_targets(symbol: str) -> Dict[str, object]:
    """Get analyst price target summary data for a ticker.

    Use this tool when the user asks for consensus analyst target levels or the
    current, mean, high, low, and median target prices for a symbol.
    """

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_analyst_price_targets(**request.model_dump())
        return AnalystPriceTargetsResult.model_validate(result).model_dump(exclude_none=True)

    return _run_tool("get_analyst_price_targets", operation)


@mcp.tool()
def get_recommendations_summary(symbol: str) -> Dict[str, object]:
    """Get recommendation summary aggregates for a ticker.

    Use this tool for higher-level analyst recommendation rollups rather than
    the fuller recommendations table from `get_recommendations`.
    """

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_recommendations_summary(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_recommendations_summary", operation)


@mcp.tool()
def get_upgrades_downgrades(symbol: str) -> Dict[str, object]:
    """Get broker upgrades and downgrades for a ticker.

    Use this tool when the user asks about analyst rating changes or recent
    broker actions affecting a symbol.
    """

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_upgrades_downgrades(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_upgrades_downgrades", operation)


@mcp.tool()
def get_earnings_estimate(symbol: str) -> Dict[str, object]:
    """Get analyst earnings estimate data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_earnings_estimate(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_earnings_estimate", operation)


@mcp.tool()
def get_revenue_estimate(symbol: str) -> Dict[str, object]:
    """Get analyst revenue estimate data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_revenue_estimate(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_revenue_estimate", operation)


@mcp.tool()
def get_earnings_history(symbol: str) -> Dict[str, object]:
    """Get historical earnings surprise and estimate data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_earnings_history(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_earnings_history", operation)


@mcp.tool()
def get_eps_trend(symbol: str) -> Dict[str, object]:
    """Get EPS trend data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_eps_trend(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_eps_trend", operation)


@mcp.tool()
def get_eps_revisions(symbol: str) -> Dict[str, object]:
    """Get EPS revision data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_eps_revisions(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_eps_revisions", operation)


@mcp.tool()
def get_growth_estimates(symbol: str) -> Dict[str, object]:
    """Get analyst growth estimate data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_growth_estimates(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_growth_estimates", operation)


@mcp.tool()
def get_sustainability(symbol: str) -> Dict[str, object]:
    """Get sustainability and ESG-related data for a ticker when available."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_sustainability(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_sustainability", operation)


@mcp.tool()
def get_major_holders(symbol: str) -> Dict[str, object]:
    """Get major holders data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_major_holders(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_major_holders", operation)


@mcp.tool()
def get_institutional_holders(symbol: str) -> Dict[str, object]:
    """Get institutional holders data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_institutional_holders(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_institutional_holders", operation)


@mcp.tool()
def get_mutualfund_holders(symbol: str) -> Dict[str, object]:
    """Get mutual fund holders data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_mutualfund_holders(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_mutualfund_holders", operation)


@mcp.tool()
def get_insider_purchases(symbol: str) -> Dict[str, object]:
    """Get insider purchases data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_insider_purchases(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_insider_purchases", operation)


@mcp.tool()
def get_insider_transactions(symbol: str) -> Dict[str, object]:
    """Get insider transactions data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_insider_transactions(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_insider_transactions", operation)


@mcp.tool()
def get_insider_roster_holders(symbol: str) -> Dict[str, object]:
    """Get insider roster holders data for a ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_insider_roster_holders(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_insider_roster_holders", operation)


@mcp.tool()
def get_funds_data(symbol: str) -> Dict[str, object]:
    """Get the aggregate funds-data bundle for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_funds_data(**request.model_dump())
        return FundsDataResult.model_validate(result).model_dump()

    return _run_tool("get_funds_data", operation)


@mcp.tool()
def get_fund_asset_classes(symbol: str) -> Dict[str, object]:
    """Get fund asset-class allocations for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_fund_asset_classes(**request.model_dump())
        return MappingResult(values=result).model_dump()

    return _run_tool("get_fund_asset_classes", operation)


@mcp.tool()
def get_fund_bond_holdings(symbol: str) -> Dict[str, object]:
    """Get bond holdings summary data for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_fund_bond_holdings(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_fund_bond_holdings", operation)


@mcp.tool()
def get_fund_bond_ratings(symbol: str) -> Dict[str, object]:
    """Get bond ratings allocations for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_fund_bond_ratings(**request.model_dump())
        return MappingResult(values=result).model_dump()

    return _run_tool("get_fund_bond_ratings", operation)


@mcp.tool()
def get_fund_description(symbol: str) -> Dict[str, object]:
    """Get descriptive text for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_fund_description(**request.model_dump())
        return TextValueResult.model_validate(result).model_dump()

    return _run_tool("get_fund_description", operation)


@mcp.tool()
def get_fund_equity_holdings(symbol: str) -> Dict[str, object]:
    """Get equity holdings summary data for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_fund_equity_holdings(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_fund_equity_holdings", operation)


@mcp.tool()
def get_fund_operations(symbol: str) -> Dict[str, object]:
    """Get fund operations summary data for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_fund_operations(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_fund_operations", operation)


@mcp.tool()
def get_fund_overview(symbol: str) -> Dict[str, object]:
    """Get high-level overview metadata for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_fund_overview(**request.model_dump())
        return MappingResult(values=result).model_dump()

    return _run_tool("get_fund_overview", operation)


@mcp.tool()
def get_fund_sector_weightings(symbol: str) -> Dict[str, object]:
    """Get sector weightings for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_fund_sector_weightings(**request.model_dump())
        return MappingResult(values=result).model_dump()

    return _run_tool("get_fund_sector_weightings", operation)


@mcp.tool()
def get_fund_top_holdings(symbol: str) -> Dict[str, object]:
    """Get top holdings for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_fund_top_holdings(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_fund_top_holdings", operation)


@mcp.tool()
def get_fund_quote_type(symbol: str) -> Dict[str, object]:
    """Get the fund quote type classification for an ETF or fund ticker."""

    def operation() -> Dict[str, object]:
        request = SymbolRequest(symbol=symbol)
        result = wrapper.get_fund_quote_type(**request.model_dump())
        return TextValueResult.model_validate(result).model_dump()

    return _run_tool("get_fund_quote_type", operation)


@mcp.tool()
def get_calendars(
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 12,
    offset: int = 0,
    force: bool = False,
    market_cap: Optional[float] = None,
    filter_most_active: bool = True,
) -> Dict[str, object]:
    """Get the aggregate Yahoo Finance calendars bundle for a date range."""

    def operation() -> Dict[str, object]:
        request = EarningsCalendarRequest(
            start=start,
            end=end,
            limit=limit,
            offset=offset,
            force=force,
            market_cap=market_cap,
            filter_most_active=filter_most_active,
        )
        result = wrapper.get_calendars(**request.model_dump())
        return CalendarsResult.model_validate(result).model_dump()

    return _run_tool("get_calendars", operation)


@mcp.tool()
def get_earnings_calendar(
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 12,
    offset: int = 0,
    force: bool = False,
    market_cap: Optional[float] = None,
    filter_most_active: bool = True,
) -> Dict[str, object]:
    """Get the Yahoo Finance earnings calendar for a date range."""

    def operation() -> Dict[str, object]:
        request = EarningsCalendarRequest(
            start=start,
            end=end,
            limit=limit,
            offset=offset,
            force=force,
            market_cap=market_cap,
            filter_most_active=filter_most_active,
        )
        result = wrapper.get_earnings_calendar(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_earnings_calendar", operation)


@mcp.tool()
def get_economic_events_calendar(
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 12,
    offset: int = 0,
    force: bool = False,
) -> Dict[str, object]:
    """Get the Yahoo Finance economic events calendar for a date range."""

    def operation() -> Dict[str, object]:
        request = CalendarRangeRequest(start=start, end=end, limit=limit, offset=offset, force=force)
        result = wrapper.get_economic_events_calendar(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_economic_events_calendar", operation)


@mcp.tool()
def get_ipo_calendar(
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 12,
    offset: int = 0,
    force: bool = False,
) -> Dict[str, object]:
    """Get the Yahoo Finance IPO calendar for a date range."""

    def operation() -> Dict[str, object]:
        request = CalendarRangeRequest(start=start, end=end, limit=limit, offset=offset, force=force)
        result = wrapper.get_ipo_calendar(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_ipo_calendar", operation)


@mcp.tool()
def get_splits_calendar(
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 12,
    offset: int = 0,
    force: bool = False,
) -> Dict[str, object]:
    """Get the Yahoo Finance splits calendar for a date range."""

    def operation() -> Dict[str, object]:
        request = CalendarRangeRequest(start=start, end=end, limit=limit, offset=offset, force=force)
        result = wrapper.get_splits_calendar(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_splits_calendar", operation)


@mcp.tool()
def get_sector(key: str) -> Dict[str, object]:
    """Get aggregate sector overview and linked data for a Yahoo Finance sector key."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_sector(**request.model_dump())
        return SectorResult.model_validate(result).model_dump()

    return _run_tool("get_sector", operation)


@mcp.tool()
def get_sector_overview(key: str) -> Dict[str, object]:
    """Get sector overview metadata for a Yahoo Finance sector key."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_sector_overview(**request.model_dump())
        return MappingResult(values=result).model_dump()

    return _run_tool("get_sector_overview", operation)


@mcp.tool()
def get_sector_research_reports(key: str) -> List[Dict[str, object]]:
    """Get sector research reports for a Yahoo Finance sector key."""

    def operation() -> List[Dict[str, object]]:
        request = KeyRequest(key=key)
        result = wrapper.get_sector_research_reports(**request.model_dump())
        return result

    return _run_tool("get_sector_research_reports", operation)


@mcp.tool()
def get_sector_industries(key: str) -> Dict[str, object]:
    """Get industries within a Yahoo Finance sector."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_sector_industries(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_sector_industries", operation)


@mcp.tool()
def get_sector_top_companies(key: str) -> Dict[str, object]:
    """Get top companies within a Yahoo Finance sector."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_sector_top_companies(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_sector_top_companies", operation)


@mcp.tool()
def get_sector_top_etfs(key: str) -> Dict[str, object]:
    """Get top ETFs for a Yahoo Finance sector."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_sector_top_etfs(**request.model_dump())
        return MappingResult(values=result).model_dump()

    return _run_tool("get_sector_top_etfs", operation)


@mcp.tool()
def get_sector_top_mutual_funds(key: str) -> Dict[str, object]:
    """Get top mutual funds for a Yahoo Finance sector."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_sector_top_mutual_funds(**request.model_dump())
        return MappingResult(values=result).model_dump()

    return _run_tool("get_sector_top_mutual_funds", operation)


@mcp.tool()
def get_sector_ticker(key: str) -> Dict[str, object]:
    """Get the ticker symbol associated with a Yahoo Finance sector."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_sector_ticker(**request.model_dump())
        return TextValueResult.model_validate(result).model_dump()

    return _run_tool("get_sector_ticker", operation)


@mcp.tool()
def get_industry(key: str) -> Dict[str, object]:
    """Get aggregate industry overview and linked data for a Yahoo Finance industry key."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_industry(**request.model_dump())
        return IndustryResult.model_validate(result).model_dump()

    return _run_tool("get_industry", operation)


@mcp.tool()
def get_industry_overview(key: str) -> Dict[str, object]:
    """Get industry overview metadata for a Yahoo Finance industry key."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_industry_overview(**request.model_dump())
        return MappingResult(values=result).model_dump()

    return _run_tool("get_industry_overview", operation)


@mcp.tool()
def get_industry_research_reports(key: str) -> List[Dict[str, object]]:
    """Get industry research reports for a Yahoo Finance industry key."""

    def operation() -> List[Dict[str, object]]:
        request = KeyRequest(key=key)
        result = wrapper.get_industry_research_reports(**request.model_dump())
        return result

    return _run_tool("get_industry_research_reports", operation)


@mcp.tool()
def get_industry_top_companies(key: str) -> Dict[str, object]:
    """Get top companies within a Yahoo Finance industry."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_industry_top_companies(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_industry_top_companies", operation)


@mcp.tool()
def get_industry_top_growth_companies(key: str) -> Dict[str, object]:
    """Get top growth companies within a Yahoo Finance industry."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_industry_top_growth_companies(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_industry_top_growth_companies", operation)


@mcp.tool()
def get_industry_top_performing_companies(key: str) -> Dict[str, object]:
    """Get top performing companies within a Yahoo Finance industry."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_industry_top_performing_companies(**request.model_dump())
        return AnalysisTableResult.model_validate(result).model_dump()

    return _run_tool("get_industry_top_performing_companies", operation)


@mcp.tool()
def get_industry_ticker(key: str) -> Dict[str, object]:
    """Get the ticker symbol associated with a Yahoo Finance industry."""

    def operation() -> Dict[str, object]:
        request = KeyRequest(key=key)
        result = wrapper.get_industry_ticker(**request.model_dump())
        return TextValueResult.model_validate(result).model_dump()

    return _run_tool("get_industry_ticker", operation)


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
        return MarketSummaryResult.model_validate(result).model_dump(exclude_none=True)
    return _run_tool("get_market_summary", operation)


@mcp.tool()
def get_market(market: str) -> Dict[str, object]:
    """Get Yahoo Finance market summary and status data for a market code.

    Use this tool when you want the combined market-level payload in one call.
    For status-only requests, use `get_market_status`.
    """

    def operation() -> Dict[str, object]:
        request = MarketRequest(market=market)
        result = wrapper.get_market(**request.model_dump())
        return MarketSummaryResult.model_validate(result).model_dump(exclude_none=True)

    return _run_tool("get_market", operation)


@mcp.tool()
def get_market_status(market: str) -> Dict[str, object]:
    """Get Yahoo Finance market status data for a market code."""

    def operation() -> Dict[str, object]:
        request = MarketRequest(market=market)
        result = wrapper.get_market_status(**request.model_dump())
        return MarketStatusResult.model_validate(result).model_dump(exclude_none=True)

    return _run_tool("get_market_status", operation)


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


def _tool_functions():
    return [
        get_server_metadata,
        get_info,
        get_quote_snapshot,
        get_batch_info,
        get_batch_quote_snapshot,
        get_batch_news,
        get_history,
        get_history_metadata,
        get_isin,
        download_history,
        get_news,
        get_option_expirations,
        get_option_chain,
        get_actions,
        get_dividends,
        get_splits,
        get_capital_gains,
        get_shares_full,
        get_sec_filings,
        get_earnings_dates,
        get_ticker_calendar,
        get_recommendations,
        get_analyst_price_targets,
        get_recommendations_summary,
        get_upgrades_downgrades,
        get_earnings_estimate,
        get_revenue_estimate,
        get_earnings_history,
        get_eps_trend,
        get_eps_revisions,
        get_growth_estimates,
        get_sustainability,
        get_major_holders,
        get_institutional_holders,
        get_mutualfund_holders,
        get_insider_purchases,
        get_insider_transactions,
        get_insider_roster_holders,
        get_funds_data,
        get_fund_asset_classes,
        get_fund_bond_holdings,
        get_fund_bond_ratings,
        get_fund_description,
        get_fund_equity_holdings,
        get_fund_operations,
        get_fund_overview,
        get_fund_sector_weightings,
        get_fund_top_holdings,
        get_fund_quote_type,
        get_calendars,
        get_earnings_calendar,
        get_economic_events_calendar,
        get_ipo_calendar,
        get_splits_calendar,
        get_sector,
        get_sector_overview,
        get_sector_research_reports,
        get_sector_industries,
        get_sector_top_companies,
        get_sector_top_etfs,
        get_sector_top_mutual_funds,
        get_sector_ticker,
        get_industry,
        get_industry_overview,
        get_industry_research_reports,
        get_industry_top_companies,
        get_industry_top_growth_companies,
        get_industry_top_performing_companies,
        get_industry_ticker,
        get_income_stmt,
        get_balance_sheet,
        get_cashflow,
        get_market_summary,
        get_market,
        get_market_status,
        search,
        lookup,
    ]


def _build_http_mcp() -> FastMCP:
    http_mcp = FastMCP("yfinance")
    for tool_fn in _tool_functions():
        http_mcp.add_tool(tool_fn)
    return http_mcp


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
