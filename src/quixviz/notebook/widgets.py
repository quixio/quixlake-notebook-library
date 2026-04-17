"""ipywidgets range slider that drives chart.zoom_to on change.

Gives you the same LOD refetch behaviour as the Plotly relayout loop
but with an explicit slider UI underneath the chart — useful if a
`FigureWidget` isn't viable in your notebook environment.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quixviz.chart import TimeseriesChart


_SLIDER_STEPS = 400


def range_slider(chart: "TimeseriesChart", steps: int = _SLIDER_STEPS):
    """Return a VBox containing a range slider and the chart output.

    Moving the slider calls `chart.zoom_to(...)` which recomputes the
    bucket and refetches. The figure below updates on each change.

    Usage in a notebook cell:

        from quixviz.notebook.widgets import range_slider
        range_slider(chart)
    """
    try:
        import ipywidgets as widgets
        from IPython.display import clear_output, display
    except ImportError as e:
        raise ImportError(
            "range_slider requires ipywidgets. Install via "
            "`pip install quixviz[jupyter]`."
        ) from e

    if chart._x_min is None or chart._x_max is None:
        chart.preflight()
    assert chart._x_min is not None and chart._x_max is not None

    x_min_ms = float(chart._x_min)
    x_max_ms = float(chart._x_max)
    step = max(1.0, (x_max_ms - x_min_ms) / steps)

    time_like = chart.spec.x_unit in ("timestamp", "ms", "s")
    slider = widgets.FloatRangeSlider(
        value=[x_min_ms, x_max_ms],
        min=x_min_ms,
        max=x_max_ms,
        step=step,
        description="range",
        readout=False,
        continuous_update=False,
        layout=widgets.Layout(width="100%"),
    )
    label = widgets.HTML()
    bucket_label = widgets.HTML()
    output = widgets.Output()

    def _fmt(ms: float) -> str:
        if time_like:
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return f"{ms:,.0f}"

    def _render(lo: float, hi: float):
        fig = chart.zoom_to(
            _to_user_bound(lo, chart.spec.x_unit),
            _to_user_bound(hi, chart.spec.x_unit),
        )
        label.value = f"<code>{_fmt(lo)}</code> → <code>{_fmt(hi)}</code>"
        bucket_label.value = (
            f"<small>bucket {chart._last_bucket_ms:,} ms · "
            f"{len(chart._df)} points</small>"
        )
        with output:
            clear_output(wait=True)
            display(fig)

    def _on_change(change):
        lo, hi = change["new"]
        if hi <= lo:
            return
        _render(lo, hi)

    slider.observe(_on_change, names="value")
    _render(x_min_ms, x_max_ms)

    return widgets.VBox([slider, widgets.HBox([label, bucket_label]), output])


def _to_user_bound(ms: float, x_unit: str):
    if x_unit == "numeric":
        return ms
    if x_unit == "ms":
        return int(ms)
    if x_unit == "s":
        return ms / 1000.0
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
