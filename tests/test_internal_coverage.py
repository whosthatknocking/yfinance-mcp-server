from __future__ import annotations

import logging
import os
import runpy
import warnings
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from pydantic import ValidationError

from yfinance_mcp import server
from yfinance_mcp.cache import InMemoryTTLCache
from yfinance_mcp.logging_utils import _resolve_log_level
from yfinance_mcp.schemas import QuoteSnapshotResult
from yfinance_mcp.utils import serialize_value
from yfinance_mcp.wrapper import YFinanceError, YFinanceWrapper


def test_cache_expires_entries_and_supports_stale_reads():
    cache = InMemoryTTLCache()

    with patch("yfinance_mcp.cache.time.time", side_effect=[100.0, 100.0, 102.0, 102.0]):
        cache.set("quote:AAPL", {"value": 1}, ttl_seconds=1)
        assert cache.get_entry("quote:AAPL", allow_stale=True).value == {"value": 1}
        assert cache.get("quote:AAPL") is None
        assert cache.get_entry("quote:AAPL", allow_stale=True) is None


def test_resolve_log_level_uses_configured_env_value(monkeypatch):
    monkeypatch.setenv("YF_LOG_LEVEL", "debug")
    monkeypatch.delenv("YF_TRANSPORT", raising=False)

    assert _resolve_log_level() == logging.DEBUG


def test_quote_snapshot_model_preserves_existing_additional_fields():
    payload = QuoteSnapshotResult.model_validate(
        {"lastPrice": 123.45, "additional_fields": {"source": "test"}}
    ).model_dump(exclude_none=True)

    assert payload["additional_fields"] == {"source": "test"}


def test_quote_snapshot_model_handles_non_mapping_input():
    with pytest.raises(ValidationError):
        QuoteSnapshotResult.model_validate("not-a-dict")


def test_serialize_value_handles_datetime_types_and_tolist_failures():
    class BadList:
        def tolist(self):
            raise RuntimeError("boom")

    class BadNa:
        pass

    with patch("yfinance_mcp.utils.pd.isna", side_effect=TypeError("unsupported")):
        result = serialize_value(
            {
                "ts": pd.Timestamp("2026-01-01T10:15:00"),
                "dt": datetime(2026, 1, 1, 10, 15, 0),
                "d": date(2026, 1, 1),
                "bad_list": BadList(),
                "bad_na": BadNa(),
            }
        )

    assert result["ts"] == "2026-01-01T10:15:00"
    assert result["dt"] == "2026-01-01T10:15:00"
    assert result["d"] == "2026-01-01"
    assert isinstance(result["bad_list"], BadList)
    assert isinstance(result["bad_na"], BadNa)


def test_run_tool_converts_validation_error_to_value_error():
    with patch.object(server, "logger"):
        def operation():
            raise ValidationError.from_exception_data("Example", [])

        with pytest.raises(ValueError):
            server._run_tool("bad_tool", operation)


def test_run_tool_converts_timeout_error_to_value_error():
    with patch.object(server, "logger") as mocked_logger:
        def operation():
            raise YFinanceError("timeout", "timed out", {"symbol": "AAPL"})

        with pytest.raises(ValueError) as exc_info:
            server._run_tool("quote_tool", operation)

    assert exc_info.value.args[0]["category"] == "timeout"
    assert mocked_logger.warning.call_args.args[0] == "tool_timeout"


def test_run_tool_converts_non_timeout_yfinance_error_to_value_error():
    with patch.object(server, "logger") as mocked_logger:
        def operation():
            raise YFinanceError("invalid_input", "bad request", {"symbol": "AAPL"})

        with pytest.raises(ValueError) as exc_info:
            server._run_tool("quote_tool", operation)

    assert exc_info.value.args[0]["category"] == "invalid_input"
    assert mocked_logger.warning.call_args.args[0] == "tool_failed"


def test_run_tool_reraises_unexpected_exceptions():
    with patch.object(server, "logger"):
        with pytest.raises(RuntimeError):
            server._run_tool("broken", lambda: (_ for _ in ()).throw(RuntimeError("boom")))


def test_get_server_metadata_returns_valid_payload():
    payload = {
        "server_name": "yfinance",
        "server_version": "1.0.0",
        "supported_yfinance_version": "2.0.0",
        "transport_modes": ["stdio", "streamable-http"],
        "cache_backend": "memory",
    }
    with patch.object(server.wrapper, "get_metadata", return_value=payload):
        assert server.get_server_metadata() == payload


