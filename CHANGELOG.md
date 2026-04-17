# Changelog

## Unreleased

### Added

- **`DuckDBTransport`** (`quixviz.DuckDBTransport`) — local SQL transport
  backed by DuckDB over parquet files. Implements the same `Transport`
  protocol as `QuixClient`, so charts swap in with no other changes.
  Pins the session to `UTC` and strips tz-aware datetimes so the output
  matches the HTTP/CSV transport regardless of host timezone.
- **Marimo state-driven zoom loop** — `zoom_from_selection(value, set_win)`
  helper in `quixviz.notebook` translates a plotly box-select payload
  into a new window via `mo.state`. Pairs with `marimo_chart(chart)`,
  which primes the figure for horizontal box-select zoom.
- **Offline LOD demo** (`examples/demo_marimo_local.py`) — marimo
  notebook over locally-generated synthetic telemetry. Slider runs in
  hours-from-start so handle labels stay readable; datetime range and
  bucket size shown in the readout.
- **Synthetic data generator** (`examples/generate_demo_data.py`) —
  writes `demo_telemetry.parquet` with layered 24 h / 1 h / 1 min / 1 s
  sinusoids plus noise across multiple drivers, so each zoom level
  reveals new structure. Default: 4.32 M rows at 50 Hz over 24 hours.
- **`[local]` optional extra** pulling in `duckdb>=0.10` and
  `pyarrow>=14`.
- **`.env.example`** documenting `QUIX_LAKE_URL` / `QUIX_LAKE_TOKEN`.

### Fixed

- **Axis misalignment by local timezone offset** — the pinned x-axis
  range was emitted as tz-aware UTC ISO (`…+00:00`) while DuckDB's
  `time_bucket` output landed as tz-aware UTC in pandas. The browser
  converted both to the host's local timezone independently, drifting
  the data away from the axis window by the local offset (most visible
  on BST machines as a ~1 h gap). `_ms_to_axis_range` now emits naive
  UTC ISO, and `DuckDBTransport.execute` strips tz from datetime
  columns so data and axis live in the same frame.
- **`PlotlyRenderer.update` now accepts `x_range`** — pins the visible
  axis to the queried window. Without this, sparse data collapsed the
  axis to wherever rows happened to exist, hiding the fact that coarse
  zooms still returned the requested span.

### Changed

- **Secrets removed from example sources.** `smoke_ac_telemetry.py`,
  `demo_marimo.py`, and `demo.ipynb` now require `QUIX_LAKE_URL` and
  `QUIX_LAKE_TOKEN` environment variables instead of silently falling
  back to a hardcoded SDK token. `.ipynb_checkpoints/` directory (which
  held stale copies) removed; `.gitignore` now excludes it.
- **Marimo demo UX** — slider runs in hours-from-start instead of raw
  ms (handles render as `12.50` not `1.8e12`); readout shows a full
  datetime range with bucket and point count. In-chart rangeslider /
  rangeselector disabled in the local demo so the top slider is the
  single zoom path (the in-chart ones are browser-only and can't
  refetch).

### Notes

- The Plotly in-chart rangeslider is browser-side zoom only: no Python
  callback, no refetch. In Jupyter, `attach_jupyter` bridges in-chart
  zoom back via `FigureWidget` relayout events. In marimo, use
  `zoom_from_selection` for the equivalent feedback loop.
