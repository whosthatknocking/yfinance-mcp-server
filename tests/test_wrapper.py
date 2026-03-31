from yfinance_mcp.cache import InMemoryTTLCache
from yfinance_mcp.wrapper import YFinanceWrapper


def test_wrapper_metadata_includes_transport_modes():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    payload = wrapper.get_metadata()

    assert payload["server_name"] == "yfinance"
    assert "stdio" in payload["transport_modes"]
    assert "streamable-http" in payload["transport_modes"]
