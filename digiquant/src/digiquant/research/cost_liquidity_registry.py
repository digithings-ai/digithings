"""Private append-only cost/liquidity evidence registry (#2709 / WP7.3).

Persists immutable LiquiditySnapshot, ActionCostEstimate, and ActionCostOutcome rows
from migration ``082_olympus_cost_liquidity.sql``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

from digiquant.dashboard.temporal import require_utc_datetime
from digiquant.portfolio.action_cost_inputs import (
    ActionCostBindingError,
    realized_cost_input_from_execution,
)
from digiquant.portfolio.cost_liquidity import CostLiquidityBundle, compare_action_cost
from digiquant.portfolio.h9_cost_evidence import (
    build_cost_bundles_for_commit,
    investor_currency_from_state,
)
from digiquant.portfolio.models.cost_liquidity import (
    ActionCostEstimate,
    ActionCostOutcome,
    LiquiditySnapshot,
)
from digiquant.portfolio.models.portfolio_ledger import DecisionIntent, PaperExecution
from digiquant.portfolio.models.risk_policy import RiskPolicy
from digiquant.research.supabase_io import SupabaseClient

logger = logging.getLogger(__name__)

LIQUIDITY_SNAPSHOTS = "olympus_liquidity_snapshots"
ACTION_COST_ESTIMATES = "olympus_action_cost_estimates"
ACTION_COST_OUTCOMES = "olympus_action_cost_outcomes"
PAPER_EXECUTIONS = "portfolio_ledger_paper_executions"
DECISION_INTENTS = "portfolio_ledger_decision_intents"
REQUESTED_TARGETS = "portfolio_ledger_requested_targets"


class CostLiquidityRegistryConflict(RuntimeError):
    """Same identity already stored with a different content hash."""


class CostLiquidityRegistryError(RuntimeError):
    """Registry persistence refused or left an inconsistent state."""


class _WriteKind(StrEnum):
    WRITTEN = "written"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class CostRegistryWriteResult:
    """Outcome of one cost/liquidity registry write pass."""

    snapshots_written: int = 0
    snapshots_skipped: int = 0
    estimates_written: int = 0
    estimates_skipped: int = 0
    outcomes_written: int = 0
    outcomes_skipped: int = 0
    degraded_reason: str | None = None
    conflicts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.degraded_reason is None and not self.conflicts


@dataclass(frozen=True)
class OutcomeResolveResult:
    """Counts from one resolve_realized_action_cost_outcomes pass."""

    resolved: int = 0
    pending: int = 0
    skipped: int = 0
    conflicts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.conflicts


def _insert(*, client: SupabaseClient, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    client.table(table).insert(rows).execute()


def _fetch_by_id(
    *,
    client: SupabaseClient,
    table: str,
    id_column: str,
    row_id: UUID | str,
) -> dict[str, Any] | None:
    resp = client.table(table).select("*").eq(id_column, str(row_id)).limit(1).execute()
    rows = list(getattr(resp, "data", None) or [])
    return rows[0] if rows else None


def _content_matches(existing: dict[str, Any], expected_hash: str) -> bool:
    return str(existing.get("content_hash") or "") == expected_hash


def _parse_timestamp(raw: Any, *, field_name: str) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return require_utc_datetime(raw, field_name=field_name)
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return require_utc_datetime(datetime.fromisoformat(text), field_name=field_name)


def _snapshot_row(*, snapshot: LiquiditySnapshot, order_intent_id: UUID) -> dict[str, Any]:
    return {
        "snapshot_id": str(snapshot.snapshot_id),
        "method_version": snapshot.method_version,
        "symbol": snapshot.symbol.strip().upper(),
        "as_of_session": snapshot.as_of_session.isoformat(),
        "order_intent_id": str(order_intent_id),
        "status": snapshot.status.value,
        "unavailable_reason": snapshot.unavailable_reason,
        "content_hash": snapshot.content_hash,
        "resolved_at": snapshot.resolved_at.isoformat(),
        "snapshot_body": snapshot.model_dump(mode="json"),
    }


def _estimate_row(estimate: ActionCostEstimate) -> dict[str, Any]:
    return {
        "estimate_id": str(estimate.estimate_id),
        "order_intent_id": str(estimate.order_intent_id),
        "portfolio_commit_id": str(estimate.portfolio_commit_id),
        "policy_id": str(estimate.policy_id),
        "liquidity_snapshot_id": str(estimate.liquidity_snapshot_id),
        "symbol": estimate.symbol.strip().upper(),
        "status": estimate.status.value,
        "unavailable_reason": estimate.unavailable_reason,
        "content_hash": estimate.content_hash,
        "effective_at": estimate.effective_at.isoformat(),
        "estimated_at": estimate.estimated_at.isoformat(),
        "estimate_body": estimate.model_dump(mode="json"),
    }


def _outcome_row(outcome: ActionCostOutcome) -> dict[str, Any]:
    return {
        "outcome_id": str(outcome.outcome_id),
        "estimate_id": str(outcome.estimate_id),
        "execution_id": str(outcome.execution_id),
        "order_intent_id": (
            str(outcome.order_intent_id) if outcome.order_intent_id is not None else None
        ),
        "status": outcome.status.value,
        "unavailable_reason": outcome.unavailable_reason,
        "content_hash": outcome.content_hash,
        "compared_at": outcome.compared_at.isoformat(),
        "outcome_body": outcome.model_dump(mode="json"),
    }


def _persist_snapshot(
    *,
    client: SupabaseClient,
    snapshot: LiquiditySnapshot,
    order_intent_id: UUID,
) -> _WriteKind:
    existing = _fetch_by_id(
        client=client,
        table=LIQUIDITY_SNAPSHOTS,
        id_column="snapshot_id",
        row_id=snapshot.snapshot_id,
    )
    if existing is not None:
        if _content_matches(existing, snapshot.content_hash):
            return _WriteKind.SKIPPED
        raise CostLiquidityRegistryConflict(
            f"snapshot_id {snapshot.snapshot_id} exists with different content_hash"
        )
    _insert(
        client=client,
        table=LIQUIDITY_SNAPSHOTS,
        rows=[_snapshot_row(snapshot=snapshot, order_intent_id=order_intent_id)],
    )
    return _WriteKind.WRITTEN


def _persist_estimate(*, client: SupabaseClient, estimate: ActionCostEstimate) -> _WriteKind:
    existing = _fetch_by_id(
        client=client,
        table=ACTION_COST_ESTIMATES,
        id_column="estimate_id",
        row_id=estimate.estimate_id,
    )
    if existing is not None:
        if _content_matches(existing, estimate.content_hash):
            return _WriteKind.SKIPPED
        raise CostLiquidityRegistryConflict(
            f"estimate_id {estimate.estimate_id} exists with different content_hash"
        )
    snapshot_row = _fetch_by_id(
        client=client,
        table=LIQUIDITY_SNAPSHOTS,
        id_column="snapshot_id",
        row_id=estimate.liquidity_snapshot_id,
    )
    if snapshot_row is None:
        raise CostLiquidityRegistryError(
            f"estimate {estimate.estimate_id} references missing snapshot "
            f"{estimate.liquidity_snapshot_id}"
        )
    _insert(client=client, table=ACTION_COST_ESTIMATES, rows=[_estimate_row(estimate)])
    return _WriteKind.WRITTEN


def _persist_outcome(*, client: SupabaseClient, outcome: ActionCostOutcome) -> _WriteKind:
    existing = _fetch_by_id(
        client=client,
        table=ACTION_COST_OUTCOMES,
        id_column="outcome_id",
        row_id=outcome.outcome_id,
    )
    if existing is not None:
        if _content_matches(existing, outcome.content_hash):
            return _WriteKind.SKIPPED
        raise CostLiquidityRegistryConflict(
            f"outcome_id {outcome.outcome_id} exists with different content_hash"
        )
    estimate_row = _fetch_by_id(
        client=client,
        table=ACTION_COST_ESTIMATES,
        id_column="estimate_id",
        row_id=outcome.estimate_id,
    )
    if estimate_row is None:
        raise CostLiquidityRegistryError(
            f"outcome {outcome.outcome_id} references missing estimate {outcome.estimate_id}"
        )
    _insert(client=client, table=ACTION_COST_OUTCOMES, rows=[_outcome_row(outcome)])
    return _WriteKind.WRITTEN


def persist_cost_liquidity_bundle(
    *,
    client: SupabaseClient,
    bundle: CostLiquidityBundle,
) -> CostRegistryWriteResult:
    """Append one liquidity snapshot and one action cost estimate."""
    s_written = s_skipped = e_written = e_skipped = 0
    order_id = bundle.estimate.order_intent_id

    try:
        kind = _persist_snapshot(
            client=client,
            snapshot=bundle.liquidity_snapshot,
            order_intent_id=order_id,
        )
    except CostLiquidityRegistryConflict as exc:
        return CostRegistryWriteResult(conflicts=(str(exc),), degraded_reason="content_conflict")
    if kind is _WriteKind.WRITTEN:
        s_written += 1
    else:
        s_skipped += 1

    try:
        kind = _persist_estimate(client=client, estimate=bundle.estimate)
    except CostLiquidityRegistryConflict as exc:
        return CostRegistryWriteResult(
            snapshots_written=s_written,
            snapshots_skipped=s_skipped,
            conflicts=(str(exc),),
            degraded_reason="content_conflict",
        )
    except CostLiquidityRegistryError as exc:
        return CostRegistryWriteResult(
            snapshots_written=s_written,
            snapshots_skipped=s_skipped,
            degraded_reason=str(exc),
        )
    if kind is _WriteKind.WRITTEN:
        e_written += 1
    else:
        e_skipped += 1

    return CostRegistryWriteResult(
        snapshots_written=s_written,
        snapshots_skipped=s_skipped,
        estimates_written=e_written,
        estimates_skipped=e_skipped,
    )


def persist_cost_liquidity_bundles(
    *,
    client: SupabaseClient,
    bundles: list[CostLiquidityBundle],
) -> CostRegistryWriteResult:
    """Persist many bundles; first conflict stops the batch."""
    total = CostRegistryWriteResult()
    for bundle in bundles:
        result = persist_cost_liquidity_bundle(client=client, bundle=bundle)
        total = CostRegistryWriteResult(
            snapshots_written=total.snapshots_written + result.snapshots_written,
            snapshots_skipped=total.snapshots_skipped + result.snapshots_skipped,
            estimates_written=total.estimates_written + result.estimates_written,
            estimates_skipped=total.estimates_skipped + result.estimates_skipped,
            degraded_reason=result.degraded_reason,
            conflicts=total.conflicts + result.conflicts,
        )
        if not result.ok:
            break
    return total


def get_liquidity_snapshot(
    *,
    client: SupabaseClient,
    snapshot_id: UUID,
    knowledge_cutoff_at: datetime,
) -> LiquiditySnapshot | None:
    """Exact-ID read; invisible when resolved_at is after the pinned cutoff."""
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    row = _fetch_by_id(
        client=client,
        table=LIQUIDITY_SNAPSHOTS,
        id_column="snapshot_id",
        row_id=snapshot_id,
    )
    if row is None:
        return None
    resolved = _parse_timestamp(row.get("resolved_at"), field_name="resolved_at")
    if resolved is None or resolved > cutoff:
        return None
    body = row.get("snapshot_body")
    if isinstance(body, dict):
        return LiquiditySnapshot.model_validate(body)
    return LiquiditySnapshot.model_validate(row)


def get_action_cost_estimate(
    *,
    client: SupabaseClient,
    estimate_id: UUID,
    knowledge_cutoff_at: datetime,
) -> ActionCostEstimate | None:
    """Exact-ID read; invisible when effective_at is after the pinned cutoff."""
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    row = _fetch_by_id(
        client=client,
        table=ACTION_COST_ESTIMATES,
        id_column="estimate_id",
        row_id=estimate_id,
    )
    if row is None:
        return None
    effective = _parse_timestamp(row.get("effective_at"), field_name="effective_at")
    if effective is None or effective > cutoff:
        return None
    body = row.get("estimate_body")
    if isinstance(body, dict):
        return ActionCostEstimate.model_validate(body)
    return ActionCostEstimate.model_validate(row)


def get_action_cost_outcome(
    *,
    client: SupabaseClient,
    outcome_id: UUID,
    knowledge_cutoff_at: datetime,
) -> ActionCostOutcome | None:
    """Exact-ID read; invisible when compared_at is after the pinned cutoff."""
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    row = _fetch_by_id(
        client=client,
        table=ACTION_COST_OUTCOMES,
        id_column="outcome_id",
        row_id=outcome_id,
    )
    if row is None:
        return None
    compared = _parse_timestamp(row.get("compared_at"), field_name="compared_at")
    if compared is None or compared > cutoff:
        return None
    body = row.get("outcome_body")
    if isinstance(body, dict):
        return ActionCostOutcome.model_validate(body)
    return ActionCostOutcome.model_validate(row)


def collect_risk_policy_from_state(state: Any) -> RiskPolicy | None:
    """Extract resolved risk policy from portfolio phase state."""
    portfolio = getattr(state, "phase_portfolio", None)
    if portfolio is None:
        return None
    raw = getattr(portfolio, "risk_policy", None)
    if not isinstance(raw, dict):
        return None
    try:
        return RiskPolicy.model_validate(raw)
    except Exception as exc:
        logger.warning(
            "cost liquidity registry: skipping invalid risk policy (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return None


def persist_action_cost_estimates_for_commit(
    *,
    client: SupabaseClient,
    state: Any,
    commit_id: UUID,
) -> CostRegistryWriteResult:
    """Build and persist estimates after authoritative order intents exist."""
    policy = collect_risk_policy_from_state(state)
    if policy is None:
        return CostRegistryWriteResult(degraded_reason="missing_risk_policy")
    if investor_currency_from_state(state) is None:
        return CostRegistryWriteResult(degraded_reason="currency_missing")
    try:
        bundles = build_cost_bundles_for_commit(
            client=client,
            state=state,
            commit_id=commit_id,
            policy=policy,
        )
    except Exception as exc:
        logger.warning(
            "cost liquidity registry: bundle build failed (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return CostRegistryWriteResult(degraded_reason=f"{type(exc).__name__}: {exc}"[:300])
    return persist_cost_liquidity_bundles(client=client, bundles=bundles)


def collect_cost_artifacts_from_bundles(
    bundles: list[CostLiquidityBundle],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Serialize bundles for typed portfolio state attachment."""
    snapshots: dict[str, dict[str, Any]] = {}
    estimates: dict[str, dict[str, Any]] = {}
    for bundle in bundles:
        snapshots[str(bundle.liquidity_snapshot.snapshot_id)] = (
            bundle.liquidity_snapshot.model_dump(mode="json")
        )
        estimates[str(bundle.estimate.order_intent_id)] = bundle.estimate.model_dump(mode="json")
    return snapshots, estimates