def test_get_option_chain_returns_named_payload():
    payload = {
        "symbol": "SPY",
        "date": "2026-06-19",
        "calls": {"columns": ["strike"], "data": [[500]], "index": [0]},
        "puts": {"columns": ["strike"], "data": [[400]], "index": [0]},
    }
    with patch.object(server.wrapper, "get_option_chain", return_value=payload) as mocked:
        assert server.get_option_chain("SPY", date="2026-06-19") == payload

    mocked.assert_called_once_with(symbol="SPY", date="2026-06-19")


def test_get_balance_sheet_and_cashflow_return_dataframe_payload():
    payload = {"columns": ["value"], "data": [[1]], "index": ["2025"]}
    with patch.object(server.wrapper, "get_balance_sheet", return_value=payload) as mocked_balance:
        assert server.get_balance_sheet("AAPL") == payload
    with patch.object(server.wrapper, "get_cashflow", return_value=payload) as mocked_cashflow:
        assert server.get_cashflow("AAPL") == payload

    mocked_balance.assert_called_once_with(symbol="AAPL", freq="yearly", pretty=False)
    mocked_cashflow.assert_called_once_with(symbol="AAPL", freq="yearly", pretty=False)


def test_main_runs_stdio_transport(monkeypatch):
    monkeypatch.setenv("YF_TRANSPORT", "stdio")
    with patch.object(server.mcp, "run") as mocked_run:
        server.main()

    mocked_run.assert_called_once_with(transport="stdio")


def test_main_runs_http_transport(monkeypatch):
    monkeypatch.setenv("YF_TRANSPORT", "streamable-http")
    monkeypatch.setenv("YF_HTTP_HOST", "127.0.0.1")
    monkeypatch.setenv("YF_HTTP_PORT", "9001")
    monkeypatch.setenv("YF_UVICORN_LOG_LEVEL", "warning")
    with patch.object(server, "_build_http_app", return_value="app") as mocked_build, patch(
        "yfinance_mcp.server.uvicorn.run"
    ) as mocked_run:
        server.main()

    mocked_build.assert_called_once_with()
    mocked_run.assert_called_once_with("app", host="127.0.0.1", port=9001, log_level="warning")


def test_server_module_executes_main_when_run_as_script(monkeypatch):
    monkeypatch.setenv("YF_TRANSPORT", "stdio")
    with patch("mcp.server.fastmcp.FastMCP.run") as mocked_run:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            runpy.run_module("yfinance_mcp.server", run_name="__main__")

    mocked_run.assert_called_once_with(transport="stdio")


def test_removed_tools_are_not_in_public_tool_list():
    tool_names = {tool.__name__ for tool in server._tool_functions()}

    assert "get_shares" not in tool_names
    assert "get_earnings" not in tool_names


def test_wrapper_direct_helpers_cover_remaining_branches():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch.object(wrapper, "get_market_summary", return_value={"market": "us"}) as mocked_market:
        assert wrapper.get_market("us") == {"market": "us"}
    mocked_market.assert_called_once_with("us")


def test_wrapper_extract_lookup_matches_handles_invalid_rows():
    payload = {
        "columns": ["shortName", "exchange", "quoteType", "regularMarketPrice", "rank"],
        "data": [["Alphabet Inc.", "NMS", "equity", 297.0, 1], "bad-row", ["", "NMS", "equity", 1.0, 2]],
        "index": ["GOOG", "SKIP", ""],
    }

    matches = YFinanceWrapper._extract_lookup_matches(payload)

    assert matches == [
        {
            "symbol": "GOOG",
            "name": "Alphabet Inc.",
            "exchange": "NMS",
            "quoteType": "equity",
            "lastPrice": 297.0,
            "rank": 1,
        }
    ]

    assert YFinanceWrapper._extract_lookup_matches({"columns": [], "data": [], "index": "bad"}) == []
    assert YFinanceWrapper._extract_lookup_matches({"columns": [], "data": "bad", "index": []}) == []

    minimal_matches = YFinanceWrapper._extract_lookup_matches(
        {"columns": [], "data": [[]], "index": ["GOOG"]}
    )
    assert minimal_matches == [
        {
            "symbol": "GOOG",
            "name": "",
            "exchange": "",
            "quoteType": "",
            "lastPrice": None,
            "rank": None,
        }
    ]


