"""Marimo integration: in-chart zoom → refetch.

`mo.ui.plotly` exposes the current *box selection* as a list of point
dicts via `.value`. We use horizontal box-select as the zoom gesture:
the user drags a box across the chart, we extract the x-range from the
selected points, and refetch at the new LOD.

Usage in a marimo notebook (three cells):

    # Cell A — state holds the active window (ms)
    get_win, set_win = mo.state((x_min, x_max))

    # Cell B — rebuild the figure + widget whenever state changes
    lo, hi = get_win()
    chart.zoom_to(lo, hi)
    fig = chart.figure()
    fig.update_layout(dragmode="select", selectdirection="h")
    widget = mo.ui.plotly(fig)
    widget

    # Cell C — translate selection to a new window
    zoom_from_selection(widget.value, set_win)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import pandas as pd

if TYPE_CHECKING:
    from quixviz.chart import TimeseriesChart


def marimo_chart(chart: "TimeseriesChart"):
    """Return a plotly UIElement primed for horizontal box-select zoom.

    Pair with `zoom_from_selection(widget.value, set_win)` in a
    downstream cell to close the loop.
    """
    try:
        import marimo as mo
    except ImportError as e:
        raise ImportError(
            "marimo is not installed. Install the marimo extra: "
            "`pip install quixviz[marimo]`"
        ) from e

    fig = chart.figure()
    fig.update_layout(dragmode="select", selectdirection="h")
    return mo.ui.plotly(fig)


def _selection_x_range(value: Any) -> tuple | None:
    """Extract (min_x, max_x) from `mo.ui.plotly.value`.

    Marimo returns the selection as a list of point dicts. Each dict's
    `x` is whatever Plotly natively stores for the axis — ISO strings
    for date axes, floats for numeric axes. We leave the raw values
    alone and let `chart.zoom_to` coerce them.
    """
    if not value or not isinstance(value, list):
        return None
    xs = [p["x"] for p in value if isinstance(p, dict) and p.get("x") is not None]
    if len(xs) < 2:
        return None
    return min(xs), max(xs)


def _to_ms(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    return float(pd.to_datetime(v).timestamp() * 1000)


def zoom_from_selection(
    value: Any,
    set_window: Callable[[tuple[float, float]], None],
) -> bool:
    """Push a new window to `mo.state` setter from a plotly selection.

    Returns True if the state was updated. No-op on empty selection so
    the loop settles after the widget rebuilds.
    """
    rng = _selection_x_range(value)
    if rng is None:
        return False
    lo, hi = _to_ms(rng[0]), _to_ms(rng[1])
    if hi <= lo:
        return False
    set_window((lo, hi))
    return True


def apply_zoom(chart: "TimeseriesChart", value: Any) -> "TimeseriesChart":
    """Apply a plotly widget's `.value` directly to the chart (no state).

    Handles both the current selection format (list of point dicts) and
    the legacy relayout-dict shape. Prefer the state-driven pattern
    with `zoom_from_selection` — this helper is kept for single-cell
    quick demos where the loop doesn't need to close visually.
    """
    rng = _selection_x_range(value)
    if rng is not None:
        chart.zoom_to(rng[0], rng[1])
        return chart
    if isinstance(value, dict):
        relayout = value.get("relayout_data") or value
        if isinstance(relayout, dict):
            chart.on_relayout(relayout)
    return chart
