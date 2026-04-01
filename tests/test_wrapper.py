from unittest.mock import patch
import pandas as pd

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

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker, patch.object(wrapper, "lookup") as mocked_lookup:
        mocked_ticker.return_value.fast_info = {"lastPrice": 123.45, "currency": "USD"}

        result = wrapper.get_fast_info("GOOG")

    assert result == {"lastPrice": 123.45, "currency": "USD"}
    mocked_ticker.assert_called_once_with("GOOG")
    mocked_lookup.assert_not_called()


def test_get_fast_info_resolves_unique_company_name_via_lookup():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    lookup_payload = {
        "query": "Tesla",
        "stock": {
            "columns": ["symbol", "shortName"],
            "data": [["TSLA", "Tesla, Inc."]],
            "index": [0],
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


def test_get_fast_info_rejects_ambiguous_company_name_lookup():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    lookup_payload = {
        "query": "Google",
        "stock": {
            "columns": ["symbol", "shortName"],
            "data": [["GOOG", "Alphabet Inc."], ["GOOGL", "Alphabet Inc."]],
            "index": [0, 1],
        },
    }

    with patch.object(wrapper, "lookup", return_value=lookup_payload):
        try:
            wrapper.get_fast_info("Google")
        except YFinanceError as exc:
            assert exc.category == "invalid_input"
            assert "ambiguous" in str(exc)
            assert exc.details["matches"] == [
                {"symbol": "GOOG", "name": "Alphabet Inc."},
                {"symbol": "GOOGL", "name": "Alphabet Inc."},
            ]
        else:  # pragma: no cover - defensive
            raise AssertionError("Expected YFinanceError for ambiguous company-name quote request")


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


def test_get_earnings_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"Earnings": [100.0]}, index=["2025"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_earnings.return_value = payload
        result = wrapper.get_earnings("AAPL", freq="yearly")

    assert result == {"columns": ["Earnings"], "data": [[100.0]], "index": ["2025"]}


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


def test_get_shares_returns_dataframe_payload():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())
    payload = pd.DataFrame({"BasicShares": [1000]}, index=["2025"])

    with patch("yfinance_mcp.wrapper.yf.Ticker") as mocked_ticker:
        mocked_ticker.return_value.get_shares.return_value = payload
        result = wrapper.get_shares("AAPL")

    assert result == {"columns": ["BasicShares"], "data": [[1000]], "index": ["2025"]}


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
