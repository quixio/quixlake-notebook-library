"""Interactive zoom widget using anywidget + plotly.js.

Plotly.js emits ``plotly_relayout`` events for every zoom gesture
(modebar buttons, mouse-wheel, drag-zoom, dblclick reset).
``mo.ui.plotly`` only exposes selection events, so those zoom gestures
never reach Python and no refetch happens.

This module wires plotly.js directly via anywidget so we can listen to
``plotly_relayout`` and sync the visible x-range back to Python.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from quixviz.chart import TimeseriesChart


# Loaded lazily so importing this module doesn't require anywidget.
_WIDGET_CLASS = None


def _build_class():
    import anywidget
    import traitlets

    esm = r"""
function loadPlotly() {
    if (window.Plotly) return Promise.resolve(window.Plotly);
    if (window.__quixvizPlotlyLoading) return window.__quixvizPlotlyLoading;
    window.__quixvizPlotlyLoading = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = "https://cdn.plot.ly/plotly-2.35.2.min.js";
        s.onload = () => resolve(window.Plotly);
        s.onerror = (e) => reject(new Error("plotly cdn load failed"));
        document.head.appendChild(s);
    });
    return window.__quixvizPlotlyLoading;
}

function render({ model, el }) {
    el.innerHTML = "";
    el.style.width = "100%";
    el.style.border = "2px solid #4a9eff";  // blue border = anywidget loaded
    el.style.padding = "4px";
    el.style.boxSizing = "border-box";

    const status = document.createElement("div");
    status.style.cssText = "font:11px/1.4 monospace;color:#888;padding:2px 4px;";
    status.textContent = "[quixviz] loading plotly.js...";
    el.appendChild(status);

    const plotEl = document.createElement("div");
    plotEl.style.width = "100%";
    plotEl.style.minHeight = "400px";
    el.appendChild(plotEl);

    function log(msg) {
        status.textContent = "[quixviz] " + msg;
        console.log("[quixviz]", msg);
    }

    let listenerAttached = false;

    function draw(Plotly) {
        let fig;
        try {
            fig = JSON.parse(model.get("figure_json"));
        } catch (e) {
            log("bad figure_json: " + e.message);
            return Promise.resolve();
        }
        const config = Object.assign(
            { responsive: true, displaylogo: false },
            fig.config || {},
        );
        return Plotly.react(plotEl, fig.data, fig.layout, config).then(() => {
            if (listenerAttached) {
                log("redrawn @ " + new Date().toLocaleTimeString());
                return;
            }
            listenerAttached = true;
            plotEl.on("plotly_relayout", (ev) => {
                const keys = Object.keys(ev);
                log("relayout: " + keys.join(","));
                if (ev["xaxis.autorange"]) {
                    model.set("x_range", []);
                    model.set("relayout_counter", model.get("relayout_counter") + 1);
                    model.save_changes();
                    return;
                }
                let lo = ev["xaxis.range[0]"];
                let hi = ev["xaxis.range[1]"];
                if (lo === undefined || hi === undefined) {
                    const r = ev["xaxis.range"];
                    if (Array.isArray(r) && r.length === 2) {
                        [lo, hi] = r;
                    }
                }
                if (lo === undefined || hi === undefined) return;
                model.set("x_range", [String(lo), String(hi)]);
                model.set("relayout_counter", model.get("relayout_counter") + 1);
                model.save_changes();
            });
            log("ready — zoom to trigger refetch");
        });
    }

    loadPlotly().then((Plotly) => {
        draw(Plotly);
        model.on("change:figure_json", () => draw(Plotly));
    }).catch((err) => {
        log("FAILED to load plotly: " + err.message);
    });
}

export default { render };
"""

    class QuixvizInteractive(anywidget.AnyWidget):  # type: ignore[misc]
        _esm = esm
        figure_json = traitlets.Unicode("").tag(sync=True)
        x_range = traitlets.List(traitlets.Unicode(), default_value=[]).tag(sync=True)
        relayout_counter = traitlets.Int(0).tag(sync=True)

    return QuixvizInteractive


def _get_class():
    global _WIDGET_CLASS
    if _WIDGET_CLASS is None:
        _WIDGET_CLASS = _build_class()
    return _WIDGET_CLASS


def interactive_chart(chart: "TimeseriesChart"):
    """Return a marimo anywidget that refetches on any plotly zoom gesture."""
    try:
        import marimo as mo
    except ImportError as e:
        raise ImportError(
            "marimo is not installed. Install the marimo extra: "
            "`pip install quixviz[marimo]`"
        ) from e
    try:
        import anywidget  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "anywidget is not installed. Install it with: pip install anywidget"
        ) from e

    fig = chart.figure()
    Widget = _get_class()
    inner = Widget(figure_json=fig.to_json())
    return mo.ui.anywidget(inner)


def apply_interactive_zoom(widget, chart: "TimeseriesChart", set_window) -> bool:
    """Read a zoom event from the widget and push it to marimo state."""
    x_range = getattr(widget, "x_range", None)
    if not x_range or len(x_range) != 2:
        return False
    lo_ms = _coerce_ms(x_range[0], chart.spec.x_unit)
    hi_ms = _coerce_ms(x_range[1], chart.spec.x_unit)
    if hi_ms <= lo_ms:
        return False
    set_window((lo_ms, hi_ms))
    return True


def _coerce_ms(v: Any, x_unit: str) -> float:
    """Convert a plotly relayout bound into the chart's internal ms scale."""
    import pandas as pd

    if x_unit == "numeric":
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        pass
    return float(pd.to_datetime(v).timestamp() * 1000)
