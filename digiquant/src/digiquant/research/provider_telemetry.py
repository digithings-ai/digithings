"""Durable append-only writer for dashboard provider telemetry (#1979, Task 1.5).

Drains one run's in-process telemetry buffers from ``digigraph.usage`` and appends them to the
private ledger migration ``067_olympus_provider_telemetry.sql`` created: ``olympus_node_runs``,
``olympus_provider_calls``, ``olympus_provider_attempts``.

Three properties of that ledger shape everything here.

**It is append-only with no correction path.** ``reject_olympus_provider_telemetry_mutation()``
raises unconditionally on ``BEFORE UPDATE OR DELETE`` per row and ``BEFORE TRUNCATE`` per
statement, with no role exemption, and ``service_role`` holds only ``SELECT`` and ``INSERT``. A
malformed row can never be repaired or removed — only superseded by appending another. So every
record is re-validated through its Pydantic model immediately before insert, and a record that
fails is counted and dropped rather than written.

**Three foreign keys make an incomplete batch unpersistable, not merely incomplete.**
``olympus_provider_calls.node_run_id`` references ``olympus_node_runs``,
``olympus_provider_calls.parent_call_id`` self-references, and
``olympus_provider_attempts.call_id`` references ``olympus_provider_calls``. A record whose
referent is absent from this flush is *quarantined* — counted and reported as incomplete
coverage — never submitted. Quarantine is decided per record, not per flush, because the real
production shape is mixed (see below).

**Telemetry is never a dependency of portfolio completion.** Every insert is independently
fail-soft. A failed flush is a logged, counted condition; it cannot change the run's return
value, its exit code, the portfolio commit, or the ``atlas_run_diagnostics`` aggregate row.

Production shape as of #1982 (Task 1.4)
---------------------------------------
Two gates decide whether a provider call is attributed or orphaned:

1. The run needs an identifier. ``node_run_scope`` yields ``None`` when ``active_run_id()`` is
   ``None``, and ``chain.py`` only supplies one when ``deps.diagnostics is not None``. Without
   it, no node runs and no logical calls are produced *at the source* — but physical attempts
   still are, because ``_emit_attempt`` guards only on a missing observer.
2. The call must originate inside a ``build_pipeline`` node, since only ``_instrumented`` opens
   a node scope. research phases, portfolio phases, and the publish terminal phase all qualify. The
   beliefs-distillation fold does not: ``chain.py`` calls it directly, outside any graph. When
   the fold calls an LLM (daily short fold with new lessons, or a full rewrite), those provider
   calls are orphaned. Empty-lesson carry-forward makes no provider call.

So a flush can carry attributed records and orphaned attempts *together*, and eligibility is
therefore decided per record rather than per flush.

One consequence for reconciliation. ``usage.record`` gates only on capture being active
(``usage.py:279``), while a ``ProviderCallRecord`` additionally needs an open node scope. So the
aggregate counts calls the detailed side structurally cannot see, and whenever an un-scoped call
happens the detailed counts are a strict *subset* of the aggregate. A detailed count BELOW the
aggregate is therefore explainable; a detailed count ABOVE it never is. ``_log_result`` says
which of the two it saw rather than reporting a bare disagreement.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import (
    Any,  # score:allow untyped any — scored-lint: duck-typed Supabase client
    Literal,
    Mapping,
    Sequence,
)
from uuid import UUID

from digillm import (
    ArtifactRef,
    NodeRunRecord,
    ProviderAttemptRecord,
    ProviderCallRecord,
)
from pydantic import ValidationError

logger = logging.getLogger(__name__)

NODE_RUNS_TABLE = "olympus_node_runs"
PROVIDER_CALLS_TABLE = "olympus_provider_calls"
PROVIDER_ATTEMPTS_TABLE = "olympus_provider_attempts"

#: The keys ``detailed_usage_projection()`` and ``snapshot()`` both report, and the only ones a
#: reconciliation claim may be made about. Everything else exists on one side only.
RECONCILED_KEYS: tuple[str, ...] = (
    "llm_calls",
    "prompt_tokens",
    "completion_tokens",
    "cost_usd",
    "search_calls",
)

ReconciliationStatus = Literal["reconciled", "mismatched", "unavailable"]

# Double-flush guard, keyed by (run_id, attempt). `pipeline-digiquant.yml` retries the chain up to
# three times inside ONE job, so run_id alone is not unique within a process — the attempt number
# is what distinguishes them, exactly as it does for the `atlas_run_diagnostics` conflict key.
# Bounded because nothing else prunes it; a chain process handles a handful of attempts and exits,
# and the cap only matters to a long-lived host that imports this module.
_GUARD_LOCK = threading.Lock()
_FLUSHED: dict[tuple[str, int], None] = {}
_FLUSHED_MAX = 256


def _claim_flush(key: tuple[str, int]) -> bool:
    """Claim the right to flush ``key`` once. ``False`` means someone already did.

    Claimed *before* the inserts run, not after they succeed. That is deliberate and is the
    opposite of the usual retry-friendly ordering: because the ledger admits no deletes, a batch
    that landed halfway cannot be undone, so re-running the flush would duplicate whatever did
    land. One permanently incomplete record set is recoverable evidence; two overlapping partial
    ones are not.
    """
    with _GUARD_LOCK:
        if key in _FLUSHED:
            return False
        _FLUSHED[key] = None
        while len(_FLUSHED) > _FLUSHED_MAX:
            _FLUSHED.pop(next(iter(_FLUSHED)))
        return True


def reset_flush_guard() -> None:
    """Forget every claimed flush. For tests; production claims once per process attempt."""
    with _GUARD_LOCK:
        _FLUSHED.clear()


@dataclass(frozen=True)
class TierResult:
    """Outcome of appending one table's worth of records."""

    table: str
    buffered: int
    submitted: int
    inserted: int
    quarantined: int
    rejected: int
    error_type: str | None = None

    @property
    def ok(self) -> bool:
        """The submitted rows all landed. Says nothing about what was held back."""
        return self.error_type is None and self.inserted == self.submitted

    @property
    def complete(self) -> bool:
        """Every buffered record landed — nothing quarantined, rejected, or lost."""
        return self.ok and self.inserted == self.buffered


