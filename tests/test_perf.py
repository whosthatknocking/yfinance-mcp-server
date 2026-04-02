import time
from unittest.mock import patch

import anyio
import pandas as pd
import pytest

from yfinance_mcp import server
from yfinance_mcp.cache import InMemoryTTLCache
from yfinance_mcp.utils import serialize_value
from yfinance_mcp.wrapper import YFinanceWrapper


@pytest.mark.perf
def test_get_info_warm_cache_is_faster_than_cold_path():
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class SlowTicker:
        @property
        def info(self):
            time.sleep(0.03)
            return {"symbol": "AAPL", "marketCap": 100}

    with patch.object(wrapper, "_ticker", return_value=SlowTicker()) as mocked:
        cold_started = time.perf_counter()
        cold_result = wrapper.get_info("AAPL")
        cold_elapsed = time.perf_counter() - cold_started

        warm_started = time.perf_counter()
        warm_result = wrapper.get_info("AAPL")
        warm_elapsed = time.perf_counter() - warm_started

    assert cold_result == warm_result
    assert mocked.call_count == 1
    assert warm_elapsed < cold_elapsed / 4


@pytest.mark.perf
@pytest.mark.anyio
async def test_registered_async_tool_calls_run_concurrently_for_blocking_upstream_work():
    tool = server.mcp._tool_manager.get_tool("get_quote_snapshot")
    assert tool is not None

    async def invoke(symbol: str):
        return await tool.run({"symbol": symbol}, context=None, convert_result=False)

    results = {}

    async def invoke_and_store(symbol: str):
        results[symbol] = await invoke(symbol)

    def slow_get_fast_info(symbol: str):
        time.sleep(0.1)
        return {"lastPrice": 123.45, "currency": "USD", "symbol": symbol}

    started = time.perf_counter()
    with patch.object(server.wrapper, "get_fast_info", side_effect=slow_get_fast_info):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(invoke_and_store, "AAPL")
            task_group.start_soon(invoke_and_store, "MSFT")
            task_group.start_soon(invoke_and_store, "NVDA")
    elapsed = time.perf_counter() - started

    assert results["AAPL"]["lastPrice"] == 123.45
    assert results["MSFT"]["lastPrice"] == 123.45
    assert results["NVDA"]["lastPrice"] == 123.45
    assert elapsed < 0.25


@pytest.mark.perf
def test_large_dataframe_serialization_completes_within_reasonable_time_budget():
    rows = 2_000
    columns = 6
    frame = pd.DataFrame(
        {f"col_{index}": list(range(rows)) for index in range(columns)},
        index=pd.date_range("2025-01-01", periods=rows, freq="D"),
    )

    started = time.perf_counter()
    payload = serialize_value(frame)
    elapsed = time.perf_counter() - started

    assert payload["columns"] == [f"col_{index}" for index in range(columns)]
    assert len(payload["data"]) == rows
    assert len(payload["index"]) == rows
    assert elapsed < 1.0
