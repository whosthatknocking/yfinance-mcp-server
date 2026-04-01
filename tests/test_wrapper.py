from unittest.mock import patch
from types import SimpleNamespace
from datetime import date
import pandas as pd
import pytest

from yfinance_mcp.cache import InMemoryTTLCache
from yfinance_mcp.logging_utils import bind_request_context, clear_request_context, get_upstream_call_count
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


def test_compute_retry_delay_honors_retry_after_header():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeResponse:
        headers = {"Retry-After": "12"}

    class FakeException(RuntimeError):
        def __init__(self):
            super().__init__("429 too many requests")
            self.response = FakeResponse()

    with patch.object(wrapper, "_compute_backoff", return_value=0.5):
        delay = wrapper._compute_retry_delay(attempt=1, exc=FakeException())

    assert delay == 12.0


def test_wait_for_throttle_cooldown_sleeps_for_remaining_budget():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.time.time", side_effect=[100.0, 100.0]), patch(
        "yfinance_mcp.wrapper.time.sleep"
    ) as mocked_sleep:
        wrapper._throttle_cooldown_until = 103.0
        wrapper._wait_for_throttle_cooldown(start=99.0, error_context={"symbol": "AAPL"})

    mocked_sleep.assert_called_once_with(3.0)


def test_repeated_throttle_failures_start_cooldown_and_serve_stale_cache():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    wrapper.retry_policy.max_retries = 2
    wrapper.retry_policy.throttle_cooldown_threshold = 2
    wrapper.retry_policy.throttle_cooldown_seconds = 5.0

    with patch("yfinance_mcp.wrapper.time.sleep") as mocked_sleep:
        result = wrapper._run_with_retry(
            operation=lambda: (_ for _ in ()).throw(RuntimeError("429 too many requests")),
            error_context={"symbol": "AAPL"},
            stale_value={"cached": True},
        )

    assert result == {"cached": True}
    assert wrapper._throttle_cooldown_until > 0
    assert mocked_sleep.call_count >= 2


def test_retry_returns_stale_cache_for_transient_failures():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    result = wrapper._run_with_retry(
        operation=lambda: (_ for _ in ()).throw(RuntimeError("429 too many requests")),
        error_context={"symbol": "AAPL"},
        stale_value={"cached": True},
    )

    assert result == {"cached": True}


def test_retry_increments_upstream_call_count_in_request_context():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    bind_request_context(request_id="req-1", tool_name="test_tool")

    try:
        result = wrapper._run_with_retry(
            operation=lambda: {"ok": True},
            error_context={"symbol": "AAPL"},
        )
        assert result == {"ok": True}
        assert get_upstream_call_count() == 1
    finally:
        clear_request_context()


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


def test_get_fast_info_uses_explicit_ticker_without_lookup():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.logger") as mocked_logger, patch(
        "yfinance_mcp.wrapper.yf.Ticker"
    ) as mocked_ticker, patch.object(wrapper, "lookup") as mocked_lookup:
        mocked_ticker.return_value.fast_info = {"lastPrice": 123.45, "currency": "USD"}
        mocked_ticker.return_value.info = {}

        result = wrapper.get_fast_info("GOOG")

    assert result == {"lastPrice": 123.45, "currency": "USD"}
    mocked_ticker.assert_called_once_with("GOOG")
    mocked_lookup.assert_not_called()
    logged_events = [call.args[0] for call in mocked_logger.info.call_args_list]
    assert "quote_request_resolved" in logged_events
    assert "quote_snapshot_ready" in logged_events


def test_get_fast_info_resolves_unique_company_name_via_lookup():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    lookup_payload = {
        "query": "Tesla",
        "stock": {
            "columns": ["shortName", "regularMarketPrice", "exchange", "quoteType"],
            "data": [["Tesla, Inc.", 381.5, "NMS", "equity"]],
            "index": ["TSLA"],
        },
    }

    with patch.object(wrapper, "lookup", return_value=lookup_payload) as mocked_lookup, patch(
        "yfinance_mcp.wrapper.yf.Ticker"
    ) as mocked_ticker:
        mocked_ticker.return_value.fast_info = {"lastPrice": 234.56, "currency": "USD"}

        result = wrapper.get_fast_info("Tesla")

    assert result == {"lastPrice": 234.56, "currency": "USD"}
    mocked_lookup.assert_called_once_with("Tesla", count=10)
    mocked_ticker.assert_called_once_with("TSLA")


