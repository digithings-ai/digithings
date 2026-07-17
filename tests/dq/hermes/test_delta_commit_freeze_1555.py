"""Regression: the silent H4→H9 delta-day commit freeze (#1555).

Since 2026-06-26 every daily run reported ``ok:true, degraded:false,
book_materialized:true`` while nothing committed to ``positions`` / ``nav_history`` /
``decision_log`` / ``documents`` for weeks. Root cause:

- The H4 held-staleness gate (#1017/#1026) moves a quiet held name into
  ``focus_roster_excluded`` (no fresh analyst, absent from the H7 PM memo).
- H8 sizing then DROPS that held name from the sized book (it is neither a PM long
  nor inside the min-hold window).
- H9 ``coherence_errors`` fails closed ("held ticker X missing from book and not flat
  in H7") and returns a ``PhaseError`` whose ``phase="hermes_h9_commit_run"`` never
  reaches the degraded gate (which only escalates ``phase="chain"`` errors / research
  failures) — so the run stays "ok" and the freeze is invisible.

Two halves are pinned here:

1. :class:`TestDeltaDayCommits` — a delta day with held positions now COMMITS (the
   gated-out held names are carried at their drifted weight). Fails on pre-fix code
   by the *absence* of a commit manifest + positions.
2. :class:`TestUncommittedBookIsLoud` — a book that materializes but never commits is
   forced ``degraded`` with ``book_committed=False`` and a head-of-summary marker, so
   the failure mode can never again hide behind ``ok:true``.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas import diagnostics
from digiquant.olympus.atlas.graph import AtlasInput
from digiquant.olympus.atlas.state import AtlasResearchState, PhaseHermesState
from digiquant.olympus.atlas.testing.simulator import (
    build_quiet_day_canned_extras,
    simulated_pipeline,
)

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 29)
WATCHLIST = ("AAPL", "MSFT")


def _run_quiet_delta(*, commit_run: bool = True) -> tuple[AtlasResearchState, dict]:
    """Run the Atlas→Hermes chain for a quiet delta day with two held positions.

    Both watchlist names are prior-book holdings with sub-threshold price moves, so H4
    gates them out of the roster (Stage 1b staleness gate) and dispatches no analyst —
    the exact production shape that froze the commit path.
    """
    extras = build_quiet_day_canned_extras(run_date=RUN_DATE, watchlist=WATCHLIST)
    with simulated_pipeline(
        watchlist=WATCHLIST,
        canned_extras=extras,
        replace_canned_defaults=True,
        commit_run=commit_run,
    ) as run:
        final = run.invoke(AtlasInput(run_date=RUN_DATE, watchlist=WATCHLIST, refresh_scope="none"))
    return final, run.client.store


class TestDeltaDayCommits:
    """The book produced on a quiet delta day must actually commit (#1555 fix)."""

    def test_gated_out_held_names_are_carried_and_book_commits(self) -> None:
        final, store = _run_quiet_delta()

        # Precondition: this IS the frozen scenario — both held names were gated out of
        # H5 (no fresh analyst) and quietly recorded in the excluded ledger.
        assert final.phase_hermes.asset_analysts == {}, "quiet day: no analyst should dispatch"
        excluded = {e.ticker for e in final.phase_hermes.focus_roster_excluded}
        assert {"AAPL", "MSFT"} <= excluded, "held names must be in the gated-out ledger"

        # The fix: gated-out held names are carried into the sized book at drifted weight.
        book_tickers = {
            row["ticker"]
            for row in (final.phase_hermes.sized_book or {}).get("recommended_portfolio", [])
        }
        assert {"AAPL", "MSFT"} <= book_tickers, (
            f"gated-out held names dropped from the sized book: saw {book_tickers}"
        )

        # A green run must be provably committed: manifest present + positions written.
        manifest = final.phase_hermes.commit_manifest
        assert manifest is not None, "no commit manifest — the book never committed"
        assert manifest.get("status") == "committed"

        assert not final.errors, f"unexpected coherence fail-closed: {final.errors}"

        positions = {r["ticker"] for r in store.get("positions", []) if r["ticker"] != "CASH"}
        assert {"AAPL", "MSFT"} <= positions, f"held positions not booked: {positions}"

        manifest_docs = [
            r
            for r in store.get("documents", [])
            if str(r.get("document_key", "")).startswith("commit-run/")
        ]
        assert manifest_docs, "commit-run manifest document was not published"

    def test_green_run_implies_committed_book(self) -> None:
        final, _ = _run_quiet_delta()
        summary = diagnostics.summarize_run(final)
        assert summary.status == "ok"
        # An "ok" status must never again coexist with an uncommitted book.
        assert summary.book_materialized is True
        assert summary.book_committed is True
        assert diagnostics.book_committed(final) is True


class TestUncommittedBookIsLoud:
    """A materialized-but-uncommitted book must be loud: degraded + structured signal."""

    def test_chain_uncommitted_book_flips_degraded(self) -> None:
        # commit_run wiring off → H8 materializes a book, H9 is a no-op (no manifest).
        # Pre-#1555 this reported status "ok"; now it must be degraded.
        final, store = _run_quiet_delta(commit_run=False)
        assert final.phase_hermes.sized_book is not None
        assert final.phase_hermes.commit_manifest is None
        assert "positions" not in store

        summary = diagnostics.summarize_run(final)
        assert summary.status == "degraded"
        assert summary.book_materialized is True
        assert summary.book_committed is False
        assert diagnostics.is_degraded(final) is True

    def test_summarize_run_escalates_and_marks_head(self) -> None:
        state = AtlasResearchState(
            run_type="delta", run_date=RUN_DATE, baseline_date=date(2026, 6, 26)
        )
        # A fresh research segment so the base verdict would otherwise be "ok".
        from digiquant.olympus.atlas.state import SegmentPayload, SegmentSlot

        state.phase1_outputs = {
            "macro": SegmentSlot(payload=SegmentPayload(segment="macro", body={}, as_of=RUN_DATE))
        }
        state.phase_hermes = PhaseHermesState(
            sized_book={"recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}]},
            commit_manifest=None,
        )
        summary = diagnostics.summarize_run(state)
        assert summary.status == "degraded"  # escalated from "ok"
        assert summary.book_committed is False
        # The commit-failure marker is at the HEAD so it survives the error_summary cap.
        assert summary.error_summary.startswith("hermes_h9_commit_run/uncommitted")

    def test_h9_commit_error_flips_degraded_even_without_materialized_book(self) -> None:
        # H9 exit: sized_book is None but H7 emitted a memo → PhaseError
        # ("sized_book missing but H7 pm_direction_memo present"). Here ``book_materialized``
        # is False, so the materialized-but-uncommitted trigger alone would miss it — the
        # escalation must also fire on any ``hermes_h9_commit_run`` PhaseError (#1555 3a).
        from digiquant.olympus.atlas.state import PhaseError, SegmentPayload, SegmentSlot

        state = AtlasResearchState(
            run_type="delta", run_date=RUN_DATE, baseline_date=date(2026, 6, 26)
        )
        state.phase1_outputs = {
            "macro": SegmentSlot(payload=SegmentPayload(segment="macro", body={}, as_of=RUN_DATE))
        }
        state.errors = [
            PhaseError(
                phase="hermes_h9_commit_run",
                node="hermes/portfolio/commit-run",
                message="sized_book missing but H7 pm_direction_memo present",
                retryable=False,
            )
        ]
        summary = diagnostics.summarize_run(state)
        assert summary.book_materialized is False  # nothing materialized …
        assert summary.status == "degraded"  # … yet the H9 error still gates the run
        assert summary.error_summary.startswith("hermes_h9_commit_run/uncommitted")

    def test_idempotency_noop_counts_as_committed(self) -> None:
        state = AtlasResearchState(
            run_type="delta", run_date=RUN_DATE, baseline_date=date(2026, 6, 26)
        )
        from digiquant.olympus.atlas.state import SegmentPayload, SegmentSlot

        state.phase1_outputs = {
            "macro": SegmentSlot(payload=SegmentPayload(segment="macro", body={}, as_of=RUN_DATE))
        }
        state.phase_hermes = PhaseHermesState(
            sized_book={"recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}]},
            commit_manifest={"status": "noop", "source_run_id": str(state.run_id)},
        )
        summary = diagnostics.summarize_run(state)
        assert summary.status == "ok"  # noop = already booked, not a gap
        assert summary.book_committed is True

    def test_diagnostics_row_carries_structured_commit_flag(self) -> None:
        from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

        state = AtlasResearchState(
            run_type="delta", run_date=RUN_DATE, baseline_date=date(2026, 6, 26)
        )
        from digiquant.olympus.atlas.state import SegmentPayload, SegmentSlot

        state.phase1_outputs = {
            "macro": SegmentSlot(payload=SegmentPayload(segment="macro", body={}, as_of=RUN_DATE))
        }
        state.phase_hermes = PhaseHermesState(
            sized_book={"recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}]},
            commit_manifest=None,
        )
        client = FakeSupabaseClient()
        summary = diagnostics.write_row(
            client, state=state, run_id="freeze-1", run_type="delta", run_date=RUN_DATE
        )
        assert summary is not None
        row = client.store["atlas_run_diagnostics"][0]
        assert row["status"] == "degraded"
        # Truncation-proof structured signal (not buried in error_summary text).
        assert row["breakdown"]["book_committed"] is False
        assert row["breakdown"]["book_materialized"] is True
