"""LRU cache tests."""

from __future__ import annotations

import pandas as pd

from quixviz.cache import TileCache, TileKey


def _k(sql: str = "a", bucket: int = 1000, lo: float = 0, hi: float = 1) -> TileKey:
    return TileKey(sql_hash=sql, bucket_ms=bucket, x_min=lo, x_max=hi)


def test_roundtrip():
    cache = TileCache(max_entries=4)
    df = pd.DataFrame({"x": [1]})
    k = _k()
    cache.put(k, df)
    assert cache.get(k) is df


def test_miss_returns_none():
    assert TileCache().get(_k()) is None


def test_evicts_lru():
    cache = TileCache(max_entries=2)
    a, b, c = _k("a"), _k("b"), _k("c")
    cache.put(a, pd.DataFrame({"x": [1]}))
    cache.put(b, pd.DataFrame({"x": [2]}))
    # Access a to make b the LRU
    cache.get(a)
    cache.put(c, pd.DataFrame({"x": [3]}))
    assert cache.get(b) is None
    assert cache.get(a) is not None
    assert cache.get(c) is not None
