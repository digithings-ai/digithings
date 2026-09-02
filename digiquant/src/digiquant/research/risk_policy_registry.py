"""Private append-only H8 risk policy / covariance snapshot registry (#2698 / WP6.3).

Persists immutable :class:`~digiquant.portfolio.models.risk_policy.RiskPolicy`
and :class:`~digiquant.portfolio.models.risk_policy.CovarianceSnapshot` rows
from migration ``081_olympus_risk_policy_snapshots.sql``, plus one run ref per
``source_run_id``.

**Exact retry:** same primary key + same ``content_hash`` is a no-op.
**Content conflict:** same primary key + different ``content_hash`` raises
:class:`RiskPolicyRegistryConflict` — never UPDATE.
**Cutoff reads:** exact-ID selects only; rows with ``effective_at`` / ``resolved_at``
after the pinned knowledge cutoff are invisible.
**H9 boundary:** writers are fail-soft after portfolio booking; a registry failure
must not rebook. Resolved artifacts never feed incumbent ``size_portfolio`` in Phase 1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import (
    Any,  # score:allow untyped any — duck-typed Supabase client / row dicts
)
from uuid import UUID

from digiquant.research.supabase_io import SupabaseClient
from digiquant.portfolio.models.risk_policy import (
    CovarianceSnapshot,
    RiskPolicy,
)
from digiquant.dashboard.temporal import require_utc_datetime

logger = logging.getLogger(__name__)

POLICIES = "olympus_risk_policies"
SNAPSHOTS = "olympus_covariance_snapshots"
RUN_REFS = "olympus_h8_risk_run_refs"


class RiskPolicyRegistryConflict(RuntimeError):
    """Same identity already stored with a different content hash."""


class RiskPolicyRegistryError(RuntimeError):
    """Registry persistence refused or left an inconsistent state."""


class _WriteKind(StrEnum):
    WRITTEN = "written"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RiskRegistryWriteResult:
    """Outcome of one :func:`persist_h8_risk_snapshots` call."""

    policies_written: int = 0
    policies_skipped: int = 0
    snapshots_written: int = 0
    snapshots_skipped: int = 0
    run_refs_written: int = 0
    run_refs_skipped: int = 0
    degraded_reason: str | None = None
    conflicts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.degraded_reason is None and not self.conflicts


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


def _policy_row(policy: RiskPolicy) -> dict[str, Any]:
    return {
        "policy_id": str(policy.policy_id),
        "method_version": policy.method_version,
        "source_run_id": policy.source_run_id,
        "status": policy.status.value,
        "unavailable_reason": policy.unavailable_reason,
        "content_hash": policy.content_hash,
        "effective_at": policy.effective_at.isoformat(),
        "policy_body": policy.model_dump(mode="json"),
    }


def _snapshot_row(snapshot: CovarianceSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": str(snapshot.snapshot_id),
        "method_version": snapshot.method_version,
        "as_of_session": snapshot.as_of_session.isoformat(),
        "lookback_days": snapshot.lookback_days,
        "status": snapshot.status.value,
        "unavailable_reason": snapshot.unavailable_reason,
        "content_hash": snapshot.content_hash,
        "resolved_at": snapshot.resolved_at.isoformat(),
        "snapshot_body": snapshot.model_dump(mode="json"),
    }


def _run_ref_row(
    *,
    source_run_id: str,
    run_date: date,
    policy: RiskPolicy,
    snapshot: CovarianceSnapshot,
) -> dict[str, Any]:
    return {
        "source_run_id": source_run_id,
        "run_date": run_date.isoformat(),
        "policy_id": str(policy.policy_id),
        "snapshot_id": str(snapshot.snapshot_id),
        "effective_at": policy.effective_at.isoformat(),
    }


def _persist_policy(*, client: SupabaseClient, policy: RiskPolicy) -> _WriteKind:
    existing = _fetch_by_id(
        client=client,
        table=POLICIES,
        id_column="policy_id",
        row_id=policy.policy_id,
    )
    if existing is not None:
        if _content_matches(existing, policy.content_hash):
            return _WriteKind.SKIPPED
        raise RiskPolicyRegistryConflict(
            f"policy_id {policy.policy_id} exists with different content_hash"
        )
    _insert(client=client, table=POLICIES, rows=[_policy_row(policy)])
    return _WriteKind.WRITTEN


def _persist_snapshot(*, client: SupabaseClient, snapshot: CovarianceSnapshot) -> _WriteKind:
    existing = _fetch_by_id(
        client=client,
        table=SNAPSHOTS,
        id_column="snapshot_id",
        row_id=snapshot.snapshot_id,
    )
    if existing is not None:
        if _content_matches(existing, snapshot.content_hash):
            return _WriteKind.SKIPPED
        raise RiskPolicyRegistryConflict(
            f"snapshot_id {snapshot.snapshot_id} exists with different content_hash"
        )
    _insert(client=client, table=SNAPSHOTS, rows=[_snapshot_row(snapshot)])
    return _WriteKind.WRITTEN


def _persist_run_ref(
    *,
    client: SupabaseClient,
    source_run_id: str,
    run_date: date,
    policy: RiskPolicy,
    snapshot: CovarianceSnapshot,
) -> _WriteKind:
    existing = _fetch_by_id(
        client=client,
        table=RUN_REFS,
        id_column="source_run_id",
        row_id=source_run_id,
    )
    if existing is not None:
        same_policy = str(existing.get("policy_id") or "") == str(policy.policy_id)
        same_snapshot = str(existing.get("snapshot_id") or "") == str(snapshot.snapshot_id)
        if same_policy and same_snapshot:
            return _WriteKind.SKIPPED
        raise RiskPolicyRegistryConflict(
            f"source_run_id {source_run_id} exists with different policy/snapshot ids"
        )
    policy_row = _fetch_by_id(
        client=client,
        table=POLICIES,
        id_column="policy_id",
        row_id=policy.policy_id,
    )
    if policy_row is None:
        raise RiskPolicyRegistryError(
            f"run ref {source_run_id} references missing policy {policy.policy_id}"
        )
    snapshot_row = _fetch_by_id(
        client=client,
        table=SNAPSHOTS,
        id_column="snapshot_id",
        row_id=snapshot.snapshot_id,
    )
    if snapshot_row is None:
        raise RiskPolicyRegistryError(
            f"run ref {source_run_id} references missing snapshot {snapshot.snapshot_id}"
        )
    _insert(
        client=client,
        table=RUN_REFS,
        rows=[
            _run_ref_row(
                source_run_id=source_run_id,
                run_date=run_date,
                policy=policy,
                snapshot=snapshot,
            )
        ],
    )
    return _WriteKind.WRITTEN


_POLICY_FIELDS = frozenset(
    {
        "policy_id",
        "method_version",
        "source_run_id",
        "status",
        "unavailable_reason",
        "content_hash",
        "effective_at",
        "policy_body",
    }
)
_SNAPSHOT_FIELDS = frozenset(
    {
        "snapshot_id",
        "method_version",
        "as_of_session",
        "lookback_days",
        "status",
        "unavailable_reason",
        "content_hash",
        "resolved_at",
        "snapshot_body",
    }
)


def get_risk_policy(
    *,
    client: SupabaseClient,
    policy_id: UUID,
    knowledge_cutoff_at: datetime,
) -> RiskPolicy | None:
    """Exact-ID read; invisible when ``effective_at`` is after the pinned cutoff."""
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    row = _fetch_by_id(
        client=client,
        table=POLICIES,
        id_column="policy_id",
        row_id=policy_id,
    )
    if row is None:
        return None
    effective = _parse_timestamp(row.get("effective_at"), field_name="effective_at")
    if effective is None or effective > cutoff:
        return None
    body = row.get("policy_body")
    if isinstance(body, dict):
        return RiskPolicy.model_validate(body)
    payload = {k: row[k] for k in _POLICY_FIELDS if k in row}
    return RiskPolicy.model_validate(payload)


def get_covariance_snapshot(
    *,
    client: SupabaseClient,
    snapshot_id: UUID,
    knowledge_cutoff_at: datetime,
) -> CovarianceSnapshot | None:
    """Exact-ID read; invisible when ``resolved_at`` is after the pinned cutoff."""
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    row = _fetch_by_id(
        client=client,
        table=SNAPSHOTS,
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
        return CovarianceSnapshot.model_validate(body)
    payload = {k: row[k] for k in _SNAPSHOT_FIELDS if k in row}
    return CovarianceSnapshot.model_validate(payload)


def collect_h8_risk_snapshots_from_state(
    state: Any,
) -> tuple[RiskPolicy | None, CovarianceSnapshot | None]:
    """Extract typed H8 risk artifacts from Hermes phase state for H9 persistence."""
    hermes = getattr(state, "phase_hermes", None)
    if hermes is None:
        return None, None

    policy_raw = getattr(hermes, "risk_policy", None)
    snapshot_raw = getattr(hermes, "covariance_snapshot", None)
    policy: RiskPolicy | None = None
    snapshot: CovarianceSnapshot | None = None

    if isinstance(policy_raw, dict):
        try:
            policy = RiskPolicy.model_validate(policy_raw)
        except Exception as exc:
            logger.warning(
                "risk policy registry: skipping invalid policy (%s: %s)",
                type(exc).__name__,
                exc,
            )
    if isinstance(snapshot_raw, dict):
        try:
            snapshot = CovarianceSnapshot.model_validate(snapshot_raw)
        except Exception as exc:
            logger.warning(
                "risk policy registry: skipping invalid covariance snapshot (%s: %s)",
                type(exc).__name__,
                exc,
            )
    return policy, snapshot


def persist_h8_risk_snapshots(
    *,
    client: SupabaseClient,
    source_run_id: str,
    run_date: date,
    policy: RiskPolicy,
    snapshot: CovarianceSnapshot,
) -> RiskRegistryWriteResult:
    """Append policy, snapshot, then run ref. Never mutates existing rows."""
    conflicts: list[str] = []
    p_written = p_skipped = s_written = s_skipped = r_written = r_skipped = 0

    try:
        kind = _persist_policy(client=client, policy=policy)
    except RiskPolicyRegistryConflict as exc:
        conflicts.append(str(exc))
        return RiskRegistryWriteResult(
            conflicts=tuple(conflicts), degraded_reason="content_conflict"
        )
    if kind is _WriteKind.WRITTEN:
        p_written += 1
    else:
        p_skipped += 1

    try:
        kind = _persist_snapshot(client=client, snapshot=snapshot)
    except RiskPolicyRegistryConflict as exc:
        conflicts.append(str(exc))
        return RiskRegistryWriteResult(
            policies_written=p_written,
            policies_skipped=p_skipped,
            conflicts=tuple(conflicts),
            degraded_reason="content_conflict",
        )
    if kind is _WriteKind.WRITTEN:
        s_written += 1
    else:
        s_skipped += 1

    try:
        kind = _persist_run_ref(
            client=client,
            source_run_id=source_run_id,
            run_date=run_date,
            policy=policy,
            snapshot=snapshot,
        )
    except RiskPolicyRegistryConflict as exc:
        conflicts.append(str(exc))
        return RiskRegistryWriteResult(
            policies_written=p_written,
            policies_skipped=p_skipped,
            snapshots_written=s_written,
            snapshots_skipped=s_skipped,
            conflicts=tuple(conflicts),
            degraded_reason="content_conflict",
        )
    except RiskPolicyRegistryError as exc:
        return RiskRegistryWriteResult(
            policies_written=p_written,
            policies_skipped=p_skipped,
            snapshots_written=s_written,
            snapshots_skipped=s_skipped,
            degraded_reason=str(exc),
            conflicts=tuple(conflicts),
        )
    if kind is _WriteKind.WRITTEN:
        r_written += 1
    else:
        r_skipped += 1

    return RiskRegistryWriteResult(
        policies_written=p_written,
        policies_skipped=p_skipped,
        snapshots_written=s_written,
        snapshots_skipped=s_skipped,
        run_refs_written=r_written,
        run_refs_skipped=r_skipped,
        conflicts=tuple(conflicts),
        degraded_reason="content_conflict" if conflicts else None,
    )


def persist_h8_risk_snapshots_from_state(
    *,
    client: SupabaseClient,
    state: Any,
) -> RiskRegistryWriteResult:
    """Collect H8 artifacts from Hermes state; empty is success."""
    policy, snapshot = collect_h8_risk_snapshots_from_state(state)
    if policy is None or snapshot is None:
        return RiskRegistryWriteResult()
    source_run_id = str(getattr(state, "run_id", "") or "").strip()
    if not source_run_id:
        return RiskRegistryWriteResult(degraded_reason="missing_source_run_id")
    run_date = getattr(state, "run_date", None)
    if run_date is None:
        return RiskRegistryWriteResult(degraded_reason="missing_run_date")
    return persist_h8_risk_snapshots(
        client=client,
        source_run_id=source_run_id,
        run_date=run_date,
        policy=policy,
        snapshot=snapshot,
    )


__all__ = [
    "POLICIES",
    "RUN_REFS",
    "SNAPSHOTS",
    "RiskPolicyRegistryConflict",
    "RiskPolicyRegistryError",
    "RiskRegistryWriteResult",
    "collect_h8_risk_snapshots_from_state",
    "get_covariance_snapshot",
    "get_risk_policy",
    "persist_h8_risk_snapshots",
    "persist_h8_risk_snapshots_from_state",
]