def test_get_fast_info_prefers_info_market_price_over_fast_info_last_price():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.fast_info = {"lastPrice": 245.67, "currency": "USD", "previousClose": 240.0}
        mocked_ticker.return_value.info = {"regularMarketPrice": 380.87, "previousClose": 371.75}

        result = wrapper.get_fast_info("TSLA")

    assert result["lastPrice"] == 380.87
    assert result["previousClose"] == 240.0


def test_get_fast_info_uses_current_price_and_fills_previous_close_when_missing():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.fast_info = {"lastPrice": 245.67, "currency": "USD"}
        mocked_ticker.return_value.info = {"currentPrice": 380.87, "previousClose": 371.75}

        result = wrapper.get_fast_info("TSLA")

    assert result["lastPrice"] == 380.87
    assert result["previousClose"] == 371.75


def test_get_fast_info_keeps_fast_info_price_when_info_has_no_market_price():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.fast_info = {"lastPrice": 245.67, "currency": "USD", "previousClose": 240.0}
        mocked_ticker.return_value.info = {"previousClose": 371.75}

        result = wrapper.get_fast_info("TSLA")

    assert result["lastPrice"] == 245.67
    assert result["previousClose"] == 240.0


def test_get_fast_info_uses_first_lookup_stock_match_for_company_name():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    lookup_payload = {
        "query": "Google",
        "stock": {
            "columns": ["shortName", "regularMarketPrice", "exchange", "quoteType", "rank"],
            "data": [
                ["Alphabet Inc.", 297.37, "NMS", "equity", 22479],
                ["Alphabet Inc. Class A", 299.99, "NMS", "equity", 22480],
            ],
            "index": ["GOOG", "GOOGL"],
        },
    }

    with patch.object(wrapper, "lookup", return_value=lookup_payload) as mocked_lookup, patch(
        "yfinance_mcp.wrapper.yf.Ticker"
    ) as mocked_ticker:
        mocked_ticker.return_value.fast_info = {"lastPrice": 297.37, "currency": "USD"}
        mocked_ticker.return_value.info = {"regularMarketPrice": 297.37}

        result = wrapper.get_fast_info("Google")

    assert result["lastPrice"] == 297.37
    mocked_lookup.assert_called_once_with("Google", count=10)
    mocked_ticker.assert_called_once_with("GOOG")


def test_get_fast_info_logs_fallback_when_lookup_has_no_match():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.logger") as mocked_logger, patch.object(
        wrapper, "lookup", return_value={"stock": None, "all": None}
    ), patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.fast_info = {"lastPrice": 123.45, "currency": "USD"}
        mocked_ticker.return_value.info = {}

        result = wrapper.get_fast_info("Google")

    assert result == {"lastPrice": 123.45, "currency": "USD"}
    logged_events = [call.args[0] for call in mocked_logger.info.call_args_list]
    assert "quote_symbol_resolution_fallback" in logged_events


def test_get_batch_news_returns_list_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeTickers:
        def __init__(self, tickers):
            self._tickers = tickers

        def news(self):
            return [{"title": "Example", "publisher": "Example News"}]

    with patch("yfinance_mcp.wrapper.yf.Tickers", FakeTickers):
        result = wrapper.get_batch_news(["AAPL", "MSFT"])

    assert result == [{"title": "Example", "publisher": "Example News"}]


def test_get_batch_news_flattens_symbol_keyed_payloads():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeTickers:
        def __init__(self, tickers):
            self._tickers = tickers

        def news(self):
            return {
                "AAPL": [{"title": "Apple story"}],
                "MSFT": [{"title": "Microsoft story", "symbol": "MSFT"}],
            }

    with patch("yfinance_mcp.wrapper.yf.Tickers", FakeTickers):
        result = wrapper.get_batch_news(["AAPL", "MSFT"])

    assert result == [
        {"symbol": "AAPL", "title": "Apple story"},
        {"title": "Microsoft story", "symbol": "MSFT"},
    ]


def test_get_batch_news_skips_non_list_symbol_entries():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeTickers:
        def __init__(self, tickers):
            self._tickers = tickers

        def news(self):
            return {"AAPL": "skip-me", "MSFT": [{"title": "Microsoft story"}]}

    with patch("yfinance_mcp.wrapper.yf.Tickers", FakeTickers):
        result = wrapper.get_batch_news(["AAPL", "MSFT"])

    assert result == [{"symbol": "MSFT", "title": "Microsoft story"}]


