from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List

import pandas as pd


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def normalize_symbols(symbols: Iterable[str]) -> List[str]:
    return [normalize_symbol(symbol) for symbol in symbols if symbol.strip()]


def serialize_value(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return dataframe_to_payload(value)
    if isinstance(value, pd.Series):
        return series_to_payload(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if pd.isna(value):
        return None
    if isinstance(value, dict):
        return {str(key): serialize_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value]
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes)):
        try:
            return serialize_value(value.tolist())
        except Exception:
            pass
    return value


def dataframe_to_payload(frame: pd.DataFrame) -> Dict[str, Any]:
    clean = frame.copy()
    clean.columns = [str(column) for column in clean.columns]
    return {
        "columns": [str(column) for column in clean.columns],
        "data": [[serialize_value(item) for item in row] for row in clean.itertuples(index=False, name=None)],
        "index": [serialize_value(item) for item in clean.index.tolist()],
    }


def series_to_payload(series: pd.Series) -> Dict[str, Any]:
    return {
        "name": str(series.name) if series.name is not None else None,
        "index": [serialize_value(item) for item in series.index.tolist()],
        "data": [serialize_value(item) for item in series.tolist()],
    }
