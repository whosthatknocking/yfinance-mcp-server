from __future__ import annotations

import os
from typing import Dict, List, Optional

import structlog
import yfinance as yf
from pydantic import ValidationError

from . import __version__
from .logging_utils import configure_logging
from .schemas import (
    DownloadRequest,
    HistoryRequest,
    JsonListResult,
    JsonObjectResult,
    MarketRequest,
    NewsRequest,
    OptionChainResult,
    OptionChainRequest,
    StatementRequest,
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


@mcp.tool()
def get_server_metadata() -> Dict[str, object]:
    """Return server metadata.

    Use this tool to inspect the MCP server version, supported yfinance version,
    transport modes, and active cache backend. It is useful for environment
    checks and compatibility debugging.
    """
    try:
        metadata = ToolMetadata(**wrapper.get_metadata())
        return metadata.model_dump()
    except Exception as exc:  # pragma: no cover - exercised through MCP runtime
        _handle_error(exc)


@mcp.tool()
def get_info(symbol: str) -> Dict[str, object]:
    """Get detailed company and profile information for a single ticker.

    Use this tool for reference-style data such as company profile fields,
    exchange metadata, business summary information, and other broad ticker
    details. For a lighter quote snapshot, use `get_fast_info` instead.
    """
    try:
        result = wrapper.get_info(symbol)
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_quote_snapshot(symbol: str) -> Dict[str, object]:
    """Get the latest quote-oriented snapshot for a single ticker.

    Use this tool when the request is about the latest stock information, latest
    market snapshot, current trading context, or a quick symbol overview. This
    tool is intended for quote-style stock lookups such as latest price, market
    cap, and recent trading context. For richer company profile information, use
    `get_info`.
    """
    try:
        result = wrapper.get_fast_info(symbol)
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


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
    range. For multi-ticker historical retrieval, use `download`.
    """
    try:
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
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


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
    try:
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
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_news(symbol: str, count: int = 10, tab: str = "news") -> List[Dict[str, object]]:
    """Get recent Yahoo Finance news for a ticker.

    Use this tool to retrieve recent article metadata tied to a symbol. It is
    useful for event-driven analysis, sentiment review, and contextualizing
    recent market moves.
    """
    try:
        request = NewsRequest(symbol=symbol, count=count, tab=tab)
        result = wrapper.get_news(**request.model_dump())
        return JsonListResult(items=result).items
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_option_expirations(symbol: str) -> List[str]:
    """Get available option expiration dates for a ticker.

    Use this tool before `get_option_chain` when you need to discover which
    option expiration dates are available for a symbol.
    """
    try:
        result = wrapper.get_option_expirations(symbol)
        return JsonListResult(items=result).items
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_option_chain(symbol: str, date: Optional[str] = None) -> Dict[str, object]:
    """Get calls and puts for a ticker option chain.

    Use this tool for options analysis after you know the desired expiration
    date. Pair it with `get_option_expirations` when you need to discover valid
    dates first.
    """
    try:
        request = OptionChainRequest(symbol=symbol, date=date)
        result = wrapper.get_option_chain(**request.model_dump())
        return OptionChainResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_income_stmt(symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, object]:
    """Get income statement data for a ticker.

    Use this tool for annual, quarterly, or trailing income statement analysis.
    It is best suited for revenue, margin, and profitability review.
    """
    try:
        request = StatementRequest(symbol=symbol, freq=freq, pretty=pretty)
        result = wrapper.get_income_stmt(**request.model_dump())
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_balance_sheet(symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, object]:
    """Get balance sheet data for a ticker.

    Use this tool for annual or quarterly balance sheet analysis such as assets,
    liabilities, and capital structure review.
    """
    try:
        request = StatementRequest(symbol=symbol, freq=freq, pretty=pretty)
        result = wrapper.get_balance_sheet(**request.model_dump())
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_cashflow(symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, object]:
    """Get cashflow statement data for a ticker.

    Use this tool for annual, quarterly, or trailing cashflow analysis,
    including operating cashflow, investing activity, and free-cash-flow style
    review.
    """
    try:
        request = StatementRequest(symbol=symbol, freq=freq, pretty=pretty)
        result = wrapper.get_cashflow(**request.model_dump())
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_market_summary(market: str) -> Dict[str, object]:
    """Get Yahoo Finance market summary data for a market code.

    Use this tool when you need a market-level overview rather than a
    single-ticker lookup. For example, it can provide a quick view of the US
    market summary.
    """
    try:
        request = MarketRequest(market=market)
        result = wrapper.get_market_summary(**request.model_dump())
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


def main() -> None:
    transport = os.getenv("YF_TRANSPORT", "stdio")
    logger.info(
        "starting_server",
        transport=transport,
        server_version=__version__,
        yfinance_version=getattr(yf, "__version__", "unknown"),
    )
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=os.getenv("YF_HTTP_HOST", "127.0.0.1"),
            port=int(os.getenv("YF_HTTP_PORT", "8000")),
        )
        return
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
