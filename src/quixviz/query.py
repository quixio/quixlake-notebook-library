"""SQL builders for preflight range detection and bucketed aggregation.

These mirror `buildSql` / `preflightRange` in the Svelte store so the
server sees the same shape of query regardless of client.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from quixviz.lod import ms_to_interval
from quixviz.series import AggFn, Series, TimeRange, XUnit


def quote_ident(name: str) -> str:
    """Quote a DuckDB column identifier. Escapes embedded double quotes."""
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def quote_table(name: str) -> str:
    """Table references must stay unquoted for the Quix lake API.

    The backend rewrites `FROM <bare_ident>` into a `read_parquet([...])`
    call using a regex that does not match quoted identifiers. Quoting
    the table name defeats partition pruning and file-list substitution.
    """
    if not name.replace("_", "").replace("-", "").isalnum():
        raise ValueError(
            f"Table name {name!r} contains characters that are incompatible "
            "with the Quix lake API (only letters, digits, underscore, hyphen)."
        )
    return name


def _quote_literal(value: str | int | float | datetime) -> str:
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return f"TIMESTAMP '{value.isoformat(sep=' ')}'"
    s = str(value).replace("'", "''")
    return f"TIMESTAMP '{s}'"


def _bucket_expr(x: str, x_unit: XUnit, bucket_ms: float) -> str:
    xq = quote_ident(x)
    if x_unit == "numeric":
        size = max(1, int(round(bucket_ms)))
        return f"(({xq} / {size}) * {size})"
    interval = ms_to_interval(bucket_ms)
    if x_unit == "ms":
        return f"time_bucket(INTERVAL '{interval}', to_timestamp({xq} / 1000.0))"
    if x_unit == "s":
        return f"time_bucket(INTERVAL '{interval}', to_timestamp({xq}))"
    return f"time_bucket(INTERVAL '{interval}', {xq})"


def _agg_expr(agg: AggFn, y: str, x: str) -> str:
    yq = quote_ident(y)
    xq = quote_ident(x)
    if agg == "min":
        return f"MIN({yq})"
    if agg == "max":
        return f"MAX({yq})"
    if agg == "avg":
        return f"AVG({yq})"
    if agg == "sum":
        return f"SUM({yq})"
    if agg == "count":
        return f"COUNT({yq})"
    if agg == "first":
        return f"arg_min({yq}, {xq})"
    if agg == "last":
        return f"arg_max({yq}, {xq})"
    raise ValueError(f"Unknown aggregation: {agg}")


def agg_alias(y: str, agg: AggFn) -> str:
    return f"{y}__{agg}"


def _where_clause(
    spec: Series,
    x_min: float | str | datetime | None,
    x_max: float | str | datetime | None,
) -> str:
    parts: list[str] = []
    if spec.where:
        parts.append(f"({spec.where})")
    xq = quote_ident(spec.x)
    if x_min is not None:
        parts.append(f"{xq} >= {_render_x_bound(x_min, spec.x_unit)}")
    if x_max is not None:
        parts.append(f"{xq} <= {_render_x_bound(x_max, spec.x_unit)}")
    if not parts:
        return ""
    return " WHERE " + " AND ".join(parts)


def _render_x_bound(
    value: float | str | datetime,
    x_unit: XUnit,
) -> str:
    if x_unit in ("ms", "s", "numeric"):
        if isinstance(value, datetime):
            epoch_s = value.timestamp()
            return str(epoch_s * 1000 if x_unit == "ms" else epoch_s)
        return str(value)
    return _quote_literal(value)


def build_preflight_sql(spec: Series) -> str:
    """One round-trip: MIN, MAX, COUNT of the x column.

    Iceberg per-file stats make this O(files) rather than O(rows).
    """
    xq = quote_ident(spec.x)
    tbl = quote_table(spec.table)
    where = _where_clause(spec, _bound(spec.time_range, "start"), _bound(spec.time_range, "end"))
    return (
        f"SELECT MIN({xq}) AS x_min, MAX({xq}) AS x_max, COUNT(*) AS row_count "
        f"FROM {tbl}{where}"
    )


def build_bucket_sql(
    spec: Series,
    bucket_ms: float,
    x_min: float | str | datetime | None,
    x_max: float | str | datetime | None,
) -> str:
    """Bucketed aggregation query for the visible window."""
    xq = quote_ident(spec.x)
    tbl = quote_table(spec.table)
    bucket = _bucket_expr(spec.x, spec.x_unit, bucket_ms)

    select_parts: list[str] = [f"{bucket} AS {quote_ident(spec.x)}"]
    group_parts: list[str] = ["1"]
    order_parts: list[str] = [f"{quote_ident(spec.x)} ASC"]

    if spec.group_by:
        gq = quote_ident(spec.group_by)
        select_parts.append(gq)
        group_parts.append("2")
        order_parts.append(f"{gq} ASC")

    for y in spec.y:
        for agg in spec.agg:
            expr = _agg_expr(agg, y, spec.x)
            select_parts.append(f"{expr} AS {quote_ident(agg_alias(y, agg))}")

    where = _where_clause(spec, x_min, x_max)
    return (
        "SELECT "
        + ", ".join(select_parts)
        + f" FROM {tbl}{where} "
        + "GROUP BY " + ", ".join(group_parts)
        + " ORDER BY " + ", ".join(order_parts)
    )


def _bound(tr: TimeRange | None, which: str) -> float | str | datetime | None:
    if tr is None:
        return None
    return getattr(tr, which)


def expected_columns(spec: Series) -> list[str]:
    cols = [spec.x]
    if spec.group_by:
        cols.append(spec.group_by)
    for y in spec.y:
        for agg in spec.agg:
            cols.append(agg_alias(y, agg))
    return cols


def iter_y_agg(spec: Series) -> Iterable[tuple[str, AggFn]]:
    for y in spec.y:
        for agg in spec.agg:
            yield y, agg