@dataclass(frozen=True)
class ReconciliationResult:
    """Whether the detailed records account for the aggregate the run already reports.

    ``unavailable`` is a distinct state from ``mismatched`` on purpose (plan Invariant 4). A
    provider that omits usage or cost leaves ``_nullable_sum`` returning ``None``, and ``None``
    must propagate as *unknown* rather than collapse to ``0`` — a fabricated zero would read as
    "this run cost nothing", which is the exact false claim the ledger exists to prevent.
    """

    status: ReconciliationStatus
    detailed: Mapping[str, int | float | None]
    aggregate: Mapping[str, int | float | None]
    unavailable_keys: tuple[str, ...]
    mismatched_keys: tuple[str, ...]
    attempts_missing_usage: int
    attempts_missing_cost: int

    @property
    def billing_exact(self) -> bool:
        """Whether an exact-billing claim is permitted. Only a full match earns it."""
        return self.status == "reconciled"


@dataclass(frozen=True)
class FlushResult:
    """What one run's flush actually achieved, including everything it could not do."""

    run_id: str
    attempt: int
    node_runs: TierResult
    provider_calls: TierResult
    provider_attempts: TierResult
    reconciliation: ReconciliationResult
    skipped: str | None = None

    @property
    def tiers(self) -> tuple[TierResult, ...]:
        return (self.node_runs, self.provider_calls, self.provider_attempts)

    @property
    def inserted_total(self) -> int:
        return sum(tier.inserted for tier in self.tiers)

    @property
    def withheld_total(self) -> int:
        """Records held back rather than written: quarantined referents plus rejected records."""
        return sum(tier.quarantined + tier.rejected for tier in self.tiers)

    @property
    def complete(self) -> bool:
        """Every buffered record in every tier reached the ledger."""
        return self.skipped is None and all(tier.complete for tier in self.tiers)

    @property
    def partially_written(self) -> bool:
        """Some rows landed while another tier failed outright.

        The ledger is now permanently inconsistent and cannot be repaired — no UPDATE, no DELETE,
        no TRUNCATE. This is reported rather than fixed, because reporting is the only available
        action. A reader must treat the affected run's detail as partial evidence.
        """
        return self.inserted_total > 0 and any(tier.error_type is not None for tier in self.tiers)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _artifact_rows(artifacts: Sequence[ArtifactRef]) -> list[dict[str, str]]:
    return [
        {
            "artifact_type": ref.artifact_type,
            "artifact_id": ref.artifact_id,
            "version": ref.version,
        }
        for ref in artifacts
    ]


