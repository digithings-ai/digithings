"""Private append-only prospective forecast registry (#2663 / WP4.6, #2684 / WP5.4).

Persists immutable :class:`~digiquant.olympus.hermes.models.forecast.ForecastAssessment`
bases and :class:`~digiquant.olympus.hermes.models.forecast.ForecastAmendment` records
into migration ``079_olympus_forecast_registry.sql`` tables, plus observational
:class:`~digiquant.olympus.hermes.models.forecast_calibration.ForecastCalibration` /
:class:`~digiquant.olympus.hermes.models.forecast_calibration.CalibratedForecast`
shadow rows into migration ``080`` tables.

**Exact retry:** same primary key + same ``content_hash`` is a no-op.
**Content conflict:** same primary key + different ``content_hash`` raises
:class:`ForecastRegistryConflict` — never UPDATE.
**Cutoff reads:** exact-ID selects only; rows with ``known_at`` after the pinned
knowledge cutoff are invisible.
**H9 boundary:** writers are fail-soft after portfolio booking; a registry failure
must not rebook. Shadow calibration never feeds incumbent H8.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import (
    Any,  # score:allow untyped any — duck-typed Supabase client / row dicts
)
from uuid import UUID

from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.models.forecast import (
    ForecastAmendment,
    ForecastAssessment,
)
from digiquant.olympus.hermes.models.forecast_calibration import (
    CalibratedForecast,
    ForecastCalibration,
)
from digiquant.olympus.temporal import require_utc_datetime

logger = logging.getLogger(__name__)

ASSESSMENTS = "olympus_forecast_assessments"
AMENDMENTS = "olympus_forecast_amendments"
CALIBRATIONS = "olympus_forecast_calibrations"
CALIBRATED_FORECASTS = "olympus_calibrated_forecasts"


class ForecastRegistryConflict(RuntimeError):
    """Same identity already stored with a different content hash."""


class ForecastRegistryError(RuntimeError):
    """Registry persistence refused or left an inconsistent state."""


class _WriteKind(StrEnum):
    WRITTEN = "written"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RegistryWriteResult:
    """Outcome of one :func:`persist_forecast_lineage` / shadow calibration call."""

    assessments_written: int = 0
    assessments_skipped: int = 0
    amendments_written: int = 0
    amendments_skipped: int = 0
    calibrations_written: int = 0
    calibrations_skipped: int = 0
    calibrated_forecasts_written: int = 0
    calibrated_forecasts_skipped: int = 0
    degraded_reason: str | None = None
    conflicts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.degraded_reason is None and not self.conflicts


def _insert(*, client: SupabaseClient, table: str, rows: list[dict[str, Any]]) -> None:
    """Single INSERT gate — keeps ``upsert``/``update`` out of this module."""
    if not rows:
        return
    client.table(table).insert(rows).execute()


def _assessment_row(assessment: ForecastAssessment) -> dict[str, Any]:
    return {
        "forecast_id": str(assessment.forecast_id),
        "ticker": assessment.ticker.strip().upper(),
        "source_run_id": assessment.source_run_id,
        "provider_invocation_id": assessment.provider_invocation_id,
        "prompt_version": assessment.prompt_version,
        "artifact_version": assessment.artifact_version,
        "terms": assessment.terms.model_dump(mode="json"),
        "price_anchor": assessment.price_anchor.model_dump(mode="json"),
        "content_hash": assessment.content_hash,
        "effective_at": assessment.effective_at.isoformat(),
        "known_at": assessment.known_at.isoformat(),
    }


def _amendment_row(amendment: ForecastAmendment) -> dict[str, Any]:
    return {
        "amendment_id": str(amendment.amendment_id),
        "base_forecast_id": str(amendment.base_forecast_id),
        "supersedes_amendment_id": (
            str(amendment.supersedes_amendment_id)
            if amendment.supersedes_amendment_id is not None
            else None
        ),
        "ticker": amendment.ticker.strip().upper(),
        "source_run_id": amendment.source_run_id,
        "provider_invocation_id": amendment.provider_invocation_id,
        "reason": amendment.reason,
        "terms": amendment.terms.model_dump(mode="json"),
        "new_evidence_ids": list(amendment.new_evidence_ids),
        "contradiction_ids": list(amendment.contradiction_ids),
        "content_hash": amendment.content_hash,
        "effective_at": amendment.effective_at.isoformat(),
        "known_at": amendment.known_at.isoformat(),
    }


def _calibration_row(calibration: ForecastCalibration) -> dict[str, Any]:
    return {
        "calibration_id": str(calibration.calibration_id),
        "cohort_key": calibration.cohort_key,
        "prior_definition": calibration.prior_definition,
        "method_version": calibration.method_version,
        "sample_count": calibration.sample_count,
        "equivalent_sample_size": str(calibration.equivalent_sample_size),
        "bias": None if calibration.bias is None else str(calibration.bias),
        "dispersion": None if calibration.dispersion is None else str(calibration.dispersion),
        "brier_score": None if calibration.brier_score is None else str(calibration.brier_score),
        "log_score": None if calibration.log_score is None else str(calibration.log_score),
        "reliability": str(calibration.reliability),
        "status": calibration.status.value,
        "unavailable_reason": calibration.unavailable_reason,
        "outcome_ids": [str(item) for item in calibration.outcome_ids],
        "content_hash": calibration.content_hash,
        "effective_at": calibration.effective_at.isoformat(),
        "known_at": calibration.known_at.isoformat(),
    }


def _calibrated_forecast_row(subject: CalibratedForecast) -> dict[str, Any]:
    return {
        "calibrated_forecast_id": str(subject.calibrated_forecast_id),
        "base_forecast_id": str(subject.base_forecast_id),
        "effective_forecast_id": str(subject.effective_forecast_id),
        "calibration_id": (None if subject.calibration_id is None else str(subject.calibration_id)),
        "ticker": subject.ticker.strip().upper(),
        "expected_gross_return": (
            None if subject.expected_gross_return is None else str(subject.expected_gross_return)
        ),
        "forecast_error_std": (
            None if subject.forecast_error_std is None else str(subject.forecast_error_std)
        ),
        "downside_quantiles": (
            None
            if subject.downside_quantiles is None
            else [str(item) for item in subject.downside_quantiles]
        ),
        "calibrated_positive_probability": (
            None
            if subject.calibrated_positive_probability is None
            else str(subject.calibrated_positive_probability)
        ),
        "reliability_weight": str(subject.reliability_weight),
        "effective_until": (
            None if subject.effective_until is None else subject.effective_until.isoformat()
        ),
        "status": subject.status.value,
        "unavailable_reason": subject.unavailable_reason,
        "content_hash": subject.content_hash,
        "effective_at": subject.effective_at.isoformat(),
        "known_at": subject.known_at.isoformat(),
    }


def _fetch_by_id(
    *,
    client: SupabaseClient,
    table: str,
    id_column: str,
    row_id: UUID,
) -> dict[str, Any] | None:
    resp = client.table(table).select("*").eq(id_column, str(row_id)).limit(1).execute()
    rows = list(getattr(resp, "data", None) or [])
    return rows[0] if rows else None


def _content_matches(existing: dict[str, Any], expected_hash: str) -> bool:
    return str(existing.get("content_hash") or "") == expected_hash


def _persist_assessment(
    *,
    client: SupabaseClient,
    assessment: ForecastAssessment,
) -> _WriteKind:
    existing = _fetch_by_id(
        client=client,
        table=ASSESSMENTS,
        id_column="forecast_id",
        row_id=assessment.forecast_id,
    )
    if existing is not None:
        if _content_matches(existing, assessment.content_hash):
            return _WriteKind.SKIPPED
        raise ForecastRegistryConflict(
            f"forecast_id {assessment.forecast_id} exists with different content_hash"
        )
    _insert(client=client, table=ASSESSMENTS, rows=[_assessment_row(assessment)])
    return _WriteKind.WRITTEN


def _persist_amendment(
    *,
    client: SupabaseClient,
    amendment: ForecastAmendment,
) -> _WriteKind:
    existing = _fetch_by_id(
        client=client,
        table=AMENDMENTS,
        id_column="amendment_id",
        row_id=amendment.amendment_id,
    )
    if existing is not None:
        if _content_matches(existing, amendment.content_hash):
            return _WriteKind.SKIPPED
        raise ForecastRegistryConflict(
            f"amendment_id {amendment.amendment_id} exists with different content_hash"
        )
    base = _fetch_by_id(
        client=client,
        table=ASSESSMENTS,
        id_column="forecast_id",
        row_id=amendment.base_forecast_id,
    )
    if base is None:
        raise ForecastRegistryError(
            f"amendment {amendment.amendment_id} references missing base "
            f"{amendment.base_forecast_id}"
        )
    _insert(client=client, table=AMENDMENTS, rows=[_amendment_row(amendment)])
    return _WriteKind.WRITTEN


def _persist_calibration(
    *,
    client: SupabaseClient,
    calibration: ForecastCalibration,
) -> _WriteKind:
    existing = _fetch_by_id(
        client=client,
        table=CALIBRATIONS,
        id_column="calibration_id",
        row_id=calibration.calibration_id,
    )
    if existing is not None:
        if _content_matches(existing, calibration.content_hash):
            return _WriteKind.SKIPPED
        raise ForecastRegistryConflict(
            f"calibration_id {calibration.calibration_id} exists with different content_hash"
        )
    _insert(client=client, table=CALIBRATIONS, rows=[_calibration_row(calibration)])
    return _WriteKind.WRITTEN


def _persist_calibrated_forecast(
    *,
    client: SupabaseClient,
    subject: CalibratedForecast,
) -> _WriteKind:
    existing = _fetch_by_id(
        client=client,
        table=CALIBRATED_FORECASTS,
        id_column="calibrated_forecast_id",
        row_id=subject.calibrated_forecast_id,
    )
    if existing is not None:
        if _content_matches(existing, subject.content_hash):
            return _WriteKind.SKIPPED
        raise ForecastRegistryConflict(
            f"calibrated_forecast_id {subject.calibrated_forecast_id} exists "
            "with different content_hash"
        )
    base = _fetch_by_id(
        client=client,
        table=ASSESSMENTS,
        id_column="forecast_id",
        row_id=subject.base_forecast_id,
    )
    if base is None:
        raise ForecastRegistryError(
            f"calibrated forecast {subject.calibrated_forecast_id} references "
            f"missing base {subject.base_forecast_id}"
        )
    if subject.calibration_id is not None:
        cal = _fetch_by_id(
            client=client,
            table=CALIBRATIONS,
            id_column="calibration_id",
            row_id=subject.calibration_id,
        )
        if cal is None:
            raise ForecastRegistryError(
                f"calibrated forecast {subject.calibrated_forecast_id} references "
                f"missing calibration {subject.calibration_id}"
            )
    _insert(client=client, table=CALIBRATED_FORECASTS, rows=[_calibrated_forecast_row(subject)])
    return _WriteKind.WRITTEN


def persist_forecast_lineage(
    *,
    client: SupabaseClient,
    assessments: list[ForecastAssessment] | tuple[ForecastAssessment, ...] = (),
    amendments: list[ForecastAmendment] | tuple[ForecastAmendment, ...] = (),
) -> RegistryWriteResult:
    """Append base assessments then amendments. Never mutates existing rows.

    Bases must land before amendments that reference them. Exact retries skip;
    content conflicts and hard write errors surface on the result (callers that
    want fail-soft H9 behavior should catch and mark degraded).
    """
    a_written = a_skipped = 0
    m_written = m_skipped = 0
    conflicts: list[str] = []

    for assessment in assessments:
        try:
            kind = _persist_assessment(client=client, assessment=assessment)
        except ForecastRegistryConflict as exc:
            conflicts.append(str(exc))
            continue
        if kind is _WriteKind.WRITTEN:
            a_written += 1
        else:
            a_skipped += 1

    for amendment in amendments:
        try:
            kind = _persist_amendment(client=client, amendment=amendment)
        except ForecastRegistryConflict as exc:
            conflicts.append(str(exc))
            continue
        except ForecastRegistryError as exc:
            return RegistryWriteResult(
                assessments_written=a_written,
                assessments_skipped=a_skipped,
                amendments_written=m_written,
                amendments_skipped=m_skipped,
                degraded_reason=str(exc),
                conflicts=tuple(conflicts),
            )
        if kind is _WriteKind.WRITTEN:
            m_written += 1
        else:
            m_skipped += 1

    return RegistryWriteResult(
        assessments_written=a_written,
        assessments_skipped=a_skipped,
        amendments_written=m_written,
        amendments_skipped=m_skipped,
        conflicts=tuple(conflicts),
        degraded_reason="content_conflict" if conflicts else None,
    )


def persist_shadow_calibrations(
    *,
    client: SupabaseClient,
    calibrations: list[ForecastCalibration] | tuple[ForecastCalibration, ...] = (),
    calibrated_forecasts: list[CalibratedForecast] | tuple[CalibratedForecast, ...] = (),
) -> RegistryWriteResult:
    """Append calibration versions then shadow subjects. Never mutates existing rows.

    Calibrations must land before subjects that FK them. Exact retries skip;
    content conflicts surface on the result. Callers that want fail-soft H9
    behavior should catch and mark degraded.
    """
    c_written = c_skipped = 0
    s_written = s_skipped = 0
    conflicts: list[str] = []

    for calibration in calibrations:
        try:
            kind = _persist_calibration(client=client, calibration=calibration)
        except ForecastRegistryConflict as exc:
            conflicts.append(str(exc))
            continue
        if kind is _WriteKind.WRITTEN:
            c_written += 1
        else:
            c_skipped += 1

    for subject in calibrated_forecasts:
        try:
            kind = _persist_calibrated_forecast(client=client, subject=subject)
        except ForecastRegistryConflict as exc:
            conflicts.append(str(exc))
            continue
        except ForecastRegistryError as exc:
            return RegistryWriteResult(
                calibrations_written=c_written,
                calibrations_skipped=c_skipped,
                calibrated_forecasts_written=s_written,
                calibrated_forecasts_skipped=s_skipped,
                degraded_reason=str(exc),
                conflicts=tuple(conflicts),
            )
        if kind is _WriteKind.WRITTEN:
            s_written += 1
        else:
            s_skipped += 1

    return RegistryWriteResult(
        calibrations_written=c_written,
        calibrations_skipped=c_skipped,
        calibrated_forecasts_written=s_written,
        calibrated_forecasts_skipped=s_skipped,
        conflicts=tuple(conflicts),
        degraded_reason="content_conflict" if conflicts else None,
    )


def _parse_known_at(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return require_utc_datetime(raw, field_name="known_at")
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return require_utc_datetime(datetime.fromisoformat(text), field_name="known_at")


_ASSESSMENT_FIELDS = frozenset(
    {
        "forecast_id",
        "ticker",
        "source_run_id",
        "provider_invocation_id",
        "prompt_version",
        "artifact_version",
        "terms",
        "price_anchor",
        "content_hash",
        "effective_at",
        "known_at",
    }
)
_AMENDMENT_FIELDS = frozenset(
    {
        "amendment_id",
        "base_forecast_id",
        "supersedes_amendment_id",
        "ticker",
        "source_run_id",
        "provider_invocation_id",
        "reason",
        "terms",
        "new_evidence_ids",
        "contradiction_ids",
        "content_hash",
        "effective_at",
        "known_at",
    }
)


def get_forecast_assessment(
    *,
    client: SupabaseClient,
    forecast_id: UUID,
    knowledge_cutoff_at: datetime,
) -> ForecastAssessment | None:
    """Exact-ID read; invisible when ``known_at`` is after the pinned cutoff."""
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    row = _fetch_by_id(
        client=client,
        table=ASSESSMENTS,
        id_column="forecast_id",
        row_id=forecast_id,
    )
    if row is None:
        return None
    known = _parse_known_at(row.get("known_at"))
    if known is None or known > cutoff:
        return None
    payload = {k: row[k] for k in _ASSESSMENT_FIELDS if k in row}
    return ForecastAssessment.model_validate(payload)


def get_forecast_amendment(
    *,
    client: SupabaseClient,
    amendment_id: UUID,
    knowledge_cutoff_at: datetime,
) -> ForecastAmendment | None:
    """Exact-ID read; invisible when ``known_at`` is after the pinned cutoff."""
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    row = _fetch_by_id(
        client=client,
        table=AMENDMENTS,
        id_column="amendment_id",
        row_id=amendment_id,
    )
    if row is None:
        return None
    known = _parse_known_at(row.get("known_at"))
    if known is None or known > cutoff:
        return None
    payload = {k: row[k] for k in _AMENDMENT_FIELDS if k in row}
    return ForecastAmendment.model_validate(payload)


def collect_lineage_from_state(
    state: Any,
) -> tuple[list[ForecastAssessment], list[ForecastAmendment]]:
    """Extract typed lineage artifacts from Hermes phase state for H9 persistence.

    Bases come from ``phase_hermes.asset_analysts[*].forecast_assessment``.
    Amendments come from ``phase_hermes.deliberation_summaries[*].forecast_amendment``
    when H6 attached a complete accepted amendment dump.
    """
    hermes = getattr(state, "phase_hermes", None)
    assessments: list[ForecastAssessment] = []
    amendments: list[ForecastAmendment] = []
    if hermes is None:
        return assessments, amendments

    analysts = getattr(hermes, "asset_analysts", None) or {}
    for payload in analysts.values():
        if not isinstance(payload, dict):
            continue
        raw = payload.get("forecast_assessment")
        if raw is None:
            continue
        try:
            assessments.append(ForecastAssessment.model_validate(raw))
        except Exception as exc:
            logger.warning(
                "forecast registry: skipping invalid assessment (%s: %s)",
                type(exc).__name__,
                exc,
            )

    summaries = getattr(hermes, "deliberation_summaries", None) or {}
    for summary in summaries.values():
        if not isinstance(summary, dict):
            continue
        raw_am = summary.get("forecast_amendment")
        if raw_am is None:
            continue
        try:
            amendments.append(ForecastAmendment.model_validate(raw_am))
        except Exception as exc:
            logger.warning(
                "forecast registry: skipping invalid amendment (%s: %s)",
                type(exc).__name__,
                exc,
            )

    return assessments, amendments


def collect_shadow_calibrations_from_state(
    state: Any,
) -> tuple[list[ForecastCalibration], list[CalibratedForecast]]:
    """Extract WP5.4 shadow calibration artifacts from Hermes typed state."""
    hermes = getattr(state, "phase_hermes", None)
    calibrations: list[ForecastCalibration] = []
    subjects: list[CalibratedForecast] = []
    if hermes is None:
        return calibrations, subjects

    for raw in (getattr(hermes, "forecast_calibrations", None) or {}).values():
        if not isinstance(raw, dict):
            continue
        try:
            calibrations.append(ForecastCalibration.model_validate(raw))
        except Exception as exc:
            logger.warning(
                "forecast registry: skipping invalid calibration (%s: %s)",
                type(exc).__name__,
                exc,
            )

    for raw in (getattr(hermes, "calibrated_forecasts", None) or {}).values():
        if not isinstance(raw, dict):
            continue
        try:
            subjects.append(CalibratedForecast.model_validate(raw))
        except Exception as exc:
            logger.warning(
                "forecast registry: skipping invalid calibrated forecast (%s: %s)",
                type(exc).__name__,
                exc,
            )

    return calibrations, subjects


def persist_forecast_lineage_from_state(
    *,
    client: SupabaseClient,
    state: Any,
) -> RegistryWriteResult:
    """Collect lineage + shadow calibrations from Hermes state; empty is success."""
    assessments, amendments = collect_lineage_from_state(state)
    calibrations, subjects = collect_shadow_calibrations_from_state(state)
    lineage = RegistryWriteResult()
    if assessments or amendments:
        lineage = persist_forecast_lineage(
            client=client,
            assessments=assessments,
            amendments=amendments,
        )
        if lineage.degraded_reason and lineage.degraded_reason != "content_conflict":
            return lineage

    shadow = RegistryWriteResult()
    if calibrations or subjects:
        shadow = persist_shadow_calibrations(
            client=client,
            calibrations=calibrations,
            calibrated_forecasts=subjects,
        )

    conflicts = tuple(dict.fromkeys([*lineage.conflicts, *shadow.conflicts]))
    degraded = lineage.degraded_reason or shadow.degraded_reason
    if conflicts and degraded is None:
        degraded = "content_conflict"
    return RegistryWriteResult(
        assessments_written=lineage.assessments_written,
        assessments_skipped=lineage.assessments_skipped,
        amendments_written=lineage.amendments_written,
        amendments_skipped=lineage.amendments_skipped,
        calibrations_written=shadow.calibrations_written,
        calibrations_skipped=shadow.calibrations_skipped,
        calibrated_forecasts_written=shadow.calibrated_forecasts_written,
        calibrated_forecasts_skipped=shadow.calibrated_forecasts_skipped,
        conflicts=conflicts,
        degraded_reason=degraded,
    )


__all__ = [
    "AMENDMENTS",
    "ASSESSMENTS",
    "CALIBRATED_FORECASTS",
    "CALIBRATIONS",
    "ForecastRegistryConflict",
    "ForecastRegistryError",
    "RegistryWriteResult",
    "collect_lineage_from_state",
    "collect_shadow_calibrations_from_state",
    "get_forecast_amendment",
    "get_forecast_assessment",
    "persist_forecast_lineage",
    "persist_forecast_lineage_from_state",
    "persist_shadow_calibrations",
]
