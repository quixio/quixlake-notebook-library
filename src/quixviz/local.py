"""DuckDB-backed transport for local files — no HTTP, no remote lake.

Useful for demos, tests, and offline notebooks. Point it at one or
more parquet files and it exposes them as queryable tables, matching
the same `Transport` protocol as `QuixClient`.

    transport = DuckDBTransport(tables={"telemetry": "data/telemetry.parquet"})
    chart = qv.timeseries(transport, table="telemetry", ...)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Mapping

import pandas as pd

if TYPE_CHECKING:
    import duckdb


class DuckDBTransport:
    """Run SQL locally via DuckDB. Conforms to `quixviz.client.Transport`."""

    def __init__(
        self,
        tables: Mapping[str, str | Path] | None = None,
        *,
        database: str = ":memory:",
        connection: "duckdb.DuckDBPyConnection | None" = None,
    ) -> None:
        import duckdb

        self._con = connection if connection is not None else duckdb.connect(database)
        # Pin the session to UTC so `time_bucket(to_timestamp(...))` doesn't
        # silently shift into the machine's local timezone (BST, CET, etc.)
        # and drift the bucketed x values away from the window we queried.
        self._con.execute("SET TimeZone = 'UTC'")
        if tables:
            for name, source in tables.items():
                self.register_parquet(name, source)

    def register_parquet(self, name: str, path: str | Path) -> None:
        p = str(Path(path).resolve()).replace("\\", "/").replace("'", "''")
        self._con.execute(
            f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{p}')"
        )

    def register_view(self, name: str, sql: str) -> None:
        self._con.execute(f"CREATE OR REPLACE VIEW {name} AS {sql}")

    def execute(self, sql: str) -> pd.DataFrame:
        df = self._con.execute(sql).df()
        # DuckDB returns `time_bucket(to_timestamp(...))` as tz-aware UTC.
        # The HTTP/CSV transport returns naive strings, and the chart's
        # axis range is naive UTC — strip tz so renders match regardless
        # of the browser's local timezone.
        for col in df.columns:
            s = df[col]
            if pd.api.types.is_datetime64_any_dtype(s) and s.dt.tz is not None:
                df[col] = s.dt.tz_convert("UTC").dt.tz_localize(None)
        return df

    def close(self) -> None:
        self._con.close()
