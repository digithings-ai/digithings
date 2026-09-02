"""Unit tests for digiquant.research.phases.preflight."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from digiquant.data.prices import refresh as refresh_mod
from digiquant.research.phases.preflight import PreflightDeps, build_preflight_node
from digiquant.research.state import ResearchConfigBundle, ResearchState

from tests.dq.research.test_supabase_io import FakeSupabaseClient


@pytest.mark.unit
class TestPreflight:
    def _client_with_fresh_data(self, latest: date) -> FakeSupabaseClient:
        return FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [
                    {"date": latest.isoformat(), "ticker": "SPY"},
                    {"date": latest.isoformat(), "ticker": "QQQ"},
                ],
                "macro_series_observations": [
                    {"obs_date": latest.isoformat()},
                ],
            }
        )

    def test_baseline_run_happy_path(self) -> None:
        run_date = date(2026, 4, 26)
        client = self._client_with_fresh_data(date(2026, 4, 25))
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(watchlist=["SPY", "QQQ"]),
        )
        node = build_preflight_node(deps)
        state = ResearchState(run_type="baseline", run_date=run_date)

        out = node(state)

        assert out["config"].watchlist == ["SPY", "QQQ"]
        # Fresh data → supabase is source of truth (not fallback).
        assert out["data_layer"].fallback_used == "supabase"
        assert out["data_layer"].price_technicals_latest == date(2026, 4, 25)
        assert out["data_layer"].macro_series_latest == date(2026, 4, 25)

    def test_daily_cadence_delta_without_baseline_date_succeeds(self) -> None:
        client = self._client_with_fresh_data(date(2026, 4, 25))
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(),
        )
        node = build_preflight_node(deps)
        state = ResearchState(run_type="delta", run_date=date(2026, 4, 27))
        out = node(state)
        assert "config" in out

    def test_stale_price_technicals_signals_scripts_fallback(self) -> None:
        run_date = date(2026, 4, 26)
        # Latest 6 days old — beyond the default 3-day staleness threshold.
        client = self._client_with_fresh_data(date(2026, 4, 20))
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(),
            price_staleness_days=3,
        )
        node = build_preflight_node(deps)
        state = ResearchState(run_type="baseline", run_date=run_date)
        out = node(state)
        assert out["data_layer"].fallback_used == "scripts"

    def _stale_deps(self) -> tuple[FakeSupabaseClient, PreflightDeps]:
        client = self._client_with_fresh_data(date(2026, 4, 20))  # 6 days stale
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(watchlist=["SPY"]),
            price_staleness_days=3,
        )
        return client, deps

    def test_on_demand_refresh_off_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Without ATLAS_REFRESH_ON_DEMAND the stale signal stands and no recompute is attempted.
        monkeypatch.delenv("ATLAS_REFRESH_ON_DEMAND", raising=False)
        _client, deps = self._stale_deps()
        with patch.object(refresh_mod, "recompute_technicals_from_history") as recompute:
            out = build_preflight_node(deps)(
                ResearchState(run_type="baseline", run_date=date(2026, 4, 26))
            )
        recompute.assert_not_called()
        assert out["data_layer"].fallback_used == "scripts"

    def test_on_demand_refresh_clears_fallback_when_now_fresh(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_REFRESH_ON_DEMAND", "1")
        client, deps = self._stale_deps()
        run_date = date(2026, 4, 26)

        def _fake_recompute(*, client, tickers, as_of):
            # Simulate the upsert: the table is now fresh on the re-probe.
            client.canned_reads["price_technicals"] = [{"date": as_of.isoformat(), "ticker": "SPY"}]
            return SimpleNamespace(tickers_processed=1, rows_upserted=12)

        with patch.object(
            refresh_mod, "recompute_technicals_from_history", side_effect=_fake_recompute
        ):
            out = build_preflight_node(deps)(ResearchState(run_type="baseline", run_date=run_date))
        # Refresh brought it current → fallback cleared back to supabase.
        assert out["data_layer"].fallback_used == "supabase"
        assert out["data_layer"].price_technicals_latest == run_date

    def test_on_demand_refresh_is_fail_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_REFRESH_ON_DEMAND", "1")
        _client, deps = self._stale_deps()
        with patch.object(
            refresh_mod,
            "recompute_technicals_from_history",
            side_effect=RuntimeError("supabase down"),
        ):
            out = build_preflight_node(deps)(
                ResearchState(run_type="baseline", run_date=date(2026, 4, 26))
            )
        # Refresh failed → keep the stale data + the scripts signal (never crashes preflight).
        assert out["data_layer"].fallback_used == "scripts"

    def test_missing_price_technicals_signals_no_source(self) -> None:
        run_date = date(2026, 4, 26)
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [],
                "macro_series_observations": [],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(),
        )
        node = build_preflight_node(deps)
        state = ResearchState(run_type="baseline", run_date=run_date)
        out = node(state)
        assert out["data_layer"].fallback_used == "none"
        assert out["data_layer"].price_technicals_latest is None

    def test_preflight_hydrates_current_weights_from_prior_book(self) -> None:
        run_date = date(2026, 6, 19)
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [{"date": "2026-06-18", "ticker": "SPY"}],
                "macro_series_observations": [{"obs_date": "2026-06-18"}],
                "positions": [
                    {"date": "2026-06-18", "ticker": "SHY", "weight_pct": 30},
                    {"date": "2026-06-18", "ticker": "CASH", "weight_pct": 70},
                ],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(watchlist=["SPY"]),
        )
        out = build_preflight_node(deps)(
            ResearchState(run_type="delta", run_date=run_date, baseline_date=date(2026, 6, 17))
        )
        assert out["config"].preferences["current_weights"] == {"SHY": 30.0, "CASH": 70.0}
        assert out["prior_context"].prior_book[0]["ticker"] == "SHY"

    def test_preflight_marks_current_weights_to_market(self) -> None:
        # #955: with price history showing SHY +10% since the last run, the hydrated
        # current_weights must reflect the drifted book, not the raw prior 30/70.
        run_date = date(2026, 6, 19)
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [{"date": "2026-06-18", "ticker": "SHY"}],
                "macro_series_observations": [{"obs_date": "2026-06-18"}],
                "positions": [
                    {"date": "2026-06-18", "ticker": "SHY", "weight_pct": 30},
                    {"date": "2026-06-18", "ticker": "CASH", "weight_pct": 70},
                ],
                "price_history": [
                    {"date": "2026-06-17", "ticker": "SHY", "close": 100.0},
                    {"date": "2026-06-18", "ticker": "SHY", "close": 110.0},  # +10%
                ],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(watchlist=["SHY"]),
        )
        out = build_preflight_node(deps)(
            ResearchState(run_type="delta", run_date=run_date, baseline_date=date(2026, 6, 17))
        )
        weights = out["config"].preferences["current_weights"]
        # SHY value 30*1.10=33 vs CASH 70, NAV 103 → SHY ~32.04%, CASH ~67.96%.
        assert weights["SHY"] == pytest.approx(33.0 / 103.0 * 100.0, abs=1e-2)
        assert weights["CASH"] == pytest.approx(70.0 / 103.0 * 100.0, abs=1e-2)
        assert weights["SHY"] > 30.0  # drifted up from the raw prior weight

    def test_preflight_loads_continuity_sidecars(self) -> None:
        run_date = date(2026, 6, 19)
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [
                    {
                        "date": "2026-06-18",
                        "document_key": "analyst/SHY",
                        "payload": {"stance": "hold", "conviction_score": 2, "thesis": "Hold SHY."},
                    }
                ],
                "price_technicals": [{"date": "2026-06-18", "ticker": "SPY"}],
                "macro_series_observations": [{"obs_date": "2026-06-18"}],
                "positions": [
                    {"date": "2026-06-18", "ticker": "SHY", "weight_pct": 30},
                    {"date": "2026-06-18", "ticker": "CASH", "weight_pct": 70},
                ],
                "theses": [
                    {
                        "date": "2026-06-18",
                        "thesis_id": "shy-duration",
                        "name": "Duration",
                        "status": "ACTIVE",
                    }
                ],
                "nav_history": [
                    {"date": "2026-06-18", "nav": 101.0, "cash_pct": 70, "invested_pct": 30}
                ],
                "portfolio_metrics": [{"date": "2026-06-18", "pnl_pct": 1.0, "sharpe": 0.9}],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(watchlist=["SPY"]),
        )
        out = build_preflight_node(deps)(
            ResearchState(run_type="delta", run_date=run_date, baseline_date=date(2026, 6, 17))
        )
        pc = out["prior_context"]
        assert pc.prior_analyst_by_ticker["SHY"]["stance"] == "hold"
        assert pc.active_theses[0]["thesis_id"] == "shy-duration"
        assert pc.portfolio_performance["nav"] == 101.0

    def test_preflight_first_run_has_no_current_weights(self) -> None:
        run_date = date(2026, 6, 17)
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [{"date": "2026-06-16", "ticker": "SPY"}],
                "macro_series_observations": [{"obs_date": "2026-06-16"}],
                "positions": [],
            }
        )
        deps = PreflightDeps(client=client, config_loader=lambda: ResearchConfigBundle())
        out = build_preflight_node(deps)(ResearchState(run_type="baseline", run_date=run_date))
        assert "current_weights" not in out["config"].preferences
        assert out["prior_context"].prior_book == []


@pytest.mark.unit
class TestPreflightDataStarvation:
    """Data-layer starvation detection (#946).

    Three deterministic flags surfaced on ``DataLayerSnapshot``:
    (a) ``price_basket_gap`` — expected basket tickers with zero rows;
    (b) ``stale_price`` — price_technicals >2 business days stale;
    (c) ``stale_macro`` — macro_series >2 business days stale.
    """

    def _run(
        self,
        *,
        run_date: date,
        pt_rows: list[dict],
        macro_rows: list[dict],
    ) -> dict:
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": pt_rows,
                "macro_series_observations": macro_rows,
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(watchlist=["SPY", "QQQ"]),
        )
        return build_preflight_node(deps)(ResearchState(run_type="baseline", run_date=run_date))

    # ── (a) price_basket_gap ──────────────────────────────────────────────

    def test_empty_price_technicals_flags_all_basket_tickers(self) -> None:
        """When price_technicals returns zero rows, every expected basket ticker
        must appear in ``price_basket_gap``."""
        out = self._run(
            run_date=date(2026, 6, 20),
            pt_rows=[],
            macro_rows=[{"obs_date": "2026-06-19"}],
        )
        gap = out["data_layer"].price_basket_gap
        # At minimum the core market tickers should be flagged.
        assert len(gap) > 0
        assert "SPY" in gap
        assert "QQQ" in gap

    def test_full_coverage_has_no_basket_gap(self) -> None:
        """When every expected basket ticker has at least one row, gap is empty."""
        from digiquant.research.phases.preflight import _market_context_tickers

        tickers = _market_context_tickers()
        pt_rows = [{"date": "2026-06-19", "ticker": t} for t in tickers]
        out = self._run(
            run_date=date(2026, 6, 20),
            pt_rows=pt_rows,
            macro_rows=[{"obs_date": "2026-06-19"}],
        )
        assert out["data_layer"].price_basket_gap == []

    def test_partial_coverage_flags_missing_tickers(self) -> None:
        """Some basket tickers present, others missing — only missing ones flagged."""
        out = self._run(
            run_date=date(2026, 6, 20),
            pt_rows=[
                {"date": "2026-06-19", "ticker": "SPY"},
                {"date": "2026-06-19", "ticker": "QQQ"},
            ],
            macro_rows=[{"obs_date": "2026-06-19"}],
        )
        gap = out["data_layer"].price_basket_gap
        # SPY and QQQ present, so they should NOT be in the gap.
        assert "SPY" not in gap
        assert "QQQ" not in gap
        # But other core tickers like IWM, TLT should be in the gap.
        assert "IWM" in gap
        assert "TLT" in gap

    # ── (b) stale_price ───────────────────────────────────────────────────

    def test_stale_price_fires_when_gt_2_business_days(self) -> None:
        """price_technicals_latest more than 2 business days before run_date
        sets stale_price=True."""
        # run_date is Wednesday 2026-06-17; latest is Friday 2026-06-12.
        # That is 3 business days gap (Mon, Tue, Wed) > 2 → stale.
        out = self._run(
            run_date=date(2026, 6, 17),
            pt_rows=[{"date": "2026-06-12", "ticker": "SPY"}],
            macro_rows=[{"obs_date": "2026-06-16"}],
        )
        assert out["data_layer"].stale_price is True

    def test_fresh_price_within_2_business_days(self) -> None:
        """price_technicals_latest within 2 business days → stale_price=False."""
        # run_date is Wednesday 2026-06-17; latest is Monday 2026-06-15.
        # That is 2 business days gap (Tue, Wed) = 2, not > 2 → not stale.
        out = self._run(
            run_date=date(2026, 6, 17),
            pt_rows=[{"date": "2026-06-15", "ticker": "SPY"}],
            macro_rows=[{"obs_date": "2026-06-16"}],
        )
        assert out["data_layer"].stale_price is False

    def test_stale_price_over_weekend_not_false_alarm(self) -> None:
        """A Monday run_date with Friday latest is 1 business day → not stale."""
        # run_date is Monday 2026-06-15; latest is Friday 2026-06-12.
        # 1 business day gap (Mon) → not stale.
        out = self._run(
            run_date=date(2026, 6, 15),
            pt_rows=[{"date": "2026-06-12", "ticker": "SPY"}],
            macro_rows=[{"obs_date": "2026-06-12"}],
        )
        assert out["data_layer"].stale_price is False

    def test_no_price_data_is_stale(self) -> None:
        """No price_technicals at all → stale_price=True."""
        out = self._run(
            run_date=date(2026, 6, 17),
            pt_rows=[],
            macro_rows=[{"obs_date": "2026-06-16"}],
        )
        assert out["data_layer"].stale_price is True

    # ── (c) stale_macro ───────────────────────────────────────────────────

    def test_stale_macro_fires_when_gt_2_business_days(self) -> None:
        """macro_series_latest more than 2 business days before run_date
        sets stale_macro=True."""
        # Wednesday run_date with previous Friday latest = 3 bdays → stale.
        out = self._run(
            run_date=date(2026, 6, 17),
            pt_rows=[{"date": "2026-06-16", "ticker": "SPY"}],
            macro_rows=[{"obs_date": "2026-06-12"}],
        )
        assert out["data_layer"].stale_macro is True

    def test_fresh_macro_within_2_business_days(self) -> None:
        """macro_series_latest within 2 business days → stale_macro=False."""
        out = self._run(
            run_date=date(2026, 6, 17),
            pt_rows=[{"date": "2026-06-16", "ticker": "SPY"}],
            macro_rows=[{"obs_date": "2026-06-15"}],
        )
        assert out["data_layer"].stale_macro is False

    def test_no_macro_data_is_stale(self) -> None:
        """No macro_series at all → stale_macro=True."""
        out = self._run(
            run_date=date(2026, 6, 17),
            pt_rows=[{"date": "2026-06-16", "ticker": "SPY"}],
            macro_rows=[],
        )
        assert out["data_layer"].stale_macro is True


# ─── WP12.3 research-state pin (#2863) ───────────────────────────────────────


def _seed_research_store():
    """Minimal strict ResearchStateVersion for preflight pin tests."""
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal
    from uuid import UUID

    from digiquant.dashboard.research_retrieval.models import (
        BeliefStatus,
        BeliefVersion,
        EvidenceRecord,
        ResearchStateManifest,
        ResearchStateVersion,
        TypedProvenance,
        belief_content_hash,
        belief_version_id,
        content_digest,
        evidence_content_hash,
        evidence_record_id,
        manifest_content_hash,
        research_state_version_id,
    )
    from digiquant.dashboard.research_retrieval.store import ResearchStateStore

    ts = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)
    prov = TypedProvenance(
        source_run_id="run-wp123",
        attempt_id="1",
        artifact_id="artifact-preflight",
    )
    store = ResearchStateStore()
    e_hash = evidence_content_hash(
        source="ingest:sec_8k",
        authority="edgar",
        summary="Filed 8-K for pin test",
        supersedes_evidence_id=None,
    )
    evidence = EvidenceRecord(
        evidence_id=evidence_record_id(
            source="ingest:sec_8k",
            authority="edgar",
            content_hash=e_hash,
        ),
        content_hash=e_hash,
        source="ingest:sec_8k",
        authority="edgar",
        summary="Filed 8-K for pin test",
        event_time=ts - timedelta(hours=2),
        effective_as_of=ts - timedelta(hours=1),
        known_at=ts - timedelta(minutes=30),
        recorded_at=ts,
        provenance=prov,
        affected_belief_ids=(),
        novelty_of=(),
        contradiction_of=(),
        supersedes_evidence_id=None,
    )
    belief_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    b_hash = belief_content_hash(
        belief_id=belief_id,
        statement="Base case for pin",
        confidence=Decimal("0.5"),
        horizon_sessions=21,
        status=BeliefStatus.ACTIVE,
        supporting_evidence_ids=(evidence.evidence_id,),
        counter_evidence_ids=(),
        invalidation_rules=(),
    )
    belief = BeliefVersion(
        belief_version_id=belief_version_id(
            belief_id=belief_id,
            content_hash=b_hash,
            supersedes_version_id=None,
        ),
        belief_id=belief_id,
        statement="Base case for pin",
        confidence=Decimal("0.5"),
        horizon_sessions=21,
        status=BeliefStatus.ACTIVE,
        supporting_evidence_ids=(evidence.evidence_id,),
        counter_evidence_ids=(),
        invalidation_rules=(),
        supersedes_version_id=None,
        event_time=ts - timedelta(hours=3),
        effective_as_of=ts - timedelta(hours=2),
        known_at=ts - timedelta(minutes=20),
        recorded_at=ts,
        schema_version=1,
        content_hash=b_hash,
        provenance=prov,
    )
    store.append_evidence(evidence)
    store.append_belief(belief)
    manifest = ResearchStateManifest(
        evidence_ids=(evidence.evidence_id,),
        belief_version_ids=(belief.belief_version_id,),
        expected_event_version_ids=(),
        patch_ids=(),
        legacy_ref_ids=(),
        content_hash=manifest_content_hash(
            evidence_ids=(evidence.evidence_id,),
            belief_version_ids=(belief.belief_version_id,),
            expected_event_version_ids=(),
            patch_ids=(),
            legacy_ref_ids=(),
        ),
    )
    v_hash = content_digest(
        {
            "manifest_content_hash": manifest.content_hash,
            "parent_state_version_id": None,
            "schema_version": 1,
        }
    )
    version = ResearchStateVersion(
        state_version_id=research_state_version_id(
            manifest_content_hash=manifest.content_hash,
            parent_id=None,
            schema_version=1,
        ),
        parent_state_version_id=None,
        manifest=manifest,
        event_time=ts - timedelta(hours=1),
        effective_as_of=ts - timedelta(minutes=5),
        known_at=ts,
        recorded_at=ts,
        schema_version=1,
        content_hash=v_hash,
        provenance=prov,
    )
    store.append_state_version(version)
    return store, version, ts


@pytest.mark.unit
class TestResearchStatePreflightPin:
    def test_no_store_yields_typed_state_unavailable(self) -> None:
        from datetime import UTC, datetime

        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [{"date": "2026-04-25", "ticker": "SPY"}],
                "macro_series_observations": [{"obs_date": "2026-04-25"}],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(watchlist=["SPY"]),
            research_state_store=None,
        )
        node = build_preflight_node(deps)
        state = ResearchState(
            run_type="baseline",
            run_date=date(2026, 4, 26),
            knowledge_cutoff_at=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
        )
        out = node(state)
        assert out["research_state_status"] == "state_unavailable"
        assert out["research_state_pin"] is None
        assert "shadow" in (out["research_state_unavailable_reason"] or "").lower()

    def test_cutoff_bound_pin_resume_and_child_lineage(self) -> None:
        from datetime import timedelta
        from decimal import Decimal
        from uuid import UUID

        from digiquant.dashboard.research_retrieval.models import (
            BeliefStatus,
            BeliefVersion,
            EvidenceRecord,
            ResearchStateManifest,
            ResearchStatePin,
            ResearchStateVersion,
            TypedProvenance,
            belief_content_hash,
            belief_version_id,
            content_digest,
            evidence_content_hash,
            evidence_record_id,
            manifest_content_hash,
            research_state_version_id,
        )
        from digiquant.dashboard.research_retrieval.pin import child_version_must_name_parent

        store, root, ts = _seed_research_store()
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [{"date": "2026-04-25", "ticker": "SPY"}],
                "macro_series_observations": [{"obs_date": "2026-04-25"}],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(watchlist=["SPY"]),
            research_state_store=store,
            research_state_attempt_id="attempt-1",
        )
        node = build_preflight_node(deps)
        cutoff = ts + timedelta(minutes=1)
        state = ResearchState(
            run_type="baseline",
            run_date=date(2026, 4, 26),
            knowledge_cutoff_at=cutoff,
        )
        out = node(state)
        assert out["research_state_status"] == "pinned"
        pin = out["research_state_pin"]
        assert pin is not None
        assert pin["state_version_id"] == str(root.state_version_id)
        assert pin["attempt_id"] == "attempt-1"

        # Same-run child must name the pinned root as parent.
        prov = TypedProvenance(
            source_run_id="run-wp123",
            attempt_id="1",
            artifact_id="artifact-preflight",
        )
        e_hash = evidence_content_hash(
            source="ingest:sec_8k",
            authority="edgar",
            summary="Post-pin filing",
            supersedes_evidence_id=None,
        )
        child_evidence = EvidenceRecord(
            evidence_id=evidence_record_id(
                source="ingest:sec_8k",
                authority="edgar",
                content_hash=e_hash,
            ),
            content_hash=e_hash,
            source="ingest:sec_8k",
            authority="edgar",
            summary="Post-pin filing",
            event_time=ts,
            effective_as_of=ts + timedelta(minutes=2),
            known_at=ts + timedelta(minutes=2),
            recorded_at=ts + timedelta(minutes=2),
            provenance=prov,
            affected_belief_ids=(),
            novelty_of=(),
            contradiction_of=(),
            supersedes_evidence_id=None,
        )
        store.append_evidence(child_evidence)
        belief_id = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        b_hash = belief_content_hash(
            belief_id=belief_id,
            statement="Child belief after pin",
            confidence=Decimal("0.4"),
            horizon_sessions=21,
            status=BeliefStatus.ACTIVE,
            supporting_evidence_ids=(child_evidence.evidence_id,),
            counter_evidence_ids=(),
            invalidation_rules=(),
        )
        child_belief = BeliefVersion(
            belief_version_id=belief_version_id(
                belief_id=belief_id,
                content_hash=b_hash,
                supersedes_version_id=None,
            ),
            belief_id=belief_id,
            statement="Child belief after pin",
            confidence=Decimal("0.4"),
            horizon_sessions=21,
            status=BeliefStatus.ACTIVE,
            supporting_evidence_ids=(child_evidence.evidence_id,),
            counter_evidence_ids=(),
            invalidation_rules=(),
            supersedes_version_id=None,
            event_time=ts,
            effective_as_of=ts + timedelta(minutes=2),
            known_at=ts + timedelta(minutes=2),
            recorded_at=ts + timedelta(minutes=2),
            schema_version=1,
            content_hash=b_hash,
            provenance=prov,
        )
        store.append_belief(child_belief)
        child_manifest = ResearchStateManifest(
            evidence_ids=(child_evidence.evidence_id,),
            belief_version_ids=(child_belief.belief_version_id,),
            expected_event_version_ids=(),
            patch_ids=(),
            legacy_ref_ids=(),
            content_hash=manifest_content_hash(
                evidence_ids=(child_evidence.evidence_id,),
                belief_version_ids=(child_belief.belief_version_id,),
                expected_event_version_ids=(),
                patch_ids=(),
                legacy_ref_ids=(),
            ),
        )
        child_hash = content_digest(
            {
                "manifest_content_hash": child_manifest.content_hash,
                "parent_state_version_id": root.state_version_id.hex,
                "schema_version": 1,
            }
        )
        child = ResearchStateVersion(
            state_version_id=research_state_version_id(
                manifest_content_hash=child_manifest.content_hash,
                parent_id=root.state_version_id,
                schema_version=1,
            ),
            parent_state_version_id=root.state_version_id,
            manifest=child_manifest,
            event_time=ts,
            effective_as_of=ts + timedelta(minutes=2),
            known_at=ts + timedelta(minutes=2),
            recorded_at=ts + timedelta(minutes=2),
            schema_version=1,
            content_hash=child_hash,
            provenance=prov,
        )
        pinned = ResearchStatePin.model_validate(pin)
        child_version_must_name_parent(pinned=pinned, child=child)
        store.append_state_version(child)

        # Resume: checkpoint dump kept; store pin still the root (no re-select).
        resume_state = ResearchState(
            run_type="baseline",
            run_date=date(2026, 4, 26),
            knowledge_cutoff_at=cutoff,
            research_state_pin=pin,
            research_state_status="pinned",
        )
        resume_out = node(resume_state)
        assert "research_state_pin" not in resume_out
        stored = store.get_pin(run_id=str(state.run_id), attempt_id="attempt-1")
        assert stored is not None
        assert stored.state_version_id == root.state_version_id
        loaded_root = store.load_state_version(root.state_version_id)
        loaded_child = store.load_state_version(child.state_version_id)
        assert loaded_root.version.parent_state_version_id is None
        assert loaded_child.version.parent_state_version_id == root.state_version_id

    def test_explicit_missing_version_is_state_unavailable(self) -> None:
        from datetime import UTC, datetime
        from uuid import uuid4

        store, _root, _ts = _seed_research_store()
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [{"date": "2026-04-25", "ticker": "SPY"}],
                "macro_series_observations": [{"obs_date": "2026-04-25"}],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(),
            research_state_store=store,
            research_state_attempt_id="1",
        )
        node = build_preflight_node(deps)
        missing = uuid4()
        out = node(
            ResearchState(
                run_type="baseline",
                run_date=date(2026, 4, 26),
                knowledge_cutoff_at=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
                requested_research_state_version_id=str(missing),
            )
        )
        assert out["research_state_status"] == "state_unavailable"
        assert out["research_state_pin"] is None
        assert str(missing) in (out["research_state_unavailable_reason"] or "")

    def test_explicit_version_pins_exact_id(self) -> None:
        from datetime import timedelta

        store, root, ts = _seed_research_store()
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [{"date": "2026-04-25", "ticker": "SPY"}],
                "macro_series_observations": [{"obs_date": "2026-04-25"}],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(),
            research_state_store=store,
            research_state_attempt_id="2",
        )
        node = build_preflight_node(deps)
        out = node(
            ResearchState(
                run_type="baseline",
                run_date=date(2026, 4, 26),
                knowledge_cutoff_at=ts + timedelta(minutes=1),
                requested_research_state_version_id=str(root.state_version_id),
            )
        )
        assert out["research_state_status"] == "pinned"
        assert out["research_state_pin"]["state_version_id"] == str(root.state_version_id)

    def test_pin_fail_closed_on_effective_as_of_after_requested(self) -> None:
        """WP12.2 hardenings (#2867): store pin reject → typed state_unavailable."""
        from datetime import timedelta

        from digiquant.dashboard.research_retrieval.pin import pin_research_state_for_preflight

        store, root, ts = _seed_research_store()
        # Preflight defaults requested_as_of to cutoff; exercise the WP12.3 helper
        # with an earlier as-of so effective_as_of > requested_as_of while known_at
        # still clears the cutoff envelope (same shape as store unit coverage).
        result = pin_research_state_for_preflight(
            store=store,
            run_id="run-fail-closed-eff",
            attempt_id="1",
            knowledge_cutoff_at=ts + timedelta(hours=1),
            requested_as_of=ts - timedelta(hours=1),
            explicit_state_version_id=root.state_version_id,
            pinned_at=ts + timedelta(hours=1),
        )
        assert result.status == "state_unavailable"
        assert result.pin is None
        reason = (result.unavailable_reason or "").lower()
        assert "effective_as_of" in reason and "requested_as_of" in reason

    def test_pin_fail_closed_on_look_ahead_child(self) -> None:
        """WP12.2 hardenings (#2867): drifted future-known child → state_unavailable."""
        from datetime import timedelta

        from digiquant.dashboard.research_retrieval.models import EvidenceRecord

        store, root, ts = _seed_research_store()
        # Simulate durable drift: evidence known_at moves past cutoff after append.
        early = store._evidence[next(iter(store._evidence))]
        drifted = EvidenceRecord.model_construct(**early.model_dump())
        object.__setattr__(drifted, "known_at", ts + timedelta(hours=3))
        store._evidence[early.evidence_id] = drifted

        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [{"date": "2026-04-25", "ticker": "SPY"}],
                "macro_series_observations": [{"obs_date": "2026-04-25"}],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: ResearchConfigBundle(),
            research_state_store=store,
            research_state_attempt_id="fail-closed-child",
        )
        node = build_preflight_node(deps)
        out = node(
            ResearchState(
                run_type="baseline",
                run_date=date(2026, 4, 26),
                knowledge_cutoff_at=ts + timedelta(hours=2),
                requested_research_state_version_id=str(root.state_version_id),
            )
        )
        assert out["research_state_status"] == "state_unavailable"
        assert out["research_state_pin"] is None
        reason = (out["research_state_unavailable_reason"] or "").lower()
        assert "evidence" in reason and "knowledge_cutoff" in reason
