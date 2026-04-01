from __future__ import annotations

import os

import pytest

from yfinance_mcp.wrapper import YFinanceWrapper


RUN_LIVE_TESTS = os.getenv("YF_RUN_LIVE_TESTS") == "1"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not RUN_LIVE_TESTS,
        reason="Set YF_RUN_LIVE_TESTS=1 to run live yfinance integration tests.",
    ),
]


def _assert_dataframe_payload(payload):
    assert isinstance(payload, dict)
    assert isinstance(payload.get("columns"), list)
    assert isinstance(payload.get("data"), list)
    assert isinstance(payload.get("index"), list)


def _assert_series_payload(payload):
    assert isinstance(payload, dict)
    assert isinstance(payload.get("index"), list)
    assert isinstance(payload.get("data"), list)


def _assert_mapping_payload(payload):
    assert isinstance(payload, dict)


def _assert_text_payload(payload):
    assert isinstance(payload, dict)
    assert "value" in payload


def _assert_list_payload(payload):
    assert isinstance(payload, list)


def _assert_quote_snapshot(payload):
    assert isinstance(payload, dict)
    assert payload.get("lastPrice") is not None
    assert payload.get("currency")


def _assert_batch_quote_snapshot(payload):
    assert isinstance(payload, dict)
    assert payload.get("results")


def _assert_batch_info(payload):
    assert isinstance(payload, dict)
    assert payload.get("results")


def _assert_market_payload(payload):
    assert isinstance(payload, dict)
    assert payload.get("market") == "us"


def _assert_search_payload(payload):
    assert isinstance(payload, dict)


def _assert_lookup_payload(payload):
    assert isinstance(payload, dict)
    assert payload.get("query")


def _assert_funds_payload(payload):
    assert isinstance(payload, dict)
    assert "quote_type" in payload


def _assert_sector_payload(payload):
    assert isinstance(payload, dict)
    assert payload.get("key") == "technology"


def _assert_industry_payload(payload):
    assert isinstance(payload, dict)
    assert payload.get("key") == "software-infrastructure"


def _assert_calendar_bundle(payload):
    assert isinstance(payload, dict)
    assert "earnings_calendar" in payload