def _node_run_row(record: NodeRunRecord) -> dict[str, Any]:
    return {
        "node_run_id": str(record.node_run_id),
        "run_id": record.run_id,
        "node_name": record.node_name,
        "fanout_key": record.fanout_key,
        "outcome": record.outcome.value,
        "artifacts": _artifact_rows(record.artifacts),
        "started_at": _iso(record.started_at),
        "finished_at": _iso(record.finished_at),
    }


def _provider_call_row(record: ProviderCallRecord) -> dict[str, Any]:
    return {
        "call_id": str(record.call_id),
        "node_run_id": str(record.node_run_id),
        "parent_call_id": str(record.parent_call_id) if record.parent_call_id else None,
        "purpose": record.purpose.value,
        "requested_model": record.requested_model,
        "cache_status": record.cache_status.value,
        "outcome": record.outcome.value,
        "attempt_count": record.attempt_count,
        "artifacts": _artifact_rows(record.artifacts),
        "no_artifact_reason": (
            record.no_artifact_reason.value if record.no_artifact_reason is not None else None
        ),
        "error_type": record.error_type,
        "started_at": _iso(record.started_at),
        "finished_at": _iso(record.finished_at),
    }


def _provider_attempt_row(record: ProviderAttemptRecord) -> dict[str, Any]:
    return {
        "attempt_id": str(record.attempt_id),
        "call_id": str(record.call_id),
        "attempt_number": record.attempt_number,
        "provider": record.provider,
        "requested_model": record.requested_model,
        "served_model": record.served_model,
        "outcome": record.outcome.value,
        "retry_reason": record.retry_reason.value,
        "prompt_tokens": record.prompt_tokens,
        "completion_tokens": record.completion_tokens,
        # str, not float: the column is `numeric` and a float round-trip would quietly lose
        # sub-cent precision on exactly the values cost attribution is built from.
        "cost_usd": str(record.cost_usd) if isinstance(record.cost_usd, Decimal) else None,
        "error_type": record.error_type,
        "started_at": _iso(record.started_at),
        "finished_at": _iso(record.finished_at),
    }


def _revalidate(record: Any, model: type[Any]) -> Any:
    """Re-run every validator on an already-constructed record, returning the validated instance.

    Not redundant. ``model_construct`` bypasses validation entirely, and a record can also be
    built by a producer that has since drifted from the contract. Round-tripping through
    ``model_dump`` → ``model_validate`` re-runs the field constraints *and* the cross-field
    ``model_validator``s that encode the lifecycle rules migration 067 also enforces as CHECKs.
    Against a ledger with no correction path, paying this on every record is cheap insurance.

    Returns the *revalidated* instance, not a boolean, and callers must serialize that rather
    than the record handed in. Validating a throwaway copy and then serializing the original
    proves less than it looks: `model_construct` can seat a plain `str` in a `StrEnum` field,
    which dumps to something `model_validate` happily accepts while the original still has no
    `.value` for the row builder to read. Serializing the validated object closes that gap
    instead of documenting it.
    """
    try:
        return model.model_validate(record.model_dump())
    except ValidationError:
        return None


