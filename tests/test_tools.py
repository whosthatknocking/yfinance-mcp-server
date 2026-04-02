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
    payload = {"lastPrice": 123.45, "currency": "USD", "fiftyDayAverage": 200.0}
    with patch.object(server.wrapper, "get_fast_info", return_value=payload) as mocked:
        result = server.get_quote_snapshot("TSLA")

    assert result["lastPrice"] == 123.45
    assert result["currency"] == "USD"
    assert result["additional_fields"] == {"fiftyDayAverage": 200.0}
    mocked.assert_called_once_with("TSLA")


def test_run_tool_logs_upstream_call_count():
    with patch.object(server, "next_request_id", return_value="req-123"):
        with patch.object(server, "logger") as mocked_logger:
            result = server._run_tool("test_tool", lambda: "ok")

    assert result == "ok"
    completion_call = mocked_logger.info.call_args_list[-1]
    assert completion_call.args[0] == "tool_completed"
    assert completion_call.kwargs["tool_name"] == "test_tool"
    assert completion_call.kwargs["upstream_call_count"] == 0
    assert "elapsed_ms" in completion_call.kwargs


def test_run_tool_logs_quote_snapshot_completion_details():
    payload = {"lastPrice": 123.45, "currency": "USD", "additional_fields": {"symbol": "ORCL"}}

    with patch.object(server, "next_request_id", return_value="req-123"):
        with patch.object(server, "logger") as mocked_logger:
            result = server._run_tool("get_quote_snapshot", lambda: payload)

    assert result == payload
    completion_call = mocked_logger.info.call_args_list[-1]
    assert completion_call.args[0] == "tool_completed"
    assert completion_call.kwargs["tool_name"] == "get_quote_snapshot"
    assert completion_call.kwargs["last_price"] == 123.45
    assert completion_call.kwargs["currency"] == "USD"
    assert completion_call.kwargs["quote_symbol"] == "ORCL"


def test_registered_tools_are_async_to_avoid_blocking_http_event_loop():
    tool = server.mcp._tool_manager.get_tool("get_quote_snapshot")

    assert tool is not None
    assert tool.is_async is True


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


def test_get_batch_news_returns_list_payload():
    payload = [{"title": "Example", "publisher": "Example News"}]
    with patch.object(server.wrapper, "get_batch_news", return_value=payload) as mocked:
        result = server.get_batch_news(["AAPL", "MSFT"])

    assert result == payload
    mocked.assert_called_once_with(symbols=["AAPL", "MSFT"])


def test_get_info_returns_named_response_model_payload():
    payload = {"symbol": "TSLA", "shortName": "Tesla, Inc.", "marketCap": 1000, "industry": "Auto Manufacturers"}
    with patch.object(server.wrapper, "get_info", return_value=payload) as mocked:
        result = server.get_info("TSLA")

    assert result["symbol"] == "TSLA"
    assert result["shortName"] == "Tesla, Inc."
    assert result["marketCap"] == 1000
    assert result["additional_fields"] == {"industry": "Auto Manufacturers"}
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


def test_get_history_metadata_returns_mapping_payload():
    payload = {"currency": "USD", "instrumentType": "EQUITY"}
    with patch.object(server.wrapper, "get_history_metadata", return_value=payload) as mocked:
        result = server.get_history_metadata("AAPL")

    assert result == {"values": payload}
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_isin_returns_text_payload():
    payload = {"value": "US0378331005"}
    with patch.object(server.wrapper, "get_isin", return_value=payload) as mocked:
        result = server.get_isin("AAPL")

    assert result == payload
    mocked.assert_called_once_with(symbol="AAPL")