def _decision_for_order(
    *,
    client: SupabaseClient,
    order_intent_id: UUID,
) -> DecisionIntent | None:
    order_row = _fetch_by_id(
        client=client,
        table="portfolio_ledger_order_intents",
        id_column="id",
        row_id=order_intent_id,
    )
    if order_row is None:
        return None
    approved_id = str(order_row.get("approved_target_id") or "")
    if not approved_id:
        return None
    approved = _fetch_by_id(
        client=client,
        table="portfolio_ledger_approved_targets",
        id_column="id",
        row_id=approved_id,
    )
    if approved is None:
        return None
    requested_id = str(approved.get("requested_target_id") or "")
    if not requested_id:
        return None
    requested = _fetch_by_id(
        client=client,
        table=REQUESTED_TARGETS,
        id_column="id",
        row_id=requested_id,
    )
    if requested is None:
        return None
    decision_id = str(requested.get("decision_intent_id") or "")
    if not decision_id:
        return None
    decision_row = _fetch_by_id(
        client=client,
        table=DECISION_INTENTS,
        id_column="id",
        row_id=decision_id,
    )
    if decision_row is None:
        return None
    return DecisionIntent.model_validate(decision_row)


def _existing_outcome_for_execution(
    *,
    client: SupabaseClient,
    estimate_id: UUID,
    execution_id: UUID,
) -> dict[str, Any] | None:
    resp = (
        client.table(ACTION_COST_OUTCOMES)
        .select("*")
        .eq("estimate_id", str(estimate_id))
        .eq("execution_id", str(execution_id))
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    return rows[0] if rows else None


def resolve_realized_action_cost_outcomes(
    *,
    client: SupabaseClient,
    run_date: date,
    knowledge_cutoff_at: datetime,
    currency: str | None = None,
) -> OutcomeResolveResult:
    """Compare persisted estimates with authoritative fills when they arrive."""
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    resp = (
        client.table(ACTION_COST_ESTIMATES)
        .select("*")
        .lte("effective_at", cutoff.isoformat())
        .execute()
    )
    estimates_rows = list(getattr(resp, "data", None) or [])
    if not estimates_rows:
        return OutcomeResolveResult()

    exec_resp = (
        client.table(PAPER_EXECUTIONS)
        .select("*")
        .eq("executed_date", run_date.isoformat())
        .execute()
    )
    executions_by_order: dict[str, dict[str, Any]] = {}
    for row in exec_resp.data or []:
        oid = str(row.get("order_intent_id") or "")
        if oid:
            executions_by_order[oid] = row

    resolved = pending = skipped = 0
    conflicts: list[str] = []
    currency_code = (currency or "USD").strip().upper()

    for est_row in estimates_rows:
        body = est_row.get("estimate_body")
        if isinstance(body, dict):
            estimate = ActionCostEstimate.model_validate(body)
        else:
            try:
                estimate = ActionCostEstimate.model_validate(est_row)
            except Exception:
                skipped += 1
                continue

        order_key = str(estimate.order_intent_id)
        exec_row = executions_by_order.get(order_key)
        if exec_row is None:
            pending += 1
            continue

        execution = PaperExecution.model_validate(exec_row)
        existing = _existing_outcome_for_execution(
            client=client,
            estimate_id=estimate.estimate_id,
            execution_id=execution.id,
        )
        if existing is not None:
            skipped += 1
            continue

        decision = _decision_for_order(client=client, order_intent_id=estimate.order_intent_id)
        if decision is None:
            pending += 1
            continue

        try:
            realized = realized_cost_input_from_execution(
                execution=execution,
                decision=decision,
                order_intent_id=estimate.order_intent_id,
                currency=currency_code,
            )
        except ActionCostBindingError as exc:
            logger.info(
                "cost outcomes: skip order %s (%s)",
                estimate.order_intent_id,
                exc,
            )
            pending += 1
            continue

        outcome = compare_action_cost(estimate, realized, compared_at=datetime.now(tz=UTC))
        try:
            kind = _persist_outcome(client=client, outcome=outcome)
        except CostLiquidityRegistryConflict as exc:
            conflicts.append(str(exc))
            return OutcomeResolveResult(
                resolved=resolved,
                pending=pending,
                skipped=skipped,
                conflicts=tuple(conflicts),
            )
        except CostLiquidityRegistryError as exc:
            conflicts.append(str(exc))
            return OutcomeResolveResult(
                resolved=resolved,
                pending=pending,
                skipped=skipped,
                conflicts=tuple(conflicts),
            )
        if kind is _WriteKind.WRITTEN:
            resolved += 1
        else:
            skipped += 1

    return OutcomeResolveResult(
        resolved=resolved,
        pending=pending,
        skipped=skipped,
        conflicts=tuple(conflicts),
    )


def resolve_realized_action_cost_outcomes_from_state(
    *,
    client: SupabaseClient,
    state: Any,
) -> OutcomeResolveResult:
    """Preflight entry — uses pinned cutoff and portfolio currency from state."""
    cutoff = getattr(state, "knowledge_cutoff_at", None)
    if cutoff is None:
        return OutcomeResolveResult()
    run_date = getattr(state, "run_date", None)
    if run_date is None:
        return OutcomeResolveResult()
    currency = investor_currency_from_state(state)
    if currency is None:
        logger.info("cost liquidity registry: currency_missing — skipping outcome resolve")
        return OutcomeResolveResult()
    return resolve_realized_action_cost_outcomes(
        client=client,
        run_date=run_date,
        knowledge_cutoff_at=cutoff,
        currency=currency,
    )


__all__ = [
    "ACTION_COST_ESTIMATES",
    "ACTION_COST_OUTCOMES",
    "LIQUIDITY_SNAPSHOTS",
    "CostLiquidityRegistryConflict",
    "CostLiquidityRegistryError",
    "CostRegistryWriteResult",
    "OutcomeResolveResult",
    "collect_cost_artifacts_from_bundles",
    "collect_risk_policy_from_state",
    "get_action_cost_estimate",
    "get_action_cost_outcome",
    "get_liquidity_snapshot",
    "persist_action_cost_estimates_for_commit",
    "persist_cost_liquidity_bundle",
    "persist_cost_liquidity_bundles",
    "resolve_realized_action_cost_outcomes",
    "resolve_realized_action_cost_outcomes_from_state",
]
