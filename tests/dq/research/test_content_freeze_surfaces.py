"""Where a content freeze becomes visible (#1749, #1751) — the Atlas-side surfaces.

Split from ``tests/dq/dashboard/test_content_freeze_provenance.py``, which holds the pure
``edit_mode`` half. These tests import Atlas phases, which pull ``digigraph`` →
``openai``, so they must live here: ``tests/dq/research/conftest.py`` gates collection on
``digigraph`` being importable, and the ``digiquant`` CI lane installs only
``digiquant[dev]``. A test importing ``_node_factory`` from ``tests/dq/dashboard/`` is a
collection error in that lane, not a skip.

Three surfaces, each of which reported a frozen segment as fresh:

* the freshness badge (``_slot_freshness`` → ``daily_snapshots.snapshot``) said ``today``
* the diagnostics ``breakdown`` said nothing at all
* the published ``document-deltas/*`` row advertised six changes that did not happen
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.research.phases._node_factory import EditSegmentResult, _delta_row
from digiquant.research.phases.phase7_synthesis import _slot_freshness
from digiquant.research.snapshot import SegmentFreshness as ReadPathFreshness
from digiquant.research.snapshot import SnapshotEnvelope
from digiquant.research.state import AtlasResearchState, Carried, SegmentPayload
from digiquant.research.telemetry import CONTENT_FREEZE_KEY, content_freeze_breakdown
from digiquant.dashboard.edit_mode import DocumentPatch, PatchOp
from digiquant.dashboard.edit_mode.content_identity import UNCHANGED_FLAG_KEY, UNCHANGED_SINCE_KEY

_HEALTHCARE_BODY = {
    "segment": "sector-healthcare",
    "date": "2026-07-29",
    "headline": "Healthcare holds its bid",
    "bias": "bullish",
    "conviction": "medium",
}
_NOOP_OPS = [
    PatchOp(op="set", path="/headline", value="Healthcare holds its bid", reason="Updated market"),
    PatchOp(op="set", path="/bias", value="bullish", reason="Continued outperformance"),
    PatchOp(op="set", path="/relative_strength_vs_spy", value="outperforming", reason="XLV v SPY"),
    PatchOp(op="set", path="/sub_segment_leader", value="Biotech", reason="Biotech leads"),
    PatchOp(op="set", path="/driver_confirmation_count", value=2, reason="Two drivers"),
    PatchOp(op="set", path="/conviction", value="medium", reason="Unchanged conviction"),
]


def _patch(ops: list[PatchOp]) -> DocumentPatch:
    return DocumentPatch(
        schema_version="1.0",
        date=date(2026, 7, 31),
        prior_date=date(2026, 7, 29),
        target_document_key="sector-healthcare",
        status="updated",
        ops=ops,
    )


@pytest.mark.unit
class TestFreshnessBadge:
    """#1749's badge half — the surface an Olympus user actually reads."""

    def _payload(self, body: dict[str, object]) -> SegmentPayload:
        return SegmentPayload(segment="sector-healthcare", body=body, as_of=date(2026, 7, 31))

    def test_frozen_body_reports_frozen_and_the_content_date(self) -> None:
        body = {**_HEALTHCARE_BODY, UNCHANGED_FLAG_KEY: True, UNCHANGED_SINCE_KEY: "2026-07-28"}
        fresh = _slot_freshness(self._payload(body))
        assert fresh.source == "frozen"
        assert fresh.as_of == "2026-07-28"

    def test_changed_body_reports_today(self) -> None:
        fresh = _slot_freshness(self._payload(dict(_HEALTHCARE_BODY)))
        assert fresh.source == "today"
        assert fresh.as_of == "2026-07-31"

    def test_carried_slot_still_reports_baseline(self) -> None:
        """``frozen`` must not absorb ``baseline``: a carried segment was never regenerated,
        a frozen one ran and produced nothing. Different facts, different labels."""
        carried = Carried(baseline_date=date(2026, 7, 26), reason="below_triage_threshold")
        fresh = _slot_freshness(carried)
        assert fresh.source == "baseline"
        assert fresh.as_of == "2026-07-26"

    def test_marker_without_a_date_is_frozen_not_today(self) -> None:
        """Fail toward disclosure: a marker with a missing date loses the length, never the
        fact. Silently reporting ``today`` is the failure this whole change exists to stop."""
        fresh = _slot_freshness(self._payload({**_HEALTHCARE_BODY, UNCHANGED_FLAG_KEY: True}))
        assert fresh.source == "frozen"
        assert fresh.as_of == "2026-07-31"