def test_get_batch_news_returns_empty_list_for_unexpected_payload_type():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeTickers:
        def __init__(self, tickers):
            self._tickers = tickers

        def news(self):
            return "unexpected"

    with patch("yfinance_mcp.wrapper.yf.Tickers", FakeTickers):
        result = wrapper.get_batch_news(["AAPL", "MSFT"])

    assert result == []


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


def test_get_market_status_returns_normalized_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeMarket:
        def __init__(self, market: str, timeout: int):
            self.status = {"status": "open"}

    with patch("yfinance_mcp.wrapper.yf.Market", FakeMarket):
        result = wrapper.get_market_status("us")

    assert result == {"market": "us", "status": {"status": "open"}}


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


def test_get_history_metadata_returns_mapping_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_history_metadata.return_value = {"currency": "USD"}
        result = wrapper.get_history_metadata("AAPL")

    assert result == {"currency": "USD"}


def test_get_isin_returns_text_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_isin.return_value = "US0378331005"
        result = wrapper.get_isin("AAPL")

    assert result == {"value": "US0378331005"}


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


def test_get_recommendations_summary_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"strongBuy": [12]}, index=["0m"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_recommendations_summary.return_value = payload
        result = wrapper.get_recommendations_summary("AAPL")

    assert result == {"columns": ["strongBuy"], "data": [[12]], "index": ["0m"]}


def test_get_upgrades_downgrades_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"To Grade": ["Buy"]}, index=["2026-01-01"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_upgrades_downgrades.return_value = payload
        result = wrapper.get_upgrades_downgrades("AAPL")

    assert result == {"columns": ["To Grade"], "data": [["Buy"]], "index": ["2026-01-01"]}


def test_get_earnings_estimate_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"avg": [1.2]}, index=["0q"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_earnings_estimate.return_value = payload
        result = wrapper.get_earnings_estimate("AAPL")

    assert result == {"columns": ["avg"], "data": [[1.2]], "index": ["0q"]}


def test_get_revenue_estimate_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"avg": [1000.0]}, index=["0q"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_revenue_estimate.return_value = payload
        result = wrapper.get_revenue_estimate("AAPL")

    assert result == {"columns": ["avg"], "data": [[1000.0]], "index": ["0q"]}


def test_get_earnings_history_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"epsActual": [1.4]}, index=["2026-01-30"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_earnings_history.return_value = payload
        result = wrapper.get_earnings_history("AAPL")

    assert result == {"columns": ["epsActual"], "data": [[1.4]], "index": ["2026-01-30"]}


def test_get_eps_trend_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"current": [5.2]}, index=["0q"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_eps_trend.return_value = payload
        result = wrapper.get_eps_trend("AAPL")

    assert result == {"columns": ["current"], "data": [[5.2]], "index": ["0q"]}


def test_get_eps_revisions_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"upLast7days": [2]}, index=["0q"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_eps_revisions.return_value = payload
        result = wrapper.get_eps_revisions("AAPL")

    assert result == {"columns": ["upLast7days"], "data": [[2]], "index": ["0q"]}


def test_get_growth_estimates_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"stockTrend": ["+10%"]}, index=["AAPL"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_growth_estimates.return_value = payload
        result = wrapper.get_growth_estimates("AAPL")

    assert result == {"columns": ["stockTrend"], "data": [["+10%"]], "index": ["AAPL"]}


def test_get_sustainability_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"Value": [50.0]}, index=["totalEsg"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_sustainability.return_value = payload
        result = wrapper.get_sustainability("AAPL")

    assert result == {"columns": ["Value"], "data": [[50.0]], "index": ["totalEsg"]}


def test_get_major_holders_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"Value": [0.55]}, index=["Percent held by insiders"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_major_holders.return_value = payload
        result = wrapper.get_major_holders("AAPL")

    assert result == {"columns": ["Value"], "data": [[0.55]], "index": ["Percent held by insiders"]}


def test_get_institutional_holders_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"Shares": [1000]}, index=["Example Fund"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_institutional_holders.return_value = payload
        result = wrapper.get_institutional_holders("AAPL")

    assert result == {"columns": ["Shares"], "data": [[1000]], "index": ["Example Fund"]}


def test_get_mutualfund_holders_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"Shares": [500]}, index=["Example Mutual Fund"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_mutualfund_holders.return_value = payload
        result = wrapper.get_mutualfund_holders("AAPL")

    assert result == {"columns": ["Shares"], "data": [[500]], "index": ["Example Mutual Fund"]}


def test_get_insider_purchases_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"Shares": [250]}, index=["Purchases"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_insider_purchases.return_value = payload
        result = wrapper.get_insider_purchases("AAPL")

    assert result == {"columns": ["Shares"], "data": [[250]], "index": ["Purchases"]}


def test_get_insider_transactions_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"Shares": [100]}, index=["2026-01-01"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_insider_transactions.return_value = payload
        result = wrapper.get_insider_transactions("AAPL")

    assert result == {"columns": ["Shares"], "data": [[100]], "index": ["2026-01-01"]}


def test_get_insider_roster_holders_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"Position": ["Director"]}, index=["Example Insider"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_insider_roster_holders.return_value = payload
        result = wrapper.get_insider_roster_holders("AAPL")

    assert result == {"columns": ["Position"], "data": [["Director"]], "index": ["Example Insider"]}


class _FakeFundsData:
    def __init__(self):
        self.asset_classes = {"stockPosition": 99.0}
        self.bond_holdings = pd.DataFrame({"SPY": [1.0]}, index=["Maturity"])
        self.bond_ratings = {"aaa": 10.0}
        self.description = "Example fund"
        self.equity_holdings = pd.DataFrame({"SPY": [5.0]}, index=["Price/Book"])
        self.fund_operations = pd.DataFrame({"SPY": [0.09]}, index=["Annual Report Expense Ratio"])
        self.fund_overview = {"family": "Example"}
        self.sector_weightings = {"technology": 30.0}
        self.top_holdings = pd.DataFrame({"Name": ["Apple"], "Holding Percent": [7.0]})

    def quote_type(self):
        return "ETF"


def test_get_funds_data_returns_aggregate_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_funds_data("SPY")

    assert result["quote_type"] == "ETF"
    assert result["description"] == "Example fund"
    assert result["asset_classes"] == {"stockPosition": 99.0}
    assert result["bond_ratings"] == {"aaa": 10.0}


def test_get_fund_asset_classes_returns_mapping_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_fund_asset_classes("SPY")

    assert result == {"stockPosition": 99.0}


def test_get_fund_bond_holdings_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_fund_bond_holdings("SPY")

    assert result == {"columns": ["SPY"], "data": [[1.0]], "index": ["Maturity"]}


def test_get_fund_bond_ratings_returns_mapping_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_fund_bond_ratings("SPY")

    assert result == {"aaa": 10.0}


def test_get_fund_description_returns_text_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_fund_description("SPY")

    assert result == {"value": "Example fund"}


def test_get_fund_equity_holdings_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_fund_equity_holdings("SPY")

    assert result == {"columns": ["SPY"], "data": [[5.0]], "index": ["Price/Book"]}


def test_get_fund_operations_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_fund_operations("SPY")

    assert result == {"columns": ["SPY"], "data": [[0.09]], "index": ["Annual Report Expense Ratio"]}


def test_get_fund_overview_returns_mapping_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_fund_overview("SPY")

    assert result == {"family": "Example"}


def test_get_fund_sector_weightings_returns_mapping_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_fund_sector_weightings("SPY")

    assert result == {"technology": 30.0}


def test_get_fund_top_holdings_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_fund_top_holdings("SPY")

    assert result == {"columns": ["Name", "Holding Percent"], "data": [["Apple", 7.0]], "index": [0]}


def test_get_fund_quote_type_returns_text_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = _FakeFundsData()
        result = wrapper.get_fund_quote_type("SPY")

    assert result == {"value": "ETF"}


class _FakeCalendars:
    def __init__(self, start=None, end=None):
        self.start = start
        self.end = end

    def get_earnings_calendar(self, **kwargs):
        return pd.DataFrame({"Symbol": ["AAPL"]}, index=["2026-01-30"])

    def get_economic_events_calendar(self, **kwargs):
        return pd.DataFrame({"Event": ["CPI"]}, index=["2026-01-10"])

    def get_ipo_info_calendar(self, **kwargs):
        return pd.DataFrame({"Company": ["Example Co"]}, index=["2026-01-15"])

    def get_splits_calendar(self, **kwargs):
        return pd.DataFrame({"Symbol": ["XYZ"]}, index=["2026-01-20"])


def test_get_calendars_returns_aggregate_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Calendars", _FakeCalendars):
        result = wrapper.get_calendars(start="2026-01-01", end="2026-03-31")

    assert result["earnings_calendar"] == {"columns": ["Symbol"], "data": [["AAPL"]], "index": ["2026-01-30"]}
    assert result["economic_events_calendar"] == {"columns": ["Event"], "data": [["CPI"]], "index": ["2026-01-10"]}
    assert result["ipo_calendar"] == {"columns": ["Company"], "data": [["Example Co"]], "index": ["2026-01-15"]}
    assert result["splits_calendar"] == {"columns": ["Symbol"], "data": [["XYZ"]], "index": ["2026-01-20"]}


def test_get_earnings_calendar_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Calendars", _FakeCalendars):
        result = wrapper.get_earnings_calendar(start="2026-01-01", end="2026-03-31")

    assert result == {"columns": ["Symbol"], "data": [["AAPL"]], "index": ["2026-01-30"]}


def test_get_economic_events_calendar_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Calendars", _FakeCalendars):
        result = wrapper.get_economic_events_calendar(start="2026-01-01", end="2026-03-31")

    assert result == {"columns": ["Event"], "data": [["CPI"]], "index": ["2026-01-10"]}


def test_get_ipo_calendar_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Calendars", _FakeCalendars):
        result = wrapper.get_ipo_calendar(start="2026-01-01", end="2026-03-31")

    assert result == {"columns": ["Company"], "data": [["Example Co"]], "index": ["2026-01-15"]}


def test_get_splits_calendar_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Calendars", _FakeCalendars):
        result = wrapper.get_splits_calendar(start="2026-01-01", end="2026-03-31")

    assert result == {"columns": ["Symbol"], "data": [["XYZ"]], "index": ["2026-01-20"]}


class _FakeTickerObject:
    def __init__(self, ticker: str):
        self.ticker = ticker


class _FakeSector:
    def __init__(self, key: str):
        self.key = key
        self.name = "Technology"
        self.symbol = "^YH311"
        self.overview = {"description": "Example"}
        self.research_reports = [{"id": "report-1"}]
        self.industries = pd.DataFrame({"name": ["Software"]}, index=[0])
        self.top_companies = pd.DataFrame({"name": ["Apple"]}, index=[0])
        self.top_etfs = {"XLK": "Technology Select Sector SPDR Fund"}
        self.top_mutual_funds = {"FSPTX": "Fidelity Select Technology"}
        self.ticker = _FakeTickerObject("^YH311")


class _FakeIndustry:
    def __init__(self, key: str):
        self.key = key
        self.name = "Software - Infrastructure"
        self.symbol = "^YH31110030"
        self.sector_key = "technology"
        self.sector_name = "Technology"
        self.overview = {"description": "Example"}
        self.research_reports = [{"id": "report-1"}]
        self.top_companies = pd.DataFrame({"name": ["Microsoft"]}, index=[0])
        self.top_growth_companies = pd.DataFrame({"name": ["Cloud Co"]}, index=[0])
        self.top_performing_companies = pd.DataFrame({"name": ["Infra Co"]}, index=[0])
        self.ticker = _FakeTickerObject("^YH31110030")


def test_get_sector_returns_aggregate_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Sector", _FakeSector):
        result = wrapper.get_sector("technology")

    assert result["key"] == "technology"
    assert result["name"] == "Technology"
    assert result["symbol"] == "^YH311"
    assert result["ticker_symbol"] == "^YH311"


def test_get_sector_industries_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Sector", _FakeSector):
        result = wrapper.get_sector_industries("technology")

    assert result == {"columns": ["name"], "data": [["Software"]], "index": [0]}


def test_get_sector_top_etfs_returns_mapping_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Sector", _FakeSector):
        result = wrapper.get_sector_top_etfs("technology")

    assert result == {"XLK": "Technology Select Sector SPDR Fund"}


def test_get_sector_ticker_returns_text_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Sector", _FakeSector):
        result = wrapper.get_sector_ticker("technology")

    assert result == {"value": "^YH311"}


def test_get_industry_returns_aggregate_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Industry", _FakeIndustry):
        result = wrapper.get_industry("software-infrastructure")

    assert result["key"] == "software-infrastructure"
    assert result["symbol"] == "^YH31110030"
    assert result["sector_key"] == "technology"
    assert result["ticker_symbol"] == "^YH31110030"


def test_get_industry_top_growth_companies_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Industry", _FakeIndustry):
        result = wrapper.get_industry_top_growth_companies("software-infrastructure")

    assert result == {"columns": ["name"], "data": [["Cloud Co"]], "index": [0]}


def test_get_industry_ticker_returns_text_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Industry", _FakeIndustry):
        result = wrapper.get_industry_ticker("software-infrastructure")

    assert result == {"value": "^YH31110030"}


def test_get_capital_gains_returns_series_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.Series([0.25], index=["2026-01-01"], name="Capital Gains")

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_capital_gains.return_value = payload
        result = wrapper.get_capital_gains("VTI", period="1y")

    assert result == {"name": "Capital Gains", "index": ["2026-01-01"], "data": [0.25]}


def test_get_shares_full_returns_series_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.Series([1000], index=["2025-01-01"], name="Shares")

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_shares_full.return_value = payload
        result = wrapper.get_shares_full("AAPL", start="2025-01-01", end="2026-01-01")

    assert result == {"name": "Shares", "index": ["2025-01-01"], "data": [1000]}


def test_get_sec_filings_returns_list_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = [{"date": "2026-02-24", "type": "8-K"}]

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_sec_filings.return_value = payload
        result = wrapper.get_sec_filings("AAPL")

    assert result == payload


def test_get_info_returns_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.info = {"symbol": "AAPL", "shortName": "Apple Inc."}
        result = wrapper.get_info("AAPL")

    assert result == {"symbol": "AAPL", "shortName": "Apple Inc."}


@pytest.mark.parametrize("method_name,args", [
    ("get_batch_info", (["", " "],)),
    ("get_batch_quote_snapshot", (["", " "],)),
    ("get_batch_news", (["", " "],)),
    ("download", (["", " "],)),
])
def test_batch_methods_reject_empty_symbols(method_name, args):
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with pytest.raises(YFinanceError) as exc_info:
        getattr(wrapper, method_name)(*args)

    assert exc_info.value.category == "invalid_input"


def test_download_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"close": [100.0]}, index=["2026-01-01"])

    with patch("yfinance_mcp.wrapper.yf.download", return_value=payload) as mocked:
        result = wrapper.download(["AAPL", "MSFT"], period="1mo")

    assert result == {"columns": ["close"], "data": [[100.0]], "index": ["2026-01-01"]}
    mocked.assert_called_once()