def _order_calls_by_lineage(
    calls: Sequence[ProviderCallRecord],
    known_node_runs: set[UUID],
) -> tuple[list[ProviderCallRecord], list[ProviderCallRecord]]:
    """Split logical calls into (insertable in FK-safe order, quarantined).

    A call is insertable only when its ``node_run_id`` names a node run that landed in this
    flush, and its ``parent_call_id`` is either absent or names another insertable call. Parents
    are emitted before children so the self-referencing ``fk_olympus_provider_calls_parent``
    holds row by row, which keeps the batch valid even if the client splits it into several
    statements.

    Resolution is iterative rather than recursive so a parent cycle — impossible from the current
    producer, permanent if it ever happened — terminates as quarantine instead of a stack
    overflow or an FK error.
    """
    by_id = {call.call_id: call for call in calls}
    eligible = [call for call in calls if call.node_run_id in known_node_runs]
    pending = {call.call_id: call for call in eligible}

    ordered: list[ProviderCallRecord] = []
    placed: set[UUID] = set()
    progressed = True
    while pending and progressed:
        progressed = False
        for call_id in list(pending):
            call = pending[call_id]
            parent = call.parent_call_id
            if parent is None or parent in placed:
                ordered.append(call)
                placed.add(call_id)
                del pending[call_id]
                progressed = True

    # Anything still pending has an unresolvable parent: absent from this flush, itself
    # quarantined, or part of a cycle. `by_id` keeps declaration order stable for the report.
    quarantined = [call for call in by_id.values() if call.call_id not in placed]
    return ordered, quarantined


def _insert(client: Any, table: str, rows: Sequence[Mapping[str, Any]]) -> str | None:
    """Append ``rows``. Returns ``None`` on success or a sanitized exception type on failure.

    Only the exception *type name* is retained. A provider or driver message can carry a URL, a
    row payload, or a credential fragment, and this ledger has no column that may hold any of
    them — so the message never leaves this function.
    """
    if not rows:
        return None
    try:
        client.table(table).insert(list(rows)).execute()
    except Exception as exc:  # telemetry persistence must never abort portfolio work
        error_type = type(exc).__name__
        logger.warning(
            "provider telemetry: %s insert failed (%s); %d record(s) not durable, run continues",
            table,
            error_type,
            len(rows),
        )
        return error_type
    return None


def _reconcile(
    detailed: Mapping[str, int | float | None] | None,
    aggregate: Mapping[str, int | float | None] | None,
    attempts: Sequence[ProviderAttemptRecord],
) -> ReconciliationResult:
    """Compare the detailed projection against the compatibility aggregate on the shared keys."""
    detailed = dict(detailed or {})
    aggregate = dict(aggregate or {})
    missing_usage = sum(
        1
        for attempt in attempts
        if attempt.prompt_tokens is None or attempt.completion_tokens is None
    )
    missing_cost = sum(1 for attempt in attempts if attempt.cost_usd is None)

    unavailable: list[str] = []
    mismatched: list[str] = []
    for key in RECONCILED_KEYS:
        left = detailed.get(key)
        right = aggregate.get(key)
        if left is None or right is None:
            unavailable.append(key)
            continue
        # Cost is a rounded float on both sides; compare at the precision `snapshot()` and
        # `detailed_usage_projection()` both round to rather than by exact float equality.
        if isinstance(left, float) or isinstance(right, float):
            if round(float(left), 6) != round(float(right), 6):
                mismatched.append(key)
        elif left != right:
            mismatched.append(key)

    if unavailable:
        status: ReconciliationStatus = "unavailable"
    elif mismatched:
        status = "mismatched"
    else:
        status = "reconciled"

    return ReconciliationResult(
        status=status,
        detailed=detailed,
        aggregate=aggregate,
        unavailable_keys=tuple(unavailable),
        mismatched_keys=tuple(mismatched),
        attempts_missing_usage=missing_usage,
        attempts_missing_cost=missing_cost,
    )


def _partition_valid(records: Sequence[Any], model: type[Any], table: str) -> tuple[list[Any], int]:
    """Split records into the *revalidated* instances and a count of those that did not survive."""
    validated = (_revalidate(record, model) for record in records)
    valid = [record for record in validated if record is not None]
    rejected = len(records) - len(valid)
    if rejected:
        logger.warning(
            "provider telemetry: %d %s record(s) failed validation and were never submitted",
            rejected,
            table,
        )
    return valid, rejected


def _empty_tier(table: str, buffered: int) -> TierResult:
    return TierResult(
        table=table, buffered=buffered, submitted=0, inserted=0, quarantined=0, rejected=0
    )


