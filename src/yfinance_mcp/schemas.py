from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .utils import normalize_period


class DataFramePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: List[str]
    data: List[List[Any]]
    index: List[Any]


class HistoryResult(DataFramePayload):
    pass


class DownloadHistoryResult(DataFramePayload):
    pass


class StatementResult(DataFramePayload):
    pass


class SeriesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str]
    index: List[Any]
    data: List[Any]


class ActionSeriesResult(SeriesPayload):
    pass


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quotes: List[Dict[str, Any]]
    news: List[Dict[str, Any]]
    lists: List[Dict[str, Any]]
    research: List[Dict[str, Any]]
    nav: List[Dict[str, Any]]


class LookupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    all: DataFramePayload
    stock: DataFramePayload
    etf: DataFramePayload
    mutualfund: DataFramePayload
    index: DataFramePayload
    future: DataFramePayload
    currency: DataFramePayload
    cryptocurrency: DataFramePayload


class ToolMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_name: str
    server_version: str
    supported_yfinance_version: str
    transport_modes: List[str]
    cache_backend: str


class InfoResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: Optional[str] = Field(
        default=None,
        description="Ticker symbol when available in the upstream info payload.",
    )
    shortName: Optional[str] = Field(
        default=None,
        description="Short company or instrument name when available.",
    )
    longName: Optional[str] = Field(
        default=None,
        description="Long company or instrument name when available.",
    )
    exchange: Optional[str] = Field(
        default=None,
        description="Exchange code when available.",
    )
    quoteType: Optional[str] = Field(
        default=None,
        description="Instrument type such as EQUITY or ETF when available.",
    )
    currency: Optional[str] = Field(
        default=None,
        description="Currency code when available.",
    )
    marketCap: Optional[Any] = Field(
        default=None,
        description="Market capitalization when available.",
    )
    longBusinessSummary: Optional[str] = Field(
        default=None,
        description="Business summary text when available.",
    )


class QuoteSnapshotResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    currency: Optional[str] = Field(
        default=None,
        description="Currency code for the quote snapshot when available.",
    )
    exchange: Optional[str] = Field(
        default=None,
        description="Exchange code when available.",
    )
    lastPrice: Optional[Any] = Field(
        default=None,
        description="Latest known trading price when available.",
    )
    previousClose: Optional[Any] = Field(
        default=None,
        description="Previous close value when available.",
    )
    open: Optional[Any] = Field(
        default=None,
        description="Session open price when available.",
    )
    dayHigh: Optional[Any] = Field(
        default=None,
        description="Session high price when available.",
    )
    dayLow: Optional[Any] = Field(
        default=None,
        description="Session low price when available.",
    )
    marketCap: Optional[Any] = Field(
        default=None,
        description="Market capitalization when available.",
    )
    quoteType: Optional[str] = Field(
        default=None,
        description="Instrument type such as EQUITY or ETF when available.",
    )
    timezone: Optional[str] = Field(
        default=None,
        description="Exchange timezone when available.",
    )


class JsonListResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[Any]


class StringListResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[str]


class NewsItem(BaseModel):
    model_config = ConfigDict(extra="allow")


class NewsListResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[NewsItem]


class MarketSummaryResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    market: Optional[str] = Field(
        default=None,
        description="Requested market code when included in the payload.",
    )
    status: Optional[Any] = Field(
        default=None,
        description="Market status payload when available.",
    )
    summary: Optional[Any] = Field(
        default=None,
        description="Market summary payload when available.",
    )


class OptionChainResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    date: Optional[str]
    calls: DataFramePayload
    puts: DataFramePayload


class HistoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(
        min_length=1,
        description="Yahoo Finance ticker symbol such as AAPL, MSFT, TSLA, or SPY.",
        examples=["AAPL"],
    )
    period: Optional[str] = Field(
        default=None,
        description="Named lookback period such as 1d, 5d, 1mo, 6mo, 1y, 5y, or max. Use either period or start/end.",
        examples=["6mo"],
    )
    interval: str = Field(
        default="1d",
        description="Price interval such as 1d, 1wk, 1mo, or supported intraday intervals when available.",
        examples=["1d"],
    )
    start: Optional[str] = Field(
        default=None,
        description="Start date in YYYY-MM-DD format. Use with end for explicit date ranges.",
        examples=["2025-01-01"],
    )
    end: Optional[str] = Field(
        default=None,
        description="End date in YYYY-MM-DD format. Use with start for explicit date ranges.",
        examples=["2025-03-31"],
    )
    prepost: bool = False
    auto_adjust: bool = True
    actions: bool = True

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: Optional[str]) -> Optional[str]:
        return normalize_period(value)


class StatementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(
        min_length=1,
        description="Yahoo Finance ticker symbol such as AAPL, AMZN, or META.",
        examples=["AMZN"],
    )
    freq: str = Field(
        default="yearly",
        pattern="^(yearly|quarterly|trailing)$",
        description="Statement frequency. Use yearly for annual statements, quarterly for quarter-level data, or trailing where supported.",
        examples=["yearly"],
    )
    pretty: bool = False


class DownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickers: List[str] = Field(
        min_length=1,
        description="List of Yahoo Finance ticker symbols for a batch historical download.",
        examples=[["AAPL", "MSFT", "NVDA"]],
    )
    period: Optional[str] = Field(
        default=None,
        description="Named lookback period such as 1mo, 6mo, 1y, or max. Use either period or start/end.",
        examples=["1y"],
    )
    interval: str = Field(
        default="1d",
        description="Price interval such as 1d, 1wk, or 1mo.",
        examples=["1wk"],
    )
    start: Optional[str] = Field(default=None, description="Start date in YYYY-MM-DD format.", examples=["2024-01-01"])
    end: Optional[str] = Field(default=None, description="End date in YYYY-MM-DD format.", examples=["2025-01-01"])
    auto_adjust: bool = True
    prepost: bool = False
    actions: bool = False

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: Optional[str]) -> Optional[str]:
        return normalize_period(value)


class NewsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(
        min_length=1,
        description="Yahoo Finance ticker symbol for which to retrieve recent news.",
        examples=["TSLA"],
    )
    count: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of news items to request.",
        examples=[10],
    )
    tab: str = Field(
        default="news",
        description="Yahoo Finance news tab to query. Use the default unless you know a specific tab is needed.",
        examples=["news"],
    )


class OptionChainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(
        min_length=1,
        description="Yahoo Finance ticker symbol for the option chain, such as SPY or AAPL.",
        examples=["SPY"],
    )
    date: Optional[str] = Field(
        default=None,
        description="Specific expiration date in YYYY-MM-DD format. If omitted, yfinance uses its default behavior.",
        examples=["2025-06-20"],
    )


class MarketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: str = Field(
        min_length=1,
        description="Yahoo Finance market code such as us.",
        examples=["us"],
    )


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        description="Ticker symbol or company name to search, such as microsoft, MSFT, or tesla.",
        examples=["microsoft"],
    )
    max_results: int = Field(
        default=8,
        ge=1,
        le=25,
        description="Maximum number of quote matches to return.",
        examples=[8],
    )
    news_count: int = Field(
        default=8,
        ge=0,
        le=25,
        description="Maximum number of related news items to include.",
        examples=[5],
    )
    lists_count: int = Field(
        default=8,
        ge=0,
        le=25,
        description="Maximum number of Yahoo Finance lists to include.",
        examples=[5],
    )
    include_cb: bool = True
    include_nav_links: bool = False
    include_research: bool = False
    include_cultural_assets: bool = False
    enable_fuzzy_query: bool = False
    recommended: int = Field(
        default=8,
        ge=0,
        le=25,
        description="Recommended result count requested from Yahoo Finance.",
        examples=[8],
    )


class LookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        description="Instrument lookup query such as microsoft, MSFT, or bitcoin.",
        examples=["microsoft"],
    )
    count: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Maximum number of rows to return per lookup category.",
        examples=[25],
    )


class PeriodRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(
        min_length=1,
        description="Yahoo Finance ticker symbol such as AAPL, MSFT, TSLA, or SPY.",
        examples=["AAPL"],
    )
    period: str = Field(
        default="max",
        description="Named lookback period such as 5d, 1mo, 6mo, 1y, ytd, or max.",
        examples=["max"],
    )

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        return normalize_period(value) or "max"


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    message: str
    details: Optional[Dict[str, Any]] = None
