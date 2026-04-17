"""quixviz — zoom-aware timeseries visualisation against the Quix data lake."""

from quixviz.client import QuixClient, connect
from quixviz.series import Series, TimeRange
from quixviz.chart import TimeseriesChart, timeseries
from quixviz.local import DuckDBTransport

__version__ = "0.1.0"

__all__ = [
    "DuckDBTransport",
    "QuixClient",
    "Series",
    "TimeRange",
    "TimeseriesChart",
    "connect",
    "timeseries",
]