def test_get_news_and_option_endpoints_return_payloads():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeChain:
        calls = pd.DataFrame({"strike": [500]})
        puts = pd.DataFrame({"strike": [400]})

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_news.return_value = [{"title": "Example"}]
        mocked_ticker.return_value.options = ("2026-06-19",)
        mocked_ticker.return_value.option_chain.return_value = FakeChain()

        news = wrapper.get_news("AAPL")
        expirations = wrapper.get_option_expirations("AAPL")
        chain = wrapper.get_option_chain("AAPL", date="2026-06-19")

    assert news == [{"title": "Example"}]
    assert expirations == ["2026-06-19"]
    assert chain["symbol"] == "AAPL"
    assert chain["calls"]["columns"] == ["strike"]
    assert chain["puts"]["columns"] == ["strike"]


@pytest.mark.parametrize("method_name", ["get_actions", "get_dividends", "get_splits"])
def test_series_wrappers_return_series_payload(method_name):
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.Series([1.0], index=["2026-01-01"], name="Series")

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        getattr(mocked_ticker.return_value, method_name).return_value = payload
        result = getattr(wrapper, method_name)("AAPL", period="1y")

    assert result == {"name": "Series", "index": ["2026-01-01"], "data": [1.0]}


def test_shares_and_recommendation_endpoints_raise_on_empty_payloads():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_shares_full.return_value = pd.Series(dtype=float)
        mocked_ticker.return_value.get_earnings_dates.return_value = pd.DataFrame()
        mocked_ticker.return_value.get_recommendations.return_value = pd.DataFrame()
        with pytest.raises(YFinanceError):
            wrapper.get_shares_full("AAPL")
        with pytest.raises(YFinanceError):
            wrapper.get_earnings_dates("AAPL")
        with pytest.raises(YFinanceError):
            wrapper.get_recommendations("AAPL")


