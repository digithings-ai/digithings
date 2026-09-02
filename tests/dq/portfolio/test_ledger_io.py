"""Ledger ``_insert`` requires ``workspace_id`` on every row (#3426)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from digiquant.portfolio.writers.ledger_io import _insert
from digiquant.dashboard.tenancy import house_workspace_id

pytestmark = pytest.mark.unit


class _CaptureClient:
    """Records the rows ``_insert`` passes to ``table().insert()``."""

    def __init__(self) -> None:
        self.inserted: list[dict[str, Any]] = []
        self.table_name: str | None = None

    def table(self, name: str) -> _CaptureClient:
        self.table_name = name
        return self

    def insert(self, rows: list[dict[str, Any]]) -> _CaptureClient:
        self.inserted = [dict(row) for row in rows]
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.inserted)


def test_insert_raises_when_workspace_id_is_missing() -> None:
    client = _CaptureClient()
    with pytest.raises(ValueError, match="workspace_id"):
        _insert(client=client, table="portfolio_ledger_commits", rows=[{"id": "row-1"}])
    assert client.inserted == []


def test_insert_raises_when_workspace_id_is_blank() -> None:
    client = _CaptureClient()
    with pytest.raises(ValueError, match="workspace_id"):
        _insert(
            client=client,
            table="broker_orders",
            rows=[{"id": "row-1", "workspace_id": "  "}],
        )
    assert client.inserted == []


def test_insert_passes_existing_workspace_id_through_unchanged() -> None:
    overlay = str(uuid4())
    assert overlay != str(house_workspace_id())
    row = {"id": "row-1", "workspace_id": overlay, "symbol": "SPY"}
    client = _CaptureClient()
    _insert(client=client, table="broker_orders", rows=[row])
    assert client.inserted == [row]
    assert client.inserted[0]["workspace_id"] == overlay
    assert client.inserted[0]["workspace_id"] != str(house_workspace_id())
