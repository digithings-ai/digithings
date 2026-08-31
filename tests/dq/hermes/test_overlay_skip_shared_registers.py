"""Overlay must not last-writer-win house theses / analyst / vehicle / decision_log / onchain.

Those tables have no ``workspace_id`` column. Overlay persist-on is not a
license to upsert them.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from digiquant.olympus.atlas.decision_log import (
    ReflectorOutput,
    persist_pending,
    resolve_pending,
)
from digiquant.olympus.atlas.phases.preflight import (
    PreflightDeps,
    PreflightReflectDeps,
    build_preflight_node,
    build_preflight_reflect_node,
)
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState, PhaseHermesState
from digiquant.olympus.atlas.supabase_io import upsert_onchain_cohort_positioning
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


def _analyst_state(*, workspace_id: str | None) -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="delta",
        run_date=_RUN,
        config=AtlasConfigBundle(workspace_id=workspace_id),
    )
    state.phase_hermes = PhaseHermesState(
        asset_analysts={
            "SPY": {
                "ticker": "SPY",
                "conviction_score": 3,
                "stance": "buy",
                "thesis": "overlay must not smash house",
                "risks": "",
                "sources": [],
            }
        }
    )
    return state


def test_overlay_persist_on_does_not_write_decision_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    overlay_client = FakeSupabaseClient()
    overlay_count = persist_pending(
        client=overlay_client,
        state=_analyst_state(workspace_id=str(overlay)),
    )
    assert overlay_count == 0
    assert overlay_client.store.get("decision_log", []) == []

    house_client = FakeSupabaseClient()
    house_count = persist_pending(
        client=house_client,
        state=_analyst_state(workspace_id=str(house_workspace_id())),
    )
    omitted = FakeSupabaseClient()
    omitted_count = persist_pending(client=omitted, state=_analyst_state(workspace_id=None))
    assert house_count == 1
    assert omitted_count == 1
    assert [r["ticker"] for r in house_client.store["decision_log"]] == ["SPY"]
    assert [r["ticker"] for r in omitted.store["decision_log"]] == ["SPY"]


def test_overlay_resolve_pending_does_not_stamp_house_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    pending = {
        "id": "row-house",
        "run_id": "house-run",
        "run_date": "2026-08-20",
        "ticker": "SPY",
        "stance": "buy",
        "conviction": 3,
        "thesis": "t",
        "benchmark": "SPY",
        "holding_days": 1,
        "status": "pending",
    }
    overlay_client = FakeSupabaseClient(canned_reads={"decision_log": [pending]})
    overlay_client.store["decision_log"] = [dict(pending)]
    called: list[object] = []

    def reflector(_inputs: dict[str, object]) -> ReflectorOutput:
        called.append(_inputs)
        raise AssertionError("overlay must not invoke the house reflector")

    resolved = resolve_pending(
        client=overlay_client,
        run_date=_RUN,
        reflector=reflector,
        workspace_id=str(overlay),
    )
    assert resolved == 0
    assert called == []
    assert overlay_client.store["decision_log"][0]["status"] == "pending"


def test_overlay_preflight_reflect_skips_decision_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    calls: list[str] = []

    def fake_resolve_pending(**_kwargs: object) -> int:
        calls.append("decision_log")
        return 0

    monkeypatch.setattr(
        "digiquant.olympus.atlas.phases.preflight.resolve_pending",
        fake_resolve_pending,
    )
    node = build_preflight_reflect_node(PreflightReflectDeps(client=FakeSupabaseClient()))
    overlay_state = AtlasResearchState(
        run_type="delta",
        run_date=_RUN,
        config=AtlasConfigBundle(workspace_id=str(overlay)),
    )
    assert node(overlay_state) == {}
    assert calls == []

    house_state = AtlasResearchState(
        run_type="delta",
        run_date=_RUN,
        config=AtlasConfigBundle(workspace_id=str(house_workspace_id())),
    )
    assert node(house_state) == {}
    assert calls == ["decision_log"]


def test_overlay_persist_on_does_not_write_onchain_cohort_positioning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    row = {"date": "2026-08-30", "market": "ETH", "divergence": -0.8}
    overlay_client = FakeSupabaseClient()
    overlay_written = upsert_onchain_cohort_positioning(
        client=overlay_client,
        rows=[row],
        workspace_id=overlay,
    )
    assert overlay_written == 0
    assert overlay_client.store.get("onchain_cohort_positioning", []) == []

    house_client = FakeSupabaseClient()
    house_written = upsert_onchain_cohort_positioning(
        client=house_client,
        rows=[row],
        workspace_id=house_workspace_id(),
    )
    omitted = FakeSupabaseClient()
    omitted_written = upsert_onchain_cohort_positioning(client=omitted, rows=[row])
    assert house_written == 1
    assert omitted_written == 1
    assert [r["market"] for r in house_client.store["onchain_cohort_positioning"]] == ["ETH"]
    assert [r["market"] for r in omitted.store["onchain_cohort_positioning"]] == ["ETH"]


def test_overlay_preflight_injects_onchain_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import patch

    from digiquant.data.onchain.hyperdash import cohort_summary_to_positioning

    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    summary = {
        "timestamp": "2026-08-30T00:00:00Z",
        "totalTraders": 999,
        "pnlCohorts": [
            {
                "id": "extremely_profitable",
                "longNotional": 1_000_000,
                "shortNotional": 4_000_000,
                "topMarkets": [
                    {"ticker": "ETH", "longNotional": 100_000, "shortNotional": 900_000}
                ],
            },
            {
                "id": "rekt",
                "longNotional": 5_000_000,
                "shortNotional": 1_000_000,
                "topMarkets": [
                    {"ticker": "ETH", "longNotional": 900_000, "shortNotional": 100_000}
                ],
            },
        ],
    }
    overlay_client = FakeSupabaseClient(
        canned_reads={
            "daily_snapshots": [],
            "documents": [],
            "price_technicals": [{"date": "2026-08-30", "ticker": "SPY"}],
            "macro_series_observations": [],
        }
    )
    deps = PreflightDeps(
        client=overlay_client,
        config_loader=lambda: AtlasConfigBundle(workspace_id=str(overlay)),
    )
    node = build_preflight_node(deps)
    overlay_state = AtlasResearchState(
        run_type="delta",
        run_date=_RUN,
        config=AtlasConfigBundle(workspace_id=str(overlay)),
    )
    with patch(
        "digiquant.olympus.atlas.phases.preflight.get_onchain_cohort_positioning",
        lambda: cohort_summary_to_positioning(summary),
    ):
        out = node(overlay_state)
    assert "onchain_positioning" in out["data_layer"].market_context
    assert overlay_client.store.get("onchain_cohort_positioning", []) == []
