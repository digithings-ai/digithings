"""Build versioned direction prerequisite snapshot at research preflight (#2946 / WP14.3)."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

from digiquant.dashboard.research_retrieval.direction_decision_context import (
    DirectionPrerequisiteSnapshot,
)
from digiquant.dashboard.research_retrieval.models import content_digest
from digiquant.dashboard.temporal import require_utc_datetime
from digiquant.research.forecast_outcomes import (
    ForecastOutcomeIntegrityError,
    ResolvedOutcomesMemo,
    list_resolved_outcomes_as_of_memoized,
)
from digiquant.research.supabase_io import SupabaseClient

logger = logging.getLogger(__name__)

_ACCOUNTING_PERIODS = "accounting_periods"

# Identity columns for the tip-period version pin (#4556). ``accounting_periods``
# has never had a stored ``content_hash`` (see 072_olympus_period_accounting.sql);
# the original h7 select asked for one anyway, so every run 400'd with ``42703``
# and the accounting pin was silently dropped. Pin the row identity locally.
_PERIOD_PIN_FIELDS = (
    "id",
    "period_date",
    "status",
    "policy_version_id",
    "supersedes_id",
    "recorded_at",
)
# PostgREST select list for that identity pin.
_PERIOD_PIN_COLUMNS = ", ".join(_PERIOD_PIN_FIELDS)


def _period_version_pin(row: dict[str, Any]) -> str | None:
    """Locally computed version pin for one accounting-period row (#4556)."""
    identity = {key: row.get(key) for key in _PERIOD_PIN_FIELDS if row.get(key) is not None}
    if not identity:
        return None
    return content_digest({"kind": _ACCOUNTING_PERIODS, "period": identity})


def _parse_uuid(raw: Any) -> UUID | None:
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def _load_latest_accounting_period(
    client: SupabaseClient,
    *,
    before_date: date,
) -> tuple[UUID | None, str | None]:
    """Return tip accounting-period id + a locally computed version pin before run_date."""
    try:
        resp = (
            client.table(_ACCOUNTING_PERIODS)
            .select(_PERIOD_PIN_COLUMNS)
            .lt("period_date", before_date.isoformat())
            .order("period_date", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.debug("direction prerequisites: accounting load failed (%s)", exc)
        return None, None
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return None, None
    row = rows[0]
    period_id = _parse_uuid(row.get("id"))
    if period_id is None:
        return None, None
    return period_id, _period_version_pin(row)


def build_direction_prerequisite_snapshot(
    *,
    client: SupabaseClient | None,
    run_date: date,
    knowledge_cutoff_at: datetime | None,
    research_state_pin: dict[str, object] | None,
    prior_effective_forecast_ids: tuple[str, ...] = (),
    outcome_lesson_pin: dict[str, object] | None = None,
    resolved_outcomes_memo: ResolvedOutcomesMemo | None = None,
) -> DirectionPrerequisiteSnapshot | None:
    """Pin versioned WP3/WP5/WP15 inputs for direction context compile at preflight.

    ``resolved_outcomes_memo`` is the run-scoped cohort memo shared with the
    portfolio direction phase (#4617): the first reader issues the
    ``list_resolved_outcomes_as_of`` GET and the second reuses it. ``None``
    reads directly (legacy behavior).
    """
    state_version_id: UUID | None = None
    if isinstance(research_state_pin, dict):
        state_version_id = _parse_uuid(research_state_pin.get("state_version_id"))

    outcome_lesson_version_id: UUID | None = None
    outcome_lesson_content_hash: str | None = None
    if isinstance(outcome_lesson_pin, dict):
        outcome_lesson_version_id = _parse_uuid(outcome_lesson_pin.get("lesson_version_id"))
        raw_hash = outcome_lesson_pin.get("content_hash")
        if raw_hash:
            outcome_lesson_content_hash = str(raw_hash)

    accounting_period_id: UUID | None = None
    accounting_period_content_hash: str | None = None
    matured_ids: tuple[str, ...] = ()
    unresolved_ids: tuple[str, ...] = ()

    if client is not None:
        accounting_period_id, accounting_period_content_hash = _load_latest_accounting_period(
            client,
            before_date=run_date,
        )
        if knowledge_cutoff_at is not None:
            try:
                cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
                resolved = list_resolved_outcomes_as_of_memoized(
                    client=client, knowledge_cutoff_at=cutoff, memo=resolved_outcomes_memo
                )
                matured_set = {str(o.outcome_id) for o in resolved}
                matured_ids = tuple(sorted(matured_set))
                resolved_effective = {str(o.effective_forecast_id) for o in resolved}
                unresolved = [
                    eid
                    for eid in prior_effective_forecast_ids
                    if eid and eid not in resolved_effective
                ]
                unresolved_ids = tuple(sorted(set(unresolved)))
            except ForecastOutcomeIntegrityError:
                # #4298: a stale persisted digest must fail preflight loud with the
                # named error (outcome_id + repair tool) — never fall through to a
                # snapshot that silently omits the matured cohort.
                raise
            except Exception as exc:
                logger.debug("direction prerequisites: forecast outcomes load failed (%s)", exc)

    if (
        state_version_id is None
        and accounting_period_id is None
        and not matured_ids
        and not unresolved_ids
        and outcome_lesson_version_id is None
    ):
        return None

    return DirectionPrerequisiteSnapshot(
        state_version_id=state_version_id,
        accounting_period_id=accounting_period_id,
        accounting_period_content_hash=accounting_period_content_hash,
        matured_forecast_outcome_ids=matured_ids,
        unresolved_forecast_effective_ids=unresolved_ids,
        ex_ante_risk_snapshot_hash=None,
        action_cost_estimate_ids=(),
        outcome_lesson_version_id=outcome_lesson_version_id,
        outcome_lesson_content_hash=outcome_lesson_content_hash,
    )


__all__ = ["build_direction_prerequisite_snapshot"]
