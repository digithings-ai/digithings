"""Overlay must not last-writer-win house theses / analyst / vehicle registers.

``theses``, ``analyst_coverage``, and ``thesis_vehicles`` have no
``workspace_id`` column. Overlay persist-on is not a license to upsert them.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState
from digiquant.olympus.hermes.models.thesis import (
    ThesisReviewOutput,
    ThesisStatusUpdate,
    ThesisVehicleMapOutput,
    ThesisVehicleMapping,
)
from digiquant.olympus.hermes.portfolio_materialize import MaterializeDeps, build_materialize_node
from digiquant.olympus.hermes.writers.analyst_io import upsert_analyst_coverage
from digiquant.olympus.hermes.writers.thesis_io import (
    persist_thesis_review,
    persist_thesis_vehicle_map,
    upsert_thesis_row,
    upsert_thesis_vehicles,
)
from digiquant.olympus.overlay.persist import skip_overlay_shared_register
from digiquant.olympus.tenancy import house_workspace_id

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

_RUN = date(2026, 8, 30)


def test_skip_overlay_shared_register_private_only() -> None:
    overlay = uuid4()
    assert skip_overlay_shared_register(overlay) is True
    assert skip_overlay_shared_register(None) is False
    assert skip_overlay_shared_register(house_workspace_id()) is False


def test_overlay_persist_on_does_not_write_theses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    overlay_client = FakeSupabaseClient()
    upsert_thesis_row(
        overlay_client,
        run_date=_RUN,
        thesis_id="ai-capex",
        name="AI capex",
        status="ACTIVE",
        workspace_id=overlay,
    )
    assert overlay_client.store.get("theses", []) == []

    house_client = FakeSupabaseClient()
    upsert_thesis_row(
        house_client,
        run_date=_RUN,
        thesis_id="ai-capex",
        name="AI capex",
        status="ACTIVE",
        workspace_id=house_workspace_id(),
    )
    omitted = FakeSupabaseClient()
    upsert_thesis_row(
        omitted,
        run_date=_RUN,
        thesis_id="ai-capex",
        name="AI capex",
        status="ACTIVE",
    )
    assert [r["thesis_id"] for r in house_client.store["theses"]] == ["ai-capex"]
    assert [r["thesis_id"] for r in omitted.store["theses"]] == ["ai-capex"]


def test_overlay_persist_on_does_not_write_analyst_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    overlay_client = FakeSupabaseClient()
    upsert_analyst_coverage(
        overlay_client,
        run_date=_RUN,
        ticker="NVDA",
        document_key="analyst/nvda",
        workspace_id=overlay,
    )
    assert overlay_client.store.get("analyst_coverage", []) == []

    house_client = FakeSupabaseClient()
    upsert_analyst_coverage(
        house_client,
        run_date=_RUN,
        ticker="NVDA",
        document_key="analyst/nvda",
        workspace_id=house_workspace_id(),
    )
    assert [r["ticker"] for r in house_client.store["analyst_coverage"]] == ["NVDA"]


def test_overlay_persist_on_does_not_write_thesis_vehicles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    overlay_client = FakeSupabaseClient()
    written = upsert_thesis_vehicles(
        overlay_client,
        run_date=_RUN,
        thesis_id="ai-capex",
        tickers=["NVDA"],
        workspace_id=overlay,
    )
    assert written == 0
    assert overlay_client.store.get("thesis_vehicles", []) == []
    assert overlay_client.store.get("theses", []) == []

    house_client = FakeSupabaseClient()
    house_written = upsert_thesis_vehicles(
        house_client,
        run_date=_RUN,
        thesis_id="ai-capex",
        tickers=["NVDA"],
        workspace_id=house_workspace_id(),
    )
    assert house_written == 1
    assert [r["ticker"] for r in house_client.store["thesis_vehicles"]] == ["NVDA"]


def test_overlay_persist_thesis_review_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    review = ThesisReviewOutput(
        reviewed_theses=[
            ThesisStatusUpdate(thesis_id="ai-capex", new_status="MONITORING"),
        ]
    )
    overlay_client = FakeSupabaseClient()
    count = persist_thesis_review(
        overlay_client,
        run_date=_RUN,
        review=review,
        active_theses=[{"thesis_id": "ai-capex", "name": "AI capex", "status": "ACTIVE"}],
        workspace_id=overlay,
    )
    assert count == 0
    assert overlay_client.store.get("theses", []) == []

    house_client = FakeSupabaseClient()
    house_count = persist_thesis_review(
        house_client,
        run_date=_RUN,
        review=review,
        active_theses=[{"thesis_id": "ai-capex", "name": "AI capex", "status": "ACTIVE"}],
        workspace_id=house_workspace_id(),
    )
    assert house_count == 1
    assert house_client.store["theses"][0]["status"] == "MONITORING"


def test_overlay_persist_vehicle_map_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    vehicle_map = ThesisVehicleMapOutput(
        mappings=[
            ThesisVehicleMapping(thesis_id="ai-capex", candidate_tickers=["NVDA"]),
        ]
    )
    overlay_client = FakeSupabaseClient()
    count = persist_thesis_vehicle_map(
        overlay_client,
        run_date=_RUN,
        vehicle_map=vehicle_map,
        workspace_id=overlay,
    )
    assert count == 0
    assert overlay_client.store.get("thesis_vehicles", []) == []

    house_client = FakeSupabaseClient()
    house_count = persist_thesis_vehicle_map(
        house_client,
        run_date=_RUN,
        vehicle_map=vehicle_map,
        workspace_id=house_workspace_id(),
    )
    assert house_count == 1
    assert house_client.store["thesis_vehicles"][0]["ticker"] == "NVDA"


def test_overlay_materialize_skips_theses_register(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    overlay_client = FakeSupabaseClient()
    overlay_state = AtlasResearchState(
        run_type="delta",
        run_date=_RUN,
        config=AtlasConfigBundle(workspace_id=str(overlay)),
    )
    overlay_state.phase7d_rebalance = {
        "recommended_portfolio": [{"ticker": "SPY", "target_pct": 100}],
        "actions": [],
        "notes": "overlay",
    }
    build_materialize_node(MaterializeDeps(client=overlay_client))(overlay_state)
    assert overlay_client.store.get("theses", []) == []
    assert overlay_client.store.get("thesis_vehicles", []) == []

    house_client = FakeSupabaseClient()
    house_state = AtlasResearchState(
        run_type="delta",
        run_date=_RUN,
        config=AtlasConfigBundle(workspace_id=str(house_workspace_id())),
    )
    house_state.phase7d_rebalance = {
        "recommended_portfolio": [{"ticker": "SPY", "target_pct": 100}],
        "actions": [],
        "notes": "house",
    }
    build_materialize_node(MaterializeDeps(client=house_client))(house_state)
    assert [r["thesis_id"] for r in house_client.store["theses"]] == ["spy"]