def test_get_market_status_rejects_invalid_market():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeMarket:
        def __init__(self, market: str, timeout: int):
            self.status = {"finance": {"error": {"description": "invalid broad market region"}}}

    with patch("yfinance_mcp.wrapper.yf.Market", FakeMarket):
        with pytest.raises(YFinanceError):
            wrapper.get_market_status("america")


@pytest.mark.parametrize("method_name, expected", [
    ("get_sector_overview", {"description": "Example"}),
    ("get_sector_research_reports", [{"id": "report-1"}]),
    ("get_sector_top_companies", {"columns": ["name"], "data": [["Apple"]], "index": [0]}),
    ("get_sector_top_mutual_funds", {"FSPTX": "Fidelity Select Technology"}),
    ("get_industry_overview", {"description": "Example"}),
    ("get_industry_research_reports", [{"id": "report-1"}]),
    ("get_industry_top_companies", {"columns": ["name"], "data": [["Microsoft"]], "index": [0]}),
    ("get_industry_top_performing_companies", {"columns": ["name"], "data": [["Infra Co"]], "index": [0]}),
])
def test_sector_and_industry_field_endpoints(method_name, expected):
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    patch_target = "yfinance_mcp.wrapper.yf.Sector" if method_name.startswith("get_sector") else "yfinance_mcp.wrapper.yf.Industry"
    key = "technology" if method_name.startswith("get_sector") else "software-infrastructure"

    fake_type = _FakeSector if method_name.startswith("get_sector") else _FakeIndustry
    with patch(patch_target, fake_type):
        result = getattr(wrapper, method_name)(key)

    assert result == expected


