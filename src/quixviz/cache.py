"""LRU tile cache keyed by (sql hash, bucket, window).

Panning inside an already-loaded window is free; zooming to the same
bucket+range re-uses the previous fetch.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TileKey:
    sql_hash: str
    bucket_ms: int
    x_min: float
    x_max: float


class TileCache:
    def __init__(self, max_entries: int = 64) -> None:
        self._max = max_entries
        self._store: OrderedDict[TileKey, pd.DataFrame] = OrderedDict()

    def get(self, key: TileKey) -> pd.DataFrame | None:
        df = self._store.get(key)
        if df is not None:
            self._store.move_to_end(key)
        return df

    def put(self, key: TileKey, df: pd.DataFrame) -> None:
        self._store[key] = df
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()


def hash_sql(sql: str) -> str:
    return hashlib.sha1(sql.encode("utf-8")).hexdigest()[:16]