def flush_run_telemetry(
    client: Any,
    *,
    run_id: str,
    attempt: int = 1,
    node_runs: Sequence[NodeRunRecord] = (),
    provider_calls: Sequence[ProviderCallRecord] = (),
    provider_attempts: Sequence[ProviderAttemptRecord] = (),
    aggregate_snapshot: Mapping[str, Any] | None = None,
    detailed_projection: Mapping[str, int | float | None] | None = None,
) -> FlushResult:
    """Append one run's telemetry to the private ledger, fail-soft throughout.

    Tiers are written in foreign-key order — node runs, then logical calls with parents ahead of
    children, then physical attempts — and a tier that fails cascades to its dependents as
    quarantine rather than as an insert the database would reject. Nothing here raises: the
    caller is a ``finally`` block on the run's exit path, and a telemetry error there would
    replace the run's real outcome with a bookkeeping one.

    Must be called *before* ``digigraph.usage.reset()``. ``reset()`` clears the buffers, so a
    flush ordered after it writes nothing while returning a result that looks like success.
    """
    reconciliation = _reconcile(detailed_projection, aggregate_snapshot, provider_attempts)

    if not _claim_flush((run_id, attempt)):
        logger.warning(
            "provider telemetry: run %s attempt %d was already flushed; skipping to avoid "
            "duplicating rows that cannot be deleted",
            run_id,
            attempt,
        )
        return FlushResult(
            run_id=run_id,
            attempt=attempt,
            node_runs=_empty_tier(NODE_RUNS_TABLE, len(node_runs)),
            provider_calls=_empty_tier(PROVIDER_CALLS_TABLE, len(provider_calls)),
            provider_attempts=_empty_tier(PROVIDER_ATTEMPTS_TABLE, len(provider_attempts)),
            reconciliation=reconciliation,
            skipped="already_flushed",
        )

    # Tier 1 — node runs. Nothing references anything, so validity is the only gate.
    valid_nodes, rejected_nodes = _partition_valid(node_runs, NodeRunRecord, NODE_RUNS_TABLE)
    nodes_error = _insert(client, NODE_RUNS_TABLE, [_node_run_row(r) for r in valid_nodes])
    node_tier = TierResult(
        table=NODE_RUNS_TABLE,
        buffered=len(node_runs),
        submitted=len(valid_nodes),
        inserted=len(valid_nodes) if nodes_error is None else 0,
        quarantined=0,
        rejected=rejected_nodes,
        error_type=nodes_error,
    )

    # Tier 2 — logical calls. Eligibility is computed from the node runs that actually LANDED,
    # not from the ones that were offered: a record dropped by validation, or a whole tier lost
    # to a failed insert, is not a referent any foreign key can resolve.
    known_node_runs = (
        {record.node_run_id for record in valid_nodes} if nodes_error is None else set[UUID]()
    )
    valid_calls, rejected_calls = _partition_valid(
        provider_calls, ProviderCallRecord, PROVIDER_CALLS_TABLE
    )
    ordered_calls, quarantined_calls = _order_calls_by_lineage(valid_calls, known_node_runs)
    calls_error = _insert(
        client, PROVIDER_CALLS_TABLE, [_provider_call_row(r) for r in ordered_calls]
    )
    call_tier = TierResult(
        table=PROVIDER_CALLS_TABLE,
        buffered=len(provider_calls),
        submitted=len(ordered_calls),
        inserted=len(ordered_calls) if calls_error is None else 0,
        quarantined=len(quarantined_calls),
        rejected=rejected_calls,
        error_type=calls_error,
    )

    # Tier 3 — physical attempts. An attempt whose logical call is absent is the orphan shape the
    # beliefs-distillation fold produces when it runs; it is quarantined and counted, never sent.
    known_calls = (
        {record.call_id for record in ordered_calls} if calls_error is None else set[UUID]()
    )
    valid_attempts, rejected_attempts = _partition_valid(
        provider_attempts, ProviderAttemptRecord, PROVIDER_ATTEMPTS_TABLE
    )
    insertable_attempts = [r for r in valid_attempts if r.call_id in known_calls]
    quarantined_attempts = [r for r in valid_attempts if r.call_id not in known_calls]
    attempts_error = _insert(
        client, PROVIDER_ATTEMPTS_TABLE, [_provider_attempt_row(r) for r in insertable_attempts]
    )
    attempt_tier = TierResult(
        table=PROVIDER_ATTEMPTS_TABLE,
        buffered=len(provider_attempts),
        submitted=len(insertable_attempts),
        inserted=len(insertable_attempts) if attempts_error is None else 0,
        quarantined=len(quarantined_attempts),
        rejected=rejected_attempts,
        error_type=attempts_error,
    )

    result = FlushResult(
        run_id=run_id,
        attempt=attempt,
        node_runs=node_tier,
        provider_calls=call_tier,
        provider_attempts=attempt_tier,
        reconciliation=reconciliation,
    )
    _log_result(result)
    return result


