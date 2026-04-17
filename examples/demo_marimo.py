import marimo

__generated_with = "0.23.1"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo

    mo.md(
        """
        # quixviz · marimo demo

        Zoom-aware timeseries against a live Quix data lake.

        - Marimo's reactivity gives us the LOD loop for free: drag the
          slider, the next cell re-runs, the chart refetches at a new
          bucket, the new figure renders.
        - No ipywidgets, no FigureWidget — just `chart.zoom_to(...)`
          driven by `mo.ui.range_slider`.
        """
    )
    return (mo,)


@app.cell
def _():
    import os
    import quixviz as qv

    URL = os.environ["QUIX_LAKE_URL"]
    TOKEN = os.environ["QUIX_LAKE_TOKEN"]

    client = qv.connect(URL, token=TOKEN)
    return client, qv


@app.cell
def _(client, qv):
    chart = qv.timeseries(
        client,
        table="ac_telemetry",
        x="timestamp_ms",
        y=["speedKmh"],
        agg=["min", "max", "avg"],
        x_unit="ms",
    )
    x_min, x_max, count = chart.preflight()
    return chart, count, x_max, x_min


@app.cell(hide_code=True)
def _(count, mo, x_max, x_min):
    span_days = (x_max - x_min) / 86_400_000
    mo.md(
        f"Preflight — range spans **{span_days:.2f} days** over "
        f"**{count:,} rows**. `bucket_ms` will shrink automatically as "
        "you zoom in."
    )
    return


@app.cell
def _(mo, x_max, x_min):
    window = mo.ui.range_slider(
        start=x_min,
        stop=x_max,
        step=max(1.0, (x_max - x_min) / 400),
        value=[x_min, x_max],
        label="window",
        show_value=False,
        full_width=True,
        debounce=True,
    )
    window
    return (window,)


@app.cell
def _(chart, mo, window):
    # Reactive cell: marimo re-runs this whenever `window.value` changes.
    lo, hi = window.value
    fig = chart.zoom_to(lo, hi)
    readout = mo.md(
        f"**bucket:** {chart._last_bucket_ms:,} ms · "
        f"**points:** {len(chart._df)}"
    )
    mo.vstack([readout, fig])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Programmatic zoom

    You can also drive zoom from cells. Each of these re-renders the
    figure below at a fresh LOD:
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
    chart.reset()
    return


if __name__ == "__main__":
    app.run()