LIVE_CASES = [
    ("get_info", lambda w: w.get_info("AAPL"), _assert_mapping_payload),
    ("get_fast_info", lambda w: w.get_fast_info("AAPL"), _assert_quote_snapshot),
    ("get_batch_info", lambda w: w.get_batch_info(["AAPL", "MSFT"]), _assert_batch_info),
    ("get_batch_quote_snapshot", lambda w: w.get_batch_quote_snapshot(["AAPL", "MSFT"]), _assert_batch_quote_snapshot),
    ("get_batch_news", lambda w: w.get_batch_news(["AAPL", "MSFT"]), _assert_list_payload),
    ("get_history", lambda w: w.get_history("AAPL", period="1mo"), _assert_dataframe_payload),
    ("get_history_metadata", lambda w: w.get_history_metadata("AAPL"), _assert_mapping_payload),
    ("get_isin", lambda w: w.get_isin("AAPL"), _assert_text_payload),
    ("download", lambda w: w.download(["AAPL", "MSFT"], period="5d"), _assert_dataframe_payload),
    ("get_news", lambda w: w.get_news("AAPL", count=3), _assert_list_payload),
    ("get_option_expirations", lambda w: w.get_option_expirations("SPY"), _assert_list_payload),
    ("get_option_chain", lambda w: w.get_option_chain("SPY"), _assert_mapping_payload),
    ("get_actions", lambda w: w.get_actions("AAPL", period="1y"), _assert_series_payload),
    ("get_dividends", lambda w: w.get_dividends("AAPL", period="1y"), _assert_series_payload),
    ("get_splits", lambda w: w.get_splits("TSLA", period="5y"), _assert_series_payload),
    ("get_shares_full", lambda w: w.get_shares_full("AAPL", start="2025-01-01", end="2026-01-01"), _assert_series_payload),
    ("get_sec_filings", lambda w: w.get_sec_filings("AAPL"), _assert_list_payload),
    ("get_income_stmt", lambda w: w.get_income_stmt("AAPL"), _assert_dataframe_payload),
    ("get_balance_sheet", lambda w: w.get_balance_sheet("AAPL"), _assert_dataframe_payload),
    ("get_cashflow", lambda w: w.get_cashflow("AAPL"), _assert_dataframe_payload),
    ("get_market_summary", lambda w: w.get_market_summary("us"), _assert_market_payload),
    ("get_market", lambda w: w.get_market("us"), _assert_market_payload),
    ("get_market_status", lambda w: w.get_market_status("us"), _assert_market_payload),
    ("get_sector", lambda w: w.get_sector("technology"), _assert_sector_payload),
    ("get_sector_overview", lambda w: w.get_sector_overview("technology"), _assert_mapping_payload),
    ("get_sector_research_reports", lambda w: w.get_sector_research_reports("technology"), _assert_list_payload),
    ("get_sector_industries", lambda w: w.get_sector_industries("technology"), _assert_dataframe_payload),
    ("get_sector_top_companies", lambda w: w.get_sector_top_companies("technology"), _assert_dataframe_payload),
    ("get_sector_top_etfs", lambda w: w.get_sector_top_etfs("technology"), _assert_mapping_payload),
    ("get_sector_top_mutual_funds", lambda w: w.get_sector_top_mutual_funds("technology"), _assert_mapping_payload),
    ("get_sector_ticker", lambda w: w.get_sector_ticker("technology"), _assert_text_payload),
    ("get_industry", lambda w: w.get_industry("software-infrastructure"), _assert_industry_payload),
    ("get_industry_overview", lambda w: w.get_industry_overview("software-infrastructure"), _assert_mapping_payload),
    ("get_industry_research_reports", lambda w: w.get_industry_research_reports("software-infrastructure"), _assert_list_payload),
    ("get_industry_top_companies", lambda w: w.get_industry_top_companies("software-infrastructure"), _assert_dataframe_payload),
    (
        "get_industry_top_growth_companies",
        lambda w: w.get_industry_top_growth_companies("software-infrastructure"),
        _assert_dataframe_payload,
    ),
    (
        "get_industry_top_performing_companies",
        lambda w: w.get_industry_top_performing_companies("software-infrastructure"),
        _assert_dataframe_payload,
    ),
    ("get_industry_ticker", lambda w: w.get_industry_ticker("software-infrastructure"), _assert_text_payload),
    ("search", lambda w: w.search("Google", max_results=5, news_count=2, lists_count=2), _assert_search_payload),
    ("lookup", lambda w: w.lookup("Google", count=5), _assert_lookup_payload),
    (
        "get_earnings_dates",
        lambda w: w.get_earnings_dates("AAPL", limit=4, offset=0),
        _assert_dataframe_payload,
    ),
    ("get_ticker_calendar", lambda w: w.get_ticker_calendar("AAPL"), _assert_mapping_payload),
    ("get_recommendations", lambda w: w.get_recommendations("AAPL"), _assert_dataframe_payload),
    ("get_analyst_price_targets", lambda w: w.get_analyst_price_targets("AAPL"), _assert_mapping_payload),
    ("get_recommendations_summary", lambda w: w.get_recommendations_summary("AAPL"), _assert_dataframe_payload),
    ("get_upgrades_downgrades", lambda w: w.get_upgrades_downgrades("AAPL"), _assert_dataframe_payload),
    ("get_earnings_estimate", lambda w: w.get_earnings_estimate("AAPL"), _assert_dataframe_payload),
    ("get_revenue_estimate", lambda w: w.get_revenue_estimate("AAPL"), _assert_dataframe_payload),
    ("get_earnings_history", lambda w: w.get_earnings_history("AAPL"), _assert_dataframe_payload),
    ("get_eps_trend", lambda w: w.get_eps_trend("AAPL"), _assert_dataframe_payload),
    ("get_eps_revisions", lambda w: w.get_eps_revisions("AAPL"), _assert_dataframe_payload),
    ("get_growth_estimates", lambda w: w.get_growth_estimates("AAPL"), _assert_dataframe_payload),
    ("get_major_holders", lambda w: w.get_major_holders("AAPL"), _assert_dataframe_payload),
    ("get_institutional_holders", lambda w: w.get_institutional_holders("AAPL"), _assert_dataframe_payload),
    ("get_mutualfund_holders", lambda w: w.get_mutualfund_holders("AAPL"), _assert_dataframe_payload),
    ("get_insider_purchases", lambda w: w.get_insider_purchases("AAPL"), _assert_dataframe_payload),
    ("get_insider_transactions", lambda w: w.get_insider_transactions("AAPL"), _assert_dataframe_payload),
    ("get_insider_roster_holders", lambda w: w.get_insider_roster_holders("AAPL"), _assert_dataframe_payload),
    ("get_funds_data", lambda w: w.get_funds_data("SPY"), _assert_funds_payload),
    ("get_fund_asset_classes", lambda w: w.get_fund_asset_classes("SPY"), _assert_mapping_payload),
    ("get_fund_bond_holdings", lambda w: w.get_fund_bond_holdings("SPY"), _assert_dataframe_payload),
    ("get_fund_bond_ratings", lambda w: w.get_fund_bond_ratings("SPY"), _assert_mapping_payload),
    ("get_fund_description", lambda w: w.get_fund_description("SPY"), _assert_text_payload),
    ("get_fund_equity_holdings", lambda w: w.get_fund_equity_holdings("SPY"), _assert_dataframe_payload),
    ("get_fund_operations", lambda w: w.get_fund_operations("SPY"), _assert_dataframe_payload),
    ("get_fund_overview", lambda w: w.get_fund_overview("SPY"), _assert_mapping_payload),
    ("get_fund_sector_weightings", lambda w: w.get_fund_sector_weightings("SPY"), _assert_mapping_payload),
    ("get_fund_top_holdings", lambda w: w.get_fund_top_holdings("SPY"), _assert_dataframe_payload),
    ("get_fund_quote_type", lambda w: w.get_fund_quote_type("SPY"), _assert_text_payload),
    ("get_calendars", lambda w: w.get_calendars(start="2026-01-01", end="2026-03-31"), _assert_calendar_bundle),
    ("get_earnings_calendar", lambda w: w.get_earnings_calendar(start="2026-01-01", end="2026-03-31"), _assert_dataframe_payload),
    (
        "get_economic_events_calendar",
        lambda w: w.get_economic_events_calendar(start="2026-01-01", end="2026-03-31"),
        _assert_dataframe_payload,
    ),
    ("get_ipo_calendar", lambda w: w.get_ipo_calendar(start="2026-01-01", end="2026-03-31"), _assert_dataframe_payload),
    ("get_splits_calendar", lambda w: w.get_splits_calendar(start="2026-01-01", end="2026-03-31"), _assert_dataframe_payload),
]


@pytest.mark.parametrize("name,call,assertion", LIVE_CASES)
def test_live_api_smoke_matrix(name, call, assertion):
    wrapper = YFinanceWrapper()
    payload = call(wrapper)
    assertion(payload)
