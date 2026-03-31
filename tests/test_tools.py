from unittest.mock import patch

from yfinance_mcp import server


DATAFRAME_PAYLOAD = {
    "columns": ["close"],
    "data": [[1.0], [2.0]],
    "index": ["2024-01-01", "2024-01-02"],
}


def test_get_quote_snapshot_returns_wrapper_payload():
    with patch.object(server.wrapper, "get_fast_info", return_value={"lastPrice": 123.45, "currency": "USD"}) as mocked:
        result = server.get_quote_snapshot("TSLA")

    assert result["lastPrice"] == 123.45
    assert result["currency"] == "USD"
    mocked.assert_called_once_with("TSLA")


def test_get_info_returns_named_response_model_payload():
    payload = {"symbol": "TSLA", "shortName": "Tesla, Inc.", "marketCap": 1000}
    with patch.object(server.wrapper, "get_info", return_value=payload) as mocked:
        result = server.get_info("TSLA")

    assert result == payload
    mocked.assert_called_once_with("TSLA")


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


def test_get_history_rejects_invalid_request():
    try:
        server.get_history("", period="1mo")
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for invalid request")

    assert "symbol" in message