def test_download_history_returns_dataframe_payload():
    with patch.object(server.wrapper, "download", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.download_history(["AAPL", "MSFT"], interval="1wk")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once()


def test_get_news_returns_news_list():
    news_item = {
        "title": "Tesla rises",
        "publisher": "Example News",
        "link": "https://example.com/story",
        "uuid": "news-1",
        "summary": "Extra field",
    }
    with patch.object(server.wrapper, "get_news", return_value=[news_item]) as mocked:
        result = server.get_news("TSLA")

    assert result == [
        {
            "uuid": "news-1",
            "title": "Tesla rises",
            "publisher": "Example News",
            "link": "https://example.com/story",
            "additional_fields": {"summary": "Extra field"},
        }
    ]
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


def test_get_shares_full_returns_series_payload():
    with patch.object(server.wrapper, "get_shares_full", return_value=SERIES_PAYLOAD) as mocked:
        result = server.get_shares_full("AAPL", start="2025-01-01", end="2026-01-01")

    assert result == SERIES_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL", start="2025-01-01", end="2026-01-01")


def test_get_sec_filings_returns_list_payload():
    payload = [{"date": "2026-02-24", "type": "8-K"}]
    with patch.object(server.wrapper, "get_sec_filings", return_value=payload) as mocked:
        result = server.get_sec_filings("AAPL")

    assert result == [{"type": "8-K", "additional_fields": {"date": "2026-02-24"}}]
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_earnings_dates_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_earnings_dates", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_earnings_dates("AAPL", limit=4, offset=0)

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL", limit=4, offset=0)


def test_get_ticker_calendar_returns_calendar_payload():
    payload = {"dividendDate": "2026-02-11", "earningsAverage": 1.95, "customField": "extra"}
    with patch.object(server.wrapper, "get_ticker_calendar", return_value=payload) as mocked:
        result = server.get_ticker_calendar("AAPL")

    assert result == {
        "dividendDate": "2026-02-11",
        "earningsAverage": 1.95,
        "additional_fields": {"customField": "extra"},
    }
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_recommendations_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_recommendations", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_recommendations("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_analyst_price_targets_returns_payload():
    payload = {"current": 253.79, "high": 350.0, "low": 205.0, "mean": 295.31, "median": 300.0, "numberOfAnalysts": 42}
    with patch.object(server.wrapper, "get_analyst_price_targets", return_value=payload) as mocked:
        result = server.get_analyst_price_targets("AAPL")

    assert result == {
        "current": 253.79,
        "high": 350.0,
        "low": 205.0,
        "mean": 295.31,
        "median": 300.0,
        "additional_fields": {"numberOfAnalysts": 42},
    }
    mocked.assert_called_once_with(symbol="AAPL")


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


def test_get_major_holders_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_major_holders", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_major_holders("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_institutional_holders_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_institutional_holders", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_institutional_holders("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_mutualfund_holders_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_mutualfund_holders", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_mutualfund_holders("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_insider_purchases_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_insider_purchases", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_insider_purchases("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_insider_transactions_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_insider_transactions", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_insider_transactions("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_insider_roster_holders_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_insider_roster_holders", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_insider_roster_holders("AAPL")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AAPL")


def test_get_funds_data_returns_named_response_model_payload():
    payload = {
        "quote_type": "ETF",
        "description": "Example fund",
        "asset_classes": {"stockPosition": 99.0},
        "bond_holdings": DATAFRAME_PAYLOAD,
        "bond_ratings": {"aaa": 10.0},
        "equity_holdings": DATAFRAME_PAYLOAD,
        "fund_operations": DATAFRAME_PAYLOAD,
        "fund_overview": {"family": "Example"},
        "sector_weightings": {"technology": 30.0},
        "top_holdings": DATAFRAME_PAYLOAD,
    }
    with patch.object(server.wrapper, "get_funds_data", return_value=payload) as mocked:
        result = server.get_funds_data("SPY")

    assert result == payload
    mocked.assert_called_once_with(symbol="SPY")


def test_get_fund_asset_classes_returns_mapping_payload():
    payload = {"stockPosition": 99.0}
    with patch.object(server.wrapper, "get_fund_asset_classes", return_value=payload) as mocked:
        result = server.get_fund_asset_classes("SPY")

    assert result == {"values": payload}
    mocked.assert_called_once_with(symbol="SPY")


def test_get_fund_bond_holdings_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_fund_bond_holdings", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_fund_bond_holdings("SPY")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="SPY")


def test_get_fund_bond_ratings_returns_mapping_payload():
    payload = {"aaa": 10.0}
    with patch.object(server.wrapper, "get_fund_bond_ratings", return_value=payload) as mocked:
        result = server.get_fund_bond_ratings("SPY")

    assert result == {"values": payload}
    mocked.assert_called_once_with(symbol="SPY")


def test_get_fund_description_returns_text_payload():
    payload = {"value": "Example fund"}
    with patch.object(server.wrapper, "get_fund_description", return_value=payload) as mocked:
        result = server.get_fund_description("SPY")

    assert result == payload
    mocked.assert_called_once_with(symbol="SPY")


def test_get_fund_equity_holdings_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_fund_equity_holdings", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_fund_equity_holdings("SPY")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="SPY")


def test_get_fund_operations_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_fund_operations", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_fund_operations("SPY")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="SPY")


def test_get_fund_overview_returns_mapping_payload():
    payload = {"family": "Example"}
    with patch.object(server.wrapper, "get_fund_overview", return_value=payload) as mocked:
        result = server.get_fund_overview("SPY")

    assert result == {"values": payload}
    mocked.assert_called_once_with(symbol="SPY")


