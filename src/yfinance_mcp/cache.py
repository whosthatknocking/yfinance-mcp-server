from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


class CacheBackend(Protocol):
    def get_entry(self, key: str, *, allow_stale: bool = False) -> Optional["CacheEntry"]:
        ...

    def get(self, key: str) -> Optional[Any]:
        ...

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        ...


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class InMemoryTTLCache:
    def __init__(self) -> None:
        self._entries: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def get_entry(self, key: str, *, allow_stale: bool = False) -> Optional[CacheEntry]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at < time.time() and not allow_stale:
                self._entries.pop(key, None)
                return None
            return entry

    def get(self, key: str) -> Optional[Any]:
        entry = self.get_entry(key)
        if entry is None:
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self._lock:
            self._entries[key] = CacheEntry(value=value, expires_at=time.time() + ttl_seconds)
