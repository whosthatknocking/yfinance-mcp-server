from unittest.mock import patch

from yfinance_mcp import server


DATAFRAME_PAYLOAD = {
    "columns": ["close"],
    "data": [[1.0], [2.0]],
    "index": ["2024-01-01", "2024-01-02"],
}

SERIES_PAYLOAD = {
    "name": "Dividends",
    "index": ["2024-01-01", "2024-02-01"],
    "data": [0.24, 0.24],
}


def test_get_quote_snapshot_returns_wrapper_payload():
    with patch.object(server.wrapper, "get_fast_info", return_value={"lastPrice": 123.45, "currency": "USD"}) as mocked:
        result = server.get_quote_snapshot("TSLA")

    assert result["lastPrice"] == 123.45
    assert result["currency"] == "USD"
    mocked.assert_called_once_with("TSLA")


def test_get_batch_quote_snapshot_returns_named_response_model_payload():
    payload = {
        "symbols": ["AAPL", "MSFT"],
        "results": {
            "AAPL": {"lastPrice": 123.45, "currency": "USD"},
            "MSFT": {"lastPrice": 234.56, "currency": "USD"},
        },
    }
    with patch.object(server.wrapper, "get_batch_quote_snapshot", return_value=payload) as mocked:
        result = server.get_batch_quote_snapshot(["AAPL", "MSFT"])

    assert result == payload
    mocked.assert_called_once_with(symbols=["AAPL", "MSFT"])


def test_get_info_returns_named_response_model_payload():
    payload = {"symbol": "TSLA", "shortName": "Tesla, Inc.", "marketCap": 1000}
    with patch.object(server.wrapper, "get_info", return_value=payload) as mocked:
        result = server.get_info("TSLA")

    assert result == payload
    mocked.assert_called_once_with("TSLA")


def test_get_batch_info_returns_named_response_model_payload():
    payload = {
        "symbols": ["AAPL", "MSFT"],
        "results": {
            "AAPL": {"symbol": "AAPL", "shortName": "Apple Inc."},
            "MSFT": {"symbol": "MSFT", "shortName": "Microsoft Corporation"},
        },
    }
    with patch.object(server.wrapper, "get_batch_info", return_value=payload) as mocked:
        result = server.get_batch_info(["AAPL", "MSFT"])

    assert result == payload
    mocked.assert_called_once_with(symbols=["AAPL", "MSFT"])


def test_get_history_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_history", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_history("AAPL", period="1mo")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once()


def test_download_history_returns_dataframe_payload():
    with patch.object(server.wrapper, "download", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.download_history(["AAPL", "MSFT"], interval="1wk")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once()


def test_get_news_returns_news_list():
    news_item = {"title": "Tesla rises", "publisher": "Example News", "link": "https://example.com/story"}
    with patch.object(server.wrapper, "get_news", return_value=[news_item]) as mocked:
        result = server.get_news("TSLA")

    assert result == [news_item]
    mocked.assert_called_once_with(symbol="TSLA", count=10, tab="news")


def test_get_option_expirations_returns_string_list():
    with patch.object(server.wrapper, "get_option_expirations", return_value=["2025-06-20", "2025-07-18"]) as mocked:
        result = server.get_option_expirations("SPY")

    assert result == ["2025-06-20", "2025-07-18"]
    mocked.assert_called_once_with("SPY")


def test_get_actions_returns_series_payload():
    with patch.object(server.wrapper, "get_actions", return_value=SERIES_PAYLOAD) as mocked:
        result = server.get_actions("AAPL", period="1y")

    assert result == SERIES_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL", period="1y")


def test_get_dividends_returns_series_payload():
    with patch.object(server.wrapper, "get_dividends", return_value=SERIES_PAYLOAD) as mocked:
        result = server.get_dividends("AAPL", period="1y")

    assert result == SERIES_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL", period="1y")


def test_get_splits_returns_series_payload():
    with patch.object(server.wrapper, "get_splits", return_value=SERIES_PAYLOAD) as mocked:
        result = server.get_splits("AAPL", period="1y")

    assert result == SERIES_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL", period="1y")


def test_get_earnings_dates_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_earnings_dates", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_earnings_dates("AAPL", limit=4, offset=0)

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL", limit=4, offset=0)


def test_get_ticker_calendar_returns_calendar_payload():
    payload = {"Dividend Date": "2026-02-11", "Earnings Average": 1.95}
    with patch.object(server.wrapper, "get_ticker_calendar", return_value=payload) as mocked:
        result = server.get_ticker_calendar("AAPL")

    assert result == payload
    mocked.assert_called_once_with("AAPL")


def test_get_recommendations_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_recommendations", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_recommendations("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with("AAPL")


def test_get_analyst_price_targets_returns_payload():
    payload = {"current": 253.79, "high": 350.0, "low": 205.0, "mean": 295.31, "median": 300.0}
    with patch.object(server.wrapper, "get_analyst_price_targets", return_value=payload) as mocked:
        result = server.get_analyst_price_targets("AAPL")

    assert result == payload
    mocked.assert_called_once_with("AAPL")


def test_get_earnings_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_earnings", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_earnings("AAPL", freq="quarterly")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL", freq="quarterly")


