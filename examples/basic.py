"""Minimal example — run against a local Quix lake."""

import os

import quixviz as qv

client = qv.connect(
    os.environ.get("QUIX_LAKE_URL", "http://localhost"),
    token=os.environ.get("QUIX_LAKE_TOKEN"),
)

chart = qv.timeseries(
    client,
    table="telemetry",
    x="timestamp",
    y=["temperature"],
    agg=["min", "max", "avg"],
    group_by="device_id",
)

x_min, x_max, count = chart.preflight()
print(f"range=[{x_min}, {x_max}]  rows={count}")

fig = chart.show()
fig.show()