def test_get_fund_sector_weightings_returns_mapping_payload():
    payload = {"technology": 30.0}
    with patch.object(server.wrapper, "get_fund_sector_weightings", return_value=payload) as mocked:
        result = server.get_fund_sector_weightings("SPY")

    assert result == {"values": payload}
    mocked.assert_called_once_with(symbol="SPY")


def test_get_fund_top_holdings_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_fund_top_holdings", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_fund_top_holdings("SPY")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="SPY")


def test_get_fund_quote_type_returns_text_payload():
    payload = {"value": "ETF"}
    with patch.object(server.wrapper, "get_fund_quote_type", return_value=payload) as mocked:
        result = server.get_fund_quote_type("SPY")

    assert result == payload
    mocked.assert_called_once_with(symbol="SPY")


def test_get_calendars_returns_named_response_model_payload():
    payload = {
        "earnings_calendar": DATAFRAME_PAYLOAD,
        "economic_events_calendar": DATAFRAME_PAYLOAD,
        "ipo_calendar": DATAFRAME_PAYLOAD,
        "splits_calendar": DATAFRAME_PAYLOAD,
    }
    with patch.object(server.wrapper, "get_calendars", return_value=payload) as mocked:
        result = server.get_calendars(start="2026-01-01", end="2026-03-31")

    assert result == payload
    mocked.assert_called_once_with(
        start="2026-01-01",
        end="2026-03-31",
        limit=12,
        offset=0,
        force=False,
        market_cap=None,
        filter_most_active=True,
    )


def test_get_earnings_calendar_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_earnings_calendar", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_earnings_calendar(start="2026-01-01", end="2026-03-31")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(
        start="2026-01-01",
        end="2026-03-31",
        limit=12,
        offset=0,
        force=False,
        market_cap=None,
        filter_most_active=True,
    )


def test_get_economic_events_calendar_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_economic_events_calendar", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_economic_events_calendar(start="2026-01-01", end="2026-03-31")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(start="2026-01-01", end="2026-03-31", limit=12, offset=0, force=False)


def test_get_ipo_calendar_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_ipo_calendar", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_ipo_calendar(start="2026-01-01", end="2026-03-31")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(start="2026-01-01", end="2026-03-31", limit=12, offset=0, force=False)


def test_get_splits_calendar_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_splits_calendar", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_splits_calendar(start="2026-01-01", end="2026-03-31")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(start="2026-01-01", end="2026-03-31", limit=12, offset=0, force=False)


def test_get_sector_returns_named_response_model_payload():
    payload = {
        "key": "technology",
        "name": "Technology",
        "symbol": "^YH311",
        "overview": {"description": "Example"},
        "research_reports": [{"id": "report-1"}],
        "industries": DATAFRAME_PAYLOAD,
        "top_companies": DATAFRAME_PAYLOAD,
        "top_etfs": {"XLK": "Technology Select Sector SPDR Fund"},
        "top_mutual_funds": {"FSPTX": "Fidelity Select Technology"},
        "ticker_symbol": "^YH311",
    }
    with patch.object(server.wrapper, "get_sector", return_value=payload) as mocked:
        result = server.get_sector("technology")

    assert result == payload
    mocked.assert_called_once_with(key="technology")


def test_get_sector_overview_returns_mapping_payload():
    payload = {"description": "Example"}
    with patch.object(server.wrapper, "get_sector_overview", return_value=payload) as mocked:
        result = server.get_sector_overview("technology")

    assert result == {"values": payload}
    mocked.assert_called_once_with(key="technology")


def test_get_sector_research_reports_returns_list_payload():
    payload = [{"id": "report-1"}]
    with patch.object(server.wrapper, "get_sector_research_reports", return_value=payload) as mocked:
        result = server.get_sector_research_reports("technology")

    assert result == payload
    mocked.assert_called_once_with(key="technology")


def test_get_sector_industries_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_sector_industries", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_sector_industries("technology")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(key="technology")


def test_get_sector_top_companies_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_sector_top_companies", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_sector_top_companies("technology")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(key="technology")


def test_get_sector_top_etfs_returns_mapping_payload():
    payload = {"XLK": "Technology Select Sector SPDR Fund"}
    with patch.object(server.wrapper, "get_sector_top_etfs", return_value=payload) as mocked:
        result = server.get_sector_top_etfs("technology")

    assert result == {"values": payload}
    mocked.assert_called_once_with(key="technology")