def test_search_and_lookup_return_serialized_payloads_and_reject_empty_queries():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class FakeSearch:
        def __init__(self, *args, **kwargs):
            self.all = {"quotes": [{"symbol": "AAPL"}]}

    class FakeLookup:
        def __init__(self, *args, **kwargs):
            pass

        def get_all(self, count=25):
            return pd.DataFrame({"shortName": ["Apple Inc."]}, index=["AAPL"])

        get_stock = get_all
        get_etf = get_all
        get_mutualfund = get_all
        get_index = get_all
        get_future = get_all
        get_currency = get_all
        get_cryptocurrency = get_all

    with patch("yfinance_mcp.wrapper.yf.Search", FakeSearch), patch("yfinance_mcp.wrapper.yf.Lookup", FakeLookup):
        assert wrapper.search("apple") == {"quotes": [{"symbol": "AAPL"}]}
        lookup_result = wrapper.lookup("apple")
        assert lookup_result["query"] == "apple"
        assert lookup_result["stock"]["index"] == ["AAPL"]

    with pytest.raises(YFinanceError):
        wrapper.search(" ")
    with pytest.raises(YFinanceError):
        wrapper.lookup(" ")


def test_statement_endpoints_cover_supported_and_invalid_frequencies():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    ticker = SimpleNamespace(
        quarterly_income_stmt=pd.DataFrame({"value": [1]}, index=["2026Q1"]),
        ttm_income_stmt=pd.DataFrame({"value": [2]}, index=["ttm"]),
        quarterly_balance_sheet=pd.DataFrame({"value": [3]}, index=["2026Q1"]),
        quarterly_cashflow=pd.DataFrame({"value": [4]}, index=["2026Q1"]),
        ttm_cashflow=pd.DataFrame({"value": [5]}, index=["ttm"]),
        get_income_stmt=lambda pretty=False, freq="yearly": pd.DataFrame({"value": [6]}, index=["2025"]),
        get_balance_sheet=lambda pretty=False, freq="yearly": pd.DataFrame({"value": [7]}, index=["2025"]),
        get_cashflow=lambda pretty=False, freq="yearly": pd.DataFrame({"value": [8]}, index=["2025"]),
    )

    with patch.object(wrapper, "_ticker", return_value=ticker):
        assert wrapper.get_income_stmt("AAPL", freq="yearly")["data"] == [[6]]
        assert wrapper.get_income_stmt("AAPL", freq="quarterly")["data"] == [[1]]
        assert wrapper.get_income_stmt("AAPL", freq="trailing")["data"] == [[2]]
        assert wrapper.get_balance_sheet("AAPL", freq="yearly")["data"] == [[7]]
        assert wrapper.get_balance_sheet("AAPL", freq="quarterly")["data"] == [[3]]
        assert wrapper.get_cashflow("AAPL", freq="yearly")["data"] == [[8]]
        assert wrapper.get_cashflow("AAPL", freq="quarterly")["data"] == [[4]]
        assert wrapper.get_cashflow("AAPL", freq="trailing")["data"] == [[5]]

    with pytest.raises(YFinanceError):
        wrapper.get_income_stmt("AAPL", freq="monthly")
    with pytest.raises(YFinanceError):
        wrapper.get_balance_sheet("AAPL", freq="trailing")
    with pytest.raises(YFinanceError):
        wrapper.get_earnings("AAPL", freq="monthly")


