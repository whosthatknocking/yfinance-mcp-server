from unittest.mock import patch
import pandas as pd

from yfinance_mcp.cache import InMemoryTTLCache
from yfinance_mcp.wrapper import YFinanceError, YFinanceWrapper


def test_wrapper_metadata_includes_transport_modes():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    payload = wrapper.get_metadata()

    assert payload["server_name"] == "yfinance"
    assert "stdio" in payload["transport_modes"]
    assert "streamable-http" in payload["transport_modes"]


def test_compute_backoff_is_bounded():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.random.uniform", return_value=0.5) as mocked:
        delay = wrapper._compute_backoff(3)

    assert delay == 0.5
    mocked.assert_called_once()


def test_retry_returns_stale_cache_for_transient_failures():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    result = wrapper._run_with_retry(
        operation=lambda: (_ for _ in ()).throw(RuntimeError("429 too many requests")),
        error_context={"symbol": "AAPL"},
        stale_value={"cached": True},
    )

    assert result == {"cached": True}


def test_get_batch_info_returns_payload_keyed_by_symbol():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch.object(wrapper, "get_info", side_effect=[{"symbol": "AAPL"}, {"symbol": "MSFT"}]) as mocked:
        result = wrapper.get_batch_info(["AAPL", "MSFT"])

    assert result == {"symbols": ["AAPL", "MSFT"], "results": {"AAPL": {"symbol": "AAPL"}, "MSFT": {"symbol": "MSFT"}}}
    assert mocked.call_count == 2


def test_get_batch_quote_snapshot_returns_payload_keyed_by_symbol():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch.object(
        wrapper,
        "get_fast_info",
        side_effect=[{"lastPrice": 123.45, "currency": "USD"}, {"lastPrice": 234.56, "currency": "USD"}],
    ) as mocked:
        result = wrapper.get_batch_quote_snapshot(["AAPL", "MSFT"])

    assert result == {
        "symbols": ["AAPL", "MSFT"],
        "results": {
            "AAPL": {"lastPrice": 123.45, "currency": "USD"},
            "MSFT": {"lastPrice": 234.56, "currency": "USD"},
        },
    }
    assert mocked.call_count == 2


def test_get_market_summary_returns_normalized_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeMarket:
        def __init__(self, market: str, timeout: int):
            self.summary = {"NYSE": {"symbol": "^DJI"}}
            self.status = {"status": "open"}

    with patch("yfinance_mcp.wrapper.yf.Market", FakeMarket):
        result = wrapper.get_market_summary("us")

    assert result == {"market": "us", "status": {"status": "open"}, "summary": {"NYSE": {"symbol": "^DJI"}}}


def test_get_market_summary_raises_invalid_input_for_bad_market_code():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeMarket:
        def __init__(self, market: str, timeout: int):
            self.summary = {
                "finance": {
                    "result": None,
                    "error": {"code": "Bad Request", "description": "invalid broad market region"},
                }
            }
            self.status = {"finance": {"result": None, "error": {"code": "Bad Request", "description": "invalid broad market region"}}}

    with patch("yfinance_mcp.wrapper.yf.Market", FakeMarket):
        try:
            wrapper.get_market_summary("america")
        except YFinanceError as exc:
            assert exc.category == "invalid_input"
            assert "invalid broad market region" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("Expected YFinanceError for invalid market code")


def test_get_history_raises_invalid_input_for_empty_dataframe():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.history.return_value = pd.DataFrame()
        try:
            wrapper.get_history("MSFT.", period="6mo", interval="1d")
        except YFinanceError as exc:
            assert exc.category == "invalid_input"
            assert "No price history data was returned" in str(exc)
            assert exc.details["symbol"] == "MSFT"
        else:  # pragma: no cover - defensive
            raise AssertionError("Expected YFinanceError for empty history response")


def test_get_earnings_dates_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"EPS Estimate": [1.23]}, index=["2026-01-30"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_earnings_dates.return_value = payload
        result = wrapper.get_earnings_dates("AAPL", limit=4, offset=0)

    assert result == {"columns": ["EPS Estimate"], "data": [[1.23]], "index": ["2026-01-30"]}


def test_get_ticker_calendar_returns_serialized_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_calendar.return_value = {"dividendDate": "2026-02-11", "earningsAverage": 1.95}
        result = wrapper.get_ticker_calendar("AAPL")

    assert result == {"dividendDate": "2026-02-11", "earningsAverage": 1.95}


def test_get_recommendations_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"strongBuy": [10], "hold": [5]}, index=["2026-03-01"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_recommendations.return_value = payload
        result = wrapper.get_recommendations("AAPL")

    assert result == {"columns": ["strongBuy", "hold"], "data": [[10, 5]], "index": ["2026-03-01"]}


def test_get_analyst_price_targets_returns_serialized_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_analyst_price_targets.return_value = {
            "current": 253.79,
            "high": 350.0,
            "low": 205.0,
            "mean": 295.31,
            "median": 300.0,
        }
        result = wrapper.get_analyst_price_targets("AAPL")

    assert result == {"current": 253.79, "high": 350.0, "low": 205.0, "mean": 295.31, "median": 300.0}
