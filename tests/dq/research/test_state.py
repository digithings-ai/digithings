"""Unit tests for digiquant.research.state."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from digiquant.dashboard.temporal import (
    KnowledgeCutoffError,
    capture_knowledge_cutoff_at,
    require_knowledge_cutoff_at,
    require_utc_datetime,
)
from digiquant.research.graph import ResearchInput, initial_state
from digiquant.research.state import (
    Carried,
    DataLayerSnapshot,
    DeltaTriageDecision,
    DeltaTriageResult,
    ExcludedTicker,
    FocusRosterEntry,
    PhaseError,
    PhasePortfolioState,
    PriorContext,
    PublishedArtifact,
    ResearchConfigBundle,
    ResearchState,
    SegmentPayload,
    SegmentSlot,
    SegmentSlotCollisionError,
    _merge_phase_portfolio,
    _merge_right_wins_dict,
    _merge_segment_dict,
)
from pydantic import ValidationError


@pytest.mark.unit
class TestMergePhasePortfolio:
    """Reducer for nested ``phase_portfolio`` writes across H4–H9 (#1030)."""

    def test_preserves_focus_roster_excluded_from_right(self) -> None:
        """H4 writes the excluded ledger as the *right* operand; the reducer must
        carry it forward, not drop it to ``left``'s empty default (#1030).

        Before the fix, ``focus_roster_excluded`` was absent from the reducer's
        field list, so the ledger H4 produced was silently lost before H9
        commit-run read it — orphaning gated-out held positions.
        """
        left = PhasePortfolioState()  # prior state, no ledger yet
        right = PhasePortfolioState(  # H4's write
            focus_roster=[FocusRosterEntry(ticker="SPY", roster_reason="held")],
            focus_roster_excluded=[ExcludedTicker(ticker="AAPL", reason="held, quiet")],
        )
        merged = _merge_phase_portfolio(left, right)
        assert [e.ticker for e in merged.focus_roster_excluded] == ["AAPL"]

    def test_later_phase_does_not_clobber_existing_ledger(self) -> None:
        """A downstream phase (right) with no ledger must not wipe H4's ledger (left)."""
        left = PhasePortfolioState(
            focus_roster_excluded=[ExcludedTicker(ticker="AAPL", reason="held, quiet")],
        )
        right = PhasePortfolioState(asset_analysts={"SPY": {"ticker": "SPY"}})
        merged = _merge_phase_portfolio(left, right)
        assert [e.ticker for e in merged.focus_roster_excluded] == ["AAPL"]
        assert "SPY" in merged.asset_analysts


@pytest.mark.unit
class TestSegmentSlot:
    def test_fresh_payload_slot(self) -> None:
        slot = SegmentSlot(
            payload=SegmentPayload(
                segment="macro",
                body={"regime": "slowing_inflation_sticky"},
                as_of=date(2026, 4, 20),
            )
        )
        assert slot.payload.source == "today"
        assert slot.payload.segment == "macro"

    def test_carried_slot(self) -> None:
        slot = SegmentSlot(
            payload=Carried(
                baseline_date=date(2026, 4, 19),
                reason="below_triage_threshold",
            )
        )
        assert slot.payload.source == "carried"
        assert slot.payload.baseline_date == date(2026, 4, 19)

    def test_discriminator_rejects_ambiguous(self) -> None:
        with pytest.raises(ValidationError):
            SegmentSlot.model_validate({"payload": {"source": "bogus"}})

    def test_frozen_slot_cannot_be_mutated(self) -> None:
        slot = SegmentSlot(payload=Carried(baseline_date=date(2026, 4, 19), reason="x"))
        with pytest.raises(ValidationError):
            slot.payload = Carried(baseline_date=date(2026, 4, 20), reason="y")  # type: ignore[misc]


@pytest.mark.unit
class TestFrozenContexts:
    """Config + prior context must be frozen so cache keys stay stable across phases."""

    def test_config_bundle_is_frozen(self) -> None:
        cfg = ResearchConfigBundle(watchlist=["SPY"])
        with pytest.raises(ValidationError):
            cfg.watchlist = ["QQQ"]  # type: ignore[misc]

    def test_prior_context_is_frozen(self) -> None:
        ctx = PriorContext()
        with pytest.raises(ValidationError):
            ctx.last_snapshots = [{"x": 1}]  # type: ignore[misc]


@pytest.mark.unit
class TestTriage:
    def test_triage_decision_tier_validated(self) -> None:
        d = DeltaTriageDecision(
            segment="macro",
            decision="regenerate",
            reason="always mandatory",
            tier="mandatory",
        )
        assert d.decision == "regenerate"

    def test_triage_result_collects_decisions(self) -> None:
        result = DeltaTriageResult(
            evaluated_at=date(2026, 4, 20),
            baseline_date=date(2026, 4, 19),
            decisions=[
                DeltaTriageDecision(
                    segment="bonds",
                    decision="carry",
                    reason="yield_move_under_threshold",
                    tier="high",
                )
            ],
        )
        assert result.decisions[0].decision == "carry"


@pytest.mark.unit
class TestResearchState:
    def test_minimal_state_has_sensible_defaults(self) -> None:
        state = ResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        # A unique run_id is auto-generated.
        assert state.run_id is not None
        # Output slots start empty; triage None until delta run computes one.
        assert state.phase1_outputs == {}
        assert state.triage is None
        assert state.published == []
        assert state.errors == []
        assert isinstance(state.data_layer, DataLayerSnapshot)

    def test_run_type_rejects_invalid(self) -> None:
        with pytest.raises(ValidationError):
            ResearchState(run_type="nonsense", run_date=date(2026, 4, 26))  # type: ignore[arg-type]

    def test_delta_run_requires_caller_to_set_baseline_date(self) -> None:
        """A delta without a baseline is a caller bug; the state model doesn't
        enforce it at the type level — it's enforced by the preflight node.
        This test documents that the *state* allows it but the sub-graph
        must not."""
        state = ResearchState(run_type="delta", run_date=date(2026, 4, 27))
        assert state.baseline_date is None  # preflight will reject

    def test_publish_ledger_append(self) -> None:
        state = ResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        state.published.append(
            PublishedArtifact(
                table="documents",
                document_key="digest/2026-04-26.json",
                row_id="123",
                published_at=date(2026, 4, 26),
            )
        )
        assert len(state.published) == 1
        assert state.published[0].table == "documents"

    def test_errors_ledger_append(self) -> None:
        state = ResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        state.errors.append(
            PhaseError(phase="phase3_macro", node="macro_regime", message="LLM timeout")
        )
        assert state.errors[0].retryable is True


@pytest.mark.unit
class TestMergeSegmentDictReducer:
    """Reducer must fail loud on slug collisions — silent right-wins was the prior bug."""

    def _slot(self, slug: str) -> SegmentSlot:
        return SegmentSlot(payload=SegmentPayload(segment=slug, body={}, as_of=date(2026, 4, 26)))

    def test_disjoint_keys_merge(self) -> None:
        left = {"a": self._slot("a")}
        right = {"b": self._slot("b")}
        out = _merge_segment_dict(left, right)
        assert set(out) == {"a", "b"}

    def test_empty_left_returns_copy_of_right(self) -> None:
        right = {"a": self._slot("a")}
        out = _merge_segment_dict(None, right)
        assert out == right
        assert out is not right  # fresh dict so caller can mutate safely

    def test_empty_right_returns_copy_of_left(self) -> None:
        left = {"a": self._slot("a")}
        out = _merge_segment_dict(left, None)
        assert out == left
        assert out is not left

    def test_colliding_keys_raise(self) -> None:
        left = {"macro": self._slot("macro")}
        right = {"macro": self._slot("macro")}
        with pytest.raises(SegmentSlotCollisionError, match="macro"):
            _merge_segment_dict(left, right)


@pytest.mark.unit
class TestMergeRightWinsDictReducer:
    def test_disjoint_keys_merge(self) -> None:
        left = {"AAPL": {"ticker": "AAPL", "stance": "buy"}}
        right = {"MSFT": {"ticker": "MSFT", "stance": "hold"}}
        out = _merge_right_wins_dict(left, right)
        assert set(out) == {"AAPL", "MSFT"}

    def test_collision_right_wins(self) -> None:
        left = {"AAPL": {"stance": "hold"}}
        right = {"AAPL": {"stance": "buy"}}
        out = _merge_right_wins_dict(left, right)
        assert out["AAPL"]["stance"] == "buy"


@pytest.mark.unit
class TestKnowledgeCutoff:
    """WP4.1 (#2628): one UTC knowledge boundary per run."""

    def test_require_utc_rejects_naive(self) -> None:
        with pytest.raises(ValueError, match="naive"):
            require_utc_datetime(
                datetime(2026, 4, 26, 12, 0, 0),  # noqa: DTZ001 — intentional naive
                field_name="knowledge_cutoff_at",
            )

    def test_require_utc_rejects_non_utc_offset(self) -> None:
        eastern = timezone(timedelta(hours=-4))
        with pytest.raises(ValueError, match="non-UTC"):
            require_utc_datetime(
                datetime(2026, 4, 26, 12, 0, 0, tzinfo=eastern),
                field_name="knowledge_cutoff_at",
            )

    def test_state_rejects_naive_cutoff(self) -> None:
        with pytest.raises(ValidationError):
            ResearchState(
                run_type="baseline",
                run_date=date(2026, 4, 26),
                knowledge_cutoff_at=datetime(2026, 4, 26, 12, 0, 0),  # noqa: DTZ001  # type: ignore[arg-type]
            )

    def test_state_rejects_non_utc_cutoff(self) -> None:
        eastern = timezone(timedelta(hours=-4))
        with pytest.raises(ValidationError, match="UTC"):
            ResearchState(
                run_type="baseline",
                run_date=date(2026, 4, 26),
                knowledge_cutoff_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=eastern),
            )

    def test_initial_state_captures_cutoff_before_construction(self) -> None:
        pinned = datetime(2026, 4, 26, 14, 30, 0, tzinfo=UTC)
        calls: list[str] = []

        def _clock() -> datetime:
            calls.append("clock")
            return pinned

        state = initial_state(
            ResearchInput(run_date=date(2026, 4, 26), watchlist=("AAPL",)),
            clock=_clock,
        )
        assert calls == ["clock"], "cutoff must be captured before ResearchState is built"
        assert state.knowledge_cutoff_at == pinned
        assert require_knowledge_cutoff_at(state) == pinned

    def test_capture_uses_injected_clock(self) -> None:
        pinned = datetime(2026, 8, 25, 16, 0, 0, tzinfo=UTC)
        assert capture_knowledge_cutoff_at(now=lambda: pinned) == pinned

    def test_missing_cutoff_fails_closed_without_now_fallback(self) -> None:
        state = ResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        assert state.knowledge_cutoff_at is None
        with pytest.raises(KnowledgeCutoffError, match="no now\\(\\) fallback"):
            require_knowledge_cutoff_at(state)
