import pandas as pd

from yfinance_mcp.utils import dataframe_to_payload, normalize_symbols, serialize_value


def test_dataframe_to_payload_preserves_shape():
    frame = pd.DataFrame({"close": [1.0, 2.0]}, index=["2024-01-01", "2024-01-02"])

    payload = dataframe_to_payload(frame)

    assert payload["columns"] == ["close"]
    assert payload["data"] == [[1.0], [2.0]]
    assert payload["index"] == ["2024-01-01", "2024-01-02"]


def test_serialize_value_converts_nan_to_none():
    assert serialize_value(float("nan")) is None


def test_normalize_symbols_filters_empty_values():
    assert normalize_symbols([" aapl ", "", " msft "]) == ["AAPL", "MSFT"]
