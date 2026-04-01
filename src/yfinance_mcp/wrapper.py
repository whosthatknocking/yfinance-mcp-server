from __future__ import annotations

import os
import threading
import time
import random
import re
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Optional

import structlog
import yfinance as yf
import pandas as pd

from . import __version__
from .cache import CacheBackend, InMemoryTTLCache
from .logging_utils import configure_logging, increment_upstream_call_count
from .utils import normalize_symbol, normalize_symbols, serialize_value

configure_logging()
logger = structlog.get_logger(__name__)

_TICKER_PATTERN = re.compile(r"^[A-Z0-9.^=\-]{1,10}$")


class YFinanceError(RuntimeError):
    def __init__(self, category: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.category = category
        self.details = details or {}


@dataclass
class RetryPolicy:
    max_retries: int
    read_timeout: int
    total_timeout: int
    backoff_cap_seconds: float
    retry_after_cap_seconds: float
    throttle_cooldown_threshold: int
    throttle_cooldown_seconds: float


class ConcurrencyLimiter:
    def __init__(self, max_concurrency: int) -> None:
        self._semaphore = threading.BoundedSemaphore(max(1, max_concurrency))

    def __enter__(self) -> "ConcurrencyLimiter":
        self._semaphore.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._semaphore.release()


class YFinanceWrapper:
    def __init__(self, cache: Optional[CacheBackend] = None) -> None:
        self.cache = cache or InMemoryTTLCache()
        self.cache_backend_name = os.getenv("YF_CACHE_BACKEND", "memory")
        self.default_ttl = int(os.getenv("YF_CACHE_TTL", "900"))
        self.quote_ttl = int(os.getenv("YF_CACHE_TTL_QUOTE", "60"))
        self.reference_ttl = int(os.getenv("YF_CACHE_TTL_REFERENCE", "3600"))
        self.history_ttl = int(os.getenv("YF_CACHE_TTL_HISTORY", "900"))
        self.retry_policy = RetryPolicy(
            max_retries=int(os.getenv("YF_MAX_RETRIES", "3")),
            read_timeout=int(os.getenv("YF_READ_TIMEOUT", "20")),
            total_timeout=int(os.getenv("YF_TOTAL_TIMEOUT", "30")),
            backoff_cap_seconds=float(os.getenv("YF_BACKOFF_CAP_SECONDS", "4")),
            retry_after_cap_seconds=float(os.getenv("YF_RETRY_AFTER_CAP_SECONDS", "30")),
            throttle_cooldown_threshold=int(os.getenv("YF_THROTTLE_COOLDOWN_THRESHOLD", "3")),
            throttle_cooldown_seconds=float(os.getenv("YF_THROTTLE_COOLDOWN_SECONDS", "10")),
        )
        self.timeout = min(self.retry_policy.read_timeout, self.retry_policy.total_timeout)
        self.limiter = ConcurrencyLimiter(int(os.getenv("YF_UPSTREAM_CONCURRENCY", "4")))
        self._throttle_state_lock = threading.Lock()
        self._throttle_cooldown_until = 0.0
        self._consecutive_throttle_failures = 0

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "server_name": "yfinance",
            "server_version": __version__,
            "supported_yfinance_version": getattr(yf, "__version__", "unknown"),
            "transport_modes": ["stdio", "streamable-http"],
            "cache_backend": self.cache_backend_name,
        }

    def get_info(self, symbol: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)
        return self._cached_call(
            key=f"info:{normalized}",
            ttl=self.reference_ttl,
            operation=lambda: serialize_value(self._ticker(normalized).info),
            error_context={"symbol": normalized},
            allow_stale=True,
        )

    def get_fast_info(self, symbol: str) -> Dict[str, Any]:
        normalized = self._resolve_quote_symbol(symbol)
        requested_symbol = symbol.strip()

        def operation() -> Dict[str, Any]:
            ticker = self._ticker(normalized)
            fast_info = serialize_value(dict(ticker.fast_info))
            info = ticker.info
            if isinstance(info, dict):
                market_price = info.get("regularMarketPrice")
                if market_price is None:
                    market_price = info.get("currentPrice")
                if market_price is not None:
                    fast_info["lastPrice"] = serialize_value(market_price)
                if fast_info.get("previousClose") is None and info.get("previousClose") is not None:
                    fast_info["previousClose"] = serialize_value(info.get("previousClose"))
            return fast_info

        return self._cached_call(
            key=f"fast_info:{normalized}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"symbol": normalized, "requested_symbol": requested_symbol},
            allow_stale=False,
        )

    def get_batch_info(self, symbols: List[str]) -> Dict[str, Any]:
        normalized = normalize_symbols(symbols)
        if not normalized:
            raise YFinanceError("invalid_input", "At least one ticker symbol is required.")

        def operation() -> Dict[str, Any]:
            return {
                "symbols": normalized,
                "results": {symbol: self.get_info(symbol) for symbol in normalized},
            }

        return self._cached_call(
            key=f"batch_info:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"symbols": normalized},
            allow_stale=True,
        )

    def get_batch_quote_snapshot(self, symbols: List[str]) -> Dict[str, Any]:
        normalized = normalize_symbols(symbols)
        if not normalized:
            raise YFinanceError("invalid_input", "At least one ticker symbol is required.")

        def operation() -> Dict[str, Any]:
            return {
                "symbols": normalized,
                "results": {symbol: self.get_fast_info(symbol) for symbol in normalized},
            }

        return self._cached_call(
            key=f"batch_quote_snapshot:{normalized}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"symbols": normalized},
            allow_stale=False,
        )

    def get_batch_news(self, symbols: List[str]) -> List[Dict[str, Any]]:
        normalized = normalize_symbols(symbols)
        if not normalized:
            raise YFinanceError("invalid_input", "At least one ticker symbol is required.")

        def operation() -> List[Dict[str, Any]]:
            tickers = yf.Tickers(" ".join(normalized))
            news_payload = serialize_value(tickers.news())
            if isinstance(news_payload, list):
                return news_payload
            if isinstance(news_payload, dict):
                items: List[Dict[str, Any]] = []
                for symbol, stories in news_payload.items():
                    if not isinstance(stories, list):
                        continue
                    for story in stories:
                        if isinstance(story, dict) and "symbol" not in story:
                            items.append({"symbol": symbol, **story})
                        else:
                            items.append(story)
                return items
            return []

        return self._cached_call(
            key=f"batch_news:{normalized}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"symbols": normalized},
            allow_stale=True,
        )

    def get_history(
        self,
        symbol: str,
        period: Optional[str] = None,
        interval: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
        prepost: bool = False,
        auto_adjust: bool = True,
        actions: bool = True,
    ) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)
        params = {
            "period": period,
            "interval": interval,
            "start": start,
            "end": end,
            "prepost": prepost,
            "auto_adjust": auto_adjust,
            "actions": actions,
            "timeout": self.timeout,
        }
        return self._cached_call(
            key=f"history:{normalized}:{params}",
            ttl=self.history_ttl,
            operation=lambda: self._serialize_history_result(
                self._ticker(normalized).history(**{k: v for k, v in params.items() if v is not None}),
                error_context={"symbol": normalized, "params": params},
            ),
            error_context={"symbol": normalized, "params": params},
            allow_stale=True,
        )

    def get_history_metadata(self, symbol: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)
        return self._cached_call(
            key=f"history_metadata:{normalized}",
            ttl=self.reference_ttl,
            operation=lambda: serialize_value(self._ticker(normalized).get_history_metadata()),
            error_context={"symbol": normalized},
            allow_stale=True,
        )

    def get_isin(self, symbol: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)
        return self._cached_call(
            key=f"isin:{normalized}",
            ttl=self.reference_ttl,
            operation=lambda: {"value": serialize_value(self._ticker(normalized).get_isin())},
            error_context={"symbol": normalized},
            allow_stale=True,
        )

    def download(
        self,
        tickers: List[str],
        period: Optional[str] = None,
        interval: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
        auto_adjust: bool = True,
        prepost: bool = False,
        actions: bool = False,
    ) -> Dict[str, Any]:
        normalized = normalize_symbols(tickers)
        if not normalized:
            raise YFinanceError("invalid_input", "At least one ticker symbol is required.")
        params = {
            "tickers": normalized,
            "period": period,
            "interval": interval,
            "start": start,
            "end": end,
            "auto_adjust": auto_adjust,
            "prepost": prepost,
            "actions": actions,
            "timeout": self.timeout,
            "progress": False,
        }
        return self._cached_call(
            key=f"download:{params}",
            ttl=self.history_ttl,
            operation=lambda: self._serialize_history_result(
                yf.download(
                    tickers=normalized,
                    period=period,
                    interval=interval,
                    start=start,
                    end=end,
                    auto_adjust=auto_adjust,
                    prepost=prepost,
                    actions=actions,
                    timeout=self.timeout,
                    progress=False,
                ),
                error_context={"tickers": normalized, "params": params},
            ),
            error_context={"tickers": normalized, "params": params},
            allow_stale=True,
        )

    def get_news(self, symbol: str, count: int = 10, tab: str = "news") -> List[Dict[str, Any]]:
        normalized = normalize_symbol(symbol)
        return self._cached_call(
            key=f"news:{normalized}:{count}:{tab}",
            ttl=self.quote_ttl,
            operation=lambda: serialize_value(self._ticker(normalized).get_news(count=count, tab=tab)),
            error_context={"symbol": normalized, "count": count, "tab": tab},
            allow_stale=True,
        )

    def get_option_expirations(self, symbol: str) -> List[str]:
        normalized = normalize_symbol(symbol)
        return self._cached_call(
            key=f"options:{normalized}",
            ttl=self.quote_ttl,
            operation=lambda: serialize_value(list(self._ticker(normalized).options)),
            error_context={"symbol": normalized},
            allow_stale=False,
        )

    def get_option_chain(self, symbol: str, date: Optional[str] = None) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)

        def operation() -> Dict[str, Any]:
            chain = self._ticker(normalized).option_chain(date=date)
            return {
                "symbol": normalized,
                "date": date,
                "calls": serialize_value(chain.calls),
                "puts": serialize_value(chain.puts),
            }

        return self._cached_call(
            key=f"option_chain:{normalized}:{date}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"symbol": normalized, "date": date},
            allow_stale=False,
        )

    def get_actions(self, symbol: str, period: str = "max") -> Dict[str, Any]:
        return self._series_call(symbol, "actions", period=period)

    def get_dividends(self, symbol: str, period: str = "max") -> Dict[str, Any]:
        return self._series_call(symbol, "dividends", period=period)

    def get_splits(self, symbol: str, period: str = "max") -> Dict[str, Any]:
        return self._series_call(symbol, "splits", period=period)

    def get_capital_gains(self, symbol: str, period: str = "max") -> Dict[str, Any]:
        return self._series_call(symbol, "capital_gains", period=period)

    def get_shares(self, symbol: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)
        raise YFinanceError(
            "invalid_input",
            "The get_shares endpoint is not supported by the current yfinance upstream. Use get_shares_full instead.",
            {"symbol": normalized, "replacement": "get_shares_full"},
        )

    def get_shares_full(self, symbol: str, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)

        def operation() -> Dict[str, Any]:
            result = self._ticker(normalized).get_shares_full(start=start, end=end)
            if result is None or (isinstance(result, pd.Series) and result.empty):
                raise YFinanceError(
                    "invalid_input",
                    "No extended shares data was returned for the requested symbol.",
                    {"symbol": normalized, "start": start, "end": end},
                )
            return serialize_value(result)

        return self._cached_call(
            key=f"shares_full:{normalized}:{start}:{end}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"symbol": normalized, "start": start, "end": end},
            allow_stale=True,
        )

    def get_sec_filings(self, symbol: str) -> List[Dict[str, Any]]:
        normalized = normalize_symbol(symbol)
        return self._cached_call(
            key=f"sec_filings:{normalized}",
            ttl=self.reference_ttl,
            operation=lambda: serialize_value(self._ticker(normalized).get_sec_filings()),
            error_context={"symbol": normalized},
            allow_stale=True,
        )

    def get_income_stmt(self, symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, Any]:
        return self._statement_call(symbol, "income_stmt", freq=freq, pretty=pretty)

    def get_balance_sheet(self, symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, Any]:
        return self._statement_call(symbol, "balance_sheet", freq=freq, pretty=pretty)

    def get_cashflow(self, symbol: str, freq: str = "yearly", pretty: bool = False) -> Dict[str, Any]:
        return self._statement_call(symbol, "cashflow", freq=freq, pretty=pretty)

    def get_market_summary(self, market: str) -> Dict[str, Any]:
        normalized = market.strip().lower()

        def operation() -> Dict[str, Any]:
            market_obj = yf.Market(normalized, timeout=self.timeout)
            summary = market_obj.summary
            status = market_obj.status
            market_error = self._extract_market_error(summary) or self._extract_market_error(status)
            if market_error is not None:
                raise YFinanceError(
                    "invalid_input",
                    market_error.get("description", "Invalid market code."),
                    {"market": normalized, "upstream_error": market_error},
                )
            return {
                "market": normalized,
                "status": serialize_value(status),
                "summary": serialize_value(summary),
            }

        return self._cached_call(
            key=f"market_summary:{normalized}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"market": normalized},
            allow_stale=False,
        )

    def get_market(self, market: str) -> Dict[str, Any]:
        return self.get_market_summary(market)

    def get_market_status(self, market: str) -> Dict[str, Any]:
        normalized = market.strip().lower()

        def operation() -> Dict[str, Any]:
            market_obj = yf.Market(normalized, timeout=self.timeout)
            status = market_obj.status
            market_error = self._extract_market_error(status)
            if market_error is not None:
                raise YFinanceError(
                    "invalid_input",
                    market_error.get("description", "Invalid market code."),
                    {"market": normalized, "upstream_error": market_error},
                )
            return {
                "market": normalized,
                "status": serialize_value(status),
            }

        return self._cached_call(
            key=f"market_status:{normalized}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"market": normalized},
            allow_stale=False,
        )

    def get_sector(self, key: str) -> Dict[str, Any]:
        normalized = key.strip().lower()

        def operation() -> Dict[str, Any]:
            sector = yf.Sector(normalized)
            return {
                "key": sector.key,
                "name": sector.name,
                "symbol": sector.symbol,
                "overview": serialize_value(sector.overview),
                "research_reports": serialize_value(sector.research_reports),
                "industries": serialize_value(sector.industries),
                "top_companies": serialize_value(sector.top_companies),
                "top_etfs": serialize_value(sector.top_etfs),
                "top_mutual_funds": serialize_value(sector.top_mutual_funds),
                "ticker_symbol": getattr(sector.ticker, "ticker", None),
            }

        return self._cached_call(
            key=f"sector:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"key": normalized},
            allow_stale=True,
        )

    def get_sector_overview(self, key: str) -> Dict[str, Any]:
        return self._sector_field_call(key, "sector_overview", "overview")

    def get_sector_research_reports(self, key: str) -> List[Dict[str, Any]]:
        normalized = key.strip().lower()
        return self._cached_call(
            key=f"sector_research_reports:{normalized}",
            ttl=self.reference_ttl,
            operation=lambda: serialize_value(yf.Sector(normalized).research_reports),
            error_context={"key": normalized},
            allow_stale=True,
        )

    def get_sector_industries(self, key: str) -> Dict[str, Any]:
        return self._sector_field_call(key, "sector_industries", "industries")

    def get_sector_top_companies(self, key: str) -> Dict[str, Any]:
        return self._sector_field_call(key, "sector_top_companies", "top_companies")

    def get_sector_top_etfs(self, key: str) -> Dict[str, Any]:
        return self._sector_field_call(key, "sector_top_etfs", "top_etfs")

    def get_sector_top_mutual_funds(self, key: str) -> Dict[str, Any]:
        return self._sector_field_call(key, "sector_top_mutual_funds", "top_mutual_funds")

    def get_sector_ticker(self, key: str) -> Dict[str, Any]:
        normalized = key.strip().lower()

        def operation() -> Dict[str, Any]:
            sector = yf.Sector(normalized)
            ticker_symbol = getattr(sector.ticker, "ticker", None)
            return {"value": ticker_symbol}

        return self._cached_call(
            key=f"sector_ticker:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"key": normalized},
            allow_stale=True,
        )

    def get_industry(self, key: str) -> Dict[str, Any]:
        normalized = key.strip().lower()

        def operation() -> Dict[str, Any]:
            industry = yf.Industry(normalized)
            return {
                "key": industry.key,
                "name": industry.name,
                "symbol": industry.symbol,
                "sector_key": industry.sector_key,
                "sector_name": industry.sector_name,
                "overview": serialize_value(industry.overview),
                "research_reports": serialize_value(industry.research_reports),
                "top_companies": serialize_value(industry.top_companies),
                "top_growth_companies": serialize_value(industry.top_growth_companies),
                "top_performing_companies": serialize_value(industry.top_performing_companies),
                "ticker_symbol": getattr(industry.ticker, "ticker", None),
            }

        return self._cached_call(
            key=f"industry:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"key": normalized},
            allow_stale=True,
        )

    def get_industry_overview(self, key: str) -> Dict[str, Any]:
        return self._industry_field_call(key, "industry_overview", "overview")

    def get_industry_research_reports(self, key: str) -> List[Dict[str, Any]]:
        normalized = key.strip().lower()
        return self._cached_call(
            key=f"industry_research_reports:{normalized}",
            ttl=self.reference_ttl,
            operation=lambda: serialize_value(yf.Industry(normalized).research_reports),
            error_context={"key": normalized},
            allow_stale=True,
        )

    def get_industry_top_companies(self, key: str) -> Dict[str, Any]:
        return self._industry_field_call(key, "industry_top_companies", "top_companies")

    def get_industry_top_growth_companies(self, key: str) -> Dict[str, Any]:
        return self._industry_field_call(key, "industry_top_growth_companies", "top_growth_companies")

    def get_industry_top_performing_companies(self, key: str) -> Dict[str, Any]:
        return self._industry_field_call(key, "industry_top_performing_companies", "top_performing_companies")

    def get_industry_ticker(self, key: str) -> Dict[str, Any]:
        normalized = key.strip().lower()

        def operation() -> Dict[str, Any]:
            industry = yf.Industry(normalized)
            ticker_symbol = getattr(industry.ticker, "ticker", None)
            return {"value": ticker_symbol}

        return self._cached_call(
            key=f"industry_ticker:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"key": normalized},
            allow_stale=True,
        )

    def search(
        self,
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
    ) -> Dict[str, Any]:
        normalized = query.strip()
        if not normalized:
            raise YFinanceError("invalid_input", "A non-empty search query is required.")
        params = {
            "max_results": max_results,
            "news_count": news_count,
            "lists_count": lists_count,
            "include_cb": include_cb,
            "include_nav_links": include_nav_links,
            "include_research": include_research,
            "include_cultural_assets": include_cultural_assets,
            "enable_fuzzy_query": enable_fuzzy_query,
            "recommended": recommended,
            "timeout": self.timeout,
        }

        def operation() -> Dict[str, Any]:
            search_obj = yf.Search(
                normalized,
                max_results=max_results,
                news_count=news_count,
                lists_count=lists_count,
                include_cb=include_cb,
                include_nav_links=include_nav_links,
                include_research=include_research,
                include_cultural_assets=include_cultural_assets,
                enable_fuzzy_query=enable_fuzzy_query,
                recommended=recommended,
                timeout=self.timeout,
            )
            return serialize_value(search_obj.all)

        return self._cached_call(
            key=f"search:{normalized}:{params}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"query": normalized, "params": params},
            allow_stale=True,
        )

    def lookup(self, query: str, count: int = 25) -> Dict[str, Any]:
        normalized = query.strip()
        if not normalized:
            raise YFinanceError("invalid_input", "A non-empty lookup query is required.")

        def operation() -> Dict[str, Any]:
            lookup_obj = yf.Lookup(normalized, timeout=self.timeout)
            return {
                "query": normalized,
                "all": serialize_value(lookup_obj.get_all(count=count)),
                "stock": serialize_value(lookup_obj.get_stock(count=count)),
                "etf": serialize_value(lookup_obj.get_etf(count=count)),
                "mutualfund": serialize_value(lookup_obj.get_mutualfund(count=count)),
                "index": serialize_value(lookup_obj.get_index(count=count)),
                "future": serialize_value(lookup_obj.get_future(count=count)),
                "currency": serialize_value(lookup_obj.get_currency(count=count)),
                "cryptocurrency": serialize_value(lookup_obj.get_cryptocurrency(count=count)),
            }

        return self._cached_call(
            key=f"lookup:{normalized}:{count}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"query": normalized, "count": count},
            allow_stale=True,
        )

    def get_earnings_dates(self, symbol: str, limit: int = 12, offset: int = 0) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)

        def operation() -> Dict[str, Any]:
            ticker = self._ticker(normalized)
            result = ticker.get_earnings_dates(limit=limit, offset=offset)
            if isinstance(result, pd.DataFrame) and result.empty:
                raise YFinanceError(
                    "invalid_input",
                    "No earnings dates were returned for the requested symbol.",
                    {"symbol": normalized, "limit": limit, "offset": offset},
                )
            return serialize_value(result)

        return self._cached_call(
            key=f"earnings_dates:{normalized}:{limit}:{offset}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"symbol": normalized, "limit": limit, "offset": offset},
            allow_stale=True,
        )

    def get_ticker_calendar(self, symbol: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)
        return self._cached_call(
            key=f"calendar:{normalized}",
            ttl=self.reference_ttl,
            operation=lambda: serialize_value(self._ticker(normalized).get_calendar()),
            error_context={"symbol": normalized},
            allow_stale=True,
        )

    def get_recommendations(self, symbol: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)

        def operation() -> Dict[str, Any]:
            result = self._ticker(normalized).get_recommendations()
            if isinstance(result, pd.DataFrame) and result.empty:
                raise YFinanceError(
                    "invalid_input",
                    "No recommendations data was returned for the requested symbol.",
                    {"symbol": normalized},
                )
            return serialize_value(result)

        return self._cached_call(
            key=f"recommendations:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"symbol": normalized},
            allow_stale=True,
        )

    def get_analyst_price_targets(self, symbol: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)
        return self._cached_call(
            key=f"analyst_price_targets:{normalized}",
            ttl=self.reference_ttl,
            operation=lambda: serialize_value(self._ticker(normalized).get_analyst_price_targets()),
            error_context={"symbol": normalized},
            allow_stale=True,
        )

    def get_earnings(self, symbol: str, freq: str = "yearly") -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)
        raise YFinanceError(
            "invalid_input",
            "The get_earnings endpoint is deprecated upstream and is no longer exposed. Use get_income_stmt or get_earnings_dates instead.",
            {"symbol": normalized, "replacements": ["get_income_stmt", "get_earnings_dates"]},
        )

    def get_recommendations_summary(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="recommendations_summary",
            getter_name="get_recommendations_summary",
            empty_message="No recommendation summary data was returned for the requested symbol.",
        )

    def get_upgrades_downgrades(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="upgrades_downgrades",
            getter_name="get_upgrades_downgrades",
            empty_message="No upgrades or downgrades data was returned for the requested symbol.",
        )

    def get_earnings_estimate(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="earnings_estimate",
            getter_name="get_earnings_estimate",
            empty_message="No earnings estimate data was returned for the requested symbol.",
        )

    def get_revenue_estimate(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="revenue_estimate",
            getter_name="get_revenue_estimate",
            empty_message="No revenue estimate data was returned for the requested symbol.",
        )

    def get_earnings_history(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="earnings_history",
            getter_name="get_earnings_history",
            empty_message="No earnings history data was returned for the requested symbol.",
        )

    def get_eps_trend(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="eps_trend",
            getter_name="get_eps_trend",
            empty_message="No EPS trend data was returned for the requested symbol.",
        )

    def get_eps_revisions(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="eps_revisions",
            getter_name="get_eps_revisions",
            empty_message="No EPS revisions data was returned for the requested symbol.",
        )

    def get_growth_estimates(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="growth_estimates",
            getter_name="get_growth_estimates",
            empty_message="No growth estimates data was returned for the requested symbol.",
        )

    def get_sustainability(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="sustainability",
            getter_name="get_sustainability",
            empty_message="No sustainability data was returned for the requested symbol.",
        )

    def get_major_holders(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="major_holders",
            getter_name="get_major_holders",
            empty_message="No major holders data was returned for the requested symbol.",
        )

    def get_institutional_holders(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="institutional_holders",
            getter_name="get_institutional_holders",
            empty_message="No institutional holders data was returned for the requested symbol.",
        )

    def get_mutualfund_holders(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="mutualfund_holders",
            getter_name="get_mutualfund_holders",
            empty_message="No mutual fund holders data was returned for the requested symbol.",
        )

    def get_insider_purchases(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="insider_purchases",
            getter_name="get_insider_purchases",
            empty_message="No insider purchases data was returned for the requested symbol.",
        )

    def get_insider_transactions(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="insider_transactions",
            getter_name="get_insider_transactions",
            empty_message="No insider transactions data was returned for the requested symbol.",
        )

    def get_insider_roster_holders(self, symbol: str) -> Dict[str, Any]:
        return self._table_getter_call(
            symbol,
            cache_key_prefix="insider_roster_holders",
            getter_name="get_insider_roster_holders",
            empty_message="No insider roster holders data was returned for the requested symbol.",
        )

    def get_funds_data(self, symbol: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)

        def operation() -> Dict[str, Any]:
            funds_data = self._get_funds_data_object(normalized)
            return {
                "quote_type": serialize_value(funds_data.quote_type()),
                "description": serialize_value(funds_data.description),
                "asset_classes": serialize_value(funds_data.asset_classes),
                "bond_holdings": serialize_value(funds_data.bond_holdings),
                "bond_ratings": serialize_value(funds_data.bond_ratings),
                "equity_holdings": serialize_value(funds_data.equity_holdings),
                "fund_operations": serialize_value(funds_data.fund_operations),
                "fund_overview": serialize_value(funds_data.fund_overview),
                "sector_weightings": serialize_value(funds_data.sector_weightings),
                "top_holdings": serialize_value(funds_data.top_holdings),
            }

        return self._cached_call(
            key=f"funds_data:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"symbol": normalized},
            allow_stale=True,
        )

    def get_fund_asset_classes(self, symbol: str) -> Dict[str, Any]:
        return self._funds_data_field_call(symbol, "fund_asset_classes", "asset_classes")

    def get_fund_bond_holdings(self, symbol: str) -> Dict[str, Any]:
        return self._funds_data_field_call(symbol, "fund_bond_holdings", "bond_holdings")

    def get_fund_bond_ratings(self, symbol: str) -> Dict[str, Any]:
        return self._funds_data_field_call(symbol, "fund_bond_ratings", "bond_ratings")

    def get_fund_description(self, symbol: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)

        def operation() -> Dict[str, Any]:
            funds_data = self._get_funds_data_object(normalized)
            return {"value": serialize_value(funds_data.description)}

        return self._cached_call(
            key=f"fund_description:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"symbol": normalized},
            allow_stale=True,
        )

    def get_fund_equity_holdings(self, symbol: str) -> Dict[str, Any]:
        return self._funds_data_field_call(symbol, "fund_equity_holdings", "equity_holdings")

    def get_fund_operations(self, symbol: str) -> Dict[str, Any]:
        return self._funds_data_field_call(symbol, "fund_operations", "fund_operations")

    def get_fund_overview(self, symbol: str) -> Dict[str, Any]:
        return self._funds_data_field_call(symbol, "fund_overview", "fund_overview")

    def get_fund_sector_weightings(self, symbol: str) -> Dict[str, Any]:
        return self._funds_data_field_call(symbol, "fund_sector_weightings", "sector_weightings")

    def get_fund_top_holdings(self, symbol: str) -> Dict[str, Any]:
        return self._funds_data_field_call(symbol, "fund_top_holdings", "top_holdings")

    def get_fund_quote_type(self, symbol: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)

        def operation() -> Dict[str, Any]:
            funds_data = self._get_funds_data_object(normalized)
            return {"value": serialize_value(funds_data.quote_type())}

        return self._cached_call(
            key=f"fund_quote_type:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"symbol": normalized},
            allow_stale=True,
        )

    def get_calendars(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 12,
        offset: int = 0,
        force: bool = False,
        market_cap: Optional[float] = None,
        filter_most_active: bool = True,
    ) -> Dict[str, Any]:
        normalized_start = self._normalize_calendar_date(start)
        normalized_end = self._normalize_calendar_date(end)

        def operation() -> Dict[str, Any]:
            calendars = yf.Calendars(start=normalized_start, end=normalized_end)
            return {
                "earnings_calendar": serialize_value(
                    calendars.get_earnings_calendar(
                        market_cap=market_cap,
                        filter_most_active=filter_most_active,
                        start=normalized_start,
                        end=normalized_end,
                        limit=limit,
                        offset=offset,
                        force=force,
                    )
                ),
                "economic_events_calendar": serialize_value(
                    calendars.get_economic_events_calendar(
                        start=normalized_start,
                        end=normalized_end,
                        limit=limit,
                        offset=offset,
                        force=force,
                    )
                ),
                "ipo_calendar": serialize_value(
                    calendars.get_ipo_info_calendar(
                        start=normalized_start,
                        end=normalized_end,
                        limit=limit,
                        offset=offset,
                        force=force,
                    )
                ),
                "splits_calendar": serialize_value(
                    calendars.get_splits_calendar(
                        start=normalized_start,
                        end=normalized_end,
                        limit=limit,
                        offset=offset,
                        force=force,
                    )
                ),
            }

        return self._cached_call(
            key=f"calendars:{normalized_start}:{normalized_end}:{limit}:{offset}:{force}:{market_cap}:{filter_most_active}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"start": normalized_start, "end": normalized_end, "limit": limit, "offset": offset},
            allow_stale=True,
        )

    def get_earnings_calendar(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 12,
        offset: int = 0,
        force: bool = False,
        market_cap: Optional[float] = None,
        filter_most_active: bool = True,
    ) -> Dict[str, Any]:
        normalized_start = self._normalize_calendar_date(start)
        normalized_end = self._normalize_calendar_date(end)

        def operation() -> Dict[str, Any]:
            calendars = yf.Calendars(start=normalized_start, end=normalized_end)
            return serialize_value(
                calendars.get_earnings_calendar(
                    market_cap=market_cap,
                    filter_most_active=filter_most_active,
                    start=normalized_start,
                    end=normalized_end,
                    limit=limit,
                    offset=offset,
                    force=force,
                )
            )

        return self._cached_call(
            key=f"earnings_calendar:{normalized_start}:{normalized_end}:{limit}:{offset}:{force}:{market_cap}:{filter_most_active}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"start": normalized_start, "end": normalized_end, "limit": limit, "offset": offset},
            allow_stale=True,
        )

    def get_economic_events_calendar(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 12,
        offset: int = 0,
        force: bool = False,
    ) -> Dict[str, Any]:
        return self._calendar_getter_call(
            cache_key_prefix="economic_events_calendar",
            getter_name="get_economic_events_calendar",
            start=start,
            end=end,
            limit=limit,
            offset=offset,
            force=force,
        )

    def get_ipo_calendar(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 12,
        offset: int = 0,
        force: bool = False,
    ) -> Dict[str, Any]:
        return self._calendar_getter_call(
            cache_key_prefix="ipo_calendar",
            getter_name="get_ipo_info_calendar",
            start=start,
            end=end,
            limit=limit,
            offset=offset,
            force=force,
        )

    def get_splits_calendar(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 12,
        offset: int = 0,
        force: bool = False,
    ) -> Dict[str, Any]:
        return self._calendar_getter_call(
            cache_key_prefix="splits_calendar",
            getter_name="get_splits_calendar",
            start=start,
            end=end,
            limit=limit,
            offset=offset,
            force=force,
        )

    def _statement_call(self, symbol: str, statement_name: str, freq: str, pretty: bool) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)
        allowed = {"yearly", "quarterly", "trailing"}
        if freq not in allowed:
            raise YFinanceError("invalid_input", "freq must be one of yearly, quarterly, or trailing.", {"freq": freq})
        key = f"{statement_name}:{normalized}:{freq}:{pretty}"

        def operation() -> Any:
            ticker = self._ticker(normalized)
            if statement_name == "income_stmt":
                if freq == "quarterly":
                    return ticker.quarterly_income_stmt
                if freq == "trailing":
                    return ticker.ttm_income_stmt
                return ticker.get_income_stmt(pretty=pretty, freq="yearly")
            if statement_name == "balance_sheet":
                if freq == "quarterly":
                    return ticker.quarterly_balance_sheet
                if freq == "trailing":
                    raise YFinanceError("invalid_input", "Trailing balance sheet is not supported by yfinance.")
                return ticker.get_balance_sheet(pretty=pretty, freq="yearly")
            if statement_name == "cashflow":
                if freq == "quarterly":
                    return ticker.quarterly_cashflow
                if freq == "trailing":
                    return ticker.ttm_cashflow
                return ticker.get_cashflow(pretty=pretty, freq="yearly")
            raise YFinanceError("internal_error", "Unsupported statement request.", {"statement_name": statement_name})

        return self._cached_call(
            key=key,
            ttl=self.reference_ttl,
            operation=lambda: serialize_value(operation()),
            error_context={"symbol": normalized, "statement_name": statement_name, "freq": freq},
            allow_stale=True,
        )

    def _series_call(self, symbol: str, series_name: str, period: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)
        key = f"{series_name}:{normalized}:{period}"

        def operation() -> Any:
            ticker = self._ticker(normalized)
            getter_name = f"get_{series_name}"
            getter = getattr(ticker, getter_name)
            result = getter(period=period)
            if result is None or (isinstance(result, pd.Series) and result.empty):
                raise YFinanceError(
                    "invalid_input",
                    f"No {series_name} data was returned for the requested symbol and period.",
                    {"symbol": normalized, "period": period, "series": series_name},
                )
            return result

        return self._cached_call(
            key=key,
            ttl=self.reference_ttl,
            operation=lambda: serialize_value(operation()),
            error_context={"symbol": normalized, "series": series_name, "period": period},
            allow_stale=True,
        )

    def _table_getter_call(
        self,
        symbol: str,
        cache_key_prefix: str,
        getter_name: str,
        empty_message: str,
    ) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)

        def operation() -> Any:
            ticker = self._ticker(normalized)
            getter = getattr(ticker, getter_name)
            result = getter()
            if result is None or (isinstance(result, pd.DataFrame) and result.empty):
                raise YFinanceError(
                    "invalid_input",
                    empty_message,
                    {"symbol": normalized, "getter": getter_name},
                )
            return serialize_value(result)

        return self._cached_call(
            key=f"{cache_key_prefix}:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"symbol": normalized, "getter": getter_name},
            allow_stale=True,
        )

    def _funds_data_field_call(self, symbol: str, cache_key_prefix: str, field_name: str) -> Dict[str, Any]:
        normalized = normalize_symbol(symbol)

        def operation() -> Dict[str, Any]:
            funds_data = self._get_funds_data_object(normalized)
            value = getattr(funds_data, field_name)
            return serialize_value(value)

        return self._cached_call(
            key=f"{cache_key_prefix}:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"symbol": normalized, "field": field_name},
            allow_stale=True,
        )

    def _get_funds_data_object(self, symbol: str):
        funds_data = self._ticker(symbol).get_funds_data()
        if funds_data is None:
            raise YFinanceError(
                "invalid_input",
                "No funds data was returned for the requested symbol.",
                {"symbol": symbol},
            )
        return funds_data

    def _calendar_getter_call(
        self,
        cache_key_prefix: str,
        getter_name: str,
        start: Optional[str],
        end: Optional[str],
        limit: int,
        offset: int,
        force: bool,
    ) -> Dict[str, Any]:
        normalized_start = self._normalize_calendar_date(start)
        normalized_end = self._normalize_calendar_date(end)

        def operation() -> Dict[str, Any]:
            calendars = yf.Calendars(start=normalized_start, end=normalized_end)
            getter = getattr(calendars, getter_name)
            return serialize_value(
                getter(
                    start=normalized_start,
                    end=normalized_end,
                    limit=limit,
                    offset=offset,
                    force=force,
                )
            )

        return self._cached_call(
            key=f"{cache_key_prefix}:{normalized_start}:{normalized_end}:{limit}:{offset}:{force}",
            ttl=self.quote_ttl,
            operation=operation,
            error_context={"start": normalized_start, "end": normalized_end, "limit": limit, "offset": offset},
            allow_stale=True,
        )

    @staticmethod
    def _normalize_calendar_date(value: Optional[str]) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        return datetime.fromisoformat(value).date()

    def _sector_field_call(self, key: str, cache_key_prefix: str, field_name: str):
        normalized = key.strip().lower()

        def operation():
            sector = yf.Sector(normalized)
            return serialize_value(getattr(sector, field_name))

        return self._cached_call(
            key=f"{cache_key_prefix}:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"key": normalized, "field": field_name},
            allow_stale=True,
        )

    def _industry_field_call(self, key: str, cache_key_prefix: str, field_name: str):
        normalized = key.strip().lower()

        def operation():
            industry = yf.Industry(normalized)
            return serialize_value(getattr(industry, field_name))

        return self._cached_call(
            key=f"{cache_key_prefix}:{normalized}",
            ttl=self.reference_ttl,
            operation=operation,
            error_context={"key": normalized, "field": field_name},
            allow_stale=True,
        )

    def _resolve_quote_symbol(self, symbol: str) -> str:
        requested = symbol.strip()
        normalized = normalize_symbol(symbol)
        if self._looks_like_explicit_ticker(requested, normalized):
            return normalized

        matches = self._lookup_stock_candidates(requested, count=10)
        if not matches:
            return normalized
        return matches[0]["symbol"]

    @staticmethod
    def _looks_like_explicit_ticker(requested: str, normalized: str) -> bool:
        return bool(requested) and requested == normalized and _TICKER_PATTERN.fullmatch(normalized) is not None

    def _lookup_stock_candidates(self, query: str, count: int) -> List[Dict[str, str]]:
        result = self.lookup(query, count=count)
        stock_matches = self._extract_lookup_matches(result.get("stock"))
        if stock_matches:
            return stock_matches
        return self._extract_lookup_matches(result.get("all"))

    @staticmethod
    def _extract_lookup_matches(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not payload or not isinstance(payload, dict):
            return []

        columns = payload.get("columns")
        rows = payload.get("data")
        indices = payload.get("index")
        if not isinstance(columns, list) or not isinstance(rows, list) or not isinstance(indices, list):
            return []

        normalized_columns = {str(column).strip().lower(): index for index, column in enumerate(columns)}
        name_index = next(
            (
                normalized_columns[key]
                for key in ("short name", "shortname", "long name", "longname", "name", "company")
                if key in normalized_columns
            ),
            None,
        )
        exchange_index = normalized_columns.get("exchange")
        quote_type_index = normalized_columns.get("quotetype")
        price_index = normalized_columns.get("regularmarketprice")
        rank_index = normalized_columns.get("rank")

        matches: List[Dict[str, Any]] = []
        for row_index, row in enumerate(rows):
            if not isinstance(row, list) or row_index >= len(indices):
                continue
            symbol = str(indices[row_index]).strip().upper()
            if not symbol:
                continue
            name = ""
            if name_index is not None and name_index < len(row):
                name = str(row[name_index]).strip()
            exchange = ""
            if exchange_index is not None and exchange_index < len(row):
                exchange = str(row[exchange_index]).strip().upper()
            quote_type = ""
            if quote_type_index is not None and quote_type_index < len(row):
                quote_type = str(row[quote_type_index]).strip().lower()
            last_price = None
            if price_index is not None and price_index < len(row):
                last_price = row[price_index]
            rank = None
            if rank_index is not None and rank_index < len(row):
                rank = row[rank_index]
            matches.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "exchange": exchange,
                    "quoteType": quote_type,
                    "lastPrice": last_price,
                    "rank": rank,
                }
            )
        return matches

    def _cached_call(
        self,
        key: str,
        ttl: int,
        operation: Callable[[], Any],
        error_context: Dict[str, Any],
        allow_stale: bool,
    ) -> Any:
        cached = self.cache.get(key)
        if cached is not None:
            logger.info("cache_hit", cache_key=key)
            return cached
        logger.info("cache_miss", cache_key=key)
        stale_entry_getter = getattr(self.cache, "get_entry", None)
        stale_value = None
        if callable(stale_entry_getter) and allow_stale:
            stale_entry = stale_entry_getter(key, allow_stale=True)
            if stale_entry is not None:
                stale_value = stale_entry.value
        value = self._run_with_retry(operation=operation, error_context=error_context, stale_value=stale_value)
        self.cache.set(key, value, ttl_seconds=ttl)
        return value

    def _run_with_retry(
        self,
        operation: Callable[[], Any],
        error_context: Dict[str, Any],
        stale_value: Optional[Any] = None,
    ) -> Any:
        start = time.time()
        attempt = 0
        while True:
            try:
                self._wait_for_throttle_cooldown(start=start, error_context=error_context)
                with self.limiter:
                    attempt_count = increment_upstream_call_count()
                    result = operation()
                self._clear_throttle_state()
                logger.info(
                    "upstream_call_completed",
                    attempt=attempt_count,
                    elapsed_seconds=round(time.time() - start, 3),
                    **error_context,
                )
                return result
            except YFinanceError:
                raise
            except Exception as exc:
                attempt += 1
                category = self._classify_exception(exc)
                elapsed = time.time() - start
                retry_after_seconds = self._extract_retry_after_seconds(exc)
                throttled = self._is_throttle_exception(exc)
                logger.warning(
                    "upstream_error",
                    attempt=attempt,
                    category=category,
                    error=str(exc),
                    retry_after_seconds=retry_after_seconds,
                    throttled=throttled,
                    elapsed_seconds=round(elapsed, 3),
                    total_timeout_seconds=self.retry_policy.total_timeout,
                    **error_context,
                )
                if category == "timeout":
                    logger.warning(
                        "upstream_timeout",
                        attempt=attempt,
                        elapsed_seconds=round(elapsed, 3),
                        total_timeout_seconds=self.retry_policy.total_timeout,
                        **error_context,
                    )
                if category in {"invalid_input", "upstream_permanent", "internal_error"}:
                    raise YFinanceError(category, str(exc), error_context) from exc
                if throttled:
                    self._record_throttle_failure(error_context)
                else:
                    self._clear_throttle_state()
                if attempt > self.retry_policy.max_retries or elapsed >= self.retry_policy.total_timeout:
                    if elapsed >= self.retry_policy.total_timeout:
                        logger.warning(
                            "request_deadline_exceeded",
                            attempt=attempt,
                            elapsed_seconds=round(elapsed, 3),
                            total_timeout_seconds=self.retry_policy.total_timeout,
                            category=category,
                            **error_context,
                        )
                    if stale_value is not None and category in {"upstream_temporary", "timeout"}:
                        logger.warning("serving_stale_cache", category=category, **error_context)
                        return stale_value
                    raise YFinanceError(category, str(exc), error_context) from exc
                time.sleep(self._compute_retry_delay(attempt=attempt, exc=exc))

    def _compute_backoff(self, attempt: int) -> float:
        base_delay = min(2 ** (attempt - 1), self.retry_policy.backoff_cap_seconds)
        return random.uniform(0, base_delay)

    def _compute_retry_delay(self, attempt: int, exc: Exception) -> float:
        backoff = self._compute_backoff(attempt)
        retry_after = self._extract_retry_after_seconds(exc)
        if retry_after is None:
            return backoff
        return max(backoff, min(retry_after, self.retry_policy.retry_after_cap_seconds))

    def _classify_exception(self, exc: Exception) -> str:
        message = str(exc).lower()
        if "missing optional dependency" in message:
            return "internal_error"
        if "404" in message or "invalid" in message:
            return "invalid_input"
        if "429" in message or "rate limit" in message or "too many requests" in message:
            return "upstream_temporary"
        if "not found" in message:
            return "invalid_input"
        if "timeout" in message:
            return "timeout"
        return "upstream_temporary"

    def _extract_retry_after_seconds(self, exc: Exception, now: Optional[float] = None) -> Optional[float]:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        retry_after_value = None
        if isinstance(headers, dict):
            retry_after_value = headers.get("Retry-After") or headers.get("retry-after")
        elif hasattr(headers, "get"):
            retry_after_value = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after_value is None:
            return None
        retry_after_text = str(retry_after_value).strip()
        if not retry_after_text:
            return None
        if retry_after_text.isdigit():
            return float(retry_after_text)
        try:
            parsed = parsedate_to_datetime(retry_after_text)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
        current = now if now is not None else time.time()
        return max(0.0, parsed.timestamp() - current)

    def _is_throttle_exception(self, exc: Exception) -> bool:
        message = str(exc).lower()
        if "429" in message or "rate limit" in message or "too many requests" in message:
            return True
        retry_after_seconds = self._extract_retry_after_seconds(exc)
        return retry_after_seconds is not None

    def _record_throttle_failure(self, error_context: Dict[str, Any]) -> None:
        with self._throttle_state_lock:
            self._consecutive_throttle_failures += 1
            if self._consecutive_throttle_failures < self.retry_policy.throttle_cooldown_threshold:
                return
            cooldown_until = time.time() + self.retry_policy.throttle_cooldown_seconds
            if cooldown_until <= self._throttle_cooldown_until:
                return
            self._throttle_cooldown_until = cooldown_until
        logger.warning(
            "throttle_cooldown_started",
            cooldown_seconds=self.retry_policy.throttle_cooldown_seconds,
            threshold=self.retry_policy.throttle_cooldown_threshold,
            **error_context,
        )

    def _clear_throttle_state(self) -> None:
        with self._throttle_state_lock:
            self._consecutive_throttle_failures = 0
            self._throttle_cooldown_until = 0.0

    def _get_throttle_cooldown_remaining(self, now: Optional[float] = None) -> float:
        current = now if now is not None else time.time()
        with self._throttle_state_lock:
            return max(0.0, self._throttle_cooldown_until - current)

    def _wait_for_throttle_cooldown(self, start: float, error_context: Dict[str, Any]) -> None:
        remaining = self._get_throttle_cooldown_remaining()
        if remaining <= 0:
            return
        elapsed = time.time() - start
        budget_remaining = max(0.0, self.retry_policy.total_timeout - elapsed)
        if budget_remaining <= 0:
            return
        sleep_seconds = min(remaining, budget_remaining)
        logger.warning(
            "throttle_cooldown_wait",
            cooldown_seconds=round(sleep_seconds, 3),
            total_timeout_seconds=self.retry_policy.total_timeout,
            **error_context,
        )
        time.sleep(sleep_seconds)

    def _serialize_history_result(self, result: Any, error_context: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(result, pd.DataFrame) and result.empty:
            details = dict(error_context)
            details["reason"] = "empty_history"
            raise YFinanceError(
                "invalid_input",
                "No price history data was returned for the requested symbol and date range.",
                details,
            )
        return serialize_value(result)

    @staticmethod
    def _extract_market_error(payload: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        finance = payload.get("finance")
        if not isinstance(finance, dict):
            return None
        error = finance.get("error")
        if not isinstance(error, dict):
            return None
        return error

    @staticmethod
    def _ticker(symbol: str) -> yf.Ticker:
        return yf.Ticker(symbol)
