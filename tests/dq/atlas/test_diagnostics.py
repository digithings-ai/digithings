"""Per-run diagnostics → atlas_run_diagnostics (Pillar 1B).

summarize_run counts fresh/carried/failed segments and derives a status; write_row upserts
the row (fail-soft); is_degraded gates the CLI exit. A node-failure carry (reason
NODE_FAILED_REASON) counts as failed; a deliberate carry does not.

Since #1736 ``status`` (health) and ``retry_signal`` (CI exit) diverge, and three new rules
escalate ``ok`` → ``degraded``: any failed research segment, a majority of dead Hermes
deliberations, and "Atlas researched but nothing committed". Most fixtures here therefore
pass ``phase_hermes=_committed_book()`` so that each test varies exactly one thing.
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
    PhaseHermesState,
    PublishedArtifact,
    SegmentPayload,
    SegmentSlot,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 12)


def _usage_events(count: int) -> dict[str, list[dict[str, object]]]:
    return {
        "events": [
            {
                "sequence": sequence,
                "kind": "tool_call",
                "name": f"tool-{sequence}",
                "status": "ok",
                "duration_ms": sequence,
                "retry_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "cost_usd": 0.0,
                "sources": 0,
                "input_summary": "Arguments: none",
                "output_summary": "Returned no value",
            }
            for sequence in range(1, count + 1)
        ]
    }


def _today(slug: str) -> SegmentSlot:
    return SegmentSlot(payload=SegmentPayload(segment=slug, body={}, as_of=RUN_DATE))


def _carried(reason: str) -> SegmentSlot:
    return SegmentSlot(payload=Carried(baseline_date=date(2026, 6, 9), reason=reason))


def _committed_book(**extra) -> PhaseHermesState:
    """A Hermes phase whose book both materialized AND committed — a healthy terminal."""
    return PhaseHermesState(
        sized_book={"recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}]},
        commit_manifest={"status": "committed", "source_run_id": "r1"},
        **extra,
    )


def _state(
    *, phase1=None, phase3=None, phase5=None, errors=None, phase_hermes=None
) -> AtlasResearchState:
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
    if phase_hermes is not None:
        state.phase_hermes = phase_hermes
    return state


# --------------------------------------------------------------------------- summarize


def test_counts_today_carried_and_failed() -> None:
    state = _state(
        phase1={"macro": _today("macro"), "rates": _carried("below_triage_threshold")},
        phase5={
            "sector-tech": _today("sector-tech"),
            "sector-utilities": _carried(NODE_FAILED_REASON),
        },
        phase_hermes=_committed_book(),
    )
    s = diagnostics.summarize_run(state)
    assert s.segments_total == 4
    assert s.segments_ok == 2
    assert s.segments_carried == 2  # both carries (intentional + failure)
    assert s.segments_failed == 1  # only the NODE_FAILED_REASON carry
    # STRICT (#1736): one dead segment is enough. This asserted "ok" until then, because
    # 1/4 = 25% sat under the 50% share rule — which is how 2026-07-29 lost 5 of 27
    # segments and still published a green row.
    assert s.status == "degraded"
    assert s.breakdown["degraded_reasons"] == ["failed_segments"]


def test_status_ok_when_nothing_failed_and_book_committed() -> None:
    # The only shape that still earns "ok": every segment accounted for, book committed.
    state = _state(
        phase1={"macro": _today("macro"), "rates": _carried("below_triage_threshold")},
        phase_hermes=_committed_book(),
    )
    s = diagnostics.summarize_run(state)
    assert s.segments_failed == 0
    assert s.status == "ok"
    assert "degraded_reasons" not in s.breakdown


def test_status_failed_when_nothing_fresh() -> None:
    state = _state(phase1={"macro": _carried(NODE_FAILED_REASON), "rates": _carried("threshold")})
    s = diagnostics.summarize_run(state)
    assert s.segments_ok == 0
    assert s.status == "failed"


def test_atlas_research_produced_true_when_fresh_segments() -> None:
    state = _state(phase1={"macro": _today("macro")})
    assert diagnostics.atlas_research_produced(state) is True


def test_atlas_research_produced_true_for_fully_carried_quiet_delta() -> None:
    # A quiet delta that carried everything from baseline (none fresh) still has valid
    # research for Hermes — it must not be gated as "no research".
    state = _state(phase1={"macro": _carried("below_triage_threshold")})
    assert diagnostics.atlas_research_produced(state) is True


def test_atlas_research_produced_false_on_atlas_chain_crash() -> None:
    # Even with segments in state, a chain-level atlas crash means the research is untrusted.
    state = _state(
        phase1={"macro": _today("macro")},
        errors=[PhaseError(phase="chain", node="atlas", message="empty LLM response")],
    )
    assert diagnostics.atlas_research_produced(state) is False


def test_atlas_research_produced_false_when_nothing_produced() -> None:
    assert diagnostics.atlas_research_produced(_state()) is False


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
    # A node-level PhaseError (phase != "chain", and not one of the Hermes reasoning phases)
    # is summarized but does NOT itself flip status — node failures already surface as failed
    # segments. The committed book is what keeps this "ok" now (the no-book gate, #1736).
    state = _state(
        phase1={"a": _today("a")},
        errors=[PhaseError(phase="phase5", node="sector-utilities", message="bad json")],
        phase_hermes=_committed_book(),
    )
    assert diagnostics.summarize_run(state).status == "ok"


def test_master_digest_failure_marks_degraded_and_leads_summary() -> None:
    # A master-digest synthesis failure (#1559) must escalate an otherwise-ok run
    # to degraded and LEAD the error summary so it is never buried/truncated —
    # even though it is a node-level (phase != "chain") error.
    state = _state(
        phase1={"macro": _today("macro"), "rates": _today("rates")},
        errors=[
            PhaseError(phase="phase5", node="sector-utilities", message="bad json"),
            PhaseError(
                phase="phase7_synthesis",
                node="master-digest",
                message="BadRequestError 400: maximum context length is 64000 tokens",
            ),
        ],
    )
    s = diagnostics.summarize_run(state)
    assert s.status == "degraded"
    assert s.error_summary.startswith("MASTER-DIGEST SYNTHESIS FAILED")
    assert "64000 tokens" in s.error_summary
    # First-class breakdown key, distinct from the per-segment error list.
    assert "master_digest_failed" in s.breakdown
    assert diagnostics.is_degraded(state) is True


def test_master_digest_failure_does_not_override_failed_status() -> None:
    # If nothing fresh was produced, the run is still 'failed' — the digest
    # escalation only lifts an ok run to degraded (it sits in the elif branch).
    state = _state(
        phase1={"macro": _carried(NODE_FAILED_REASON)},
        errors=[PhaseError(phase="phase7_synthesis", node="master-digest", message="overflow")],
    )
    assert diagnostics.summarize_run(state).status == "failed"


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


# ------------------------------------------------- #1736: status vs retry_signal (STRICT)


def _prod_shaped_state(*, failed: int, phase_hermes=None) -> AtlasResearchState:
    """27 research segments with ``failed`` node-failure carries — the daily prod shape."""
    slots = {f"s{i}": _today(f"s{i}") for i in range(27 - failed)}
    slots.update({f"f{i}": _carried(NODE_FAILED_REASON) for i in range(failed)})
    return _state(phase5=slots, phase_hermes=phase_hermes)


def test_strict_gate_degrades_a_single_failed_segment_without_asking_for_a_retry() -> None:
    """The 2026-07-31 shape: 4 of 27 segments dead, book committed, reported ``ok``.

    This is the keystone assertion of #1736. It must be degraded (the report is now honest)
    AND it must not ask CI to retry (the book committed — re-running burns three attempts
    plus ~20 min of backoff on work that already landed, #809).
    """
    state = _prod_shaped_state(failed=4, phase_hermes=_committed_book())
    s = diagnostics.summarize_run(state)
    assert s.segments_failed == 4
    assert (s.segments_failed / s.segments_total) * 100.0 < 50.0, "under the old share rule"
    assert s.status == "degraded"
    assert s.retry_signal is False
    assert diagnostics.is_degraded(state) is False  # CI exit unchanged


def test_retry_signal_still_fires_on_the_legacy_share_rule() -> None:
    # Above ATLAS_DEGRADED_RUN_PCT the legacy gate trips as it always has, so CI retries.
    state = _prod_shaped_state(failed=20, phase_hermes=_committed_book())
    s = diagnostics.summarize_run(state)
    assert s.status == "degraded"
    assert s.retry_signal is True


# ------------------------------------------------- #1736: no-book gate (#1766 residual hole)


def test_no_book_gate_degrades_research_with_nothing_committed() -> None:
    # H9 committing nothing at all leaves ``sized_book`` None and raises no PhaseError, so
    # the #1555 commit gate (materialized-but-uncommitted) misses it entirely and the run
    # reported "ok" — the shape behind #1766's 20-day blackout.
    state = _prod_shaped_state(failed=0)
    s = diagnostics.summarize_run(state)
    assert s.book_materialized is False and s.book_committed is False
    assert s.status == "degraded"
    assert s.breakdown["degraded_reasons"] == ["no_committed_book"]


def test_no_book_gate_silent_when_atlas_produced_no_research() -> None:
    # No research → Hermes was never run by the chain, so "no book" is not the finding
    # (the run is already ``failed`` on the nothing-fresh rule).
    assert diagnostics.summarize_run(_state()).status == "failed"


def test_no_book_gate_silent_when_atlas_crashed_at_chain_level() -> None:
    # An Atlas chain crash is ``failed`` and the no-book gate must not overwrite it.
    state = _prod_shaped_state(failed=0)
    state.errors = [PhaseError(phase="chain", node="atlas", message="empty LLM response")]
    assert diagnostics.summarize_run(state).status == "failed"


def test_noop_commit_manifest_satisfies_the_no_book_gate() -> None:
    # An idempotent re-run of an already-booked day is committed, not a gap.
    state = _prod_shaped_state(
        failed=0,
        phase_hermes=PhaseHermesState(commit_manifest={"status": "noop", "source_run_id": "r1"}),
    )
    assert diagnostics.summarize_run(state).status == "ok"


# ------------------------------------------------- #1742: Hermes deliberation density


def _hermes_deliberations(n: int, *, failed: int, phase: str = "hermes_h6_deliberation"):
    """A Hermes phase with ``n`` deliberations of which ``failed`` recorded a PhaseError."""
    hermes = _committed_book(
        deliberation_summaries={f"T{i}": {"ticker": f"T{i}"} for i in range(n)}
    )
    errors = [
        PhaseError(phase=phase, node=f"hermes/portfolio/deliberation-T{i}", message="boom")
        for i in range(failed)
    ]
    return hermes, errors


def test_hermes_deliberation_gate_degrades_a_mostly_dead_portfolio() -> None:
    # 2026-07-31: 31 of 39 deliberations dead, every research segment fine, reported "ok".
    hermes, errors = _hermes_deliberations(39, failed=31)
    state = _prod_shaped_state(failed=0, phase_hermes=hermes)
    state.errors = errors
    s = diagnostics.summarize_run(state)
    assert s.breakdown["hermes_deliberation"] == {"total": 39, "failed": 31}
    assert s.status == "degraded"
    assert "hermes_deliberations" in s.breakdown["degraded_reasons"]


def test_hermes_deliberation_gate_tolerates_routine_cap_noise() -> None:
    # The 2026-07-26 baseline: 1 of 50 — H6 emits the same (phase, node) for a benign
    # max_rounds cap as for an LLM crash, so a gate on *any* error would flip every run.
    hermes, errors = _hermes_deliberations(50, failed=1)
    state = _prod_shaped_state(failed=0, phase_hermes=hermes)
    state.errors = errors
    s = diagnostics.summarize_run(state)
    assert s.breakdown["hermes_deliberation"] == {"total": 50, "failed": 1}
    assert s.status == "ok"


def test_h9_commit_error_is_excluded_from_the_deliberation_numerator() -> None:
    # hermes_h9_commit_run is already gated by #1555; counting it here would double-count it
    # and pollute a metric that is supposed to measure *reasoning* failures.
    hermes, _ = _hermes_deliberations(4, failed=0)
    state = _prod_shaped_state(failed=0, phase_hermes=hermes)
    state.errors = [
        PhaseError(
            phase="hermes_h9_commit_run", node="hermes/portfolio/commit-run", message="conflict"
        )
    ]
    s = diagnostics.summarize_run(state)
    assert s.breakdown["hermes_deliberation"] == {"total": 4, "failed": 0}


def test_hermes_deliberation_gate_silent_when_nothing_was_deliberated() -> None:
    # Zero deliberations = no denominator, so the share gate cannot say anything. The
    # catastrophic version of this shape is caught by the no-book gate instead.
    hermes, errors = _hermes_deliberations(0, failed=2, phase="phase_hermes")
    state = _prod_shaped_state(failed=0, phase_hermes=hermes)
    state.errors = errors
    s = diagnostics.summarize_run(state)
    assert s.breakdown["hermes_deliberation"] == {"total": 0, "failed": 2}
    assert s.status == "ok"


@pytest.mark.parametrize(
    "phase",
    [
        "phase_hermes",
        "hermes_h6_deliberation",
        "hermes_h7_pm_direction",
        "phase7d_pm",
        "phase9_evolution",
    ],
)
def test_every_hermes_failure_phase_literal_is_counted(phase: str) -> None:
    # An explicit allow-list, not a ``hermes_*`` prefix: pin all five literals so a rename
    # in the phase modules fails here rather than silently emptying the metric.
    hermes, errors = _hermes_deliberations(4, failed=3, phase=phase)
    state = _prod_shaped_state(failed=0, phase_hermes=hermes)
    state.errors = errors
    s = diagnostics.summarize_run(state)
    assert s.breakdown["hermes_deliberation"] == {"total": 4, "failed": 3}
    assert s.status == "degraded"


# ------------------------------------------------- #1736: the breakdown contribution seam


def test_registered_contributor_lands_in_breakdown(breakdown_contributor) -> None:
    breakdown_contributor(lambda state: {"roster": {"width": len(state.phase5_outputs)}})
    s = diagnostics.summarize_run(_prod_shaped_state(failed=0, phase_hermes=_committed_book()))
    assert s.breakdown["roster"] == {"width": 27}


def test_contributor_failure_is_swallowed(breakdown_contributor) -> None:
    def _boom(_state):
        raise RuntimeError("contributor exploded")

    breakdown_contributor(_boom)
    breakdown_contributor(lambda _state: {"budget": {"usd": 3.0}})
    s = diagnostics.summarize_run(_prod_shaped_state(failed=0, phase_hermes=_committed_book()))
    assert s.status == "ok", "a broken contributor must never gate a run"
    assert s.breakdown["budget"] == {"usd": 3.0}, "later contributors still run"


def test_contributor_cannot_clobber_an_existing_breakdown_key(breakdown_contributor) -> None:
    breakdown_contributor(lambda _state: {"phase5_outputs": "hijacked"})
    s = diagnostics.summarize_run(_prod_shaped_state(failed=0, phase_hermes=_committed_book()))
    assert s.breakdown["phase5_outputs"] == {"ok": 27, "carried": 0, "failed": 0}


def test_contributors_do_not_run_on_the_mid_run_gating_path(breakdown_contributor) -> None:
    # ``chain`` calls atlas_research_produced BEFORE Hermes; a contributor firing there would
    # see a half-populated state (and fire twice per run).
    calls: list[int] = []
    breakdown_contributor(lambda _state: calls.append(1) or {})
    state = _prod_shaped_state(failed=0, phase_hermes=_committed_book())
    assert diagnostics.atlas_research_produced(state) is True
    assert calls == []
    diagnostics.summarize_run(state)
    assert calls == [1]


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
            "events": [
                {
                    "sequence": 1,
                    "kind": "model_call",
                    "phase": "macro",
                    "operation": "MacroReport",
                    "document_key": "macro",
                    "name": "x-ai/grok-4",
                    "status": "ok",
                    "duration_ms": 250,
                    "retry_count": 0,
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "cached_tokens": 40,
                    "cost_usd": 0.002,
                    "sources": 0,
                    "input_summary": "Structured model request",
                    "output_summary": "20 completion tokens",
                }
            ],
        },
    )
    assert summary is not None
    rows = client.store["atlas_run_diagnostics"]
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == "baseline-2026-06-12-local"
    # Per-ATTEMPT since #1762: pipeline-olympus.yml retries the chain inside one job, so
    # run_id alone let the last retry overwrite the expensive attempt's tokens and cost.
    assert row["_on_conflict"] == "run_id,attempt"
    assert row["attempt"] == 1  # no OLYMPUS_ATTEMPT in the environment → first attempt
    assert row["llm_calls"] == 12
    assert row["total_tokens"] == 4200
    assert row["segments_ok"] == 1
    assert row["segments_failed"] == 1
    assert row["model"] == "x-ai/grok-4"  # derived from usage snapshot models
    assert row["breakdown"]["models"] == ["x-ai/grok-4"]
    assert row["breakdown"]["empty_retries"] == {"total": 0, "by_model": {}}
    assert row["started_at"] == "2026-06-12T10:00:00+00:00"
    assert row["finished_at"] == "2026-06-12T10:02:03.456000+00:00"
    assert row["duration_s"] == pytest.approx(123.456)
    events = client.store["olympus_run_events"]
    assert len(events) == 1
    assert events[0]["run_id"] == "baseline-2026-06-12-local"
    assert events[0]["attempt"] == 1
    assert events[0]["run_date"] == "2026-06-12"
    assert events[0]["phase"] == "macro"
    assert events[0]["_on_conflict"] == "run_id,attempt,sequence"


def test_write_row_surfaces_empty_retries_from_usage_snapshot() -> None:
    client = FakeSupabaseClient()
    state = _state(phase1={"macro": _today("macro")})
    diagnostics.write_row(
        client,
        state=state,
        run_id="empty-retry-run",
        run_type="baseline",
        run_date=RUN_DATE,
        usage_snapshot={
            "llm_calls": 5,
            "empty_retries": {"total": 3, "by_model": {"openrouter/auto": 2, "x-ai/grok-4": 1}},
        },
    )
    row = client.store["atlas_run_diagnostics"][0]
    assert row["breakdown"]["empty_retries"] == {
        "total": 3,
        "by_model": {"openrouter/auto": 2, "x-ai/grok-4": 1},
    }


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


def test_write_row_removes_stale_higher_event_sequences() -> None:
    client = FakeSupabaseClient()
    state = _state(phase1={"macro": _today("macro")})
    diagnostics.write_row(
        client,
        state=state,
        run_id="repeated-run",
        run_type="baseline",
        run_date=RUN_DATE,
        usage_snapshot=_usage_events(5),
    )
    diagnostics.write_row(
        client,
        state=state,
        run_id="repeated-run",
        run_type="baseline",
        run_date=RUN_DATE,
        usage_snapshot=_usage_events(3),
    )

    events = client.store["olympus_run_events"]
    assert {row["sequence"] for row in events} == {1, 2, 3}


def test_write_row_clears_prior_events_when_trace_becomes_empty() -> None:
    client = FakeSupabaseClient()
    state = _state(phase1={"macro": _today("macro")})
    diagnostics.write_row(
        client,
        state=state,
        run_id="empty-rewrite",
        run_type="baseline",
        run_date=RUN_DATE,
        usage_snapshot=_usage_events(2),
    )
    diagnostics.write_row(
        client,
        state=state,
        run_id="empty-rewrite",
        run_type="baseline",
        run_date=RUN_DATE,
        usage_snapshot={"events": []},
    )

    assert client.store["olympus_run_events"] == []


def test_write_row_without_event_capture_preserves_prior_trace() -> None:
    client = FakeSupabaseClient()
    state = _state(phase1={"macro": _today("macro")})
    diagnostics.write_row(
        client,
        state=state,
        run_id="capture-absent",
        run_type="baseline",
        run_date=RUN_DATE,
        usage_snapshot=_usage_events(2),
    )
    diagnostics.write_row(
        client,
        state=state,
        run_id="capture-absent",
        run_type="baseline",
        run_date=RUN_DATE,
        usage_snapshot={"llm_calls": 2},
    )

    assert {row["sequence"] for row in client.store["olympus_run_events"]} == {1, 2}


def test_write_row_preserves_null_usage_and_wp1_join_ids() -> None:
    """Glass-box rows stay joinable to 067 and never invent zero economics (#2763)."""
    client = FakeSupabaseClient()
    state = _state(phase1={"macro": _today("macro")})
    call_id = "11111111-1111-1111-1111-111111111111"
    attempt_id = "22222222-2222-2222-2222-222222222222"
    node_run_id = "33333333-3333-3333-3333-333333333333"
    diagnostics.write_row(
        client,
        state=state,
        run_id="wp1-join",
        run_type="baseline",
        run_date=RUN_DATE,
        usage_snapshot={
            "events": [
                {
                    "sequence": 1,
                    "kind": "model_call",
                    "phase": "macro",
                    "operation": "MacroReport",
                    "document_key": "macro",
                    "name": "openrouter/auto",
                    "status": "ok",
                    "duration_ms": 10,
                    "retry_count": 0,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "cached_tokens": None,
                    "cost_usd": None,
                    "sources": 0,
                    "input_summary": "Structured model request",
                    "output_summary": "Model response returned",
                    "call_id": call_id,
                    "attempt_id": attempt_id,
                    "node_run_id": node_run_id,
                }
            ]
        },
    )
    row = client.store["olympus_run_events"][0]
    assert row["prompt_tokens"] is None
    assert row["completion_tokens"] is None
    assert row["cached_tokens"] is None
    assert row["cost_usd"] is None
    assert row["call_id"] == call_id
    assert row["attempt_id"] == attempt_id
    assert row["node_run_id"] == node_run_id


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
