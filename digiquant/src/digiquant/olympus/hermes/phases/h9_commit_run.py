"""H9 — terminal ``commit_run`` (positions, brief, decision_log; #932)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import PhaseError, PhaseHermesState
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.payloads import sized_book
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.hermes.writers.commit_io import (
    book_portfolio,
    coherence_errors,
    load_commit_manifests,
    manifest_commit_seq,
    persist_decision_log,
    publish_hermes_documents,
    publish_portfolio_brief,
    resolve_prior_commit,
    save_commit_manifest,
    weights_fingerprint,
    weights_from_sized_book,
)

logger = logging.getLogger(__name__)

NODE_ID = "hermes/portfolio/commit-run"
PHASE_NAME = "hermes_h9_commit_run"


@dataclass(frozen=True)
class CommitRunDeps:
    """Wiring for the H9 terminal commit node."""

    client: SupabaseClient


def _phase_error(message: str) -> dict[str, Any]:
    return {
        "errors": [
            PhaseError(
                phase=PHASE_NAME,
                node=NODE_ID,
                message=message[:500],
                retryable=False,
            )
        ]
    }


def _manifest_payload(
    *,
    source_run_id: str,
    status: str,
    weights: dict[str, float],
    nav: float | None = None,
    decision_log_rows: int = 0,
    commit_seq: int = 1,
    supersedes: list[str] | None = None,
    pruned_tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Commit manifest body.

    ``schema_version`` moves to 1.1 for the three fields #1744 adds: ``commit_seq``
    (the only ordering signal available — ``documents`` has no timestamp column),
    ``supersedes`` (fingerprints of the same-date books this commit replaced) and
    ``pruned_tickers`` (rows deleted because the new book dropped them). Readers of
    1.0 manifests must treat all three as absent, which ``manifest_commit_seq``
    already does.
    """
    return {
        "schema_version": "1.1",
        "source_run_id": source_run_id,
        "status": status,
        "weights_fingerprint": weights_fingerprint(weights),
        "weights": {k: round(v, 4) for k, v in sorted(weights.items())},
        "nav": nav,
        "decision_log_rows": decision_log_rows,
        "commit_seq": commit_seq,
        "supersedes": list(supersedes or []),
        "pruned_tickers": list(pruned_tickers or []),
    }


def build_commit_run_node(deps: CommitRunDeps):
    """Return the H9 commit node bound to ``deps``."""

    def commit_run(state: HermesState) -> dict[str, Any]:
        book = sized_book(state)
        if book is None:
            if state.phase_hermes.pm_direction_memo is not None:
                return _phase_error(
                    "sized_book missing but H7 pm_direction_memo present — H8 risk sizing required"
                )
            return {}

        source_run_id = str(state.run_id)
        weights = weights_from_sized_book(book)
        current_fp = weights_fingerprint(weights)

        # Date-scoped, not run_id-scoped (#1744): run_id is a fresh uuid4 per process.
        priors = load_commit_manifests(client=deps.client, run_date=state.run_date)
        latest, commit_seq = resolve_prior_commit(priors)

        if latest is not None and latest.get("weights_fingerprint") == current_fp:
            # Same date, same book, already on disk — genuinely idempotent.
            manifest = _manifest_payload(
                source_run_id=source_run_id,
                status="noop",
                weights=weights,
                nav=latest.get("nav"),
                decision_log_rows=int(latest.get("decision_log_rows") or 0),
                commit_seq=manifest_commit_seq(latest),
                supersedes=[],
            )
            return {"phase_hermes": PhaseHermesState(commit_manifest=manifest)}

        # A same-date commit with a DIFFERENT book reconciles last-writer-wins rather
        # than raising: 2026-06-24 carries three manifests with three fingerprints, so
        # a hard conflict error here would fail the phase on a shape production already
        # produces — and with the uncommitted-book gate that is a degraded run for a
        # book that did commit. `book_portfolio` prunes the superseded rows, so the
        # end state is exactly the last writer's book.
        superseded = [
            str(m.get("weights_fingerprint")) for m in priors if m.get("weights_fingerprint")
        ]
        if superseded:
            logger.warning(
                "h9 commit_run: re-committing %s over %d prior manifest(s) "
                "(prior fingerprints=%s, current=%s) — last-writer-wins (#1744)",
                state.run_date.isoformat(),
                len(priors),
                superseded,
                current_fp,
            )

        checks = coherence_errors(state, weights)
        if checks:
            return _phase_error("; ".join(checks))

        booked = book_portfolio(client=deps.client, state=state, book=book)
        brief = publish_portfolio_brief(client=deps.client, state=state, book=book)
        hermes_docs = publish_hermes_documents(client=deps.client, state=state)
        n_decisions = persist_decision_log(client=deps.client, state=state)

        manifest = _manifest_payload(
            source_run_id=source_run_id,
            status="committed",
            weights=booked.weights,
            nav=booked.nav,
            decision_log_rows=n_decisions,
            commit_seq=commit_seq,
            supersedes=superseded,
            pruned_tickers=booked.pruned_tickers,
        )
        save_commit_manifest(client=deps.client, state=state, manifest=manifest)

        logger.info(
            "h9 commit_run: booked %d positions, nav=%.4f, %d decision_log rows, "
            "%d pruned (run_id=%s, commit_seq=%d)",
            len(booked.position_rows),
            booked.nav,
            n_decisions,
            len(booked.pruned_tickers),
            source_run_id,
            commit_seq,
        )
        return {
            "phase_hermes": PhaseHermesState(commit_manifest=manifest),
            "published": [brief, *hermes_docs],
        }

    return commit_run


def build_h9_commit_run(deps: CommitRunDeps | None = None) -> PipelinePhase:
    """Wrap H9 into a single-node ``PipelinePhase``."""

    def _noop(_state: HermesState) -> dict[str, Any]:
        return {}

    node = build_commit_run_node(deps) if deps is not None else _noop
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=node)],
    )


__all__ = [
    "CommitRunDeps",
    "NODE_ID",
    "PHASE_NAME",
    "build_commit_run_node",
    "build_h9_commit_run",
]
