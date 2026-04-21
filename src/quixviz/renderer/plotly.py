"""Plotly renderer with min/max envelopes.

When a Series specifies both `min` and `max` aggregations we draw them
as a filled band (toself polygon) and overlay `avg`/`first`/`last`/etc.
as lines. This preserves spikes at coarse zoom levels — the one thing
the Svelte UI doesn't do.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from quixviz.series import Series
from quixviz.query import agg_alias, iter_y_agg

if TYPE_CHECKING:
    import plotly.graph_objects as go


BASE_HUES = [0.58, 0.08, 0.33, 0.75, 0.48, 0.93, 0.18, 0.63]


def _hex(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def _rgba(h: float, s: float, v: float, a: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return f"rgba({int(r * 255)},{int(g * 255)},{int(b * 255)},{a})"


@dataclass
class PlotlyRenderer:
    spec: Series
    height: int = 420
    marker_threshold: int = 500
    rangeslider: bool = False
    rangeselector: bool = False
    _fig: "go.Figure | None" = field(default=None, init=False, repr=False)

    def figure(self) -> "go.Figure":
        import plotly.graph_objects as go

        if self._fig is None:
            self._fig = go.Figure()
            xaxis_opts: dict = dict(title=self.spec.x)
            if self.rangeslider:
                xaxis_opts["rangeslider"] = dict(visible=True, thickness=0.06)
            if self.rangeselector and self.spec.x_unit in ("timestamp", "ms", "s"):
                xaxis_opts["rangeselector"] = dict(
                    buttons=[
                        dict(count=1, label="1m", step="minute", stepmode="backward"),
                        dict(count=10, label="10m", step="minute", stepmode="backward"),
                        dict(count=1, label="1h", step="hour", stepmode="backward"),
                        dict(count=1, label="1d", step="day", stepmode="backward"),
                        dict(count=7, label="1w", step="day", stepmode="backward"),
                        dict(step="all", label="all"),
                    ]
                )
            self._fig.update_layout(
                height=self.height,
                margin=dict(l=40, r=10, t=50, b=40),
                hovermode="x unified",
                dragmode="zoom",
                xaxis=xaxis_opts,
                yaxis=dict(title=", ".join(self.spec.y)),
                showlegend=True,
            )
        return self._fig

    def update(
        self,
        df: pd.DataFrame,
        *,
        x_range: tuple | None = None,
    ) -> "go.Figure":
        """Re-render the figure from a DataFrame.

        `x_range` pins the visible x-axis to the queried window so
        sparse data doesn't cause the axis to snap to wherever rows
        happen to land. Pass `(x_min, x_max)` in the figure's native
        x scale — datetimes for `x_unit="timestamp"`, numeric otherwise.
        """
        import plotly.graph_objects as go

        fig = self.figure()
        fig.data = ()

        if x_range is not None:
            fig.update_xaxes(range=list(x_range), autorange=False)

        if df.empty:
            return fig

        x_col = self.spec.x
        x_series = df[x_col]

        group_values: list[str | None]
        if self.spec.group_by and self.spec.group_by in df.columns:
            group_values = [v for v in df[self.spec.group_by].unique()]
        else:
            group_values = [None]

        has_envelope = "min" in self.spec.agg and "max" in self.spec.agg
        line_aggs = [a for a in self.spec.agg if not (has_envelope and a in ("min", "max"))]

        show_markers = len(df) < self.marker_threshold

        for y_idx, y in enumerate(self.spec.y):
            base_hue = BASE_HUES[y_idx % len(BASE_HUES)]
            for g_idx, group_val in enumerate(group_values):
                if group_val is None:
                    mask = pd.Series(True, index=df.index)
                    label_base = y
                else:
                    mask = df[self.spec.group_by] == group_val
                    label_base = f"{y} · {group_val}"

                sub = df[mask]
                xs = sub[x_col]
                # Distribute lightness across group values so related series cluster.
                lightness = 0.55 + (g_idx / max(1, len(group_values))) * 0.35
                line_color = _hex(base_hue, 0.65, lightness)
                fill_color = _rgba(base_hue, 0.45, lightness, 0.18)

                if has_envelope:
                    min_col = agg_alias(y, "min")
                    max_col = agg_alias(y, "max")
                    if min_col in sub.columns and max_col in sub.columns:
                        fig.add_trace(
                            go.Scatter(
                                x=pd.concat([xs, xs[::-1]]),
                                y=pd.concat([sub[max_col], sub[min_col][::-1]]),
                                fill="toself",
                                fillcolor=fill_color,
                                line=dict(width=0),
                                hoverinfo="skip",
                                name=f"{label_base} · min/max",
                                legendgroup=label_base,
                                showlegend=True,
                            )
                        )

                for agg in line_aggs:
                    col = agg_alias(y, agg)
                    if col not in sub.columns:
                        continue
                    dash = {"avg": "solid", "sum": "solid", "count": "dot"}.get(agg, "dash")
                    fig.add_trace(
                        go.Scatter(
                            x=xs,
                            y=sub[col],
                            mode="lines+markers" if show_markers else "lines",
                            line=dict(color=line_color, width=1.7, dash=dash),
                            marker=dict(size=4),
                            name=f"{label_base} · {agg}",
                            legendgroup=label_base,
                        )
                    )

        return fig