def _log_result(result: FlushResult) -> None:
    """Emit one operator-readable line. Coverage shortfalls are stated, never implied."""
    logger.info(
        "provider telemetry[%s attempt=%d]: nodes %d/%d calls %d/%d attempts %d/%d "
        "withheld=%d reconciliation=%s",
        result.run_id,
        result.attempt,
        result.node_runs.inserted,
        result.node_runs.buffered,
        result.provider_calls.inserted,
        result.provider_calls.buffered,
        result.provider_attempts.inserted,
        result.provider_attempts.buffered,
        result.withheld_total,
        result.reconciliation.status,
    )
    if result.withheld_total:
        logger.warning(
            "provider telemetry[%s attempt=%d]: %d record(s) withheld — %s. Coverage for this "
            "run is incomplete; it is not a zero.",
            result.run_id,
            result.attempt,
            result.withheld_total,
            ", ".join(
                f"{tier.table}: {tier.quarantined} unresolved referent(s), {tier.rejected} invalid"
                for tier in result.tiers
                if tier.quarantined or tier.rejected
            ),
        )
    if result.partially_written:
        logger.error(
            "provider telemetry[%s attempt=%d]: batch landed partially and the ledger admits no "
            "correction — this run's detail is permanently incomplete",
            result.run_id,
            result.attempt,
        )
    # Two independent `if`s, deliberately not `if/elif`. `status` is a single scalar answering one
    # question — "may an exact-billing claim be made?" — and `unavailable` rightly wins it. But a
    # key being unknown and a *different* key being known-and-wrong are orthogonal facts, and
    # chaining these would discard the second whenever the first held. `cost_usd` is unknown
    # whenever any contributing attempt omits cost, so the chained form suppressed real
    # disagreements on the common path.
    reconciliation = result.reconciliation
    if reconciliation.unavailable_keys:
        logger.info(
            "provider telemetry[%s attempt=%d]: billing reconciliation unavailable for %s "
            "(%d attempt(s) missing usage, %d missing cost) — not reconciled, not zero",
            result.run_id,
            result.attempt,
            ", ".join(reconciliation.unavailable_keys),
            reconciliation.attempts_missing_usage,
            reconciliation.attempts_missing_cost,
        )
    if reconciliation.mismatched_keys:
        # Direction is the whole signal. The aggregate counts calls made outside a node scope and
        # the detailed side cannot see them, so detail-below-aggregate has a standing explanation
        # and detail-above-aggregate has none — that one can only mean double-counting.
        unexplained = [
            key
            for key in reconciliation.mismatched_keys
            if _exceeds(reconciliation.detailed.get(key), reconciliation.aggregate.get(key))
        ]
        logger.warning(
            "provider telemetry[%s attempt=%d]: detailed records disagree with the aggregate on "
            "%s%s",
            result.run_id,
            result.attempt,
            ", ".join(reconciliation.mismatched_keys),
            (
                f" — {', '.join(unexplained)} exceed(s) the aggregate, which un-scoped calls "
                "cannot explain"
                if unexplained
                else " — detail is below the aggregate, consistent with calls made outside a "
                "node scope"
            ),
        )


def _exceeds(detailed: int | float | None, aggregate: int | float | None) -> bool:
    """Whether the detailed side claims MORE than the aggregate. Never legitimate."""
    if detailed is None or aggregate is None:
        return False
    return float(detailed) > float(aggregate)


__all__ = [
    "NODE_RUNS_TABLE",
    "PROVIDER_ATTEMPTS_TABLE",
    "PROVIDER_CALLS_TABLE",
    "RECONCILED_KEYS",
    "FlushResult",
    "ReconciliationResult",
    "TierResult",
    "flush_run_telemetry",
    "reset_flush_guard",
]
