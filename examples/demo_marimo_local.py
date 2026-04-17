import marimo

__generated_with = "0.23.1"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo

    mo.md(
        """
        # quixviz · local LOD demo

        Synthetic telemetry, layered sinusoids at 24h / 1h / 1min / 1s
        so each zoom level reveals new structure. Backed by a local
        DuckDB transport — no network.

        - Drag the **window** slider to change the visible range.
        - Watch `bucket` shrink as you zoom in, and the trace fill out
          with the finer-grained sinusoids that were averaged away at
          coarser buckets.
        """
    )
    return (mo,)


@app.cell
def _():
    import importlib.util
    import sys
    from pathlib import Path
    import quixviz as qv

    here = Path(__file__).parent
    parquet = here / "demo_telemetry.parquet"
    if not parquet.exists():
        # Import the neighbouring generator and run it.
        spec = importlib.util.spec_from_file_location(
            "generate_demo_data", here / "generate_demo_data.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["generate_demo_data"] = mod
        spec.loader.exec_module(mod)
        mod.generate(parquet)

    transport = qv.DuckDBTransport(tables={"demo_telemetry": parquet})
    return qv, transport


@app.cell
def _(qv, transport):
    chart = qv.timeseries(
        transport,
        table="demo_telemetry",
        x="timestamp_ms",
        y=["speedKmh"],
        agg=["min", "max", "avg"],
        x_unit="ms",
        # The in-chart rangeslider/selector are browser-only — they
        # don't refetch, and their strip goes stale when we filter the
        # data to a zoomed window. The top `window` slider is the only
        # zoom path, so turn these off.
        rangeslider=False,
        rangeselector=False,
    )
    x_min, x_max, count = chart.preflight()
    return chart, count, x_max, x_min


@app.cell(hide_code=True)
def _(count, mo, x_max, x_min):
    span_h = (x_max - x_min) / 3_600_000
    mo.md(
        f"Preflight — **{count:,} rows** spanning **{span_h:.2f} hours** "
        "at 50 Hz. `bucket_ms` shrinks automatically as you zoom in."
    )
    return


@app.cell
def _(mo, x_max, x_min):
    # Slider runs in "hours from start" so the handle bubbles render as
    # readable numbers (e.g. 12.50) instead of raw ms (1.8e12). The
    # reactive cell below converts back to ms for the query.
    window_hours = (x_max - x_min) / 3_600_000
    window = mo.ui.range_slider(
        start=0.0,
        stop=window_hours,
        step=window_hours / 10_000,
        value=[0.0, window_hours],
        label="window (hours from start)",
        show_value=True,
        full_width=True,
        debounce=True,
    )
    window
    return (window,)


@app.cell
def _(chart, mo, window, x_min):
    import pandas as pd

    lo_h, hi_h = window.value
    lo_ms = x_min + lo_h * 3_600_000
    hi_ms = x_min + hi_h * 3_600_000
    fig = chart.zoom_to(lo_ms, hi_ms)

    lo_dt = pd.Timestamp(lo_ms, unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M:%S")
    hi_dt = pd.Timestamp(hi_ms, unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M:%S")
    span_s = (hi_ms - lo_ms) / 1000
    readout = mo.md(
        f"**{lo_dt}** → **{hi_dt}** ({span_s:,.1f} s) · "
        f"bucket **{chart._last_bucket_ms:,} ms** · "
        f"points **{len(chart._df):,}**"
    )
    mo.vstack([readout, fig])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Programmatic zoom

    Each cell below jumps to a named zoom level so you can see the
    LOD tiers side by side in the chart above.
    """)
    return


@app.cell
def _(chart):
    chart.zoom_last("1h")
    return


@app.cell
def _(chart):
    chart.zoom_last("1m")
    return


@app.cell
def _(chart):
    chart.zoom_last("1s")
    return


@app.cell
def _(chart):
    chart.reset()
    return


if __name__ == "__main__":
    app.run()
