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


def test_live_get_quote_snapshot_returns_price_fields():
    wrapper = YFinanceWrapper()

    result = wrapper.get_fast_info("AAPL")

    assert isinstance(result, dict)
    assert result.get("currency")
    assert result.get("lastPrice") is not None


def test_live_get_history_returns_rows():
    wrapper = YFinanceWrapper()

    result = wrapper.get_history("MSFT", period="1mo", interval="1d")

    assert result["columns"]
    assert result["data"]
    assert result["index"]


def test_live_get_news_returns_list():
    wrapper = YFinanceWrapper()

    result = wrapper.get_news("TSLA", count=3)

    assert isinstance(result, list)
    assert len(result) <= 3


def test_live_search_returns_quote_matches():
    wrapper = YFinanceWrapper()

    result = wrapper.search("microsoft", max_results=5, news_count=0, lists_count=0)

    assert isinstance(result, dict)
    assert "quotes" in result
    assert isinstance(result["quotes"], list)


def test_live_get_option_expirations_returns_list():
    wrapper = YFinanceWrapper()

    result = wrapper.get_option_expirations("SPY")

    assert isinstance(result, list)


def test_live_get_market_status_returns_market_payload():
    wrapper = YFinanceWrapper()

    result = wrapper.get_market_status("us")

    assert result["market"] == "us"
    assert "status" in result
