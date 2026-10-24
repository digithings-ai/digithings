"""Resolve matured prospective forecasts into ``ForecastOutcome`` rows (#2676 / WP5.2).

Invoked beside legacy ``decision_log`` reflection (preflight_reflect) — never inside
it and never from conviction scores. Writes only to private append-only
``forecast_outcomes``. Missing trading calendar or closes leave the
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
    Collection,
    Mapping,
    Sequence,
)
from uuid import UUID

from pydantic import ValidationError

from digiquant.dashboard.temporal import require_utc_datetime
from digiquant.portfolio.models.forecast import (
    AmendmentOutcome,
    EffectiveForecast,
    ForecastAmendment,
    ForecastAssessment,
    PriceAnchorStatus,
    resolve_effective_forecast,
)
from digiquant.portfolio.models.forecast_calibration import (
    CalibratedForecast,
    CalibrationArtifactStatus,
    ForecastCalibration,
    ForecastOutcome,
    OutcomeStatus,
    SessionPriceSnapshot,
    calibrated_forecast_content_hash,
    calibrated_forecast_id,
    forecast_calibration_content_hash,
    forecast_calibration_id,
    forecast_outcome_content_hash,
    forecast_outcome_hash_payload,
    forecast_outcome_id,
)
from digiquant.research.data.queries import r2_backend_enabled
from digiquant.research.forecast_registry import AMENDMENTS, ASSESSMENTS
from digiquant.research.supabase_io import SupabaseClient

logger = logging.getLogger(__name__)

OUTCOMES = "forecast_outcomes"
DEFAULT_VENUE = "NYSE"
# US equity cash close proxy when price_history has no observation timestamp.
_SESSION_CLOSE_HOUR_UTC = 20

# Batched existence probe sizing (#4579). ``_existing_outcome_keys`` asks for one
# chunk of distinct ``effective_forecast_id`` values per request so a long
# assessment list cannot blow the request URL apart, and pages below the
# PostgREST 1000-row response cap (#3789) the way ``_scan_all`` does.
_OUTCOME_KEY_CHUNK = 100
_OUTCOME_KEY_PAGE = 1000


class ForecastOutcomeIntegrityError(RuntimeError):
    """A persisted resolved outcome no longer matches its canonical digest (#4298).

    Raised by :func:`list_resolved_outcomes_as_of` instead of silently dropping the
    row: a daily house reflect that quietly skips a matured label is worse than a
    loud failure. Repair the stored row with
    ``digiquant/scripts/research/repair_forecast_outcome_hashes.py``.
    """


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


# R2 generations store OHLCV as float64 by design, so a stored close such as
# ``10.380000114440918`` is the correct float rendering, not corrupt data.
# ``PositivePrice`` caps at ``decimal_places=8``, so the raw float keeps binary
# noise past the model's money precision and trips ``decimal_max_places`` (#4296).
_PRICE_QUANTUM = Decimal("0.00000001")
# ``PositivePrice`` (portfolio/models/forecast_calibration.py) is
# ``gt=0, allow_inf_nan=False, max_digits=20, decimal_places=8``, so a
# representable close is strictly below ``10**12``. A raw close at or above that
# band is not a real NYSE equity print — it is corrupt data. Treat it as an
# absent close (pending), exactly like an unparseable or non-positive one,
# rather than coercing it into a plausible price or aborting the whole
# preflight.reflect run (#4309 review F4b).
_PRICE_MAX_EXCLUSIVE = Decimal("1000000000000")  # 10**12


def _quantize_price(value: Decimal) -> Decimal:
    """Round a raw price to the price-model money precision (#4296).

    ``Decimal(str(raw))`` on an R2 float64 close yields a 15-place Decimal
    (``10.380000114440918``) that ``SessionPriceSnapshot.price`` rejects, which
    aborted ``preflight.reflect`` for the whole house research run. Normalizing
    here — at the raw-price ingress every forecast snapshot shares — gives each
    consumer a value the models accept. This is a normalization, not a
    swallowed ``ValidationError``, and it never skips a matured outcome.
    """
    return value.quantize(_PRICE_QUANTUM)


def _fetch_session_close(
    *,
    client: SupabaseClient,
    ticker: str,
    session: date,
) -> Decimal | None:
    sym = ticker.strip().upper()
    if r2_backend_enabled():
        # Sealed R2 generation; single-date window (#3780 Task 7b).
        from digiquant.research.data.queries import UnknownTickerError, r2_close_rows

        try:
            rows = r2_close_rows(tickers=[sym], since=session, until=session)
        except UnknownTickerError:
            # No sealed generation for this ticker: an absent close, not a fault.
            # A matured forecast can outlive a ticker's R2 universe membership,
            # and every caller already treats a None close as pending (#4119).
            logger.info("forecast outcomes: no R2 generation for %s; close absent", sym)
            return None
        raws = [r.get("close") for r in rows if r.get("ticker") == sym]
        raw = raws[0] if raws else None
    else:
        # Retired: migration 127 drops price_history (#4053) — R2 only above.
        resp = (
            client.table("price_history")
            .select("date, close")
            .eq("ticker", sym)
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
        price = _quantize_price(Decimal(str(raw)))
    except (ArithmeticError, ValueError):
        return None
    # ``Decimal('nan').quantize(...)`` returns NaN (it does not raise) and NaN
    # fails every ``<=``/``>=`` comparison, so an explicit finiteness check is
    # required before the range guards (#4309 review F4a). A non-finite or
    # out-of-band close is an absent close (pending), never a coerced price.
    if not price.is_finite() or price <= 0 or price >= _PRICE_MAX_EXCLUSIVE:
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


def _existing_outcome_keys(
    *,
    client: SupabaseClient,
    keys: list[tuple[UUID, date]],
) -> set[tuple[str, str]]:
    """Natural keys from ``keys`` that already have an ``OUTCOMES`` row (#4579).

    The per-assessment probe was one round trip each — 44 of them in run
    35857376877 — so the resolver asks once for every candidate instead. The
    table is append-only (migration 080), so a read-only batch sees only
    committed rows. No request is issued when there is nothing to check.
    """
    ids = sorted({str(effective_id) for effective_id, _ in keys})
    if not ids:
        return set()
    found: set[tuple[str, str]] = set()
    for start in range(0, len(ids), _OUTCOME_KEY_CHUNK):
        chunk = ids[start : start + _OUTCOME_KEY_CHUNK]
        offset = 0
        while True:
            resp = (
                client.table(OUTCOMES)
                .select("effective_forecast_id, maturity_session")
                .in_("effective_forecast_id", chunk)
                # Order on the whole natural key so a .range() page boundary can
                # never split a tie and skip a row (#3954, the _scan_all rule).
                .order("effective_forecast_id")
                .order("maturity_session")
                .range(offset, offset + _OUTCOME_KEY_PAGE - 1)
                .execute()
            )
            rows = list(getattr(resp, "data", None) or [])
            for row in rows:
                found.add((str(row["effective_forecast_id"]), str(row["maturity_session"])))
            if len(rows) < _OUTCOME_KEY_PAGE:
                break
            offset += _OUTCOME_KEY_PAGE
    return found


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


_RETURN_FRACTION_QUANTUM = Decimal("0.00000001")  # ReturnFraction decimal_places=8


def _quantize_return_fraction(value: Decimal) -> Decimal:
    """Clamp a computed return to ``ReturnFraction`` digit/place limits.

    Decimal division of prices routinely exceeds ``max_digits=16`` /
    ``decimal_places=8`` on :class:`ForecastOutcome` fields; Pydantic then raises
    ``decimal_max_digits`` during preflight_reflect outcome assembly.
    """
    return value.quantize(_RETURN_FRACTION_QUANTUM)


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
    realized = _quantize_return_fraction(
        (maturity_snapshot.price - reference_snapshot.price) / reference_snapshot.price
    )
    residual = _quantize_return_fraction(realized - forecast_mean_return)
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
    payload = forecast_outcome_hash_payload(
        base_forecast_id=base.forecast_id,
        effective_forecast_id=effective_id,
        ticker=ticker.strip().upper(),
        horizon_sessions=horizon_sessions,
        reference_session=reference_session,
        maturity_session=maturity_session,
        reference_snapshot=reference_snapshot,
        maturity_snapshot=maturity_snapshot,
        forecast_mean_return=forecast_mean_return,
        realized_return=realized,
        signed_residual=residual,
        positive_label=positive,
        status=OutcomeStatus.RESOLVED,
        unavailable_reason=None,
        event_time=event_time,
        known_at=known_at,
    )
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

    # Pass 1 — resolve every assessment that is actually due, without touching
    # OUTCOMES. The existence probe is batched afterwards (#4579).
    candidates: list[tuple[ForecastAssessment, EffectiveForecast, date, date]] = []
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

        candidates.append((assessment, effective, reference_session, maturity_session))

    # Pass 2 — one batched existence read for every candidate natural key (#4579).
    existing_keys = _existing_outcome_keys(
        client=client,
        keys=[(candidate[1].effective_id, candidate[3]) for candidate in candidates],
    )

    for assessment, effective, reference_session, maturity_session in candidates:
        if (str(effective.effective_id), maturity_session.isoformat()) in existing_keys:
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


# Run-scoped memo for the cutoff-bounded resolved-outcome cohort (#4617).
#
# Each daily run issued the byte-identical ``list_resolved_outcomes_as_of`` GET
# twice — once at research preflight (direction prerequisites) and once in the
# portfolio direction phase (shadow calibration). Both call sites share one
# client and one pinned ``knowledge_cutoff_at`` per run, so the second read is
# a cache hit. Keyed by ``(id(client), cutoff_iso)``: no TTL clocks, no round
# caps, no cross-client contamination. Errors (including
# ``ForecastOutcomeIntegrityError``) are never stored, so the #4298 fail-loud
# and generic-``Exception`` fail-soft contracts of both callers are unchanged.
ResolvedOutcomesMemo = dict[tuple[int, str], list[ForecastOutcome]]


def list_resolved_outcomes_as_of_memoized(
    *,
    client: SupabaseClient,
    knowledge_cutoff_at: datetime,
    memo: ResolvedOutcomesMemo | None,
) -> list[ForecastOutcome]:
    """Share one ``list_resolved_outcomes_as_of`` GET across a run's readers (#4617).

    Contract: share a single ``memo`` dict per (run, client) — production wires
    one instance through preflight and the direction phase. ``memo=None``
    degrades to a direct read. Hits return a copy so neither reader can mutate
    the cohort the other one sees.
    """
    if memo is None:
        return list_resolved_outcomes_as_of(client=client, knowledge_cutoff_at=knowledge_cutoff_at)
    cutoff = require_utc_datetime(knowledge_cutoff_at, field_name="knowledge_cutoff_at")
    key = (id(client), cutoff.isoformat())
    cached = memo.get(key)
    if cached is not None:
        return list(cached)
    resolved = list_resolved_outcomes_as_of(client=client, knowledge_cutoff_at=cutoff)
    memo[key] = resolved
    return list(resolved)


def list_resolved_outcomes_as_of(
    *,
    client: SupabaseClient,
    knowledge_cutoff_at: datetime,
) -> list[ForecastOutcome]:
    """Exact rows with ``status=resolved`` and ``known_at <= cutoff`` (no latest lookup).

    Used by WP5.4 shadow calibration attach. Late-known rows are invisible.
    A row that fails canonical validation raises
    :class:`ForecastOutcomeIntegrityError` rather than being silently skipped:
    dropping a matured label would quietly shrink the calibration cohort (#4298).
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
        except ValidationError as exc:
            raise ForecastOutcomeIntegrityError(
                f"forecast outcome {row.get('outcome_id')!r} failed canonical validation: {exc}. "
                "Repair stored hashes with "
                "digiquant/scripts/research/repair_forecast_outcome_hashes.py"
            ) from exc
    return sorted(out, key=lambda o: (o.known_at, str(o.outcome_id)))


@dataclass(frozen=True)
class ForecastOutcomeHashRepair:
    """One stored outcome whose digest no longer matches the canonical payload."""

    outcome_id: str
    repaired_outcome_id: str
    recorded_content_hash: str
    repaired_content_hash: str


@dataclass(frozen=True)
class ForecastOutcomeHashRepairPlan:
    """Dry-run result: rows to rewrite plus rows that are genuinely corrupt."""

    repairs: tuple[ForecastOutcomeHashRepair, ...] = field(default_factory=tuple)
    unrepairable: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.unrepairable


def _outcome_source_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Coerce one persisted row into constructor-ready field values.

    PostgREST returns ``numeric`` as JSON numbers (Python float) and ``jsonb``
    snapshots as nested objects; a direct psycopg read returns ``Decimal`` /
    ``date`` / ``datetime`` / ``UUID`` natively. Normalize both shapes.
    """
    fields: dict[str, Any] = {
        name: row[name] for name in ForecastOutcome.model_fields if name in row
    }
    for snapshot_key in ("reference_snapshot", "maturity_snapshot"):
        value = fields.get(snapshot_key)
        if isinstance(value, Mapping):
            fields[snapshot_key] = SessionPriceSnapshot.model_validate(dict(value))
    for decimal_key in ("forecast_mean_return", "realized_return", "signed_residual"):
        value = fields.get(decimal_key)
        if value is not None and not isinstance(value, Decimal):
            fields[decimal_key] = Decimal(str(value))
    for session_key in ("reference_session", "maturity_session"):
        value = fields.get(session_key)
        if isinstance(value, str):
            fields[session_key] = date.fromisoformat(value)
    for instant_key in ("event_time", "known_at"):
        value = fields.get(instant_key)
        if isinstance(value, str):
            fields[instant_key] = _parse_known_at(value)
    status = fields.get("status")
    if status is not None and not isinstance(status, OutcomeStatus):
        fields["status"] = OutcomeStatus(str(status))
    for uuid_key in ("outcome_id", "base_forecast_id", "effective_forecast_id"):
        value = fields.get(uuid_key)
        if isinstance(value, str):
            fields[uuid_key] = UUID(value)
    return fields


def plan_forecast_outcome_hash_repairs(
    *,
    rows: Sequence[Mapping[str, Any]],
    cited_outcome_ids: Collection[str] = (),
) -> ForecastOutcomeHashRepairPlan:
    """Plan idempotent digest repairs for stored outcome rows (#4298).

    Pure and read-only: rebuild each row's canonical payload from its stored
    fields, recompute ``content_hash`` and ``outcome_id``, and re-validate the
    result. A row that still fails validation after recomputation is genuinely
    corrupt (bad residual/snapshot/ordering) and is reported under
    ``unrepairable`` — never rewritten. Rows already canonical are omitted, so a
    second pass after an applied repair returns an empty plan.

    ``cited_outcome_ids`` are the ``outcome_id`` values referenced by
    ``olympus_forecast_calibrations.outcome_ids``. A repair rewrites the PK, and
    that array is covered by the calibration's own immutable
    ``content_hash``/``calibration_id`` (and, transitively, by
    ``olympus_calibrated_forecasts.calibration_id``). An in-place array rewrite
    would therefore either invalidate the immutable calibration digest or force
    a multi-table PK cascade across two more append-only tables — wrong for a
    one-shot hash repair. Such a row is refused and reported under
    ``unrepairable`` with its reason instead of being silently rewritten with
    stale lineage (#4295 G2).
    """
    repairs: list[ForecastOutcomeHashRepair] = []
    unrepairable: list[str] = []
    cited = {str(item) for item in cited_outcome_ids}
    for row in rows:
        fields = _outcome_source_fields(row)
        recorded_id = str(fields.get("outcome_id") or "")
        recorded_hash = str(fields.get("content_hash") or "")
        try:
            constructed = ForecastOutcome.model_construct(**fields)
            repaired_hash = forecast_outcome_content_hash(payload=constructed._hash_payload())
            repaired_id = forecast_outcome_id(
                effective_forecast_id=constructed.effective_forecast_id,
                maturity_session=constructed.maturity_session,
                content_hash=repaired_hash,
            )
            # Genuinely corrupt rows raise here and are never rewritten.
            ForecastOutcome.model_validate(
                {**fields, "outcome_id": repaired_id, "content_hash": repaired_hash}
            )
        except Exception as exc:
            unrepairable.append(
                f"{recorded_id or '<missing outcome_id>'}: {type(exc).__name__}: {exc}"
            )
            continue
        if recorded_id == str(repaired_id) and recorded_hash == repaired_hash:
            continue
        if recorded_id and recorded_id in cited:
            unrepairable.append(
                f"{recorded_id}: cited_by_calibration: outcome_id is still referenced by "
                "olympus_forecast_calibrations.outcome_ids, which its immutable "
                "content_hash/calibration_id cover; rewriting the digest would either "
                "invalidate that calibration or cascade PK changes across "
                "olympus_calibrated_forecasts, so refusal is deliberate (#4295 G2)"
            )
            continue
        repairs.append(
            ForecastOutcomeHashRepair(
                outcome_id=recorded_id,
                repaired_outcome_id=str(repaired_id),
                recorded_content_hash=recorded_hash,
                repaired_content_hash=repaired_hash,
            )
        )
    return ForecastOutcomeHashRepairPlan(repairs=tuple(repairs), unrepairable=tuple(unrepairable))


@dataclass(frozen=True)
class ForecastCalibrationHashRepair:
    """One stored calibration whose cited outcome ids were rewritten."""

    calibration_id: str
    repaired_calibration_id: str
    recorded_content_hash: str
    repaired_content_hash: str


@dataclass(frozen=True)
class CalibratedForecastHashRepair:
    """One stored calibrated forecast whose calibration id was rewritten."""

    calibrated_forecast_id: str
    repaired_calibrated_forecast_id: str
    recorded_content_hash: str
    repaired_content_hash: str


@dataclass(frozen=True)
class ForecastOutcomeCascadePlan:
    """Dry-run result of the full citation cascade (#4295 G2 / #4298).

    ``outcomes`` rewrites the stale ``forecast_outcomes`` rows; ``calibrations``
    and ``calibrated_forecasts`` carry the transitive id churn those rewrites
    force through the two append-only citing tables.
    """

    outcomes: tuple[ForecastOutcomeHashRepair, ...] = field(default_factory=tuple)
    calibrations: tuple[ForecastCalibrationHashRepair, ...] = field(default_factory=tuple)
    calibrated_forecasts: tuple[CalibratedForecastHashRepair, ...] = field(default_factory=tuple)
    unrepairable: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.unrepairable

    @property
    def writes(self) -> int:
        return len(self.outcomes) + len(self.calibrations) + len(self.calibrated_forecasts)


def _calibration_source_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Coerce one persisted calibration row, handling psycopg and PostgREST shapes."""
    fields: dict[str, Any] = {
        name: row[name] for name in ForecastCalibration.model_fields if name in row
    }
    for decimal_key in (
        "equivalent_sample_size",
        "bias",
        "dispersion",
        "brier_score",
        "log_score",
        "reliability",
    ):
        value = fields.get(decimal_key)
        if value is not None and not isinstance(value, Decimal):
            fields[decimal_key] = Decimal(str(value))
    calibration_id = fields.get("calibration_id")
    if isinstance(calibration_id, str):
        fields["calibration_id"] = UUID(calibration_id)
    outcome_ids = fields.get("outcome_ids")
    if outcome_ids is not None:
        fields["outcome_ids"] = tuple(UUID(str(item)) for item in outcome_ids)
    status = fields.get("status")
    if status is not None and not isinstance(status, CalibrationArtifactStatus):
        fields["status"] = CalibrationArtifactStatus(str(status))
    for instant_key in ("effective_at", "known_at"):
        value = fields.get(instant_key)
        if isinstance(value, str):
            fields[instant_key] = _parse_known_at(value)
    return fields


def _calibrated_forecast_source_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Coerce one persisted calibrated-forecast row into constructor-ready values."""
    fields: dict[str, Any] = {
        name: row[name] for name in CalibratedForecast.model_fields if name in row
    }
    for decimal_key in (
        "expected_gross_return",
        "forecast_error_std",
        "calibrated_positive_probability",
        "reliability_weight",
    ):
        value = fields.get(decimal_key)
        if value is not None and not isinstance(value, Decimal):
            fields[decimal_key] = Decimal(str(value))
    quantiles = fields.get("downside_quantiles")
    if quantiles is not None:
        fields["downside_quantiles"] = tuple(
            item if isinstance(item, Decimal) else Decimal(str(item)) for item in quantiles
        )
    for uuid_key in (
        "calibrated_forecast_id",
        "base_forecast_id",
        "effective_forecast_id",
        "calibration_id",
    ):
        value = fields.get(uuid_key)
        if isinstance(value, str):
            fields[uuid_key] = UUID(value)
    status = fields.get("status")
    if status is not None and not isinstance(status, CalibrationArtifactStatus):
        fields["status"] = CalibrationArtifactStatus(str(status))
    for instant_key in ("effective_until", "effective_at", "known_at"):
        value = fields.get(instant_key)
        if value is not None and isinstance(value, str):
            fields[instant_key] = _parse_known_at(value)
    return fields


def plan_forecast_outcome_cascade_repairs(
    *,
    outcome_rows: Sequence[Mapping[str, Any]],
    calibration_rows: Sequence[Mapping[str, Any]],
    calibrated_forecast_rows: Sequence[Mapping[str, Any]],
) -> ForecastOutcomeCascadePlan:
    """Plan the full three-table citation cascade for stale outcome digests.

    ``plan_forecast_outcome_hash_repairs`` refuses a stale row cited by a
    calibration, because rewriting its PK would leave
    ``forecast_calibrations.outcome_ids`` stale while the calibration's own
    immutable ``content_hash``/``calibration_id`` (and, transitively,
    ``calibrated_forecasts.calibration_id``) still cover the old id. This planner
    performs the whole bounded cascade instead, in dependency order:

    1. ``forecast_outcomes``: recompute ``content_hash`` -> ``outcome_id``.
    2. ``forecast_calibrations``: substitute the rewritten ids in ``outcome_ids``,
       then recompute ``content_hash`` -> ``calibration_id``. Calibrations that
       cite no rewritten outcome are omitted (nothing changed).
    3. ``calibrated_forecasts``: substitute the rewritten ``calibration_id``, then
       recompute ``content_hash`` -> ``calibrated_forecast_id``.

    Pure and read-only. Every rebuilt model is re-validated before being planned,
    so a row that is genuinely corrupt (not merely stale) is reported under
    ``unrepairable`` and neither it nor anything downstream of it is planned —
    the caller must abort the whole transaction rather than write a partial
    cascade. Already-canonical rows are omitted, so a second pass is a no-op.
    """
    outcomes: list[ForecastOutcomeHashRepair] = []
    calibrations: list[ForecastCalibrationHashRepair] = []
    calibrated_forecasts: list[CalibratedForecastHashRepair] = []
    unrepairable: list[str] = []

    outcome_id_map: dict[str, str] = {}
    for row in outcome_rows:
        recorded_id = str(row.get("outcome_id") or "")
        try:
            fields = _outcome_source_fields(row)
            recorded_hash = str(fields.get("content_hash") or "")
            constructed = ForecastOutcome.model_construct(**fields)
            repaired_hash = forecast_outcome_content_hash(payload=constructed._hash_payload())
            repaired_id = forecast_outcome_id(
                effective_forecast_id=constructed.effective_forecast_id,
                maturity_session=constructed.maturity_session,
                content_hash=repaired_hash,
            )
            ForecastOutcome.model_validate(
                {**fields, "outcome_id": repaired_id, "content_hash": repaired_hash}
            )
        except Exception as exc:
            unrepairable.append(
                f"{recorded_id or '<missing outcome_id>'}: {type(exc).__name__}: {exc}"
            )
            continue
        if recorded_id == str(repaired_id) and recorded_hash == repaired_hash:
            continue
        outcomes.append(
            ForecastOutcomeHashRepair(
                outcome_id=recorded_id,
                repaired_outcome_id=str(repaired_id),
                recorded_content_hash=recorded_hash,
                repaired_content_hash=repaired_hash,
            )
        )
        if recorded_id:
            outcome_id_map[recorded_id] = str(repaired_id)

    calibration_id_map: dict[str, str] = {}
    for row in calibration_rows:
        recorded_id = str(row.get("calibration_id") or "")
        try:
            fields = _calibration_source_fields(row)
            recorded_hash = str(fields.get("content_hash") or "")
            outcome_ids = tuple(fields.get("outcome_ids") or ())
            new_outcome_ids = tuple(
                UUID(outcome_id_map.get(str(item), str(item))) for item in outcome_ids
            )
            if new_outcome_ids == outcome_ids:
                continue
            constructed = ForecastCalibration.model_construct(
                **{**fields, "outcome_ids": new_outcome_ids}
            )
            repaired_hash = forecast_calibration_content_hash(payload=constructed._hash_payload())
            repaired_id = forecast_calibration_id(
                cohort_key=constructed.cohort_key,
                method_version=constructed.method_version,
                content_hash=repaired_hash,
            )
            ForecastCalibration.model_validate(
                {
                    **fields,
                    "outcome_ids": new_outcome_ids,
                    "content_hash": repaired_hash,
                    "calibration_id": repaired_id,
                }
            )
        except Exception as exc:
            unrepairable.append(
                f"{recorded_id or '<missing calibration_id>'}: {type(exc).__name__}: {exc}"
            )
            continue
        calibrations.append(
            ForecastCalibrationHashRepair(
                calibration_id=recorded_id,
                repaired_calibration_id=str(repaired_id),
                recorded_content_hash=recorded_hash,
                repaired_content_hash=repaired_hash,
            )
        )
        if recorded_id:
            calibration_id_map[recorded_id] = str(repaired_id)

    for row in calibrated_forecast_rows:
        recorded_id = str(row.get("calibrated_forecast_id") or "")
        try:
            fields = _calibrated_forecast_source_fields(row)
            recorded_hash = str(fields.get("content_hash") or "")
            calibration_id = fields.get("calibration_id")
            if calibration_id is None:
                continue
            repaired_calibration_id = calibration_id_map.get(str(calibration_id))
            if repaired_calibration_id is None:
                continue
            new_calibration_uuid = UUID(repaired_calibration_id)
            constructed = CalibratedForecast.model_construct(
                **{**fields, "calibration_id": new_calibration_uuid}
            )
            repaired_hash = calibrated_forecast_content_hash(payload=constructed._hash_payload())
            repaired_id = calibrated_forecast_id(
                effective_forecast_id=constructed.effective_forecast_id,
                calibration_id=constructed.calibration_id,
                content_hash=repaired_hash,
            )
            CalibratedForecast.model_validate(
                {
                    **fields,
                    "calibration_id": new_calibration_uuid,
                    "content_hash": repaired_hash,
                    "calibrated_forecast_id": repaired_id,
                }
            )
        except Exception as exc:
            unrepairable.append(
                f"{recorded_id or '<missing calibrated_forecast_id>'}: {type(exc).__name__}: {exc}"
            )
            continue
        calibrated_forecasts.append(
            CalibratedForecastHashRepair(
                calibrated_forecast_id=recorded_id,
                repaired_calibrated_forecast_id=str(repaired_id),
                recorded_content_hash=recorded_hash,
                repaired_content_hash=repaired_hash,
            )
        )

    return ForecastOutcomeCascadePlan(
        outcomes=tuple(outcomes),
        calibrations=tuple(calibrations),
        calibrated_forecasts=tuple(calibrated_forecasts),
        unrepairable=tuple(unrepairable),
    )


__all__ = [
    "DEFAULT_VENUE",
    "OUTCOMES",
    "CalibratedForecastHashRepair",
    "ForecastCalibrationHashRepair",
    "ForecastOutcomeCascadePlan",
    "ForecastOutcomeHashRepair",
    "ForecastOutcomeHashRepairPlan",
    "ForecastOutcomeIntegrityError",
    "OutcomeResolveResult",
    "ResolvedOutcomesMemo",
    "list_resolved_outcomes_as_of",
    "list_resolved_outcomes_as_of_memoized",
    "plan_forecast_outcome_cascade_repairs",
    "plan_forecast_outcome_hash_repairs",
    "resolve_matured_forecast_outcomes",
]
