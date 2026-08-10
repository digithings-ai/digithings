"""thesis_io: vehicle theses link to their real market thesis (#1047, #1563).

Covers:
  1. upsert_thesis_vehicles() writes the thesis_vehicles row and fires a
     best-effort theses.update(linked_market_thesis_id=...) for each ticker.
  2. upsert_vehicle_thesis_from_analyst() resolves the market link from the
     reliable thesis_vehicles map at CREATION time (#1563) — the caller rarely
     supplies one and the same-date H3 back-fill can never populate it, which
     left every vehicle thesis null-linked in prod. Primary = lowest
     candidate_rank; falls back to the most recent prior mapping.
  3. upsert_thesis_row() never persists a self-referential link (the shape of
     ~140 legacy rows) — the write chokepoint guard (#1563).
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
    seed: dict[str, list[dict]]
    table_name: str
    _upsert_row: dict | None = None
    _update_payload: dict | None = None
    _is_select: bool = False
    _filters: list[tuple] = field(default_factory=list)
    _order: tuple | None = None

    def select(self, _cols: str) -> "_MockQuery":
        self._is_select = True
        return self

    def eq(self, col: str, val: Any) -> "_MockQuery":
        self._filters.append(("eq", col, val))
        return self

    def lte(self, col: str, val: Any) -> "_MockQuery":
        self._filters.append(("lte", col, val))
        return self

    def order(self, col: str, desc: bool = False) -> "_MockQuery":
        self._order = (col, desc)
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
            return type("R", (), {"data": []})()
        if self._update_payload is not None:
            self.updates.append(
                {
                    "table": self.table_name,
                    "payload": self._update_payload,
                    "filters": list(self._filters),
                }
            )
            return type("R", (), {"data": []})()
        if self._is_select:
            rows = [dict(r) for r in self.seed.get(self.table_name, [])]
            for kind, col, val in self._filters:
                if kind == "eq":
                    rows = [r for r in rows if r.get(col) == val]
                elif kind == "lte":
                    rows = [r for r in rows if str(r.get(col)) <= str(val)]
            if self._order is not None:
                col, desc = self._order
                rows.sort(key=lambda r: str(r.get(col)), reverse=desc)
            return type("R", (), {"data": rows})()
        return type("R", (), {"data": []})()


@dataclass
class _MockClient:
    store: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    updates: list[dict] = field(default_factory=list)
    seed: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))

    def table(self, name: str) -> _MockQuery:
        return _MockQuery(store=self.store, updates=self.updates, seed=self.seed, table_name=name)


# ── Import the real functions under test ─────────────────────────────────────

from digiquant.olympus.hermes.writers.thesis_io import (  # noqa: E402
    resolve_primary_market_thesis,
    upsert_thesis_row,
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


class TestResolvePrimaryMarketThesis:
    def test_lowest_candidate_rank_is_primary(self) -> None:
        client = _MockClient()
        client.seed["thesis_vehicles"] = [
            {
                "ticker": "CPER",
                "thesis_id": "mat-growth",
                "candidate_rank": 2,
                "date": "2026-06-12",
            },
            {
                "ticker": "CPER",
                "thesis_id": "mat-inflation",
                "candidate_rank": 1,
                "date": "2026-06-12",
            },
        ]
        got = resolve_primary_market_thesis(client, ticker="CPER", run_date=_RUN_DATE)  # type: ignore[arg-type]
        assert got == "mat-inflation"

    def test_tie_breaks_lexically(self) -> None:
        client = _MockClient()
        client.seed["thesis_vehicles"] = [
            {"ticker": "XLB", "thesis_id": "zeta", "candidate_rank": 1, "date": "2026-06-12"},
            {"ticker": "XLB", "thesis_id": "alpha", "candidate_rank": 1, "date": "2026-06-12"},
        ]
        got = resolve_primary_market_thesis(client, ticker="XLB", run_date=_RUN_DATE)  # type: ignore[arg-type]
        assert got == "alpha"

    def test_falls_back_to_most_recent_prior_mapping(self) -> None:
        client = _MockClient()
        client.seed["thesis_vehicles"] = [
            {"ticker": "TLT", "thesis_id": "old-view", "candidate_rank": 1, "date": "2026-05-01"},
            {
                "ticker": "TLT",
                "thesis_id": "recent-view",
                "candidate_rank": 1,
                "date": "2026-06-10",
            },
        ]
        # run_date 06-12 has no mapping; must pick the newest date <= run_date.
        got = resolve_primary_market_thesis(client, ticker="TLT", run_date=_RUN_DATE)  # type: ignore[arg-type]
        assert got == "recent-view"

    def test_ignores_future_mappings(self) -> None:
        client = _MockClient()
        client.seed["thesis_vehicles"] = [
            {"ticker": "SPY", "thesis_id": "future", "candidate_rank": 1, "date": "2026-07-01"},
        ]
        got = resolve_primary_market_thesis(client, ticker="SPY", run_date=_RUN_DATE)  # type: ignore[arg-type]
        assert got is None

    def test_returns_none_when_unmapped(self) -> None:
        client = _MockClient()
        got = resolve_primary_market_thesis(client, ticker="ZZZ", run_date=_RUN_DATE)  # type: ignore[arg-type]
        assert got is None


class TestUpsertVehicleThesisLinking:
    def test_resolves_link_from_thesis_vehicles_when_caller_gives_none(self) -> None:
        client = _MockClient()
        client.seed["thesis_vehicles"] = [
            {
                "ticker": "XLE",
                "thesis_id": "energy-supercycle",
                "candidate_rank": 1,
                "date": "2026-06-12",
            },
        ]
        upsert_vehicle_thesis_from_analyst(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            ticker="XLE",
            analyst_payload={"thesis": "structural tightness"},
        )
        rows = client.store["theses"]
        assert len(rows) == 1
        assert rows[0]["thesis_id"] == "vehicle-xle"
        assert rows[0]["linked_market_thesis_id"] == "energy-supercycle"

    def test_explicit_valid_link_is_honored(self) -> None:
        client = _MockClient()
        upsert_vehicle_thesis_from_analyst(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            ticker="NVDA",
            analyst_payload={"thesis": "AI boom", "risks": "rate spike"},
            linked_market_thesis_id="ai-capex",
        )
        rows = client.store["theses"]
        assert rows[0].get("linked_market_thesis_id") == "ai-capex"

    def test_never_writes_a_self_reference(self) -> None:
        # Caller passes the vehicle's own id (the legacy self-ref shape); with no
        # thesis_vehicles mapping to resolve, the link must be dropped, not stored.
        client = _MockClient()
        upsert_vehicle_thesis_from_analyst(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            ticker="AMZN",
            analyst_payload={"thesis": "cloud re-acceleration"},
            linked_market_thesis_id="vehicle-amzn",
        )
        rows = client.store["theses"]
        assert not rows[0].get("linked_market_thesis_id")

    def test_self_ref_caller_still_resolves_real_link_from_map(self) -> None:
        # A self-ref from the caller must not block resolution from thesis_vehicles.
        client = _MockClient()
        client.seed["thesis_vehicles"] = [
            {
                "ticker": "GLD",
                "thesis_id": "real-gold-view",
                "candidate_rank": 1,
                "date": "2026-06-12",
            },
        ]
        upsert_vehicle_thesis_from_analyst(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            ticker="GLD",
            analyst_payload={"thesis": "debasement hedge"},
            linked_market_thesis_id="vehicle-gld",
        )
        rows = client.store["theses"]
        assert rows[0]["linked_market_thesis_id"] == "real-gold-view"

    def test_unmapped_ticker_stays_null(self) -> None:
        client = _MockClient()
        upsert_vehicle_thesis_from_analyst(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            ticker="AMZN",
            analyst_payload={"thesis": "cloud re-acceleration"},
        )
        rows = client.store["theses"]
        assert not rows[0].get("linked_market_thesis_id")

    def test_self_healing_relink_on_next_run(self) -> None:
        # Day 1: no mapping → null link. Day 2: mapping present → link resolves.
        client = _MockClient()
        upsert_vehicle_thesis_from_analyst(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            ticker="EWT",
            analyst_payload={"thesis": "Taiwan tech"},
        )
        assert not client.store["theses"][0].get("linked_market_thesis_id")
        client.seed["thesis_vehicles"] = [
            {"ticker": "EWT", "thesis_id": "asia-tech", "candidate_rank": 1, "date": "2026-06-13"},
        ]
        upsert_vehicle_thesis_from_analyst(
            client,  # type: ignore[arg-type]
            run_date=date(2026, 6, 13),
            ticker="EWT",
            analyst_payload={"thesis": "Taiwan tech"},
        )
        assert client.store["theses"][1]["linked_market_thesis_id"] == "asia-tech"


class TestUpsertThesisRowSelfRefGuard:
    def test_self_reference_is_dropped(self) -> None:
        client = _MockClient()
        upsert_thesis_row(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            thesis_id="vehicle-xlf",
            name="XLF vehicle thesis",
            status="ACTIVE",
            thesis_kind="vehicle",
            linked_market_thesis_id="vehicle-xlf",
        )
        rows = client.store["theses"]
        assert "linked_market_thesis_id" not in rows[0]

    def test_real_link_is_kept(self) -> None:
        client = _MockClient()
        upsert_thesis_row(
            client,  # type: ignore[arg-type]
            run_date=_RUN_DATE,
            thesis_id="vehicle-xlf",
            name="XLF vehicle thesis",
            status="ACTIVE",
            thesis_kind="vehicle",
            linked_market_thesis_id="financials-steepener",
        )
        rows = client.store["theses"]
        assert rows[0]["linked_market_thesis_id"] == "financials-steepener"