def test_wrapper_classify_exception_and_retry_after_branches():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    assert wrapper._classify_exception(RuntimeError("missing optional dependency")) == "internal_error"
    assert wrapper._classify_exception(RuntimeError("404 symbol invalid")) == "invalid_input"
    assert wrapper._classify_exception(RuntimeError("429 too many requests")) == "upstream_temporary"
    assert wrapper._classify_exception(RuntimeError("symbol not found")) == "invalid_input"
    assert wrapper._classify_exception(RuntimeError("socket timeout")) == "timeout"
    assert wrapper._classify_exception(RuntimeError("transient")) == "upstream_temporary"

    exc = RuntimeError("retry later")
    exc.response = SimpleNamespace(headers={"retry-after": "Wed, 01 Apr 2026 10:00:10 GMT"})
    assert wrapper._extract_retry_after_seconds(exc, now=1775037600.0) == 10.0

    exc.response = SimpleNamespace(headers={"retry-after": ""})
    assert wrapper._extract_retry_after_seconds(exc) is None

    exc.response = SimpleNamespace(headers={"retry-after": "bad"})
    assert wrapper._extract_retry_after_seconds(exc) is None

    exc.response = SimpleNamespace(headers={"retry-after": "7"})
    assert wrapper._is_throttle_exception(exc) is True
    assert wrapper._is_throttle_exception(RuntimeError("plain failure")) is False

    exc.response = SimpleNamespace(headers={"Retry-After": None})
    assert wrapper._extract_retry_after_seconds(exc) is None

    exc.response = SimpleNamespace(headers={"retry-after": "9"})
    assert wrapper._extract_retry_after_seconds(exc) == 9.0

    exc.response = SimpleNamespace(headers={"Retry-After": "11"})
    assert wrapper._extract_retry_after_seconds(exc) == 11.0

    exc.response = SimpleNamespace(headers={"retry-after": "12"})
    assert wrapper._extract_retry_after_seconds(exc) == 12.0

    class HeaderGetter:
        def get(self, key):
            return {"Retry-After": "13", "retry-after": None}.get(key)

    exc.response = SimpleNamespace(headers=HeaderGetter())
    assert wrapper._extract_retry_after_seconds(exc) == 13.0

    exc.response = SimpleNamespace(headers=object())
    assert wrapper._extract_retry_after_seconds(exc) is None


def test_wrapper_throttle_and_history_helper_branches():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    wrapper.retry_policy.throttle_cooldown_threshold = 2
    wrapper.retry_policy.throttle_cooldown_seconds = 5.0
    wrapper._throttle_cooldown_until = 110.0

    with patch("yfinance_mcp.wrapper.time.time", return_value=100.0):
        wrapper._record_throttle_failure({"symbol": "AAPL"})
    assert wrapper._throttle_cooldown_until == 110.0

    with patch("yfinance_mcp.wrapper.time.time", side_effect=[101.0, 101.0]), patch(
        "yfinance_mcp.wrapper.time.sleep"
    ) as mocked_sleep:
        wrapper._throttle_cooldown_until = 102.0
        wrapper.retry_policy.total_timeout = 1
        wrapper._wait_for_throttle_cooldown(start=100.0, error_context={"symbol": "AAPL"})
    mocked_sleep.assert_not_called()

    assert wrapper._serialize_history_result({"ok": True}, {"symbol": "AAPL"}) == {"ok": True}
    assert wrapper._extract_market_error("bad") is None
    assert wrapper._extract_market_error({"finance": "bad"}) is None
    assert wrapper._extract_market_error({"finance": {"error": "bad"}}) is None

    wrapper._consecutive_throttle_failures = 1
    wrapper.retry_policy.throttle_cooldown_threshold = 2
    wrapper.retry_policy.throttle_cooldown_seconds = 3.0
    wrapper._throttle_cooldown_until = 200.0
    with patch("yfinance_mcp.wrapper.time.time", return_value=100.0):
        wrapper._record_throttle_failure({"symbol": "AAPL"})
    assert wrapper._throttle_cooldown_until == 200.0


def test_wrapper_retries_reraise_immediate_yfinance_error():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with pytest.raises(YFinanceError):
        wrapper._run_with_retry(
            operation=lambda: (_ for _ in ()).throw(YFinanceError("invalid_input", "bad")),
            error_context={"symbol": "AAPL"},
        )


def test_wrapper_retry_promotes_invalid_input_exception():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with pytest.raises(YFinanceError) as exc_info:
        wrapper._run_with_retry(
            operation=lambda: (_ for _ in ()).throw(RuntimeError("404 invalid symbol")),
            error_context={"symbol": "AAPL"},
        )

    assert exc_info.value.category == "invalid_input"
