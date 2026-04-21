"""End-to-end wiring with a fake in-memory transport."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

import quixviz as qv
from quixviz.query import agg_alias


class FakeTransport:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, sql: str) -> pd.DataFrame:
        self.queries.append(sql)
        if "MIN(" in sql and "MAX(" in sql and "COUNT(" in sql:
            return pd.DataFrame(
                {"x_min": ["2024-01-01"], "x_max": ["2024-01-02"], "row_count": [1000]}
            )
        return pd.DataFrame(
            {
                "ts": [datetime(2024, 1, 1, tzinfo=timezone.utc)],
                agg_alias("v", "avg"): [10.0],
                agg_alias("v", "min"): [1.0],
                agg_alias("v", "max"): [20.0],
            }
        )


def test_preflight_sets_bounds():
    fake = FakeTransport()
    chart = qv.timeseries(fake, table="t", x="ts", y="v", agg=("min", "max", "avg"))
    x_min, x_max, count = chart.preflight()
    assert x_min < x_max
    assert count == 1000


def test_fetch_runs_preflight_then_bucket_query():
    fake = FakeTransport()
    chart = qv.timeseries(fake, table="t", x="ts", y="v", agg=("min", "max", "avg"))
    df = chart.fetch()
    assert not df.empty
    # Two SQL statements: preflight + bucket
    assert len(fake.queries) == 2
    assert "time_bucket" in fake.queries[1]


def test_fetch_is_cached():
    fake = FakeTransport()
    chart = qv.timeseries(fake, table="t", x="ts", y="v")
    chart.fetch()
    before = len(fake.queries)
    chart.fetch(x_min=chart._x_min, x_max=chart._x_max)
    assert len(fake.queries) == before  # cache hit


def test_on_relayout_triggers_refetch():
    fake = FakeTransport()
    chart = qv.timeseries(fake, table="t", x="ts", y="v")
    chart.fetch()
    before = len(fake.queries)
    chart.on_relayout({"xaxis.range[0]": "2024-01-01 06:00", "xaxis.range[1]": "2024-01-01 18:00"})
    assert len(fake.queries) > before