def test_get_sector_top_mutual_funds_returns_mapping_payload():
    payload = {"FSPTX": "Fidelity Select Technology"}
    with patch.object(server.wrapper, "get_sector_top_mutual_funds", return_value=payload) as mocked:
        result = server.get_sector_top_mutual_funds("technology")

    assert result == {"values": payload}
    mocked.assert_called_once_with(key="technology")


def test_get_sector_ticker_returns_text_payload():
    payload = {"value": "^YH311"}
    with patch.object(server.wrapper, "get_sector_ticker", return_value=payload) as mocked:
        result = server.get_sector_ticker("technology")

    assert result == payload
    mocked.assert_called_once_with(key="technology")


def test_get_industry_returns_named_response_model_payload():
    payload = {
        "key": "software-infrastructure",
        "name": "Software - Infrastructure",
        "symbol": "^YH31110030",
        "sector_key": "technology",
        "sector_name": "Technology",
        "overview": {"description": "Example"},
        "research_reports": [{"id": "report-1"}],
        "top_companies": DATAFRAME_PAYLOAD,
        "top_growth_companies": DATAFRAME_PAYLOAD,
        "top_performing_companies": DATAFRAME_PAYLOAD,
        "ticker_symbol": "^YH31110030",
    }
    with patch.object(server.wrapper, "get_industry", return_value=payload) as mocked:
        result = server.get_industry("software-infrastructure")

    assert result == payload
    mocked.assert_called_once_with(key="software-infrastructure")


def test_get_industry_overview_returns_mapping_payload():
    payload = {"description": "Example"}
    with patch.object(server.wrapper, "get_industry_overview", return_value=payload) as mocked:
        result = server.get_industry_overview("software-infrastructure")

    assert result == {"values": payload}
    mocked.assert_called_once_with(key="software-infrastructure")


def test_get_industry_research_reports_returns_list_payload():
    payload = [{"id": "report-1"}]
    with patch.object(server.wrapper, "get_industry_research_reports", return_value=payload) as mocked:
        result = server.get_industry_research_reports("software-infrastructure")

    assert result == payload
    mocked.assert_called_once_with(key="software-infrastructure")


def test_get_industry_top_companies_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_industry_top_companies", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_industry_top_companies("software-infrastructure")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(key="software-infrastructure")


def test_get_industry_top_growth_companies_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_industry_top_growth_companies", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_industry_top_growth_companies("software-infrastructure")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(key="software-infrastructure")


def test_get_industry_top_performing_companies_returns_dataframe_payload():
    with patch.object(server.wrapper, "get_industry_top_performing_companies", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_industry_top_performing_companies("software-infrastructure")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(key="software-infrastructure")


def test_get_industry_ticker_returns_text_payload():
    payload = {"value": "^YH31110030"}
    with patch.object(server.wrapper, "get_industry_ticker", return_value=payload) as mocked:
        result = server.get_industry_ticker("software-infrastructure")

    assert result == payload
    mocked.assert_called_once_with(key="software-infrastructure")


def test_get_income_stmt_returns_statement_payload():
    with patch.object(server.wrapper, "get_income_stmt", return_value=DATAFRAME_PAYLOAD) as mocked:
        result = server.get_income_stmt("AMZN", freq="yearly")

    assert result == DATAFRAME_PAYLOAD
    mocked.assert_called_once_with(symbol="AMZN", freq="yearly", pretty=False)


def test_get_market_summary_returns_named_response_model_payload():
    payload = {"market": "us", "summary": [{"symbol": "^GSPC"}], "region": "United States"}
    with patch.object(server.wrapper, "get_market_summary", return_value=payload) as mocked:
        result = server.get_market_summary("us")

    assert result == {"market": "us", "summary": [{"symbol": "^GSPC"}], "additional_fields": {"region": "United States"}}
    mocked.assert_called_once_with(market="us")


def test_get_market_returns_named_response_model_payload():
    payload = {"market": "us", "status": {"status": "open"}, "summary": [{"symbol": "^GSPC"}]}
    with patch.object(server.wrapper, "get_market", return_value=payload) as mocked:
        result = server.get_market("us")

    assert result == payload
    mocked.assert_called_once_with(market="us")


def test_get_market_status_returns_named_response_model_payload():
    payload = {"market": "us", "status": {"status": "open"}, "region": "United States"}
    with patch.object(server.wrapper, "get_market_status", return_value=payload) as mocked:
        result = server.get_market_status("us")

    assert result == {"market": "us", "status": {"status": "open"}, "additional_fields": {"region": "United States"}}
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
    message = ""
    try:
        server.get_history("", period="1mo")
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for invalid request")

    assert "symbol" in message