def test_get_recommendations_summary_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_recommendations_summary", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_recommendations_summary("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_upgrades_downgrades_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_upgrades_downgrades", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_upgrades_downgrades("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_earnings_estimate_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_earnings_estimate", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_earnings_estimate("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_revenue_estimate_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_revenue_estimate", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_revenue_estimate("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_earnings_history_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_earnings_history", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_earnings_history("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_eps_trend_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_eps_trend", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_eps_trend("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_eps_revisions_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_eps_revisions", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_eps_revisions("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_growth_estimates_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_growth_estimates", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_growth_estimates("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_sustainability_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_sustainability", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_sustainability("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_income_stmt_returns_statement_payload():
    with patch.object(server.wrapper, "get_income_stmt", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_income_stmt("AMZN", freq="yearly")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AMZN", freq="yearly", pretty=False)


def test_get_market_summary_returns_named_response_model_payload():
    payload = {"market": "us", "summary": [{"symbol": "^GSPC"}]}
    with patch.object(server.wrapper, "get_market_summary", return_value=payload) as mocked:
        result = server.get_market_summary("us")

    assert result == payload
    mocked.assert_called_once_with(market="us")


def test_search_returns_named_response_model_payload():
    payload = {"quotes": [{"symbol": "MSFT"}], "news": [], "lists": [], "research": [], "nav": []}
    with patch.object(server.wrapper, "search", return_value=payload) as mocked:
        result = server.search("microsoft", max_results=5)

    assert result == payload
    mocked.assert_called_once_with(
        query="microsoft",
        max_results=5,
        news_count=8,
        lists_count=8,
        include_cb=True,
        include_nav_links=False,
        include_research=False,
        include_cultural_assets=False,
        enable_fuzzy_query=False,
        recommended=8,
    )


def test_lookup_returns_named_response_model_payload():
    empty_table = {"columns": [], "data": [], "index": []}
    payload = {
        "query": "microsoft",
        "all": {"columns": ["symbol"], "data": [["MSFT"]], "index": ["MSFT"]},
        "stock": {"columns": ["symbol"], "data": [["MSFT"]], "index": ["MSFT"]},
        "etf": empty_table,
        "mutualfund": empty_table,
        "index": empty_table,
        "future": empty_table,
        "currency": empty_table,
        "cryptocurrency": empty_table,
    }
    with patch.object(server.wrapper, "lookup", return_value=payload) as mocked:
        result = server.lookup("microsoft", count=10)

    assert result == payload
    mocked.assert_called_once_with(query="microsoft", count=10)


def test_get_history_rejects_invalid_request():
    try:
        server.get_history("", period="1mo")
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for invalid request")

    assert "symbol" in message
