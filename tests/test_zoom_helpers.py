"""Tests for the non-widget zoom helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import quixviz as qv
from quixviz.chart import _coerce_to_ms, _duration_to_ms, _ms_to_bound
from quixviz.query import agg_alias


class FakeTransport:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, sql: str) -> pd.DataFrame:
        self.queries.append(sql)
        if "MIN(" in sql and "MAX(" in sql and "COUNT(" in sql:
            # 1-day span in ms epoch
            return pd.DataFrame({"x_min": [1_700_000_000_000], "x_max": [1_700_086_400_000], "row_count": [10_000]})
        return pd.DataFrame({"ts": [1_700_000_000_000], agg_alias("v", "avg"): [1.0]})


class TestDurationParser:
    @pytest.mark.parametrize(
        "text, ms",
        [
            ("500ms", 500),
            ("30s", 30_000),
            ("5m", 300_000),
            ("1h", 3_600_000),
            ("2d", 2 * 86_400_000),
            ("1w", 7 * 86_400_000),
            ("1.5h", 1.5 * 3_600_000),
        ],
    )
    def test_valid_strings(self, text, ms):
        assert _duration_to_ms(text) == pytest.approx(ms)

    def test_timedelta(self):
        assert _duration_to_ms(timedelta(minutes=5)) == 300_000

    def test_rejects_garbage(self):
        with pytest.raises(ValueError):
            _duration_to_ms("soonish")


class TestCoerceBounds:
    def test_ms_int_passthrough(self):
        assert _coerce_to_ms(1_700_000_000_000, "ms") == 1_700_000_000_000

    def test_s_scales_to_ms(self):
        assert _coerce_to_ms(1_700_000_000, "s") == 1_700_000_000_000

    def test_datetime_converts(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert _coerce_to_ms(dt, "timestamp") == dt.timestamp() * 1000

    def test_iso_string(self):
        assert _coerce_to_ms("2024-01-01T00:00:00Z", "timestamp") > 0


class TestMsToBound:
    def test_timestamp_returns_datetime(self):
        out = _ms_to_bound(1_700_000_000_000, "timestamp")
        assert isinstance(out, datetime)

    def test_ms_returns_int(self):
        assert _ms_to_bound(1_700_000_000_000, "ms") == 1_700_000_000_000

    def test_s_scales_down(self):
        assert _ms_to_bound(1_700_000_000_000, "s") == 1_700_000_000.0


class TestZoomAPI:
    def test_zoom_to_with_datetimes(self):
        t = FakeTransport()
        chart = qv.timeseries(t, table="telemetry", x="ts", y="v")
        chart.preflight()
        chart.zoom_to(datetime(2023, 11, 14, tzinfo=timezone.utc), datetime(2023, 11, 15, tzinfo=timezone.utc))
        assert chart._last_bucket_ms is not None
        assert "time_bucket" in t.queries[-1]

    def test_zoom_last_1h_runs_preflight_if_needed(self):
        t = FakeTransport()
        chart = qv.timeseries(t, table="telemetry", x="ts", y="v", x_unit="ms")
        chart.zoom_last("1h")
        assert any("MIN(" in q for q in t.queries)
        assert any("time_bucket" in q for q in t.queries)

    def test_zoom_last_accepts_timedelta(self):
        t = FakeTransport()
        chart = qv.timeseries(t, table="telemetry", x="ts", y="v", x_unit="ms")
        chart.zoom_last(timedelta(hours=1))
        assert any("time_bucket" in q for q in t.queries)

    def test_reset_refetches_full_range(self):
        t = FakeTransport()
        chart = qv.timeseries(t, table="telemetry", x="ts", y="v", x_unit="ms")
        chart.zoom_last("1m")
        before = len(t.queries)
        chart.reset()
        assert len(t.queries) > before
