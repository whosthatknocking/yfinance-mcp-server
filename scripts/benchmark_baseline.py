from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from unittest.mock import patch

import anyio
import pandas as pd

from yfinance_mcp import server
from yfinance_mcp.cache import InMemoryTTLCache
from yfinance_mcp.utils import serialize_value
from yfinance_mcp.wrapper import YFinanceWrapper


@dataclass
class BenchmarkResult:
    name: str
    iterations: int
    median_ms: float
    min_ms: float
    max_ms: float
    notes: str


def _to_ms(seconds: float) -> float:
    return round(seconds * 1000, 3)


def _measure(fn, *, iterations: int, warmup: int = 1) -> BenchmarkResult:
    for _ in range(warmup):
        fn()

    durations = []
    for _ in range(iterations):
        started = time.perf_counter()
        fn()
        durations.append(time.perf_counter() - started)

    return BenchmarkResult(
        name="",
        iterations=iterations,
        median_ms=_to_ms(statistics.median(durations)),
        min_ms=_to_ms(min(durations)),
        max_ms=_to_ms(max(durations)),
        notes="",
    )


def benchmark_get_info_cold_cache() -> BenchmarkResult:
    def run_once() -> None:
        wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

        class SlowTicker:
            @property
            def info(self):
                time.sleep(0.03)
                return {"symbol": "AAPL", "marketCap": 100}

        with patch.object(wrapper, "_ticker", return_value=SlowTicker()):
            wrapper.get_info("AAPL")

    result = _measure(run_once, iterations=5)
    result.name = "get_info_cold_cache"
    result.notes = "Single uncached get_info call with a mocked 30 ms upstream info property."
    return result


def benchmark_get_info_warm_cache() -> BenchmarkResult:
    wrapper = YFinanceWrapper(cache=InMemoryTTLCache())

    class SlowTicker:
        @property
        def info(self):
            time.sleep(0.03)
            return {"symbol": "AAPL", "marketCap": 100}

    with patch.object(wrapper, "_ticker", return_value=SlowTicker()):
        wrapper.get_info("AAPL")

        def run_once() -> None:
            wrapper.get_info("AAPL")

        result = _measure(run_once, iterations=10)

    result.name = "get_info_warm_cache"
    result.notes = "Warm-cache get_info call after one priming request."
    return result


async def _invoke_quote_snapshot_tool(symbol: str):
    tool = server.mcp._tool_manager.get_tool("get_quote_snapshot")
    assert tool is not None
    return await tool.run({"symbol": symbol}, context=None, convert_result=False)


def benchmark_concurrent_quote_snapshot_tool() -> BenchmarkResult:
    def slow_get_fast_info(symbol: str):
        time.sleep(0.1)
        return {"lastPrice": 123.45, "currency": "USD", "symbol": symbol}

    async def run_once() -> None:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(_invoke_quote_snapshot_tool, "AAPL")
            task_group.start_soon(_invoke_quote_snapshot_tool, "MSFT")
            task_group.start_soon(_invoke_quote_snapshot_tool, "NVDA")

    def wrapped() -> None:
        with patch.object(server.wrapper, "get_fast_info", side_effect=slow_get_fast_info):
            anyio.run(run_once)

    result = _measure(wrapped, iterations=5)
    result.name = "get_quote_snapshot_tool_concurrent_x3"
    result.notes = "Three concurrent MCP tool invocations with a mocked 100 ms blocking upstream call."
    return result


def benchmark_large_history_serialization() -> BenchmarkResult:
    rows = 2_000
    columns = 6
    frame = pd.DataFrame(
        {f"col_{index}": list(range(rows)) for index in range(columns)},
        index=pd.date_range("2025-01-01", periods=rows, freq="D"),
    )

    def run_once() -> None:
        serialize_value(frame)

    result = _measure(run_once, iterations=10)
    result.name = "serialize_dataframe_2000x6"
    result.notes = "Serialize a representative large DataFrame payload to the MCP JSON-safe structure."
    return result


def main() -> None:
    results = [
        benchmark_get_info_cold_cache(),
        benchmark_get_info_warm_cache(),
        benchmark_concurrent_quote_snapshot_tool(),
        benchmark_large_history_serialization(),
    ]
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": ".".join(str(part) for part in tuple(__import__("sys").version_info[:3])),
        "benchmarks": [asdict(result) for result in results],
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
