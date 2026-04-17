"""End-to-end smoke test against the live testrig lake."""

from __future__ import annotations

import os
import time

import quixviz as qv

URL = os.environ["QUIX_LAKE_URL"]
TOKEN = os.environ["QUIX_LAKE_TOKEN"]


def timed(label: str, fn):
    t = time.perf_counter()
    result = fn()
    dt = (time.perf_counter() - t) * 1000
    print(f"  {label}: {dt:.0f} ms")
    return result


def main() -> None:
    client = qv.connect(URL, token=TOKEN)

    chart = qv.timeseries(
        client,
        table="ac_telemetry",
        x="timestamp_ms",
        y=["speedKmh", "rpms"],
        agg=["min", "max", "avg"],
        x_unit="ms",
    )

    print("preflight:")
    x_min, x_max, count = timed("MIN/MAX/COUNT", chart.preflight)
    print(f"    range ms=[{x_min:,.0f}, {x_max:,.0f}]  span_days={(x_max - x_min) / 86_400_000:.2f}  rows={count:,}")

    print("initial fetch (full range, coarse bucket):")
    df_full = timed("bucketed GROUP BY", chart.fetch)
    print(f"    rows_returned={len(df_full)}  bucket_ms={chart._last_bucket_ms:,}")

    print("zoom to last hour of range:")
    hour_ms = 60 * 60 * 1000
    df_zoom = timed(
        "zoomed fetch",
        lambda: chart.fetch(x_min=x_max - hour_ms, x_max=x_max),
    )
    print(f"    rows_returned={len(df_zoom)}  bucket_ms={chart._last_bucket_ms:,}")

    print("zoom further to last minute:")
    min_ms = 60 * 1000
    df_fine = timed(
        "zoomed fetch",
        lambda: chart.fetch(x_min=x_max - min_ms, x_max=x_max),
    )
    print(f"    rows_returned={len(df_fine)}  bucket_ms={chart._last_bucket_ms:,}")

    print("refetch same window (should hit cache):")
    t = time.perf_counter()
    chart.fetch(x_min=x_max - min_ms, x_max=x_max)
    print(f"    cache_hit: {(time.perf_counter() - t) * 1000:.1f} ms")

    print("render figure:")
    fig = timed("plotly build", chart.figure)
    print(f"    traces={len(fig.data)}  ok")


if __name__ == "__main__":
    main()
