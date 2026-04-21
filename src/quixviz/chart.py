"""TimeseriesChart: ties client, LOD, cache, and renderer together.

Usage:

    client = qv.connect("http://localhost", token="...")
    chart = qv.timeseries(
        client, table="telemetry", x="timestamp",
        y=["temperature"], agg=["min", "max", "avg"],
        group_by="device_id",
    )
    chart.show()

`.show()` returns a Plotly FigureWidget when running inside a notebook
that supports widgets (Jupyter, marimo). In Colab the chart renders but
without a Python callback loop — see notebook/marimo.py for the reactive
marimo path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

import pandas as pd

from quixviz.cache import TileCache, TileKey, hash_sql
from quixviz.client import QuixClient, Transport
from quixviz.lod import DEFAULT_CSS_WIDTH_PX, compute_bucket_ms
from quixviz.query import build_bucket_sql, build_preflight_sql
from quixviz.renderer.plotly import PlotlyRenderer
from quixviz.series import AggFn, Series, TimeRange, XUnit


@dataclass
class TimeseriesChart:
    transport: Transport
    spec: Series
    css_width_px: int = DEFAULT_CSS_WIDTH_PX
    dpr: float = 1.0
    rangeslider: bool = True
    rangeselector: bool = True

    _cache: TileCache = field(default_factory=TileCache, init=False, repr=False)
    _renderer: PlotlyRenderer = field(init=False, repr=False)
    _x_min: float | None = field(default=None, init=False, repr=False)
    _x_max: float | None = field(default=None, init=False, repr=False)
    _last_bucket_ms: int | None = field(default=None, init=False, repr=False)
    _df: pd.DataFrame = field(default_factory=pd.DataFrame, init=False, repr=False)

    def __post_init__(self) -> None:
        self._renderer = PlotlyRenderer(
            self.spec,
            rangeslider=self.rangeslider,
            rangeselector=self.rangeselector,
        )

    def preflight(self) -> tuple[float, float, int]:
        """Fetch MIN/MAX/COUNT so we know the initial zoom range."""
        sql = build_preflight_sql(self.spec)
        df = self.transport.query(sql)
        if df.empty:
            raise RuntimeError("Preflight returned no rows — table may be empty.")
        row = df.iloc[0]
        x_min = _to_ms(row["x_min"], self.spec.x_unit)
        x_max = _to_ms(row["x_max"], self.spec.x_unit)
        count = int(row["row_count"])
        self._x_min, self._x_max = x_min, x_max
        return x_min, x_max, count

    def fetch(
        self,
        x_min: float | None = None,
        x_max: float | None = None,
    ) -> pd.DataFrame:
        """Fetch (or serve from cache) the bucketed aggregation for a window."""
        if x_min is None or x_max is None:
            if self._x_min is None or self._x_max is None:
                self.preflight()
            x_min = x_min if x_min is not None else self._x_min
            x_max = x_max if x_max is not None else self._x_max
        assert x_min is not None and x_max is not None

        bucket_ms = compute_bucket_ms(x_min, x_max, self.css_width_px, self.dpr)
        bucket_int = int(round(bucket_ms))

        x_lo, x_hi = _to_native_bounds(x_min, x_max, self.spec.x_unit)
        sql = build_bucket_sql(self.spec, bucket_ms, x_lo, x_hi)
        key = TileKey(hash_sql(sql), bucket_int, float(x_min), float(x_max))
        cached = self._cache.get(key)
        if cached is not None:
            self._df = cached
            self._last_bucket_ms = bucket_int
            return cached

        df = self.transport.query(sql)
        self._cache.put(key, df)
        self._df = df
        self._last_bucket_ms = bucket_int
        self._x_min, self._x_max = x_min, x_max
        return df

    def figure(self):
        if self._df.empty:
            self.fetch()
        return self._renderer.update(self._df, x_range=self._axis_range())

    def show(self):
        return self.figure()

    def _axis_range(self) -> tuple | None:
        """Pin the visible x-axis to the queried window.

        Without this, Plotly auto-scales the axis to the data extent —
        so a wide window with sparse data collapses the view to wherever
        rows happen to exist, masking the fact that the query returned
        little content.
        """
        if self._x_min is None or self._x_max is None:
            return None
        return _ms_to_axis_range(self._x_min, self._x_max, self.spec.x_unit)

    def zoom_to(self, start: Any, end: Any):
        """Refetch for an explicit window and return the updated figure.

        `start` / `end` accept `datetime`, ISO strings, numeric epoch
        (ms for `x_unit="ms"`, seconds for `x_unit="s"`, raw for
        `x_unit="numeric"`), or `None` to keep the current bound.

        Ideal for notebooks without ipywidgets: call in a fresh cell
        to drive the LOD loop manually.
        """
        x_min = self._x_min if start is None else _coerce_to_ms(start, self.spec.x_unit)
        x_max = self._x_max if end is None else _coerce_to_ms(end, self.spec.x_unit)
        if x_min is None or x_max is None:
            self.preflight()
            x_min = x_min if x_min is not None else self._x_min
            x_max = x_max if x_max is not None else self._x_max
        if x_min is None or x_max is None:
            raise RuntimeError("Could not resolve zoom window (preflight failed).")
        self.fetch(x_min=x_min, x_max=x_max)
        return self._renderer.update(self._df, x_range=self._axis_range())

    def zoom_last(self, duration: str | timedelta):
        """Zoom to the last N of time ending at the current `x_max`.

        Examples:

            chart.zoom_last("1h")
            chart.zoom_last("5m")
            chart.zoom_last(timedelta(days=2))

        If no range has been fetched yet, runs preflight first so we
        know where the data ends.
        """
        if self._x_max is None:
            self.preflight()
        if self._x_max is None:
            raise RuntimeError("Preflight returned no bounds.")
        ms = _duration_to_ms(duration)
        return self.zoom_to(
            _ms_to_bound(self._x_max - ms, self.spec.x_unit),
            _ms_to_bound(self._x_max, self.spec.x_unit),
        )

    def reset(self):
        """Refetch the full preflight range."""
        self.preflight()
        assert self._x_min is not None and self._x_max is not None
        self.fetch(x_min=self._x_min, x_max=self._x_max)
        return self._renderer.update(self._df)

    def on_relayout(self, relayout: dict[str, Any]) -> bool:
        """Feed a Plotly relayout event back into the chart.

        Returns True if a refetch happened, False if the event wasn't a
        zoom/pan we care about.
        """
        x_range = _extract_x_range(relayout)
        if x_range is None:
            return False
        x_min, x_max = x_range
        self.fetch(x_min=x_min, x_max=x_max)
        self._renderer.update(self._df, x_range=self._axis_range())
        return True


def timeseries(
    client: Transport | QuixClient,
    *,
    table: str | None = None,
    sql: str | None = None,
    x: str,
    y: str | Sequence[str],
    agg: AggFn | Sequence[AggFn] = ("avg",),
    group_by: str | None = None,
    where: str | None = None,
    x_unit: XUnit = "timestamp",
    time_range: TimeRange | tuple | None = None,
    css_width_px: int = DEFAULT_CSS_WIDTH_PX,
    dpr: float = 1.0,
    rangeslider: bool = True,
    rangeselector: bool = True,
) -> TimeseriesChart:
    """Build a zoom-aware timeseries chart.

    Provide either ``table`` (a bare table name) **or** ``sql`` (a custom
    SELECT query).  When ``sql`` is used, the library wraps it in a CTE and
    applies timestamp filtering + bucketing on top, so the query only needs
    to expose the columns referenced by ``x``, ``y``, and ``group_by``.

    Example with custom SQL::

        chart = qv.timeseries(
            client,
            sql=\"\"\"
                SELECT t.ts, t.temperature, d.region
                FROM telemetry t
                JOIN devices d USING (device_id)
                WHERE d.region = 'EU'
            \"\"\",
            x="ts",
            y="temperature",
            agg=["min", "max", "avg"],
            group_by="region",
        )
    """
    if isinstance(time_range, tuple):
        time_range = TimeRange(*time_range)
    spec = Series(
        table=table,
        sql=sql,
        x=x,
        y=[y] if isinstance(y, str) else list(y),
        agg=[agg] if isinstance(agg, str) else list(agg),
        group_by=group_by,
        where=where,
        x_unit=x_unit,
        time_range=time_range,
    )
    return TimeseriesChart(
        transport=client,
        spec=spec,
        css_width_px=css_width_px,
        dpr=dpr,
        rangeslider=rangeslider,
        rangeselector=rangeselector,
    )


def _to_ms(value: Any, x_unit: XUnit) -> float:
    """Normalise a boundary value to a float suitable for bucket math."""
    if isinstance(value, (int, float)):
        return float(value) * (1000 if x_unit == "s" else 1.0)
    if isinstance(value, str):
        value = pd.to_datetime(value)
    if hasattr(value, "timestamp"):
        return value.timestamp() * 1000
    return float(value)


def _to_native_bounds(
    x_min: float,
    x_max: float,
    x_unit: XUnit,
) -> tuple[float | str | datetime, float | str | datetime]:
    if x_unit == "numeric":
        return x_min, x_max
    if x_unit == "s":
        return x_min / 1000.0, x_max / 1000.0
    if x_unit == "ms":
        return x_min, x_max
    return (
        datetime.utcfromtimestamp(x_min / 1000),
        datetime.utcfromtimestamp(x_max / 1000),
    )


def _extract_x_range(relayout: dict[str, Any]) -> tuple[float, float] | None:
    """Plotly sends `xaxis.range[0]` / `xaxis.range[1]` on pan/zoom,
    or `xaxis.autorange=True` on reset. Return (min_ms, max_ms) or None.
    """
    if relayout.get("xaxis.autorange"):
        return None
    lo = relayout.get("xaxis.range[0]")
    hi = relayout.get("xaxis.range[1]")
    if lo is None or hi is None:
        rng = relayout.get("xaxis.range")
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            lo, hi = rng
    if lo is None or hi is None:
        return None
    return _coerce_ms(lo), _coerce_ms(hi)


def _coerce_ms(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    return float(pd.to_datetime(v).timestamp() * 1000)


def _coerce_to_ms(v: Any, x_unit: XUnit) -> float:
    """Accept user-supplied bounds and normalise to the internal ms scale.

    Internal bounds are always "ms since epoch" for time-like units and
    raw numeric for `x_unit="numeric"`.
    """
    if x_unit == "numeric":
        return float(v) if not isinstance(v, (datetime, str)) else float(pd.to_datetime(v).timestamp() * 1000)
    if isinstance(v, datetime):
        return v.timestamp() * 1000
    if isinstance(v, (int, float)):
        scale = {"ms": 1.0, "s": 1000.0, "timestamp": 1.0}[x_unit]
        return float(v) * scale if x_unit == "s" else float(v)
    return pd.to_datetime(v).timestamp() * 1000


def _ms_to_bound(ms: float, x_unit: XUnit):
    """Turn an internal ms bound back into a user-facing value for zoom_to."""
    if x_unit == "numeric":
        return ms
    if x_unit == "ms":
        return int(ms)
    if x_unit == "s":
        return ms / 1000.0
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _ms_to_axis_range(x_min: float, x_max: float, x_unit: XUnit) -> tuple:
    """Convert internal ms bounds into Plotly-native x-axis values.

    - `timestamp`: the x column is datetime64 after `time_bucket`, so the
      axis is a date axis — Plotly expects ISO strings or datetimes.
    - `ms`: the axis is a date axis (we convert ms to timestamp via
      `time_bucket(to_timestamp(...))`), so also ISO strings.
    - `s`: same — date axis.
    - `numeric`: raw numeric axis, pass as-is.

    We emit **naive UTC** strings (no `+00:00`). DuckDB's `time_bucket`
    returns naive TIMESTAMPs, so the data column lands as `datetime64[ns]`
    with no tz. If the axis range carried an explicit UTC tag the browser
    would convert it to local time for display, drifting it away from
    the data by the local offset.
    """
    if x_unit == "numeric":
        return (x_min, x_max)
    lo = datetime.fromtimestamp(x_min / 1000, tz=timezone.utc).replace(tzinfo=None).isoformat()
    hi = datetime.fromtimestamp(x_max / 1000, tz=timezone.utc).replace(tzinfo=None).isoformat()
    return (lo, hi)


_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h|d|w)\s*$", re.IGNORECASE)
_DURATION_SCALE_MS = {
    "ms": 1,
    "s": 1_000,
    "m": 60_000,
    "h": 3_600_000,
    "d": 86_400_000,
    "w": 7 * 86_400_000,
}


def _duration_to_ms(duration: str | timedelta) -> float:
    if isinstance(duration, timedelta):
        return duration.total_seconds() * 1000
    m = _DURATION_RE.match(duration)
    if not m:
        raise ValueError(
            f"Could not parse duration {duration!r}. "
            "Use forms like '500ms', '30s', '5m', '1h', '2d', '1w'."
        )
    value = float(m.group(1))
    unit = m.group(2).lower()
    return value * _DURATION_SCALE_MS[unit]
