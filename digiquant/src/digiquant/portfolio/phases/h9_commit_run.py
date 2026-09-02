"""H9 — terminal ``commit_run`` (positions, brief, decision_log; #932)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)
from uuid import UUID

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.portfolio.h9_cost_evidence import (
    build_cost_bundles_for_commit,
    investor_currency_from_state,
)
from digiquant.portfolio.payloads import sized_book
from digiquant.portfolio.sizing_events import SizingAdjustment
from digiquant.portfolio.state import PortfolioState
from digiquant.portfolio.writers.commit_io import (
    PreTradeRiskMode,
    book_portfolio,
    coherence_errors,
    load_commit_manifests,
    manifest_commit_seq,
    persist_decision_log,
    persist_validated_pretrade_risk_report,
    publish_portfolio_brief,
    publish_portfolio_documents,
    resolve_prior_commit,
    save_commit_manifest,
    validate_pretrade_risk_report,
    weights_fingerprint,
    weights_from_sized_book,
)
from digiquant.portfolio.writers.ledger_io import LedgerAppend, append_commit_chain
from digiquant.research.cost_liquidity_registry import (
    collect_cost_artifacts_from_bundles,
    collect_risk_policy_from_state,
    persist_cost_liquidity_bundles,
)
from digiquant.research.forecast_registry import persist_forecast_lineage_from_state
from digiquant.research.risk_policy_registry import persist_h8_risk_snapshots_from_state
from digiquant.research.state import PhaseError, PhasePortfolioState
from digiquant.research.supabase_io import SupabaseClient

logger = logging.getLogger(__name__)

NODE_ID = "portfolio/commit-run"
PHASE_NAME = "portfolio_h9_commit_run"


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


def _persist_risk_policy_registry(*, client: SupabaseClient, state: PortfolioState) -> dict[str, Any]:
    """Fail-soft H8 risk snapshot registry (#2698). Never raises into booking."""
    try:
        result = persist_h8_risk_snapshots_from_state(client=client, state=state)
    except Exception as exc:
        logger.warning(
            "h9 risk policy registry degraded (%s: %s); book retained",
            type(exc).__name__,
            exc,
        )
        return {
            "risk_policy_registry_status": "degraded",
            "risk_policy_registry_reason": f"{type(exc).__name__}: {exc}"[:300],
            "risk_policy_registry_policies_written": 0,
            "risk_policy_registry_snapshots_written": 0,
            "risk_policy_registry_run_refs_written": 0,
        }
    status = "ok" if result.ok else "degraded"
    return {
        "risk_policy_registry_status": status,
        "risk_policy_registry_reason": result.degraded_reason,
        "risk_policy_registry_policies_written": result.policies_written,
        "risk_policy_registry_policies_skipped": result.policies_skipped,
        "risk_policy_registry_snapshots_written": result.snapshots_written,
        "risk_policy_registry_snapshots_skipped": result.snapshots_skipped,
        "risk_policy_registry_run_refs_written": result.run_refs_written,
        "risk_policy_registry_run_refs_skipped": result.run_refs_skipped,
        "risk_policy_registry_conflicts": list(result.conflicts),
    }


def _persist_cost_liquidity_registry(
    *,
    client: SupabaseClient,
    state: PortfolioState,
    ledger: LedgerAppend | None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Fail-soft action cost registry (#2709). Never raises into booking."""
    empty_snapshots: dict[str, dict[str, Any]] = {}
    empty_estimates: dict[str, dict[str, Any]] = {}
    if ledger is None:
        return (
            {
                "cost_liquidity_registry_status": "skipped",
                "cost_liquidity_registry_reason": "ledger_disabled",
                "cost_liquidity_registry_snapshots_written": 0,
                "cost_liquidity_registry_estimates_written": 0,
            },
            empty_snapshots,
            empty_estimates,
        )
    policy = collect_risk_policy_from_state(state)
    if policy is None:
        return (
            {
                "cost_liquidity_registry_status": "degraded",
                "cost_liquidity_registry_reason": "missing_risk_policy",
                "cost_liquidity_registry_snapshots_written": 0,
                "cost_liquidity_registry_estimates_written": 0,
            },
            empty_snapshots,
            empty_estimates,
        )
    if investor_currency_from_state(state) is None:
        return (
            {
                "cost_liquidity_registry_status": "degraded",
                "cost_liquidity_registry_reason": "currency_missing",
                "cost_liquidity_registry_snapshots_written": 0,
                "cost_liquidity_registry_estimates_written": 0,
            },
            empty_snapshots,
            empty_estimates,
        )
    try:
        bundles = build_cost_bundles_for_commit(
            client=client,
            state=state,
            commit_id=UUID(ledger.commit_id),
            policy=policy,
        )
        result = persist_cost_liquidity_bundles(client=client, bundles=bundles)
        snapshots, estimates = collect_cost_artifacts_from_bundles(bundles)
    except Exception as exc:
        logger.warning(
            "h9 cost liquidity registry degraded (%s: %s); book retained",
            type(exc).__name__,
            exc,
        )
        return (
            {
                "cost_liquidity_registry_status": "degraded",
                "cost_liquidity_registry_reason": f"{type(exc).__name__}: {exc}"[:300],
                "cost_liquidity_registry_snapshots_written": 0,
                "cost_liquidity_registry_estimates_written": 0,
            },
            empty_snapshots,
            empty_estimates,
        )
    status = "ok" if result.ok else "degraded"
    return (
        {
            "cost_liquidity_registry_status": status,
            "cost_liquidity_registry_reason": result.degraded_reason,
            "cost_liquidity_registry_snapshots_written": result.snapshots_written,
            "cost_liquidity_registry_snapshots_skipped": result.snapshots_skipped,
            "cost_liquidity_registry_estimates_written": result.estimates_written,
            "cost_liquidity_registry_estimates_skipped": result.estimates_skipped,
            "cost_liquidity_registry_conflicts": list(result.conflicts),
        },
        snapshots,
        estimates,
    )


def _persist_forecast_registry(*, client: SupabaseClient, state: PortfolioState) -> dict[str, Any]:
    """Fail-soft prospective forecast lineage (#2663). Never raises into booking."""
    try:
        result = persist_forecast_lineage_from_state(client=client, state=state)
    except Exception as exc:
        logger.warning(
            "h9 forecast registry degraded (%s: %s); book retained",
            type(exc).__name__,
            exc,
        )
        return {
            "forecast_registry_status": "degraded",
            "forecast_registry_reason": f"{type(exc).__name__}: {exc}"[:300],
            "forecast_registry_assessments_written": 0,
            "forecast_registry_amendments_written": 0,
            "forecast_registry_calibrations_written": 0,
            "forecast_registry_calibrated_forecasts_written": 0,
        }
    status = "ok" if result.ok else "degraded"
    return {
        "forecast_registry_status": status,
        "forecast_registry_reason": result.degraded_reason,
        "forecast_registry_assessments_written": result.assessments_written,
        "forecast_registry_assessments_skipped": result.assessments_skipped,
        "forecast_registry_amendments_written": result.amendments_written,
        "forecast_registry_amendments_skipped": result.amendments_skipped,
        "forecast_registry_calibrations_written": result.calibrations_written,
        "forecast_registry_calibrations_skipped": result.calibrations_skipped,
        "forecast_registry_calibrated_forecasts_written": result.calibrated_forecasts_written,
        "forecast_registry_calibrated_forecasts_skipped": result.calibrated_forecasts_skipped,
        "forecast_registry_conflicts": list(result.conflicts),
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
    ledger: LedgerAppend | None = None,
    forecast_registry: dict[str, Any] | None = None,
    risk_policy_registry: dict[str, Any] | None = None,
    cost_liquidity_registry: dict[str, Any] | None = None,
    pretrade_risk_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Commit manifest body.

    ``schema_version`` moves to 1.1 for the three fields #1744 adds: ``commit_seq``
    (the only ordering signal available — ``documents`` has no timestamp column),
    ``supersedes`` (fingerprints of the same-date books this commit replaced) and
    ``pruned_tickers`` (rows deleted because the new book dropped them). Readers of
    1.0 manifests must treat all three as absent, which ``manifest_commit_seq``
    already does.

    ``schema_version`` moves to 1.2 for the three the authoritative commit chain adds
    (#2418): ``ledger_commit_id`` is the manifest's only pointer into the append-only
    lineage, and the two symbol lists name what the chain deliberately left out — a
    symbol frozen by an existing fill, and one with no close to price a share count
    against. All three are ``None``/empty when the ledger kill switch is off, which is
    exactly how a 1.1 reader already sees them.

    ``schema_version`` 1.3 adds optional forecast-registry artifact fields (#2663):
    status/counts only — never forecast math or prompt bodies. WP5.4 extends the
    same block with shadow calibration write counts (#2684).

    ``schema_version`` 1.4 adds optional H8 risk-policy snapshot registry fields
    (#2698 / WP6.3): status/counts only — never matrix math or sizing inputs.

    ``schema_version`` 1.5 adds optional cost/liquidity registry fields (#2709 / WP7.3):
    status/counts only — never cost math or turnover inputs.

    ``schema_version`` 1.6 adds optional pre-trade risk report registry fields
    (#2754 / WP9.4): report id/hash + write counts — never recomputed risk math.
    """
    payload: dict[str, Any] = {
        "schema_version": "1.6",
        "source_run_id": source_run_id,
        "status": status,
        "weights_fingerprint": weights_fingerprint(weights),
        "weights": {k: round(v, 4) for k, v in sorted(weights.items())},
        "nav": nav,
        "decision_log_rows": decision_log_rows,
        "commit_seq": commit_seq,
        "supersedes": list(supersedes or []),
        "pruned_tickers": list(pruned_tickers or []),
        "ledger_commit_id": ledger.commit_id if ledger else None,
        "ledger_frozen_symbols": list(ledger.frozen_symbols) if ledger else [],
        "ledger_unpriced_symbols": list(ledger.unpriced_symbols) if ledger else [],
    }
    if forecast_registry:
        payload.update(forecast_registry)
    if risk_policy_registry:
        payload.update(risk_policy_registry)
    if cost_liquidity_registry:
        payload.update(cost_liquidity_registry)
    if pretrade_risk_registry:
        payload.update(pretrade_risk_registry)
    return payload


def build_commit_run_node(deps: CommitRunDeps):
    """Return the H9 commit node bound to ``deps``."""

    def commit_run(state: PortfolioState) -> dict[str, Any]:
        book = sized_book(state)
        if book is None:
            if state.phase_portfolio.pm_direction_memo is not None:
                return _phase_error(
                    "sized_book missing but H7 pm_direction_memo present — H8 risk sizing required"
                )
            return {}

        source_run_id = str(state.run_id)
        weights = weights_from_sized_book(book)
        current_fp = weights_fingerprint(weights)

        # Date-scoped, not run_id-scoped (#1744): run_id is a fresh uuid4 per process.
        priors = load_commit_manifests(
            client=deps.client,
            run_date=state.run_date,
            workspace_id=getattr(state.config, "workspace_id", None),
        )
        latest, commit_seq = resolve_prior_commit(priors)

        # WP9.4: validate report identity before booking. Enforce rejects incomplete
        # commits; shadow records status without blocking. H9 never builds the report.
        pretrade_validation = validate_pretrade_risk_report(state, weights)
        if not pretrade_validation.ok and pretrade_validation.mode is PreTradeRiskMode.ENFORCE:
            return _phase_error(
                f"pre_trade_risk_report validation failed: {pretrade_validation.reason}"
            )

        if latest is not None and latest.get("weights_fingerprint") == current_fp:
            # Same date, same book, already on disk — genuinely idempotent.
            # Still attempt forecast registry (fail-soft): a prior commit may have
            # booked while registry was degraded (#2663). Cost registry needs the
            # prior ledger_commit_id the same way (#2807 / WP7) — ledger=None would
            # permanently skip as ledger_disabled after a degraded first write.
            registry = _persist_forecast_registry(client=deps.client, state=state)
            risk_registry = _persist_risk_policy_registry(client=deps.client, state=state)
            prior_commit_id = latest.get("ledger_commit_id")
            ledger_for_retry: LedgerAppend | None = None
            if prior_commit_id:
                ledger_for_retry = LedgerAppend(
                    commit_id=str(prior_commit_id),
                    frozen_symbols=list(latest.get("ledger_frozen_symbols") or []),
                    unpriced_symbols=list(latest.get("ledger_unpriced_symbols") or []),
                )
            cost_registry, _, _ = _persist_cost_liquidity_registry(
                client=deps.client,
                state=state,
                ledger=ledger_for_retry,
            )
            pretrade_registry = persist_validated_pretrade_risk_report(
                client=deps.client,
                validation=pretrade_validation,
                source_run_id=source_run_id,
                ledger_commit_id=str(prior_commit_id) if prior_commit_id else None,
            )
            manifest = _manifest_payload(
                source_run_id=source_run_id,
                status="noop",
                weights=weights,
                nav=latest.get("nav"),
                decision_log_rows=int(latest.get("decision_log_rows") or 0),
                commit_seq=manifest_commit_seq(latest),
                supersedes=[],
                forecast_registry=registry,
                risk_policy_registry=risk_registry,
                cost_liquidity_registry=cost_registry,
                pretrade_risk_registry=pretrade_registry,
            )
            return {"phase_portfolio": PhasePortfolioState(commit_manifest=manifest)}

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
        # Forecast registry is AFTER booking and fail-soft: a registry outage keeps
        # the one committed book and must not trigger a rebook (#2663).
        registry = _persist_forecast_registry(client=deps.client, state=state)
        risk_registry = _persist_risk_policy_registry(client=deps.client, state=state)
        brief = publish_portfolio_brief(client=deps.client, state=state, book=book)
        portfolio_docs = publish_portfolio_documents(client=deps.client, state=state)
        n_decisions = persist_decision_log(client=deps.client, state=state)

        # Before ``save_commit_manifest``, deliberately. The manifest is what the next
        # attempt reads to decide "already committed", so a partial chain must leave no
        # manifest behind — otherwise a failed append reports as a clean no-op and the
        # lineage is silently short a commit. Raising here is the honest outcome.
        h8_adjustments = [
            SizingAdjustment.model_validate(event) for event in (book.get("adjustments") or [])
        ]
        h8_requested = {
            str(ticker): float(pct) for ticker, pct in (book.get("requested_pct") or {}).items()
        }
        ledger = append_commit_chain(
            client=deps.client,
            state=state,
            weights=booked.weights,
            cash_pct=booked.cash_pct,
            nav=booked.nav,
            adjustments=h8_adjustments,
            requested_pct=h8_requested,
        )
        cost_registry, cost_snapshots, cost_estimates = _persist_cost_liquidity_registry(
            client=deps.client,
            state=state,
            ledger=ledger,
        )
        ledger_commit_uuid: UUID | None = None
        if ledger is not None and ledger.commit_id:
            ledger_commit_uuid = UUID(ledger.commit_id)
        pretrade_registry = persist_validated_pretrade_risk_report(
            client=deps.client,
            validation=pretrade_validation,
            source_run_id=source_run_id,
            ledger_commit_id=ledger_commit_uuid,
        )

        manifest = _manifest_payload(
            source_run_id=source_run_id,
            status="committed",
            weights=booked.weights,
            nav=booked.nav,
            decision_log_rows=n_decisions,
            commit_seq=commit_seq,
            supersedes=superseded,
            pruned_tickers=booked.pruned_tickers,
            ledger=ledger,
            forecast_registry=registry,
            risk_policy_registry=risk_registry,
            cost_liquidity_registry=cost_registry,
            pretrade_risk_registry=pretrade_registry,
        )
        save_commit_manifest(client=deps.client, state=state, manifest=manifest)

        logger.info(
            "h9 commit_run: booked %d positions, nav=%.4f, %d decision_log rows, "
            "%d pruned (run_id=%s, commit_seq=%d, forecast_registry=%s, "
            "cost_liquidity_registry=%s, pretrade_risk_registry=%s)",
            len(booked.position_rows),
            booked.nav,
            n_decisions,
            len(booked.pruned_tickers),
            source_run_id,
            commit_seq,
            registry.get("forecast_registry_status"),
            cost_registry.get("cost_liquidity_registry_status"),
            pretrade_registry.get("pretrade_risk_registry_status"),
        )
        phase_portfolio = PhasePortfolioState(
            commit_manifest=manifest,
            liquidity_snapshots=cost_snapshots,
            action_cost_estimates=cost_estimates,
        )
        return {
            "phase_portfolio": phase_portfolio,
            "published": [brief, *portfolio_docs],
        }

    return commit_run


def build_h9_commit_run(deps: CommitRunDeps | None = None) -> PipelinePhase:
    """Wrap H9 into a single-node ``PipelinePhase``."""

    def _noop(_state: PortfolioState) -> dict[str, Any]:
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
