from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DataFramePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: List[str]
    data: List[List[Any]]
    index: List[Any]


class ToolMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_name: str
    server_version: str
    supported_yfinance_version: str
    transport_modes: List[str]
    cache_backend: str


class JsonObjectResult(BaseModel):
    model_config = ConfigDict(extra="allow")


class JsonListResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[Any]


class OptionChainResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    date: Optional[str]
    calls: DataFramePayload
    puts: DataFramePayload


class HistoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    period: Optional[str] = None
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    prepost: bool = False
    auto_adjust: bool = True
    actions: bool = True


class StatementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    freq: str = Field(default="yearly", pattern="^(yearly|quarterly|trailing)$")
    pretty: bool = False


class DownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickers: List[str] = Field(min_length=1)
    period: Optional[str] = None
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    auto_adjust: bool = True
    prepost: bool = False
    actions: bool = False


class NewsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    count: int = Field(default=10, ge=1, le=100)
    tab: str = "news"


class OptionChainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    date: Optional[str] = None


class MarketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: str = Field(min_length=1)


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    message: str
    details: Optional[Dict[str, Any]] = None