def test_statement_call_rejects_unsupported_statement_name():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with pytest.raises(YFinanceError) as exc_info:
        wrapper._statement_call("AAPL", "unsupported", freq="yearly", pretty=False)

    assert exc_info.value.category == "internal_error"


def test_table_getter_raises_on_empty_dataframe():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_recommendations_summary.return_value = pd.DataFrame()
        with pytest.raises(YFinanceError):
            wrapper.get_recommendations_summary("AAPL")


def test_series_call_raises_on_empty_series():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_actions.return_value = pd.Series(dtype=float)
        with pytest.raises(YFinanceError):
            wrapper.get_actions("AAPL")


def test_get_shares_returns_explicit_unsupported_error():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with pytest.raises(YFinanceError) as exc_info:
        wrapper.get_shares("AAPL")

    assert exc_info.value.category == "invalid_input"
    assert "get_shares endpoint is not supported" in str(exc_info.value)


def test_get_earnings_returns_explicit_deprecation_error():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    with pytest.raises(YFinanceError) as exc_info:
        wrapper.get_earnings("AAPL", freq="yearly")

    assert exc_info.value.category == "invalid_input"
    assert "deprecated upstream" in str(exc_info.value)


def test_funds_helpers_raise_when_no_funds_data():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_funds_data.return_value = None
        with pytest.raises(YFinanceError):
            wrapper.get_funds_data("SPY")


