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
    """Return MCP server metadata, supported yfinance version, and transport modes."""
    try:
        metadata = ToolMetadata(**wrapper.get_metadata())
        return metadata.model_dump()
    except Exception as exc:  # pragma: no cover - exercised through MCP runtime
        _handle_error(exc)


@mcp.tool()
def get_info(symbol: str) -> Dict[str, object]:
    """Get comprehensive company and profile information for a ticker symbol."""
    try:
        result = wrapper.get_info(symbol)
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_fast_info(symbol: str) -> Dict[str, object]:
    """Get a lightweight quote and profile snapshot for a ticker symbol."""
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
    """Get historical OHLCV data for a ticker symbol."""
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
def download(
    tickers: List[str],
    period: Optional[str] = None,
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    auto_adjust: bool = True,
    prepost: bool = False,
    actions: bool = False,
) -> Dict[str, object]:
    """Download historical data for one or more ticker symbols."""
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
    """Get Yahoo Finance news results for a ticker symbol."""
    try:
        request = NewsRequest(symbol=symbol, count=count, tab=tab)
        result = wrapper.get_news(**request.model_dump())
        return JsonListResult(items=result).items
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_option_expirations(symbol: str) -> List[str]:
    """Get available option expiration dates for a ticker symbol."""
    try:
        result = wrapper.get_option_expirations(symbol)
        return JsonListResult(items=result).items
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_option_chain(symbol: str, date: Optional[str] = None) -> Dict[str, object]:
    """Get calls and puts for a ticker symbol option chain."""
    try:
        request = OptionChainRequest(symbol=symbol, date=date)
        result = wrapper.get_option_chain(**request.model_dump())
        return OptionChainResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_income_stmt(symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, object]:
    """Get yearly, quarterly, or trailing income statement data for a ticker symbol."""
    try:
        request = StatementRequest(symbol=symbol, freq=freq, pretty=pretty)
        result = wrapper.get_income_stmt(**request.model_dump())
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_balance_sheet(symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, object]:
    """Get yearly or quarterly balance sheet data for a ticker symbol."""
    try:
        request = StatementRequest(symbol=symbol, freq=freq, pretty=pretty)
        result = wrapper.get_balance_sheet(**request.model_dump())
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_cashflow(symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, object]:
    """Get yearly, quarterly, or trailing cashflow data for a ticker symbol."""
    try:
        request = StatementRequest(symbol=symbol, freq=freq, pretty=pretty)
        result = wrapper.get_cashflow(**request.model_dump())
        return JsonObjectResult.model_validate(result).model_dump()
    except Exception as exc:
        _handle_error(exc)


@mcp.tool()
def get_market_summary(market: str) -> Dict[str, object]:
    """Get Yahoo Finance market summary data for a market code."""
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
