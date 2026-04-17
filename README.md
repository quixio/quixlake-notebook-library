# quixviz

Zoom-aware timeseries visualisation for the Quix data lake, designed for
**marimo, Jupyter, and Google Colab**. Think Plotly, but the chart talks
back to the lake at the right level of detail for whatever window you're
looking at.

## Why

The Quix Svelte UI stays fast because it never asks the lake for more
points than pixels. `quixviz` ports that behaviour to Python:

- **Pixel-aware LOD.** Visible window divided by physical pixel width
  picks the bucket size; snapped to nice `1 / 2 / 5 × 10^k` values so
  small pan/zoom nudges don't re-issue queries.
- **Server-side aggregation** via DuckDB `time_bucket(...)` + `GROUP BY`.
  One round-trip returns `min / max / avg / first / last / count` side
  by side.
- **Preflight** uses Iceberg manifest stats (`MIN / MAX / COUNT`) so the
  initial range is cheap even for billions of rows.
- **Tile cache** keyed by `(sql, bucket, window)` so panning inside a
  loaded region is free.
- **Min/max envelopes** render as a filled band over the `avg` line, so
  spikes survive coarse zoom.

## Install

```bash
pip install quixviz           # core (HTTP transport + Plotly renderer)
pip install quixviz[jupyter]  # + ipywidgets for interactive zoom in Jupyter
pip install quixviz[marimo]   # + marimo integration
pip install quixviz[local]    # + DuckDB transport for offline / local parquet
```

## Configuration

The remote-lake examples read credentials from environment variables — no
secrets live in the repo. Copy `.env.example` to `.env`, fill in your
workspace URL and SDK token, and `source` it before running:

```bash
export QUIX_LAKE_URL=https://<workspace>.az-france-0.app.quix.io
export QUIX_LAKE_TOKEN=sdk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Quick start

```python
import quixviz as qv

client = qv.connect("http://localhost", token="...")

chart = qv.timeseries(
    client,
    table="telemetry",
    x="timestamp",
    y=["temperature", "humidity"],
    agg=["min", "max", "avg"],
    group_by="device_id",
    where="device_id IN ('A', 'B', 'C')",
    time_range=("2024-01-01", "2024-02-01"),
)

chart.show()
```

## Jupyter (interactive zoom → refetch)

```python
from quixviz.notebook import attach_jupyter

widget = attach_jupyter(chart)
widget
```

Panning or zooming fires `xaxis.range` events back into Python. The
chart recomputes the bucket size, checks the tile cache, and refetches
only if needed.

## Marimo

Drag a horizontal box on the chart to zoom — marimo re-runs the chart
cell, refetches at a finer bucket, and renders the refreshed view.

```python
import marimo as mo
import quixviz as qv
from quixviz.notebook import zoom_from_selection

chart = qv.timeseries(
    client, table="telemetry", x="timestamp", y="temperature",
    rangeslider=False, rangeselector=False,
)
x_min, x_max, _ = chart.preflight()
```

```python
# Cell: state holds the active window in ms
get_win, set_win = mo.state((x_min, x_max))
```

```python
# Cell: re-renders whenever state changes
lo, hi = get_win()
chart.zoom_to(lo, hi)
fig = chart.figure()
fig.update_layout(dragmode="select", selectdirection="h")
widget = mo.ui.plotly(fig)
widget
```

```python
# Cell: translate box-selection into a new window
zoom_from_selection(widget.value, set_win)
```

For a one-shot refetch without the feedback loop, use `apply_zoom`:

```python
from quixviz.notebook import apply_zoom, marimo_chart
widget = marimo_chart(chart); widget
# next cell:
apply_zoom(chart, widget.value); chart.figure()
```

## How the LOD math works

```
physical_px = css_width_px * device_pixel_ratio
ideal_ms    = (x_max - x_min) / physical_px
bucket_ms   = nice_ceil(ideal_ms)   # snap to 1/2/5 × 10^k
```

For example, a one-month window on a 1200px retina display:

| input                                  | bucket       |
|----------------------------------------|--------------|
| 1 hour on 1200px                       | 5 ms         |
| 1 day on 1200px                        | 50 ms        |
| 1 month on 1200px                      | 2 seconds    |
| 1 year on 1200px                       | 20 seconds   |

## Custom transports

`QuixClient` is the default HTTP/CSV transport against `POST /query`.
Anything implementing the `Transport` protocol
(`execute(sql: str) -> pd.DataFrame`) works — useful for Arrow Flight
later, or for unit tests with a fake transport:

```python
class FakeTransport:
    def execute(self, sql: str) -> pd.DataFrame:
        ...
```

### Local DuckDB transport (offline demos)

`DuckDBTransport` runs SQL directly against local parquet files via
DuckDB — no network, no token. Ideal for offline demos and for stress
testing the LOD loop with dense synthetic data.

```python
import quixviz as qv

transport = qv.DuckDBTransport(tables={"telemetry": "data/telemetry.parquet"})
chart = qv.timeseries(transport, table="telemetry", x="timestamp_ms", ...)
```

The transport pins the DuckDB session to `UTC` and strips any tz-aware
datetime columns so the result shape matches the HTTP/CSV transport.

### Offline LOD demo

`examples/demo_marimo_local.py` runs the whole stack locally. Generate
the dataset once, then open the notebook:

```bash
python examples/generate_demo_data.py           # writes demo_telemetry.parquet (~93 MB)
python -m marimo edit examples/demo_marimo_local.py
```

The synthetic signal stacks four sinusoids (24h / 1h / 1min / 1s) plus
noise, so each zoom level reveals new structure. Default dataset is
4.32M rows at 50 Hz over 24 hours.

## Tests

```bash
pip install -e .[dev]
pytest -q
```
