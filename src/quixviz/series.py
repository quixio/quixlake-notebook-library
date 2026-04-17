"""User-facing specification types for a chart query."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Sequence

AggFn = Literal["min", "max", "avg", "sum", "count", "first", "last"]

XUnit = Literal["timestamp", "ms", "s", "numeric"]
"""How the x column should be interpreted.

- "timestamp": native SQL TIMESTAMP / TIMESTAMPTZ column.
- "ms":        numeric milliseconds since epoch.
- "s":         numeric seconds since epoch.
- "numeric":   non-time numeric axis (integer modulo truncation).
"""


@dataclass(frozen=True)
class TimeRange:
    start: datetime | int | float | str | None = None
    end: datetime | int | float | str | None = None


@dataclass
class Series:
    """A single chart spec. One Series -> one SQL query at a given LOD."""

    table: str
    x: str
    y: Sequence[str]
    agg: Sequence[AggFn] = ("avg",)
    group_by: str | None = None
    where: str | None = None
    x_unit: XUnit = "timestamp"
    time_range: TimeRange | None = None
    max_group_values: int = 20

    def __post_init__(self) -> None:
        if isinstance(self.y, str):
            self.y = [self.y]
        if isinstance(self.agg, str):
            self.agg = [self.agg]
        if not self.y:
            raise ValueError("Series.y must contain at least one column")
        if not self.agg:
            raise ValueError("Series.agg must contain at least one aggregation")
