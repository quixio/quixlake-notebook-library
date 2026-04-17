"""SQL builder tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from quixviz.query import (
    agg_alias,
    build_bucket_sql,
    build_preflight_sql,
    expected_columns,
    quote_ident,
)
from quixviz.series import Series, TimeRange


def test_quote_ident_escapes_quotes():
    assert quote_ident('foo"bar') == '"foo""bar"'


def test_preflight_selects_min_max_count():
    spec = Series(table="t", x="ts", y=["v"])
    sql = build_preflight_sql(spec)
    assert "MIN(\"ts\")" in sql
    assert "MAX(\"ts\")" in sql
    assert "COUNT(*)" in sql
    assert "FROM t" in sql


def test_preflight_includes_time_range_filter():
    spec = Series(
        table="t",
        x="ts",
        y=["v"],
        time_range=TimeRange(datetime(2024, 1, 1), datetime(2024, 2, 1)),
    )
    sql = build_preflight_sql(spec)
    assert "WHERE" in sql
    assert "TIMESTAMP '2024-01-01" in sql
    assert "TIMESTAMP '2024-02-01" in sql


def test_bucket_sql_uses_time_bucket_for_timestamp():
    spec = Series(table="t", x="ts", y=["v"], agg=["avg"])
    sql = build_bucket_sql(spec, bucket_ms=60_000, x_min=None, x_max=None)
    assert "time_bucket(INTERVAL '1 minutes', \"ts\")" in sql
    assert "AVG(\"v\") AS \"v__avg\"" in sql
    assert "GROUP BY 1" in sql
    assert "ORDER BY \"ts\" ASC" in sql


def test_bucket_sql_uses_to_timestamp_for_ms_epoch():
    spec = Series(table="t", x="ts", y=["v"], x_unit="ms")
    sql = build_bucket_sql(spec, 1000, None, None)
    assert "to_timestamp(\"ts\" / 1000.0)" in sql


def test_bucket_sql_uses_modulo_for_numeric():
    spec = Series(table="t", x="offset", y=["v"], x_unit="numeric")
    sql = build_bucket_sql(spec, 50, None, None)
    assert "((\"offset\" / 50) * 50)" in sql


def test_bucket_sql_includes_group_by_column():
    spec = Series(table="t", x="ts", y=["v"], agg=["avg"], group_by="device")
    sql = build_bucket_sql(spec, 1000, None, None)
    assert "\"device\"" in sql
    assert "GROUP BY 1, 2" in sql
    assert "ORDER BY \"ts\" ASC, \"device\" ASC" in sql


def test_bucket_sql_multi_agg_columns():
    spec = Series(table="t", x="ts", y=["v"], agg=["min", "max", "avg"])
    sql = build_bucket_sql(spec, 1000, None, None)
    assert "MIN(\"v\") AS \"v__min\"" in sql
    assert "MAX(\"v\") AS \"v__max\"" in sql
    assert "AVG(\"v\") AS \"v__avg\"" in sql


def test_bucket_sql_first_last_use_arg_min_max():
    spec = Series(table="t", x="ts", y=["v"], agg=["first", "last"])
    sql = build_bucket_sql(spec, 1000, None, None)
    assert "arg_min(\"v\", \"ts\")" in sql
    assert "arg_max(\"v\", \"ts\")" in sql


def test_bucket_sql_applies_window_bounds():
    spec = Series(table="t", x="ts", y=["v"])
    sql = build_bucket_sql(
        spec,
        1000,
        x_min=datetime(2024, 1, 1),
        x_max=datetime(2024, 1, 2),
    )
    assert "\"ts\" >= TIMESTAMP '2024-01-01" in sql
    assert "\"ts\" <= TIMESTAMP '2024-01-02" in sql


def test_bucket_sql_composes_user_where_with_range():
    spec = Series(table="t", x="ts", y=["v"], where="device = 'A'")
    sql = build_bucket_sql(spec, 1000, datetime(2024, 1, 1), None)
    assert "(device = 'A')" in sql
    assert "\"ts\" >= TIMESTAMP '2024-01-01" in sql


def test_expected_columns_matches_aliases():
    spec = Series(table="t", x="ts", y=["a", "b"], agg=["min", "max"], group_by="g")
    assert expected_columns(spec) == ["ts", "g", "a__min", "a__max", "b__min", "b__max"]


def test_agg_alias_is_stable():
    assert agg_alias("temperature", "avg") == "temperature__avg"
