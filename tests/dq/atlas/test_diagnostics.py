"""Per-run diagnostics → atlas_run_diagnostics (Pillar 1B).

summarize_run counts fresh/carried/failed segments and derives a status; write_row upserts
the row (fail-soft); is_degraded gates the CLI exit. A node-failure carry (reason
NODE_FAILED_REASON) counts as failed; a deliberate carry does not.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from digiquant.olympus.atlas import diagnostics
from digiquant.olympus.atlas.phases.fail_soft import NODE_FAILED_REASON
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    Carried,
    PhaseError,
    PublishedArtifact,
    SegmentPayload,
    SegmentSlot,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 12)


def _today(slug: str) -> SegmentSlot:
    return SegmentSlot(payload=SegmentPayload(segment=slug, body={}, as_of=RUN_DATE))


def _carried(reason: str) -> SegmentSlot:
    return SegmentSlot(payload=Carried(baseline_date=date(2026, 6, 9), reason=reason))


def _state(*, phase1=None, phase3=None, phase5=None, errors=None) -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="baseline", run_date=RUN_DATE, baseline_date=date(2026, 6, 9)
    )
    if phase1:
        state.phase1_outputs = phase1
    if phase3 is not None:
        state.phase3_output = phase3
    if phase5:
        state.phase5_outputs = phase5
    if errors:
        state.errors = errors
    return state


# --------------------------------------------------------------------------- summarize


def test_counts_today_carried_and_failed() -> None:
    state = _state(
        phase1={"macro": _today("macro"), "rates": _carried("below_triage_threshold")},
        phase5={
            "sector-tech": _today("sector-tech"),
            "sector-utilities": _carried(NODE_FAILED_REASON),
        },
    )
    s = diagnostics.summarize_run(state)
    assert s.segments_total == 4
    assert s.segments_ok == 2
    assert s.segments_carried == 2  # both carries (intentional + failure)
    assert s.segments_failed == 1  # only the NODE_FAILED_REASON carry
    assert s.status == "ok"  # 1/4 failed = 25% ≤ 50%


def test_status_failed_when_nothing_fresh() -> None:
    state = _state(phase1={"macro": _carried(NODE_FAILED_REASON), "rates": _carried("threshold")})
    s = diagnostics.summarize_run(state)
    assert s.segments_ok == 0
    assert s.status == "failed"


def test_status_degraded_above_threshold() -> None:
    # 2 of 3 segments failed = 66% > 50% → degraded (but at least one fresh, so not failed).
    state = _state(
        phase5={
            "a": _today("a"),
            "b": _carried(NODE_FAILED_REASON),
            "c": _carried(NODE_FAILED_REASON),
        }
    )
    s = diagnostics.summarize_run(state)
    assert s.segments_failed == 2
    assert s.status == "degraded"


def test_macro_phase3_single_slot_is_counted() -> None:
    # phase3_output is a single slot (not a dict); its macro node-failure must be counted.
    ok_state = _state(phase1={"a": _today("a")}, phase3=_today("macro"))
    assert diagnostics.summarize_run(ok_state).segments_ok == 2  # a + macro
    failed_macro = _state(phase1={"a": _today("a")}, phase3=_carried(NODE_FAILED_REASON))
    s = diagnostics.summarize_run(failed_macro)
    assert s.segments_total == 2
    assert s.segments_failed == 1
    assert s.breakdown["phase3_output"]["failed"] == 1


def test_chain_level_error_gates_the_run() -> None:
    # A terminal-phase chain crash (phase="chain") degrades an otherwise-fresh run...
    degraded = _state(
        phase1={"a": _today("a")},
        errors=[PhaseError(phase="chain", node="publish", message="publish crashed")],
    )
    assert diagnostics.summarize_run(degraded).status == "degraded"
    # ...and a core-engine (atlas/hermes) chain crash fails it outright.
    failed = _state(
        phase1={"a": _today("a")},
        errors=[PhaseError(phase="chain", node="hermes", message="hermes crashed")],
    )
    assert diagnostics.summarize_run(failed).status == "failed"


def test_node_level_error_does_not_gate_via_chain_marker() -> None:
    # A node-level PhaseError (phase != "chain") is summarized but does NOT itself flip
    # status — node failures already surface as failed segments.
    state = _state(
        phase1={"a": _today("a")},
        errors=[PhaseError(phase="phase5", node="sector-utilities", message="bad json")],
    )
    assert diagnostics.summarize_run(state).status == "ok"


def test_empty_state_is_failed() -> None:
    assert diagnostics.summarize_run(_state()).status == "failed"


def test_error_summary_from_state_errors() -> None:
    state = _state(
        phase1={"macro": _today("macro")},
        errors=[PhaseError(phase="hermes", node="pm", message="boom")],
    )
    s = diagnostics.summarize_run(state)
    assert "hermes/pm: boom" in s.error_summary
    assert s.breakdown["errors"][0]["node"] == "pm"


def test_is_degraded_matches_status() -> None:
    failed = _state(phase1={"a": _carried(NODE_FAILED_REASON)})
    healthy = _state(phase1={"a": _today("a")})
    assert diagnostics.is_degraded(failed) is True
    assert diagnostics.is_degraded(healthy) is False


# --------------------------------------------------------------------------- write_row


def test_write_row_upserts_with_usage_and_counts() -> None:
    client = FakeSupabaseClient()
    state = _state(phase1={"macro": _today("macro")}, phase5={"x": _carried(NODE_FAILED_REASON)})
    started_at = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 6, 12, 10, 2, 3, 456000, tzinfo=timezone.utc)
    summary = diagnostics.write_row(
        client,
        state=state,
        run_id="baseline-2026-06-12-local",
        run_type="baseline",
        run_date=RUN_DATE,
        started_at=started_at,
        finished_at=finished_at,
        usage_snapshot={
            "llm_calls": 12,
            "prompt_tokens": 3400,
            "completion_tokens": 800,
            "total_tokens": 4200,
            "models": ["x-ai/grok-4"],
        },
    )
    assert summary is not None
    rows = client.store["atlas_run_diagnostics"]
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == "baseline-2026-06-12-local"
    assert row["_on_conflict"] == "run_id"
    assert row["llm_calls"] == 12
    assert row["total_tokens"] == 4200
    assert row["segments_ok"] == 1
    assert row["segments_failed"] == 1
    assert row["model"] == "x-ai/grok-4"  # derived from usage snapshot models
    assert row["breakdown"]["models"] == ["x-ai/grok-4"]
    assert row["started_at"] == "2026-06-12T10:00:00+00:00"
    assert row["finished_at"] == "2026-06-12T10:02:03.456000+00:00"
    assert row["duration_s"] == pytest.approx(123.456)


def test_write_row_is_fail_soft() -> None:
    class _Raising:
        def table(self, _name: str):
            raise RuntimeError("supabase down")

    out = diagnostics.write_row(
        _Raising(),
        state=_state(phase1={"macro": _today("macro")}),
        run_id="r1",
        run_type="baseline",
        run_date=RUN_DATE,
    )
    assert out is None  # swallowed, run continues


# --------------------------------------------------------------------------- cancelled status (#814)


def _state_with_published_snapshot(**kwargs) -> AtlasResearchState:
    """State where a daily_snapshots row was successfully published."""
    state = _state(**kwargs)
    state.published = [
        PublishedArtifact(
            table="daily_snapshots",
            document_key=None,
            row_id="snap-1",
            published_at=RUN_DATE,
        )
    ]
    return state


def test_cancelled_when_published_snapshot_with_no_fresh_segments() -> None:
    # A run with zero fresh segments + published snapshot must record status=cancelled, not failed.
    state = _state_with_published_snapshot(phase1={"macro": _carried(NODE_FAILED_REASON)})
    s = diagnostics.summarize_run(state)
    assert s.status == "cancelled"


def test_failed_when_no_snapshot_and_nothing_fresh() -> None:
    # No snapshot published + no fresh segments = genuinely failed.
    state = _state(phase1={"macro": _carried(NODE_FAILED_REASON)})
    s = diagnostics.summarize_run(state)
    assert s.status == "failed"


def test_failed_when_no_snapshot_even_without_fresh_segments() -> None:
    # No snapshot published + no fresh segments = genuinely failed, regardless of
    # whether a SIGINT fired. The snapshot check is the sole gate (#814).
    state = _state(phase1={"macro": _carried(NODE_FAILED_REASON)})
    # Confirm state.published is empty (the default).
    from digiquant.olympus.atlas.diagnostics import _snapshot_published

    assert not _snapshot_published(state), "precondition: no snapshot published"
    s = diagnostics.summarize_run(state)
    assert s.status == "failed"


def test_core_engine_crash_stays_failed_even_with_published_snapshot() -> None:
    # A core engine (atlas/hermes) crash is always failed, even if a snapshot was
    # somehow published earlier.
    state = _state_with_published_snapshot(
        phase1={"macro": _today("macro")},
        errors=[PhaseError(phase="chain", node="atlas", message="atlas crashed")],
    )
    s = diagnostics.summarize_run(state)
    assert s.status == "failed"


def test_is_degraded_false_for_cancelled() -> None:
    # A cancelled run must NOT trigger the CI retry (is_degraded=False).
    state = _state_with_published_snapshot(phase1={"macro": _carried(NODE_FAILED_REASON)})
    assert diagnostics.is_degraded(state) is False


def test_write_row_records_cancelled_status() -> None:
    # When a snapshot was published, write_row must upsert a row with status="cancelled".
    client = FakeSupabaseClient()
    state = _state_with_published_snapshot(phase1={"macro": _carried(NODE_FAILED_REASON)})
    summary = diagnostics.write_row(
        client,
        state=state,
        run_id="cancelled-run-1",
        run_type="baseline",
        run_date=RUN_DATE,
    )
    assert summary is not None
    assert summary.status == "cancelled"
    rows = client.store["atlas_run_diagnostics"]
    assert rows[0]["status"] == "cancelled"
