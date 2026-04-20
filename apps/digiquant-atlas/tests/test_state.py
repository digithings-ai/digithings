"""Unit tests for digiquant_atlas.state."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from digiquant_atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    Carried,
    DataLayerSnapshot,
    DeltaTriageDecision,
    DeltaTriageResult,
    PhaseError,
    PriorContext,
    PublishedArtifact,
    SegmentPayload,
    SegmentSlot,
    SegmentSlotCollisionError,
    _merge_segment_dict,
)


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
        cfg = AtlasConfigBundle(watchlist=["SPY"])
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
class TestAtlasResearchState:
    def test_minimal_state_has_sensible_defaults(self) -> None:
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
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
            AtlasResearchState(run_type="nonsense", run_date=date(2026, 4, 26))  # type: ignore[arg-type]

    def test_delta_run_requires_caller_to_set_baseline_date(self) -> None:
        """A delta without a baseline is a caller bug; the state model doesn't
        enforce it at the type level — it's enforced by the preflight node.
        This test documents that the *state* allows it but the sub-graph
        must not."""
        state = AtlasResearchState(run_type="delta", run_date=date(2026, 4, 27))
        assert state.baseline_date is None  # preflight will reject

    def test_publish_ledger_append(self) -> None:
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
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
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
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
