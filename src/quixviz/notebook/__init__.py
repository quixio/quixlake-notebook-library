"""Notebook integrations — wire zoom events back into the chart."""

from quixviz.notebook.interactive import apply_interactive_zoom, interactive_chart
from quixviz.notebook.jupyter import attach_jupyter
from quixviz.notebook.marimo import apply_zoom, marimo_chart, zoom_from_selection
from quixviz.notebook.widgets import range_slider

__all__ = [
    "attach_jupyter",
    "apply_interactive_zoom",
    "apply_zoom",
    "interactive_chart",
    "marimo_chart",
    "range_slider",
    "zoom_from_selection",
]
