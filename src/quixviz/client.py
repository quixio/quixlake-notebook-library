"""Thin HTTP client for the Quix data lake /query endpoint.

Mirrors the contract used by the Svelte UI and the quixlake SDK:
POST raw SQL as text/plain, receive CSV. We can swap this for Arrow
Flight later by implementing the same `execute` method.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

import pandas as pd
import requests


class Transport(Protocol):
    """Any transport that turns a SQL string into a DataFrame."""

    def execute(self, sql: str) -> pd.DataFrame: ...


@dataclass
class QuixClient:
    """Default HTTP+CSV transport for Quix lake /query."""

    base_url: str
    token: str | None = None
    timeout: int = 60
    union_by_name: bool = True

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self._session = requests.Session()
        if self.token:
            self._session.headers["Authorization"] = f"Bearer {self.token}"

    def execute(self, sql: str) -> pd.DataFrame:
        url = urljoin(self.base_url + "/", "query")
        params = {
            "explain": "false",
            "union_by_name": "true" if self.union_by_name else "false",
        }
        response = self._session.post(
            url,
            data=sql,
            params=params,
            timeout=self.timeout,
            headers={"Content-Type": "text/plain"},
        )
        if response.status_code != 200:
            raise QueryError(
                f"Query failed ({response.status_code}): {response.text}",
                sql=sql,
            )
        body = response.text
        if not body.strip():
            return pd.DataFrame()
        # The /query endpoint returns errors as `# ERROR: ...` with HTTP 200.
        if body.lstrip().startswith("# ERROR"):
            message = body.split("\n", 1)[0].lstrip("# ").strip()
            raise QueryError(f"Query failed: {message}", sql=sql)
        return pd.read_csv(io.StringIO(body))


class QueryError(RuntimeError):
    def __init__(self, message: str, *, sql: str) -> None:
        super().__init__(message)
        self.sql = sql


def connect(base_url: str, token: str | None = None, **kwargs) -> QuixClient:
    """Shortcut for building a QuixClient."""
    return QuixClient(base_url=base_url, token=token, **kwargs)
