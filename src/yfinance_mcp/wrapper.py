from __future__ import annotations

import os
import threading
import time
import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import structlog
import yfinance as yf

from . import __version__
from .cache import CacheBackend, InMemoryTTLCache
from .logging_utils import configure_logging
from .utils import normalize_symbol, normalize_symbols, serialize_value

configure_logging()
logger = structlog.get_logger(__name__)


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
        )
        self.timeout = min(self.retry_policy.read_timeout, self.retry_policy.total_timeout)
        self.limiter = ConcurrencyLimiter(int(os.getenv("YF_UPSTREAM_CONCURRENCY", "4")))

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
        normalized = normalize_symbol(symbol)
        return self._cached_call(
            key=f"fast_info:{normalized}",
            ttl=self.quote_ttl,
            operation=lambda: serialize_value(dict(self._ticker(normalized).fast_info)),
            error_context={"symbol": normalized},
            allow_stale=False,
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
            operation=lambda: serialize_value(self._ticker(normalized).history(**{k: v for k, v in params.items() if v is not None})),
            error_context={"symbol": normalized, "params": params},
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
            operation=lambda: serialize_value(
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
                )
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
                with self.limiter:
                    return operation()
            except YFinanceError:
                raise
            except Exception as exc:
                attempt += 1
                category = self._classify_exception(exc)
                elapsed = time.time() - start
                logger.warning(
                    "upstream_error",
                    attempt=attempt,
                    category=category,
                    error=str(exc),
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
                if category in {"invalid_input", "upstream_permanent"}:
                    raise YFinanceError(category, str(exc), error_context)
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
                time.sleep(self._compute_backoff(attempt))

    def _compute_backoff(self, attempt: int) -> float:
        base_delay = min(2 ** (attempt - 1), self.retry_policy.backoff_cap_seconds)
        return random.uniform(0, base_delay)

    def _classify_exception(self, exc: Exception) -> str:
        message = str(exc).lower()
        if "404" in message or "invalid" in message:
            return "invalid_input"
        if "429" in message or "rate limit" in message or "too many requests" in message:
            return "upstream_temporary"
        if "not found" in message:
            return "invalid_input"
        if "timeout" in message:
            return "timeout"
        return "upstream_temporary"

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
