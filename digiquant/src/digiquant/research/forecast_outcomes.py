"""Resolve matured prospective forecasts into ``ForecastOutcome`` rows (#2676 / WP5.2).

Invoked beside legacy ``decision_log`` reflection (preflight_reflect) — never inside
it and never from conviction scores. Writes only to private append-only
``olympus_forecast_outcomes``. Missing trading calendar or closes leave the
forecast logically pending (no invented zero return). Same-run forecasts are
excluded so outcomes cannot feedback into the run that produced them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import (
    Any,  # score:allow untyped any — duck-typed Supabase client / row dicts
    Sequence,
)
from uuid import UUID

from digiquant.research.forecast_registry import AMENDMENTS, ASSESSMENTS
from digiquant.research.supabase_io import SupabaseClient
from digiquant.portfolio.models.forecast import (
    AmendmentOutcome,
    ForecastAmendment,
    ForecastAssessment,
    PriceAnchorStatus,
    resolve_effective_forecast,
)
from digiquant.portfolio.models.forecast_calibration import (
    ForecastOutcome,
    OutcomeStatus,
    SessionPriceSnapshot,
    forecast_outcome_content_hash,
    forecast_outcome_id,
)
from digiquant.dashboard.temporal import require_utc_datetime

logger = logging.getLogger(__name__)

OUTCOMES = "olympus_forecast_outcomes"
DEFAULT_VENUE = "NYSE"
# US equity cash close proxy when price_history has no observation timestamp.
_SESSION_CLOSE_HOUR_UTC = 20


@dataclass(frozen=True)
class OutcomeResolveResult:
    """Counts from one :func:`resolve_matured_forecast_outcomes` pass."""

    resolved: int = 0
    pending: int = 0
    skipped: int = 0
    conflicts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.conflicts


def _insert(*, client: SupabaseClient, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    client.table(OUTCOMES).insert(rows).execute()


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


def _load_trading_sessions(
    *,
    client: SupabaseClient,
    venue: str,
) -> tuple[date, ...] | None:
    """Return ascending trading-session dates for ``venue``, or ``None`` if absent."""
    from digiquant.data.prices._utils import fetch_trading_days

    series = fetch_trading_days(client, venue)
    if series is None or series.is_empty():
        return None
    days = tuple(series.to_list())
    return days or None


def _session_on_or_before(target: date, sessions: Sequence[date]) -> date | None:
    prior = [d for d in sessions if d <= target]
    return prior[-1] if prior else None


def _nth_session_after(
    reference: date,
    *,
    horizon_sessions: int,
    sessions: Sequence[date],
) -> date | None:
    """Maturity = reference + ``horizon_sessions`` trading sessions (not calendar days)."""
    try:
        idx = list(sessions).index(reference)
    except ValueError:
        return None
    target_idx = idx + horizon_sessions
    if target_idx >= len(sessions):
        return None
    return sessions[target_idx]


def _session_close_utc(session: date) -> datetime:
    return datetime(
        session.year,
        session.month,
        session.day,
        _SESSION_CLOSE_HOUR_UTC,
        0,
        0,
        tzinfo=UTC,
    )


def _fetch_session_close(
    *,
    client: SupabaseClient,
    ticker: str,
    session: date,
) -> Decimal | None:
    resp = (
        client.table("price_history")
        .select("date, close")
        .eq("ticker", ticker.strip().upper())
        .eq("date", session.isoformat())
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return None
    raw = rows[0].get("close")
    if raw is None:
        return None
    try:
        price = Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return None
    if price <= 0:
        return None
    return price


def _list_cutoff_assessments(
    *,
    client: SupabaseClient,
    knowledge_cutoff_at: datetime,
) -> list[ForecastAssessment]:
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    resp = client.table(ASSESSMENTS).select("*").lte("known_at", cutoff.isoformat()).execute()
    out: list[ForecastAssessment] = []
    for row in list(getattr(resp, "data", None) or []):
        known = _parse_known_at(row.get("known_at"))
        if known is None or known > cutoff:
            continue
        payload = {k: row[k] for k in _ASSESSMENT_FIELDS if k in row}
        try:
            out.append(ForecastAssessment.model_validate(payload))
        except Exception as exc:
            logger.warning(
                "forecast outcomes: skip invalid assessment (%s: %s)",
                type(exc).__name__,
                exc,
            )
    return out


def _list_cutoff_amendments(
    *,
    client: SupabaseClient,
    base_forecast_id: UUID,
    knowledge_cutoff_at: datetime,
) -> list[ForecastAmendment]:
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    resp = (
        client.table(AMENDMENTS)
        .select("*")
        .eq("base_forecast_id", str(base_forecast_id))
        .lte("known_at", cutoff.isoformat())
        .execute()
    )
    out: list[ForecastAmendment] = []
    for row in list(getattr(resp, "data", None) or []):
        known = _parse_known_at(row.get("known_at"))
        if known is None or known > cutoff:
            continue
        payload = {k: row[k] for k in _AMENDMENT_FIELDS if k in row}
        try:
            out.append(ForecastAmendment.model_validate(payload))
        except Exception as exc:
            logger.warning(
                "forecast outcomes: skip invalid amendment (%s: %s)",
                type(exc).__name__,
                exc,
            )
    return out


def _tip_amendment(amendments: Sequence[ForecastAmendment]) -> ForecastAmendment | None:
    if not amendments:
        return None
    superseded = {
        a.supersedes_amendment_id for a in amendments if a.supersedes_amendment_id is not None
    }
    tips = [a for a in amendments if a.amendment_id not in superseded]
    pool = tips or list(amendments)
    return max(pool, key=lambda a: (a.known_at, a.effective_at, str(a.amendment_id)))


def _reference_session_for(
    assessment: ForecastAssessment,
    *,
    sessions: Sequence[date],
) -> date | None:
    anchor = assessment.price_anchor
    if anchor.status is PriceAnchorStatus.OBSERVED and anchor.observed_at is not None:
        return _session_on_or_before(anchor.observed_at.date(), sessions)
    return _session_on_or_before(assessment.effective_at.date(), sessions)


def _reference_snapshot(
    *,
    assessment: ForecastAssessment,
    reference_session: date,
    client: SupabaseClient,
    knowledge_cutoff_at: datetime,
) -> SessionPriceSnapshot | None:
    """Exact observed anchor when present; else first prospective close snapshot."""
    anchor = assessment.price_anchor
    if (
        anchor.status is PriceAnchorStatus.OBSERVED
        and anchor.price is not None
        and anchor.observed_at is not None
    ):
        return SessionPriceSnapshot(
            session_date=reference_session,
            price=anchor.price,
            observed_at=anchor.observed_at,
            known_at=assessment.known_at,
        )
    close = _fetch_session_close(client=client, ticker=assessment.ticker, session=reference_session)
    if close is None:
        return None
    observed_at = _session_close_utc(reference_session)
    known_at = knowledge_cutoff_at
    if known_at < observed_at:
        # Cutoff before session close cannot honestly know the close.
        return None
    return SessionPriceSnapshot(
        session_date=reference_session,
        price=close,
        observed_at=observed_at,
        known_at=known_at,
    )


def _maturity_snapshot(
    *,
    client: SupabaseClient,
    ticker: str,
    maturity_session: date,
    knowledge_cutoff_at: datetime,
) -> SessionPriceSnapshot | None:
    close = _fetch_session_close(client=client, ticker=ticker, session=maturity_session)
    if close is None:
        return None
    observed_at = _session_close_utc(maturity_session)
    if knowledge_cutoff_at < observed_at:
        return None
    return SessionPriceSnapshot(
        session_date=maturity_session,
        price=close,
        observed_at=observed_at,
        known_at=knowledge_cutoff_at,
    )


def _existing_outcome(
    *,
    client: SupabaseClient,
    effective_forecast_id: UUID,
    maturity_session: date,
) -> dict[str, Any] | None:
    resp = (
        client.table(OUTCOMES)
        .select("*")
        .eq("effective_forecast_id", str(effective_forecast_id))
        .eq("maturity_session", maturity_session.isoformat())
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    return rows[0] if rows else None


def _outcome_row(outcome: ForecastOutcome) -> dict[str, Any]:
    return {
        "outcome_id": str(outcome.outcome_id),
        "base_forecast_id": str(outcome.base_forecast_id),
        "effective_forecast_id": str(outcome.effective_forecast_id),
        "ticker": outcome.ticker.strip().upper(),
        "horizon_sessions": outcome.horizon_sessions,
        "reference_session": outcome.reference_session.isoformat(),
        "maturity_session": outcome.maturity_session.isoformat(),
        "reference_snapshot": (
            None
            if outcome.reference_snapshot is None
            else outcome.reference_snapshot.model_dump(mode="json")
        ),
        "maturity_snapshot": (
            None
            if outcome.maturity_snapshot is None
            else outcome.maturity_snapshot.model_dump(mode="json")
        ),
        "forecast_mean_return": (
            None if outcome.forecast_mean_return is None else str(outcome.forecast_mean_return)
        ),
        "realized_return": (
            None if outcome.realized_return is None else str(outcome.realized_return)
        ),
        "signed_residual": (
            None if outcome.signed_residual is None else str(outcome.signed_residual)
        ),
        "positive_label": outcome.positive_label,
        "status": outcome.status.value,
        "unavailable_reason": outcome.unavailable_reason,
        "content_hash": outcome.content_hash,
        "event_time": outcome.event_time.isoformat(),
        "known_at": outcome.known_at.isoformat(),
    }


def _build_resolved_outcome(
    *,
    base: ForecastAssessment,
    effective_id: UUID,
    ticker: str,
    horizon_sessions: int,
    reference_session: date,
    maturity_session: date,
    reference_snapshot: SessionPriceSnapshot,
    maturity_snapshot: SessionPriceSnapshot,
    forecast_mean_return: Decimal,
) -> ForecastOutcome:
    realized = (maturity_snapshot.price - reference_snapshot.price) / reference_snapshot.price
    residual = realized - forecast_mean_return
    positive = realized > Decimal("0")
    event_time = maturity_snapshot.observed_at
    known_at = maturity_snapshot.known_at
    draft = {
        "base_forecast_id": base.forecast_id,
        "effective_forecast_id": effective_id,
        "ticker": ticker.strip().upper(),
        "horizon_sessions": horizon_sessions,
        "reference_session": reference_session,
        "maturity_session": maturity_session,
        "reference_snapshot": reference_snapshot,
        "maturity_snapshot": maturity_snapshot,
        "forecast_mean_return": forecast_mean_return,
        "realized_return": realized,
        "signed_residual": residual,
        "positive_label": positive,
        "status": OutcomeStatus.RESOLVED,
        "unavailable_reason": None,
        "event_time": event_time,
        "known_at": known_at,
    }
    payload = {
        "base_forecast_id": str(draft["base_forecast_id"]),
        "effective_forecast_id": str(draft["effective_forecast_id"]),
        "ticker": draft["ticker"],
        "horizon_sessions": horizon_sessions,
        "reference_session": reference_session.isoformat(),
        "maturity_session": maturity_session.isoformat(),
        "reference_snapshot": reference_snapshot.model_dump(mode="json"),
        "maturity_snapshot": maturity_snapshot.model_dump(mode="json"),
        "forecast_mean_return": str(forecast_mean_return),
        "realized_return": str(realized),
        "signed_residual": str(residual),
        "positive_label": positive,
        "status": OutcomeStatus.RESOLVED.value,
        "unavailable_reason": None,
        "event_time": event_time.isoformat(),
        "known_at": known_at.isoformat(),
    }
    content_hash = forecast_outcome_content_hash(payload=payload)
    outcome_id = forecast_outcome_id(
        effective_forecast_id=effective_id,
        maturity_session=maturity_session,
        content_hash=content_hash,
    )
    return ForecastOutcome(outcome_id=outcome_id, content_hash=content_hash, **draft)  # type: ignore[arg-type]


def resolve_matured_forecast_outcomes(
    *,
    client: SupabaseClient,
    run_date: date,
    knowledge_cutoff_at: datetime,
    current_run_id: str | None = None,
    venue: str = DEFAULT_VENUE,
    trading_sessions: Sequence[date] | None = None,
) -> OutcomeResolveResult:
    """Snapshot due prospective forecasts into immutable outcome rows.

    Parameters
    ----------
    run_date:
        Current research run date — maturity must be on or before this session day.
    knowledge_cutoff_at:
        Pinned run cutoff; forecasts and closes known after it are invisible.
    current_run_id:
        When set, assessments/amendments from this run are excluded (no same-run
        feedback).
    trading_sessions:
        Optional injected calendar (tests). Production loads ``trading_calendar``.
    """
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    sessions: tuple[date, ...] | None
    if trading_sessions is not None:
        sessions = tuple(sorted(trading_sessions))
    else:
        sessions = _load_trading_sessions(client=client, venue=venue)

    if not sessions:
        logger.info(
            "forecast outcomes: trading calendar missing/empty for venue=%s — pending",
            venue,
        )
        return OutcomeResolveResult(pending=0, skipped=0)

    assessments = _list_cutoff_assessments(client=client, knowledge_cutoff_at=cutoff)
    resolved = pending = skipped = 0
    conflicts: list[str] = []
    run_key = (current_run_id or "").strip()

    for assessment in assessments:
        if run_key and assessment.source_run_id.strip() == run_key:
            skipped += 1
            continue

        amendments = _list_cutoff_amendments(
            client=client,
            base_forecast_id=assessment.forecast_id,
            knowledge_cutoff_at=cutoff,
        )
        tip = _tip_amendment(amendments)
        if tip is not None and run_key and tip.source_run_id.strip() == run_key:
            # Same-run amendment tip — fall back to base only when base is older.
            if assessment.source_run_id.strip() == run_key:
                skipped += 1
                continue
            tip = None

        effective = (
            resolve_effective_forecast(
                base=assessment,
                amendment=tip,
                amendment_outcome=AmendmentOutcome.ACCEPTED,
                known_at=cutoff,
            )
            if tip is not None
            else resolve_effective_forecast(base=assessment, known_at=cutoff)
        )

        reference_session = _reference_session_for(assessment, sessions=sessions)
        if reference_session is None:
            pending += 1
            continue

        maturity_session = _nth_session_after(
            reference_session,
            horizon_sessions=effective.terms.horizon_sessions,
            sessions=sessions,
        )
        if maturity_session is None:
            pending += 1
            continue
        if maturity_session > run_date:
            pending += 1
            continue

        existing = _existing_outcome(
            client=client,
            effective_forecast_id=effective.effective_id,
            maturity_session=maturity_session,
        )
        if existing is not None:
            skipped += 1
            continue

        ref_snap = _reference_snapshot(
            assessment=assessment,
            reference_session=reference_session,
            client=client,
            knowledge_cutoff_at=cutoff,
        )
        if ref_snap is None:
            pending += 1
            continue

        mat_snap = _maturity_snapshot(
            client=client,
            ticker=assessment.ticker,
            maturity_session=maturity_session,
            knowledge_cutoff_at=cutoff,
        )
        if mat_snap is None:
            pending += 1
            continue

        outcome = _build_resolved_outcome(
            base=assessment,
            effective_id=effective.effective_id,
            ticker=assessment.ticker,
            horizon_sessions=effective.terms.horizon_sessions,
            reference_session=reference_session,
            maturity_session=maturity_session,
            reference_snapshot=ref_snap,
            maturity_snapshot=mat_snap,
            forecast_mean_return=effective.terms.scenario_mean_return(),
        )

        # Re-check natural key after build (concurrent writer / exact retry race).
        existing = _existing_outcome(
            client=client,
            effective_forecast_id=outcome.effective_forecast_id,
            maturity_session=outcome.maturity_session,
        )
        if existing is not None:
            if str(existing.get("content_hash") or "") == outcome.content_hash:
                skipped += 1
                continue
            conflicts.append(
                f"effective_forecast_id={outcome.effective_forecast_id} "
                f"maturity={outcome.maturity_session.isoformat()} content conflict"
            )
            continue

        try:
            _insert(client=client, rows=[_outcome_row(outcome)])
        except Exception as exc:
            logger.warning(
                "forecast outcomes: insert failed for %s (%s: %s)",
                outcome.effective_forecast_id,
                type(exc).__name__,
                exc,
            )
            pending += 1
            continue
        resolved += 1

    if resolved or pending or skipped or conflicts:
        logger.info(
            "forecast outcomes resolved=%d pending=%d skipped=%d conflicts=%d (run_date=%s)",
            resolved,
            pending,
            skipped,
            len(conflicts),
            run_date.isoformat(),
        )
    return OutcomeResolveResult(
        resolved=resolved,
        pending=pending,
        skipped=skipped,
        conflicts=tuple(conflicts),
    )


_OUTCOME_FIELDS = frozenset(
    {
        "outcome_id",
        "base_forecast_id",
        "effective_forecast_id",
        "ticker",
        "horizon_sessions",
        "reference_session",
        "maturity_session",
        "reference_snapshot",
        "maturity_snapshot",
        "forecast_mean_return",
        "realized_return",
        "signed_residual",
        "positive_label",
        "status",
        "unavailable_reason",
        "content_hash",
        "event_time",
        "known_at",
    }
)


def list_resolved_outcomes_as_of(
    *,
    client: SupabaseClient,
    knowledge_cutoff_at: datetime,
) -> list[ForecastOutcome]:
    """Exact rows with ``status=resolved`` and ``known_at <= cutoff`` (no latest lookup).

    Used by WP5.4 shadow calibration attach. Late-known rows are invisible.
    Invalid rows are skipped rather than inventing labels.
    """
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    resp = (
        client.table(OUTCOMES)
        .select("*")
        .eq("status", OutcomeStatus.RESOLVED.value)
        .lte("known_at", cutoff.isoformat())
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    out: list[ForecastOutcome] = []
    for row in rows:
        known = _parse_known_at(row.get("known_at"))
        if known is None or known > cutoff:
            continue
        payload = {k: row[k] for k in _OUTCOME_FIELDS if k in row}
        try:
            out.append(ForecastOutcome.model_validate(payload))
        except Exception as exc:
            logger.warning(
                "forecast outcomes: skip invalid resolved row (%s: %s)",
                type(exc).__name__,
                exc,
            )
    return sorted(out, key=lambda o: (o.known_at, str(o.outcome_id)))


__all__ = [
    "DEFAULT_VENUE",
    "OUTCOMES",
    "OutcomeResolveResult",
    "list_resolved_outcomes_as_of",
    "resolve_matured_forecast_outcomes",
]
