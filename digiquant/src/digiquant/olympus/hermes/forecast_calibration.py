"""Deterministic forecast calibrator (#2680 / WP5.3, #2684 / WP5.4).

Core calibrator is pure (no Supabase). WP5.4 adds cutoff-safe attach helpers
invoked at the existing H6→H7 boundary; H9 persists artifacts. WP8.4 feeds
AVAILABLE ``CalibratedForecast`` slices into H8 via ``AllocationInputBundle``.

Shrinks cohort residual bias toward a declared zero-mean prior, reports
Brier/log scores, and emits ``CalibratedForecast`` subjects with non-zero
uncertainty and sample-bounded reliability.

Polars aggregates the eligible cohort; repeated identical inputs yield
identical UUID5 / content-hash identities.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence
from uuid import UUID

import polars as pl

from digiquant.olympus.hermes.models.forecast import EffectiveForecast, ForecastTerms
from digiquant.olympus.hermes.models.forecast_calibration import (
    CalibratedForecast,
    CalibrationArtifactStatus,
    ForecastCalibration,
    ForecastOutcome,
    OutcomeStatus,
    calibrated_forecast_content_hash,
    calibrated_forecast_id,
    forecast_calibration_content_hash,
    forecast_calibration_id,
)
from digiquant.olympus.temporal import require_utc_datetime

# ---------------------------------------------------------------------------
# Declared prior / method — persisted verbatim on every artifact.
# Do not change literals without bumping METHOD_VERSION (IDs would diverge).
# ---------------------------------------------------------------------------

METHOD_VERSION = "shadow-calibrator@1"
"""Implementation version stamped on every ForecastCalibration."""

_COHORT_HORIZON_RE = re.compile(r"^horizon:(\d+)\|")


PRIOR_EQUIVALENT_SAMPLE_SIZE = Decimal("8")
"""n0 — prior strength for zero-mean residual shrinkage."""

DISPERSION_FLOOR = Decimal("0.01")
"""Minimum forecast-error std so sparse cohorts never claim zero uncertainty."""

DOWNSIDE_LEVELS: tuple[Decimal, ...] = (
    Decimal("0.05"),
    Decimal("0.10"),
    Decimal("0.25"),
)
"""Empirical / parametric downside probability levels (ascending)."""

DOWNSIDE_METHOD = "empirical_residual_quantile_with_normal_fallback"
"""Downside construction: cohort residual quantiles when n>=3, else N(μ,σ)."""

EMPIRICAL_QUANTILE_MIN_N = 3
"""Minimum resolved samples before empirical residual quantiles are used."""

POSITIVE_PROB_SIGMOID_SCALE = Decimal("0.10")
"""Scale mapping outcome forecast_mean → scoring probability for Brier/log."""

PROB_CLIP = Decimal("0.000001")
"""Floor/ceiling for log-score probabilities (exclusive of 0/1)."""

SHRINKAGE_FORMULA = "bias = (n/(n+n0)) * mean(signed_residual); prior_bias=0"
"""Human-readable shrinkage identity persisted inside prior_definition."""

PRIOR_DEFINITION = (
    "zero_mean_shrinkage@v1"
    f"|n0={PRIOR_EQUIVALENT_SAMPLE_SIZE}"
    f"|shrinkage={SHRINKAGE_FORMULA}"
    f"|dispersion=population_std_floor_{DISPERSION_FLOOR}"
    f"|downside={DOWNSIDE_METHOD}"
    f"|downside_levels={','.join(str(x) for x in DOWNSIDE_LEVELS)}"
    f"|empirical_threshold=n>={EMPIRICAL_QUANTILE_MIN_N}"
    f"|positive_score_sigmoid_scale={POSITIVE_PROB_SIGMOID_SCALE}"
)
"""Full declared prior + method metadata for ForecastCalibration.prior_definition."""

_QUANTUM = Decimal("0.00000001")
_Z_NORMAL: dict[str, Decimal] = {
    "0.05": Decimal("-1.64485363"),
    "0.10": Decimal("-1.28155157"),
    "0.25": Decimal("-0.67448975"),
}


@dataclass(frozen=True)
class CalibrationBundle:
    """Cohort metrics plus one calibrated subject for H8 bundle consumption."""

    calibration: ForecastCalibration
    calibrated_forecast: CalibratedForecast


@dataclass(frozen=True)
class ShadowCalibrationAttachment:
    """Cohort calibrations + per-subject shadows for one H6→H7 attach pass."""

    calibrations: tuple[ForecastCalibration, ...]
    calibrated_forecasts: tuple[CalibratedForecast, ...]

    def calibration_dumps(self) -> dict[str, dict[str, object]]:
        return {
            str(item.calibration_id): item.model_dump(mode="json") for item in self.calibrations
        }

    def calibrated_forecast_dumps(self) -> dict[str, dict[str, object]]:
        """Keyed by ticker (upper) for typed state; last write wins on collision."""
        return {
            item.ticker.strip().upper(): item.model_dump(mode="json")
            for item in self.calibrated_forecasts
        }


def cohort_key_for_horizon(horizon_sessions: int, *, regime: str = "default") -> str:
    """Stable cohort key used by calibration identity (horizon + regime)."""
    if horizon_sessions <= 0:
        raise ValueError("horizon_sessions must be positive")
    regime_key = regime.strip() or "default"
    return f"horizon:{horizon_sessions}|regime:{regime_key}"


def horizon_sessions_from_cohort_key(cohort_key: str) -> int | None:
    """Parse ``horizon:N|…`` from a cohort key; ``None`` when the prefix is absent."""
    match = _COHORT_HORIZON_RE.match(cohort_key.strip())
    if match is None:
        return None
    return int(match.group(1))


def scenario_positive_probability(terms: ForecastTerms) -> Decimal:
    """Probability mass on strictly positive scenario returns (no half-credit at 0)."""
    mass = Decimal("0")
    for ret, prob in (
        (terms.bear_return, terms.bear_probability),
        (terms.base_return, terms.base_probability),
        (terms.bull_return, terms.bull_probability),
    ):
        if ret > Decimal("0"):
            mass += prob
    return _q(mass)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _clip_prob(value: Decimal) -> Decimal:
    if value < PROB_CLIP:
        return PROB_CLIP
    if value > Decimal("1") - PROB_CLIP:
        return Decimal("1") - PROB_CLIP
    return value


def _sigmoid_positive_prob(forecast_mean: Decimal) -> Decimal:
    """Deterministic map forecast_mean → (0,1) for proper scores on outcomes."""
    scale = float(POSITIVE_PROB_SIGMOID_SCALE)
    if scale <= 0:
        raise ValueError("POSITIVE_PROB_SIGMOID_SCALE must be positive")
    # 1 / (1 + exp(-mean/scale))
    x = float(forecast_mean) / scale
    # Stable logistic
    if x >= 0:
        z = math.exp(-x)
        p = 1.0 / (1.0 + z)
    else:
        z = math.exp(x)
        p = z / (1.0 + z)
    return _clip_prob(_q(Decimal(str(p))))


def _eligible_outcomes(
    outcomes: Sequence[ForecastOutcome],
    *,
    as_of: datetime,
    horizon_sessions: int | None = None,
) -> list[ForecastOutcome]:
    """Resolved outcomes known at or before ``as_of``, deterministic order.

    When ``horizon_sessions`` is set, only outcomes stamped with that horizon
    enter the cohort (Gate 2 / WP8 common-horizon requirement).
    """
    cutoff = require_utc_datetime(as_of, field_name="as_of")
    eligible = [
        o
        for o in outcomes
        if o.status is OutcomeStatus.RESOLVED
        and o.signed_residual is not None
        and o.forecast_mean_return is not None
        and o.positive_label is not None
        and o.known_at <= cutoff
        and (horizon_sessions is None or o.horizon_sessions == horizon_sessions)
    ]
    return sorted(eligible, key=lambda o: (o.known_at, str(o.outcome_id)))


def _unavailable_calibration(
    *,
    cohort_key: str,
    reason: str,
    effective_at: datetime,
    known_at: datetime,
) -> ForecastCalibration:
    draft = {
        "cohort_key": cohort_key.strip(),
        "prior_definition": PRIOR_DEFINITION,
        "method_version": METHOD_VERSION,
        "sample_count": 0,
        "equivalent_sample_size": PRIOR_EQUIVALENT_SAMPLE_SIZE,
        "bias": None,
        "dispersion": None,
        "brier_score": None,
        "log_score": None,
        "reliability": Decimal("0"),
        "status": CalibrationArtifactStatus.UNAVAILABLE,
        "unavailable_reason": reason,
        "outcome_ids": (),
        "effective_at": effective_at,
        "known_at": known_at,
    }
    payload = {
        "cohort_key": draft["cohort_key"],
        "prior_definition": draft["prior_definition"],
        "method_version": draft["method_version"],
        "sample_count": 0,
        "equivalent_sample_size": str(PRIOR_EQUIVALENT_SAMPLE_SIZE),
        "bias": None,
        "dispersion": None,
        "brier_score": None,
        "log_score": None,
        "reliability": "0",
        "status": CalibrationArtifactStatus.UNAVAILABLE.value,
        "unavailable_reason": reason,
        "outcome_ids": [],
        "effective_at": effective_at.isoformat(),
        "known_at": known_at.isoformat(),
    }
    content_hash = forecast_calibration_content_hash(payload=payload)
    calibration_id = forecast_calibration_id(
        cohort_key=str(draft["cohort_key"]),
        method_version=METHOD_VERSION,
        content_hash=content_hash,
    )
    return ForecastCalibration(
        calibration_id=calibration_id,
        content_hash=content_hash,
        **draft,  # type: ignore[arg-type]
    )


def _unavailable_subject(
    *,
    base_forecast_id: UUID,
    effective_forecast_id: UUID,
    ticker: str,
    reason: str,
    effective_at: datetime,
    known_at: datetime,
) -> CalibratedForecast:
    draft = {
        "base_forecast_id": base_forecast_id,
        "effective_forecast_id": effective_forecast_id,
        "calibration_id": None,
        "ticker": ticker.strip().upper(),
        "expected_gross_return": None,
        "forecast_error_std": None,
        "downside_quantiles": None,
        "calibrated_positive_probability": None,
        "reliability_weight": Decimal("0"),
        "effective_until": None,
        "status": CalibrationArtifactStatus.UNAVAILABLE,
        "unavailable_reason": reason,
        "effective_at": effective_at,
        "known_at": known_at,
    }
    payload = {
        "base_forecast_id": str(base_forecast_id),
        "effective_forecast_id": str(effective_forecast_id),
        "calibration_id": None,
        "ticker": draft["ticker"],
        "expected_gross_return": None,
        "forecast_error_std": None,
        "downside_quantiles": None,
        "calibrated_positive_probability": None,
        "reliability_weight": "0",
        "effective_until": None,
        "status": CalibrationArtifactStatus.UNAVAILABLE.value,
        "unavailable_reason": reason,
        "effective_at": effective_at.isoformat(),
        "known_at": known_at.isoformat(),
    }
    content_hash = calibrated_forecast_content_hash(payload=payload)
    calibrated_forecast_id_ = calibrated_forecast_id(
        effective_forecast_id=effective_forecast_id,
        calibration_id=None,
        content_hash=content_hash,
    )
    return CalibratedForecast(
        calibrated_forecast_id=calibrated_forecast_id_,
        content_hash=content_hash,
        **draft,  # type: ignore[arg-type]
    )


def _downside_quantiles(
    *,
    expected: Decimal,
    error_std: Decimal,
    residuals: list[Decimal],
) -> tuple[Decimal, ...]:
    """Downside return levels under the declared method.

    When ``n >= EMPIRICAL_QUANTILE_MIN_N``, use demeaned empirical residual
    quantiles around the debiased expected return; otherwise fall back to a
    normal ``N(expected, error_std)`` with fixed inverse-CDF z-scores.
    """
    n = len(residuals)
    if n >= EMPIRICAL_QUANTILE_MIN_N:
        series = pl.Series("residual", [float(r) for r in residuals])
        mean_res = Decimal(str(series.mean()))
        qs: list[Decimal] = []
        for level in DOWNSIDE_LEVELS:
            q_res = Decimal(str(series.quantile(float(level), interpolation="linear")))
            qs.append(_q(expected + (q_res - mean_res)))
        fixed: list[Decimal] = []
        for value in qs:
            if fixed and value < fixed[-1]:
                fixed.append(fixed[-1])
            else:
                fixed.append(value)
        return tuple(fixed)

    return tuple(_q(expected + _Z_NORMAL[str(level)] * error_std) for level in DOWNSIDE_LEVELS)


def calibrate_cohort(
    outcomes: Sequence[ForecastOutcome],
    *,
    cohort_key: str,
    as_of: datetime,
    effective_at: datetime | None = None,
) -> ForecastCalibration:
    """Estimate bias/dispersion/proper scores against the declared zero-mean prior.

    Late-known outcomes (``known_at > as_of``) and non-resolved rows are excluded.
    Empty eligible cohorts return typed ``unavailable`` (never invented metrics).
    """
    try:
        known_at = require_utc_datetime(as_of, field_name="as_of")
        eff_at = (
            require_utc_datetime(effective_at, field_name="effective_at")
            if effective_at is not None
            else known_at
        )
        key = cohort_key.strip()
        if not key:
            return _unavailable_calibration(
                cohort_key="invalid",
                reason="invalid_cohort_key",
                effective_at=eff_at,
                known_at=known_at,
            )

        eligible = _eligible_outcomes(
            outcomes,
            as_of=known_at,
            horizon_sessions=horizon_sessions_from_cohort_key(key),
        )
        if not eligible:
            return _unavailable_calibration(
                cohort_key=key,
                reason="empty_cohort",
                effective_at=eff_at,
                known_at=known_at,
            )

        frame = pl.DataFrame(
            {
                "outcome_id": [str(o.outcome_id) for o in eligible],
                "residual": [float(o.signed_residual) for o in eligible],  # type: ignore[arg-type]
                "forecast_mean": [float(o.forecast_mean_return) for o in eligible],  # type: ignore[arg-type]
                "positive": [1.0 if o.positive_label else 0.0 for o in eligible],
            }
        )
        n = frame.height
        n0 = float(PRIOR_EQUIVALENT_SAMPLE_SIZE)
        reliability = _q(Decimal(str(n / (n + n0))))
        bias_emp = Decimal(str(frame.select(pl.col("residual").mean()).item()))
        bias = _q(reliability * bias_emp)  # shrink toward prior 0
        # Population std; single-sample → 0 before floor.
        if n == 1:
            raw_disp = Decimal("0")
        else:
            raw_disp = Decimal(str(frame.select(pl.col("residual").std(ddof=0)).item()))
        dispersion = _q(max(raw_disp, DISPERSION_FLOOR))

        probs = [_sigmoid_positive_prob(Decimal(str(m))) for m in frame["forecast_mean"].to_list()]
        labels = [Decimal(str(y)) for y in frame["positive"].to_list()]
        brier = _q(sum(((p - y) ** 2) for p, y in zip(probs, labels, strict=True)) / Decimal(n))
        log_terms: list[Decimal] = []
        for p, y in zip(probs, labels, strict=True):
            pc = _clip_prob(p)
            if y >= Decimal("1"):
                log_terms.append(Decimal(str(math.log(float(pc)))))
            else:
                log_terms.append(Decimal(str(math.log(float(Decimal("1") - pc)))))
        log_score = _q(sum(log_terms) / Decimal(n))

        outcome_ids = tuple(o.outcome_id for o in eligible)
        draft: dict[str, object] = {
            "cohort_key": key,
            "prior_definition": PRIOR_DEFINITION,
            "method_version": METHOD_VERSION,
            "sample_count": n,
            "equivalent_sample_size": PRIOR_EQUIVALENT_SAMPLE_SIZE,
            "bias": bias,
            "dispersion": dispersion,
            "brier_score": brier,
            "log_score": log_score,
            "reliability": reliability,
            "status": CalibrationArtifactStatus.AVAILABLE,
            "unavailable_reason": None,
            "outcome_ids": outcome_ids,
            "effective_at": eff_at,
            "known_at": known_at,
        }
        payload = {
            "cohort_key": key,
            "prior_definition": PRIOR_DEFINITION,
            "method_version": METHOD_VERSION,
            "sample_count": n,
            "equivalent_sample_size": str(PRIOR_EQUIVALENT_SAMPLE_SIZE),
            "bias": str(bias),
            "dispersion": str(dispersion),
            "brier_score": str(brier),
            "log_score": str(log_score),
            "reliability": str(reliability),
            "status": CalibrationArtifactStatus.AVAILABLE.value,
            "unavailable_reason": None,
            "outcome_ids": [str(i) for i in outcome_ids],
            "effective_at": eff_at.isoformat(),
            "known_at": known_at.isoformat(),
        }
        content_hash = forecast_calibration_content_hash(payload=payload)
        calibration_id = forecast_calibration_id(
            cohort_key=key,
            method_version=METHOD_VERSION,
            content_hash=content_hash,
        )
        return ForecastCalibration(
            calibration_id=calibration_id,
            content_hash=content_hash,
            **draft,  # type: ignore[arg-type]
        )
    except Exception as exc:
        reason = f"calibration_failed:{type(exc).__name__}"
        try:
            known_at = require_utc_datetime(as_of, field_name="as_of")
        except Exception:
            known_at = datetime(1970, 1, 1, tzinfo=UTC)
        return _unavailable_calibration(
            cohort_key=(cohort_key.strip() or "invalid"),
            reason=reason[:500],
            effective_at=known_at,
            known_at=known_at,
        )


def calibrate_subject(
    *,
    base_forecast_id: UUID,
    effective_forecast_id: UUID,
    ticker: str,
    terms: ForecastTerms,
    calibration: ForecastCalibration,
    as_of: datetime,
    effective_at: datetime | None = None,
    effective_until: datetime | None = None,
    cohort_residuals: Sequence[Decimal] | None = None,
) -> CalibratedForecast:
    """Build a shadow calibrated subject from cohort metrics + effective terms.

    Does not feed incumbent H8. Unavailable calibration → typed unavailable subject.
    """
    try:
        known_at = require_utc_datetime(as_of, field_name="as_of")
        eff_at = (
            require_utc_datetime(effective_at, field_name="effective_at")
            if effective_at is not None
            else known_at
        )
        if calibration.status is not CalibrationArtifactStatus.AVAILABLE:
            reason = calibration.unavailable_reason or "calibration_unavailable"
            return _unavailable_subject(
                base_forecast_id=base_forecast_id,
                effective_forecast_id=effective_forecast_id,
                ticker=ticker,
                reason=reason,
                effective_at=eff_at,
                known_at=known_at,
            )
        assert calibration.bias is not None
        assert calibration.dispersion is not None

        raw_mean = terms.scenario_mean_return()
        expected = _q(raw_mean - calibration.bias)
        error_std = _q(max(calibration.dispersion, DISPERSION_FLOOR))
        residuals = list(cohort_residuals) if cohort_residuals is not None else []
        downside = _downside_quantiles(
            expected=expected,
            error_std=error_std,
            residuals=residuals,
        )
        p_scenario = scenario_positive_probability(terms)
        # Shrink scenario positive mass toward empirical hit rate when present on cal.
        # Cohort hit rate is not stored separately — recover via reliability + Brier is
        # underdetermined; use scenario mass shrunk toward 0.5 (neutral prior) by
        # (1-reliability), and toward scenario by reliability. Sparse → nearer 0.5.
        p_cal = _clip_prob(
            _q(
                calibration.reliability * p_scenario
                + (Decimal("1") - calibration.reliability) * Decimal("0.5")
            )
        )
        until = effective_until
        if until is None:
            # Horizon-bounded observation window: half-life sessions as calendar days proxy
            # for shadow effective_until only (not maturity labeling).
            until = eff_at + timedelta(days=int(terms.horizon_sessions))
        else:
            until = require_utc_datetime(until, field_name="effective_until")

        draft: dict[str, object] = {
            "base_forecast_id": base_forecast_id,
            "effective_forecast_id": effective_forecast_id,
            "calibration_id": calibration.calibration_id,
            "ticker": ticker.strip().upper(),
            "expected_gross_return": expected,
            "forecast_error_std": error_std,
            "downside_quantiles": downside,
            "calibrated_positive_probability": p_cal,
            "reliability_weight": calibration.reliability,
            "effective_until": until,
            "status": CalibrationArtifactStatus.AVAILABLE,
            "unavailable_reason": None,
            "effective_at": eff_at,
            "known_at": known_at,
        }
        payload = {
            "base_forecast_id": str(base_forecast_id),
            "effective_forecast_id": str(effective_forecast_id),
            "calibration_id": str(calibration.calibration_id),
            "ticker": draft["ticker"],
            "expected_gross_return": str(expected),
            "forecast_error_std": str(error_std),
            "downside_quantiles": [str(x) for x in downside],
            "calibrated_positive_probability": str(p_cal),
            "reliability_weight": str(calibration.reliability),
            "effective_until": until.isoformat(),
            "status": CalibrationArtifactStatus.AVAILABLE.value,
            "unavailable_reason": None,
            "effective_at": eff_at.isoformat(),
            "known_at": known_at.isoformat(),
        }
        content_hash = calibrated_forecast_content_hash(payload=payload)
        cf_id = calibrated_forecast_id(
            effective_forecast_id=effective_forecast_id,
            calibration_id=calibration.calibration_id,
            content_hash=content_hash,
        )
        return CalibratedForecast(
            calibrated_forecast_id=cf_id,
            content_hash=content_hash,
            **draft,  # type: ignore[arg-type]
        )
    except Exception as exc:
        reason = f"subject_calibration_failed:{type(exc).__name__}"
        try:
            known_at = require_utc_datetime(as_of, field_name="as_of")
        except Exception:
            known_at = datetime(1970, 1, 1, tzinfo=UTC)
        return _unavailable_subject(
            base_forecast_id=base_forecast_id,
            effective_forecast_id=effective_forecast_id,
            ticker=ticker,
            reason=reason[:500],
            effective_at=known_at,
            known_at=known_at,
        )


def calibrate_forecast(
    *,
    outcomes: Sequence[ForecastOutcome],
    terms: ForecastTerms,
    base_forecast_id: UUID,
    effective_forecast_id: UUID,
    ticker: str,
    as_of: datetime,
    cohort_key: str | None = None,
    effective_at: datetime | None = None,
    effective_until: datetime | None = None,
) -> CalibrationBundle:
    """Calibrate a cohort and emit one shadow subject (no persistence)."""
    key = cohort_key or cohort_key_for_horizon(terms.horizon_sessions)
    calibration = calibrate_cohort(
        outcomes,
        cohort_key=key,
        as_of=as_of,
        effective_at=effective_at,
    )
    residuals: list[Decimal] = []
    if calibration.status is CalibrationArtifactStatus.AVAILABLE:
        eligible = _eligible_outcomes(
            outcomes,
            as_of=as_of,
            horizon_sessions=horizon_sessions_from_cohort_key(key),
        )
        residuals = [o.signed_residual for o in eligible if o.signed_residual is not None]
    subject = calibrate_subject(
        base_forecast_id=base_forecast_id,
        effective_forecast_id=effective_forecast_id,
        ticker=ticker,
        terms=terms,
        calibration=calibration,
        as_of=as_of,
        effective_at=effective_at,
        effective_until=effective_until,
        cohort_residuals=residuals,
    )
    return CalibrationBundle(calibration=calibration, calibrated_forecast=subject)


def collect_effective_forecasts_from_state(state: object) -> list[EffectiveForecast]:
    """Extract typed effective forecasts from H6 deliberation summaries.

    Missing or invalid dumps are skipped — never invented. Order is ticker-sorted
    for deterministic attach/persist.
    """
    hermes = getattr(state, "phase_hermes", None)
    summaries = getattr(hermes, "deliberation_summaries", None) or {}
    found: list[EffectiveForecast] = []
    for ticker in sorted(summaries.keys()):
        summary = summaries[ticker]
        if not isinstance(summary, dict):
            continue
        raw = summary.get("effective_forecast")
        if not isinstance(raw, dict):
            continue
        try:
            found.append(EffectiveForecast.model_validate(raw))
        except Exception:
            continue
    return found


def attach_shadow_calibrations(
    *,
    subjects: Sequence[EffectiveForecast],
    outcomes: Sequence[ForecastOutcome],
    as_of: datetime,
    regime: str = "default",
) -> ShadowCalibrationAttachment:
    """Build cohort calibrations + per-subject calibrated forecasts.

    One ``ForecastCalibration`` per distinct cohort key; one ``CalibratedForecast``
    per subject. Empty subjects → empty attachment. Outcomes must already be
    cutoff-bounded by the caller (``known_at > as_of`` are ignored again inside
    the calibrator). Does not write to Supabase here; WP8.4 H8 consumes the
    attached dumps via ``AllocationInputBundle``.
    """
    known_at = require_utc_datetime(as_of, field_name="as_of")
    if not subjects:
        return ShadowCalibrationAttachment(calibrations=(), calibrated_forecasts=())

    by_cohort: dict[str, list[EffectiveForecast]] = {}
    for subject in subjects:
        key = cohort_key_for_horizon(subject.terms.horizon_sessions, regime=regime)
        by_cohort.setdefault(key, []).append(subject)

    calibrations_by_id: dict[UUID, ForecastCalibration] = {}
    calibrated: list[CalibratedForecast] = []

    for cohort_key in sorted(by_cohort.keys()):
        cohort_subjects = sorted(
            by_cohort[cohort_key],
            key=lambda s: (s.ticker.upper(), str(s.effective_id)),
        )
        # Subjects sharing a cohort_key share one calibration estimate; outcomes are
        # filtered to the cohort horizon inside calibrate_cohort (#2797).
        calibration = calibrate_cohort(
            outcomes,
            cohort_key=cohort_key,
            as_of=known_at,
            effective_at=known_at,
        )
        calibrations_by_id[calibration.calibration_id] = calibration
        residuals: list[Decimal] = []
        if calibration.status is CalibrationArtifactStatus.AVAILABLE:
            eligible = _eligible_outcomes(
                outcomes,
                as_of=known_at,
                horizon_sessions=horizon_sessions_from_cohort_key(cohort_key),
            )
            residuals = [o.signed_residual for o in eligible if o.signed_residual is not None]
        for subject in cohort_subjects:
            calibrated.append(
                calibrate_subject(
                    base_forecast_id=subject.base_forecast_id,
                    effective_forecast_id=subject.effective_id,
                    ticker=subject.ticker,
                    terms=subject.terms,
                    calibration=calibration,
                    as_of=known_at,
                    effective_at=known_at,
                    cohort_residuals=residuals,
                )
            )

    return ShadowCalibrationAttachment(
        calibrations=tuple(
            calibrations_by_id[cid] for cid in sorted(calibrations_by_id.keys(), key=str)
        ),
        calibrated_forecasts=tuple(calibrated),
    )


def attach_shadow_calibrations_from_state(
    state: object,
    *,
    outcomes: Sequence[ForecastOutcome],
    as_of: datetime | None = None,
    regime: str = "default",
) -> ShadowCalibrationAttachment:
    """Attach shadows for H6 effectives on ``state`` using cutoff-bounded outcomes.

    Requires an explicit UTC ``as_of`` or ``state.knowledge_cutoff_at``. Never falls
    back to wall-clock time (identity would diverge — #2797).
    """
    cutoff = as_of
    if cutoff is None:
        cutoff = getattr(state, "knowledge_cutoff_at", None)
    if cutoff is None:
        return ShadowCalibrationAttachment(calibrations=(), calibrated_forecasts=())
    subjects = collect_effective_forecasts_from_state(state)
    return attach_shadow_calibrations(
        subjects=subjects,
        outcomes=outcomes,
        as_of=cutoff,
        regime=regime,
    )


__all__ = [
    "DISPERSION_FLOOR",
    "DOWNSIDE_LEVELS",
    "DOWNSIDE_METHOD",
    "EMPIRICAL_QUANTILE_MIN_N",
    "METHOD_VERSION",
    "PRIOR_DEFINITION",
    "PRIOR_EQUIVALENT_SAMPLE_SIZE",
    "SHRINKAGE_FORMULA",
    "CalibrationBundle",
    "ShadowCalibrationAttachment",
    "attach_shadow_calibrations",
    "attach_shadow_calibrations_from_state",
    "calibrate_cohort",
    "calibrate_forecast",
    "calibrate_subject",
    "cohort_key_for_horizon",
    "collect_effective_forecasts_from_state",
    "horizon_sessions_from_cohort_key",
    "scenario_positive_probability",
]
