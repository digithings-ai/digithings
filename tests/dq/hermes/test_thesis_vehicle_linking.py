"""thesis_io: upsert_thesis_vehicles populates linked_market_thesis_id (#1047).

Verifies the two changes from the F4 hierarchy fix:
  1. upsert_thesis_vehicles() fires a theses.update(linked_market_thesis_id=...)
     for each ticker after writing the thesis_vehicles row.
  2. upsert_vehicle_thesis_from_analyst() now accepts and threads through a
     linked_market_thesis_id parameter.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest

pytestmark = pytest.mark.unit

# Minimal Supabase stub — avoids importing atlas.state (Python 3.12-only syntax).

_RUN_DATE = date(2026, 6, 12)


@dataclass
class _MockQuery:
    store: dict[str, list[dict]]
    updates: list[dict]
    table_name: str
    _upsert_row: dict | None = None
    _update_payload: dict | None = None
    _filters: list[tuple] = field(default_factory=list)

    def select(self, _cols: str) -> "_MockQuery":
        return self

    def eq(self, col: str, val: Any) -> "_MockQuery":
        self._filters.append(("eq", col, val))
        return self

    def upsert(self, row: dict, on_conflict: str | None = None) -> "_MockQuery":
        self._upsert_row = dict(row)
        return self

    def update(self, payload: dict) -> "_MockQuery":
        self._update_payload = dict(payload)
        return self

    def execute(self) -> object:
        if self._upsert_row is not None:
            self.store[self.table_name].append(self._upsert_row)
        if self._update_payload is not None:
            self.updates.append({"table": self.table_name, "payload": self._update_payload, "filters": list(self._filters)})
        return type("R", (), {"data": []})()


@dataclass
class _MockClient:
    store: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    updates: list[dict] = field(default_factory=list)

    def table(self, name: str) -> _MockQuery:
        return _MockQuery(store=self.store, updates=self.updates, table_name=name)


# ── Import the real functions under test ─────────────────────────────────────

from digiquant.olympus.hermes.writers.thesis_io import (  # noqa: E402
    upsert_thesis_vehicles,
    upsert_vehicle_thesis_from_analyst,
)


class TestUpsertThesisVehiclesLinksMarketThesis:
    def test_update_fires_for_each_ticker(self) -> None:
        client = _MockClient()
        upsert_thesis_vehicles(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            thesis_id="MT1",
            tickers=["EWT", "EEM"],
        )
        thesis_updates = [u for u in client.updates if u["table"] == "theses"]
        assert len(thesis_updates) == 2

    def test_linked_market_thesis_id_set_correctly(self) -> None:
        client = _MockClient()
        upsert_thesis_vehicles(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            thesis_id="MT1",
            tickers=["EWT"],
        )
        update = next(u for u in client.updates if u["table"] == "theses")
        assert update["payload"]["linked_market_thesis_id"] == "MT1"

    def test_filter_targets_vehicle_thesis_id(self) -> None:
        client = _MockClient()
        upsert_thesis_vehicles(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            thesis_id="risk-off",
            tickers=["TLT"],
        )
        update = next(u for u in client.updates if u["table"] == "theses")
        filter_vals = {col: val for _, col, val in update["filters"]}
        assert filter_vals.get("thesis_id") == "vehicle-tlt"
        assert filter_vals.get("date") == _RUN_DATE.isoformat()

    def test_thesis_vehicles_row_still_written(self) -> None:
        client = _MockClient()
        upsert_thesis_vehicles(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            thesis_id="MT1",
            tickers=["EWT"],
        )
        rows = client.store["thesis_vehicles"]
        assert len(rows) == 1
        assert rows[0]["ticker"] == "EWT"
        assert rows[0]["thesis_id"] == "MT1"

    def test_empty_tickers_no_updates(self) -> None:
        client = _MockClient()
        written = upsert_thesis_vehicles(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            thesis_id="MT1",
            tickers=[],
        )
        assert written == 0
        assert client.updates == []


class TestUpsertVehicleThesisLinkedMarketId:
    def test_linked_market_thesis_id_threaded_through(self) -> None:
        client = _MockClient()
        upsert_vehicle_thesis_from_analyst(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            ticker="NVDA",
            analyst_payload={"thesis": "AI boom", "risks": "rate spike"},
            linked_market_thesis_id="MT2",
        )
        rows = client.store["theses"]
        assert len(rows) == 1
        assert rows[0]["thesis_id"] == "vehicle-nvda"
        assert rows[0].get("linked_market_thesis_id") == "MT2"

    def test_linked_market_thesis_id_defaults_to_none(self) -> None:
        client = _MockClient()
        upsert_vehicle_thesis_from_analyst(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            ticker="AMZN",
            analyst_payload={"thesis": "cloud re-acceleration"},
        )
        rows = client.store["theses"]
        assert len(rows) == 1
        # When not passed, the field should be absent or falsy
        assert not rows[0].get("linked_market_thesis_id")
