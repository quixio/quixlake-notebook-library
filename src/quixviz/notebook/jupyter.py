"""Jupyter / IPython integration: refetch on Plotly relayout.

FigureWidget.layout.on_change gives us live pan/zoom events from the
browser back into Python, so we can refetch at the new LOD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quixviz.chart import TimeseriesChart


def attach_jupyter(chart: "TimeseriesChart"):
    """Return a FigureWidget wired to chart.on_relayout.

    Use this inside a Jupyter cell:

        widget = quixviz.notebook.attach_jupyter(chart)
        widget
    """
    import plotly.graph_objects as go

    fig = chart.figure()
    widget = go.FigureWidget(fig)

    def _on_relayout(layout, x_range):
        if x_range is None:
            return
        changed = chart.on_relayout(
            {"xaxis.range[0]": x_range[0], "xaxis.range[1]": x_range[1]}
        )
        if not changed:
            return
        new_fig = chart.figure()
        with widget.batch_update():
            widget.data = ()
            for trace in new_fig.data:
                widget.add_trace(trace)

    widget.layout.xaxis.on_change(_on_relayout, "range")
    return widget