def test_calendar_date_and_lookup_resolution_helpers():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    assert wrapper._normalize_calendar_date(None) is None
    assert wrapper._normalize_calendar_date(date(2026, 1, 1)) == date(2026, 1, 1)
    assert wrapper._normalize_calendar_date("2026-01-01") == date(2026, 1, 1)

    with patch.object(wrapper, "lookup", return_value={"stock": None, "all": None}):
        assert wrapper._resolve_quote_symbol("Google") == "GOOGLE"

    with patch.object(wrapper, "lookup", return_value={"stock": None, "all": {"columns": [], "data": [], "index": []}}):
        assert wrapper._lookup_stock_candidates("Google", count=10) == []


def test_cached_call_hit_and_stale_paths():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    wrapper.cache.set("hit", {"value": 1}, ttl_seconds=60)
    assert wrapper._cached_call("hit", 60, lambda: {"value": 2}, {"symbol": "AAPL"}, allow_stale=True) == {"value": 1}

    class FakeCache:
        def __init__(self):
            self.saved = None

        def get(self, key):
            return None

        def get_entry(self, key, allow_stale=False):
            assert allow_stale is True
            return SimpleNamespace(value={"stale": True})

        def set(self, key, value, ttl_seconds):
            self.saved = (key, value, ttl_seconds)

    fake_cache = FakeCache()
    wrapper.cache = fake_cache
    with patch.object(wrapper, "_run_with_retry", return_value={"fresh": True}) as mocked_retry:
        result = wrapper._cached_call("miss", 30, lambda: {"fresh": True}, {"symbol": "AAPL"}, allow_stale=True)

    assert result == {"fresh": True}
    assert mocked_retry.call_args.kwargs["stale_value"] == {"stale": True}


def test_retry_timeout_and_failure_paths():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    wrapper.retry_policy.max_retries = 0
    wrapper.retry_policy.total_timeout = 0

    with patch("yfinance_mcp.wrapper.logger") as mocked_logger:
        with pytest.raises(YFinanceError):
            wrapper._run_with_retry(
                operation=lambda: (_ for _ in ()).throw(RuntimeError("timeout")),
                error_context={"symbol": "AAPL"},
            )

    warning_events = [call.args[0] for call in mocked_logger.warning.call_args_list]
    assert "upstream_timeout" in warning_events
    assert "request_deadline_exceeded" in warning_events
