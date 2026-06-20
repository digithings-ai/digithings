"""H9 — terminal ``commit_run`` (positions, brief, decision_log; #932)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import PhaseError, PhaseHermesState
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.payloads import sized_book
from digiquant.olympus.hermes.state import HermesState
from digiquant.olympus.hermes.writers.commit_io import (
    book_portfolio,
    coherence_errors,
    load_commit_manifest,
    persist_decision_log,
    publish_hermes_documents,
    publish_portfolio_brief,
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
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_run_id": source_run_id,
        "status": status,
        "weights_fingerprint": weights_fingerprint(weights),
        "weights": {k: round(v, 4) for k, v in sorted(weights.items())},
        "nav": nav,
        "decision_log_rows": decision_log_rows,
    }


def build_commit_run_node(deps: CommitRunDeps):
    """Return the H9 commit node bound to ``deps``."""

    def commit_run(state: HermesState) -> dict[str, Any]:
        book = sized_book(state)
        if book is None:
            return {}

        source_run_id = str(state.run_id)
        weights = weights_from_sized_book(book)
        prior = load_commit_manifest(
            client=deps.client,
            source_run_id=source_run_id,
            run_date=state.run_date,
        )
        if prior is not None:
            prior_fp = prior.get("weights_fingerprint")
            current_fp = weights_fingerprint(weights)
            if prior_fp == current_fp:
                manifest = _manifest_payload(
                    source_run_id=source_run_id,
                    status="noop",
                    weights=weights,
                    nav=prior.get("nav"),
                    decision_log_rows=int(prior.get("decision_log_rows") or 0),
                )
                return {"phase_hermes": PhaseHermesState(commit_manifest=manifest)}
            return _phase_error(
                f"commit_run idempotency conflict for source_run_id={source_run_id}: "
                f"prior fingerprint {prior_fp!r} != current {current_fp!r}"
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
        )
        save_commit_manifest(client=deps.client, state=state, manifest=manifest)

        logger.info(
            "h9 commit_run: booked %d positions, nav=%.4f, %d decision_log rows (run_id=%s)",
            len(booked.position_rows),
            booked.nav,
            n_decisions,
            source_run_id,
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