@pytest.mark.unit
class TestReadPathAcceptsFrozen:
    """The hard coupling, and the one failure mode that would break reads of every row
    written after deploy.

    ``atlas/snapshot.py`` is the READ-path validator and both it and ``DigestPayload`` are
    ``extra="forbid"``. A ``source`` value the writer emits but that ``Literal`` omits is a
    ValidationError every time the row is read back — not a soft ignore — so the writer's
    model and this one have to widen in the same change.
    """

    def test_the_freshness_model_accepts_frozen(self) -> None:
        assert ReadPathFreshness.model_validate({"source": "frozen", "as_of": "2026-07-28"})

    def test_the_freshness_model_still_accepts_the_old_values(self) -> None:
        for source in ("today", "baseline"):
            assert ReadPathFreshness.model_validate({"source": source, "as_of": ""}).source

    def test_a_real_row_survives_the_full_envelope(self) -> None:
        """Not just the leaf model — the actual read path is
        ``SnapshotEnvelope.from_supabase_row`` → ``DigestPayload`` → nested
        ``segment_freshness``. Validating the leaf alone would pass while a real row still
        rejected."""
        from .test_snapshot import _digest_payload_kwargs

        snapshot = _digest_payload_kwargs() | {
            "date": "2026-07-31",
            "segment_freshness": {
                "sector-healthcare": {"source": "frozen", "as_of": "2026-07-28"},
                "us-equities": {"source": "today", "as_of": "2026-07-31"},
                "macro": {"source": "baseline", "as_of": "2026-07-26"},
            },
        }
        env = SnapshotEnvelope.from_supabase_row(
            {
                "date": "2026-07-31",
                "run_type": "delta",
                "baseline_date": "2026-07-26",
                "snapshot": snapshot,
                "updated_at": "2026-07-31T14:43:00+00:00",
            }
        )
        assert env.digest.segment_freshness["sector-healthcare"].source == "frozen"
        assert env.digest.segment_freshness["sector-healthcare"].as_of == "2026-07-28"
        assert env.digest.segment_freshness["us-equities"].source == "today"


@pytest.mark.unit
class TestFreezeTelemetry:
    """#1751 — the freeze had no telemetry surface at all."""

    def test_breakdown_reports_count_and_freeze_dates(self) -> None:
        """Values are the freeze DATES, not just a flag, so the row shows how long each
        segment has been stuck rather than merely that it is."""
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 7, 31),
            content_freezes={
                "sector-healthcare": "2026-07-28",
                "sector-materials": "2026-07-21",
            },
        )
        out = content_freeze_breakdown(state)
        assert out[CONTENT_FREEZE_KEY]["count"] == 2
        assert out[CONTENT_FREEZE_KEY]["segments"]["sector-healthcare"] == "2026-07-28"

    def test_no_key_when_nothing_froze(self) -> None:
        """Matches ``merge_fallback`` and ``circuit_breaker_skips``: absent, not zero."""
        state = AtlasResearchState(run_type="delta", run_date=date(2026, 7, 31))
        assert content_freeze_breakdown(state) == {}

    def test_a_checkpoint_written_before_this_field_existed_still_validates(self) -> None:
        """``chain.py`` resumes from a postgres checkpoint, so the first retry after deploy
        rehydrates a state dict with no ``content_freezes`` key. It must default, not raise."""
        pre_deploy = {"run_type": "delta", "run_date": "2026-07-31"}
        state = AtlasResearchState.model_validate(pre_deploy)
        assert state.content_freezes == {}
        assert content_freeze_breakdown(state) == {}

    def test_the_contributor_is_registered(self) -> None:
        from digiquant.research.diagnostics import _BREAKDOWN_CONTRIBUTORS

        assert content_freeze_breakdown in _BREAKDOWN_CONTRIBUTORS


@pytest.mark.unit
class TestPublishedDeltaRow:
    """#1751's sharpest half: the audit row asserted six changes that did not happen.

    Production's 2026-07-31 ``document-deltas/sector-healthcare`` row carried
    ``status="updated"`` and six ``set`` ops, each with its own ``reason``, over a body
    byte-identical to 07-29's. It is a user-visible artifact making a false claim.
    """

    def test_delta_row_records_the_merge_outcome_beside_its_ops(self) -> None:
        result = EditSegmentResult(
            slot=None,
            errors=[],
            delta=_patch(_NOOP_OPS),
            content_changed=False,
            unchanged_since="2026-07-28",
        )
        row = _delta_row(result)
        # The ops and the reasons are preserved — they are the audit trail of what the model
        # *claimed*. What is added is the deterministic fact that none of it landed.
        assert len(row["ops"]) == 6
        assert row["status"] == "updated"
        assert row["content_changed"] is False
        assert row[UNCHANGED_SINCE_KEY] == "2026-07-28"

    def test_a_real_edit_records_content_changed_true_and_no_freeze_date(self) -> None:
        row = _delta_row(EditSegmentResult(slot=None, errors=[], delta=_patch(_NOOP_OPS)))
        assert row["content_changed"] is True
        assert UNCHANGED_SINCE_KEY not in row

    def test_defaults_treat_an_early_return_as_a_real_edit(self) -> None:
        """A failed patch call, a non-SegmentPayload body, a merge fallback — every early
        return in ``_run_edit_segment`` must read as "changed", never as a silent freeze."""
        result = EditSegmentResult(slot=None, errors=[], delta=None)
        assert result.content_changed is True
        assert result.unchanged_since is None
