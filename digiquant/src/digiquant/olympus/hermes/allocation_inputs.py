"""Assemble the canonical H8 ``AllocationInputBundle`` (#2730 / WP8.3).

Validate and join H7 mandate plus exact Phase 1 forecast / policy / covariance /
cost artifacts and prior weights at H8 entry. WP8.4 feeds the validated bundle into
incumbent ``size_portfolio`` raw weights when ``h8_sizing_input_mode=calibrated``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

from digiquant.olympus.hermes.allocation_contracts import (
    AllocationCadence,
    AllocationInputBundle,
    AllocationRunContext,
    AssetInputStatus,
    CalibratedReturnSlice,
    ControlSettingsFingerprint,
    CostLiquidityBinding,
    CovarianceBinding,
    MandateReference,
    PriorBookSnapshot,
    PriorWeightEntry,
    build_source_hashes,
)
from digiquant.olympus.hermes.allocation_hashes import (
    allocation_bundle_content_hash,
    h7_memo_hash_payload,
    sha256_hex,
)
from digiquant.olympus.hermes.models.forecast_calibration import (
    CalibratedForecast,
    CalibrationArtifactStatus,
)
from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection
from digiquant.olympus.hermes.models.risk_policy import CovarianceSnapshot, RiskPolicy
from digiquant.olympus.temporal import require_utc_datetime

_CASH = "CASH"
# Common Hermes forecast horizon (trading sessions). Used as shadow fill when H6
# did not attach an effective forecast for every H7 roster ticker.
DEFAULT_FORECAST_HORIZON_SESSIONS = 21


class AllocationInputAssemblyError(ValueError):
    """Raised when H8 cannot form one coherent allocation input identity."""


def _is_cash(ticker: str) -> bool:
    return ticker.strip().upper() == _CASH


def _canonical_asset_order(memo: PMDirectionMemo) -> tuple[str, ...]:
    tickers = [entry.ticker for entry in memo.roster if not _is_cash(entry.ticker)]
    if len(tickers) != len(set(tickers)):
        raise AllocationInputAssemblyError("H7 roster tickers must be unique")
    return tuple(sorted(tickers))


def _mandate_for(entry: TickerDirection) -> MandateReference:
    ref = entry.forecast_reference
    return MandateReference(
        ticker=entry.ticker,
        direction=entry.direction,
        conviction_rank=entry.conviction_rank,
        effective_forecast_id=None if ref is None else ref.effective_forecast_id,
        forecast_reference_hash=None,
        degradation_reason=None if ref is None else ref.degradation_reason,
    )


def _h7_memo_hash(memo: PMDirectionMemo, *, session_date: date) -> str:
    roster_rows: list[dict[str, object]] = []
    for entry in memo.roster:
        if _is_cash(entry.ticker):
            continue
        ref = entry.forecast_reference
        roster_rows.append(
            {
                "ticker": entry.ticker,
                "direction": entry.direction,
                "conviction_rank": entry.conviction_rank,
                "effective_forecast_id": (
                    None
                    if ref is None or ref.effective_forecast_id is None
                    else str(ref.effective_forecast_id)
                ),
                "forecast_reference_hash": None,
                "degradation_reason": None if ref is None else ref.degradation_reason,
            }
        )
    return sha256_hex(
        h7_memo_hash_payload(session_date=session_date.isoformat(), roster=roster_rows)
    )


def _resolve_horizon(
    *,
    order: tuple[str, ...],
    horizon_by_ticker: Mapping[str, int],
    expected_horizon_sessions: int | None,
) -> int:
    horizons: list[int] = []
    for ticker in order:
        if ticker not in horizon_by_ticker:
            raise AllocationInputAssemblyError(
                f"missing horizon_sessions for H7-authorized ticker {ticker}"
            )
        horizon = int(horizon_by_ticker[ticker])
        if horizon <= 0:
            raise AllocationInputAssemblyError(f"horizon_sessions must be positive for {ticker}")
        horizons.append(horizon)
    unique = set(horizons)
    if len(unique) != 1:
        raise AllocationInputAssemblyError(
            f"all calibrated_returns must share one horizon_sessions (got {sorted(unique)})"
        )
    horizon = next(iter(unique))
    if expected_horizon_sessions is not None and horizon != expected_horizon_sessions:
        raise AllocationInputAssemblyError(
            f"horizon_sessions {horizon} does not match expected {expected_horizon_sessions}"
        )
    return horizon


def _calibrated_slice(
    *,
    ticker: str,
    horizon_sessions: int,
    calibrated: CalibratedForecast | None,
    cutoff_at: datetime,
) -> CalibratedReturnSlice:
    if calibrated is None:
        return CalibratedReturnSlice(
            ticker=ticker,
            horizon_sessions=horizon_sessions,
            expected_gross_return=None,
            forecast_error_std=None,
            reliability_weight=Decimal("0"),
            calibrated_forecast_content_hash=None,
            status=AssetInputStatus.DEGRADED,
            unavailable_reason="calibrated_forecast_missing",
        )
    if calibrated.ticker != ticker:
        raise AllocationInputAssemblyError(
            f"calibrated forecast ticker {calibrated.ticker!r} does not match {ticker!r}"
        )
    if calibrated.known_at > cutoff_at:
        raise AllocationInputAssemblyError(
            f"calibrated forecast for {ticker} has known_at after cutoff "
            f"({calibrated.known_at.isoformat()} > {cutoff_at.isoformat()})"
        )
    if calibrated.status is CalibrationArtifactStatus.AVAILABLE:
        return CalibratedReturnSlice(
            ticker=ticker,
            horizon_sessions=horizon_sessions,
            expected_gross_return=calibrated.expected_gross_return,
            forecast_error_std=calibrated.forecast_error_std,
            reliability_weight=calibrated.reliability_weight,
            calibrated_forecast_content_hash=calibrated.content_hash,
            status=AssetInputStatus.AVAILABLE,
            unavailable_reason=None,
        )
    return CalibratedReturnSlice(
        ticker=ticker,
        horizon_sessions=horizon_sessions,
        expected_gross_return=None,
        forecast_error_std=None,
        reliability_weight=calibrated.reliability_weight,
        calibrated_forecast_content_hash=None,
        status=AssetInputStatus.DEGRADED,
        unavailable_reason=calibrated.unavailable_reason or "calibrated_forecast_unavailable",
    )


def _prior_book(
    *,
    prior_risky_weights: Mapping[str, float],
    cash_weight_pct: float,
) -> PriorBookSnapshot:
    entries = tuple(
        PriorWeightEntry(ticker=ticker, weight_pct=float(weight))
        for ticker, weight in sorted(prior_risky_weights.items())
        if not _is_cash(ticker) and float(weight) > 0
    )
    return PriorBookSnapshot(entries=entries, cash_weight_pct=float(cash_weight_pct))


def _covariance_binding(
    *,
    order: tuple[str, ...],
    covariance: CovarianceSnapshot | None,
) -> CovarianceBinding | None:
    if covariance is None:
        return None
    if tuple(covariance.tickers) != order:
        # Exact version identity requires identical canonical order; omit rather than
        # invent a reordered matrix (anti-goal: matrix estimation).
        return None
    return CovarianceBinding(
        snapshot_id=covariance.snapshot_id,
        content_hash=covariance.content_hash,
        tickers=order,
    )


def _cost_binding(
    cost_hashes_by_ticker: Mapping[str, str] | None,
    *,
    order: tuple[str, ...],
) -> CostLiquidityBinding | None:
    if not cost_hashes_by_ticker:
        return None
    order_by_upper = {ticker.upper(): ticker for ticker in order}
    pairs: list[tuple[str, str]] = []
    for ticker, digest in sorted(cost_hashes_by_ticker.items(), key=lambda item: item[0].upper()):
        canonical = order_by_upper.get(ticker.upper())
        if canonical is not None:
            pairs.append((canonical, digest))
    if not pairs:
        return None
    return CostLiquidityBinding(entries=tuple(sorted(pairs, key=lambda item: item[0])))


def assemble_allocation_input_bundle(
    *,
    memo: PMDirectionMemo,
    run_id: str,
    session_date: date,
    cutoff_at: datetime,
    calibrated_by_ticker: Mapping[str, CalibratedForecast],
    horizon_by_ticker: Mapping[str, int],
    risk_policy: RiskPolicy,
    covariance: CovarianceSnapshot | None,
    prior_risky_weights: Mapping[str, float],
    cash_weight_pct: float,
    cost_hashes_by_ticker: Mapping[str, str] | None = None,
    expected_horizon_sessions: int | None = None,
    profile_config_version_id: UUID | None = None,
    analyst_stances: Mapping[str, Any] | None = None,
) -> AllocationInputBundle:
    """Join H7 + Phase 1 artifacts into one validated ``AllocationInputBundle``.

    ``analyst_stances`` is accepted so callers can pass H5 context without effect —
    authorization and direction come only from ``memo``.
    """
    del analyst_stances  # H5 must not authorize; kept for explicit no-op API.
    cutoff = require_utc_datetime(cutoff_at, field_name="cutoff_at")
    order = _canonical_asset_order(memo)
    if not order:
        raise AllocationInputAssemblyError("H7 roster has no non-CASH tickers")

    horizon = _resolve_horizon(
        order=order,
        horizon_by_ticker=horizon_by_ticker,
        expected_horizon_sessions=expected_horizon_sessions,
    )

    by_ticker = {entry.ticker: entry for entry in memo.roster if not _is_cash(entry.ticker)}
    mandates = tuple(_mandate_for(by_ticker[ticker]) for ticker in order)
    calibrated_returns = tuple(
        _calibrated_slice(
            ticker=ticker,
            horizon_sessions=horizon,
            calibrated=calibrated_by_ticker.get(ticker),
            cutoff_at=cutoff,
        )
        for ticker in order
    )

    prior = _prior_book(
        prior_risky_weights=prior_risky_weights,
        cash_weight_pct=cash_weight_pct,
    )
    control = ControlSettingsFingerprint(
        risk_policy_content_hash=risk_policy.content_hash,
        risk_policy_id=risk_policy.policy_id,
    )
    cov_binding = _covariance_binding(order=order, covariance=covariance)
    cost_binding = _cost_binding(cost_hashes_by_ticker, order=order)

    calibrated_hashes = tuple(
        (item.ticker, item.calibrated_forecast_content_hash)
        for item in calibrated_returns
        if item.calibrated_forecast_content_hash is not None
    )
    source = build_source_hashes(
        h7_memo_hash=_h7_memo_hash(memo, session_date=session_date),
        risk_policy_hash=risk_policy.content_hash,
        prior_entries=tuple((e.ticker, e.weight_pct) for e in prior.entries),
        calibrated_hashes=calibrated_hashes,  # type: ignore[arg-type]
        covariance_hash=None if cov_binding is None else cov_binding.content_hash,
        cost_hashes=() if cost_binding is None else cost_binding.entries,
    )

    run = AllocationRunContext(
        run_id=run_id,
        session_date=session_date,
        cutoff_at=cutoff,
        cadence=AllocationCadence.DAILY,
        profile_config_version_id=profile_config_version_id,
    )
    draft = AllocationInputBundle.model_construct(
        schema_version="1.0",
        run=run,
        canonical_asset_order=order,
        mandates=mandates,
        calibrated_returns=calibrated_returns,
        prior_book=prior,
        control_settings=control,
        covariance=cov_binding,
        cost_liquidity=cost_binding,
        source_hashes=source,
        bundle_content_hash="",
    )
    bundle_hash = allocation_bundle_content_hash(payload=draft._hash_payload())
    return AllocationInputBundle.model_validate(
        {
            **draft.model_dump(mode="json"),
            "bundle_content_hash": bundle_hash,
        }
    )


def _horizons_from_state(state: Any) -> dict[str, int]:
    hermes = getattr(state, "phase_hermes", None)
    summaries = getattr(hermes, "deliberation_summaries", None) or {}
    out: dict[str, int] = {}
    for ticker, summary in summaries.items():
        if not isinstance(summary, dict):
            continue
        raw = summary.get("effective_forecast")
        if not isinstance(raw, dict):
            continue
        terms = raw.get("terms")
        if not isinstance(terms, dict):
            continue
        horizon = terms.get("horizon_sessions")
        if isinstance(horizon, int) and horizon > 0:
            out[str(ticker)] = horizon
    return out


def _calibrated_from_state(state: Any) -> dict[str, CalibratedForecast]:
    hermes = getattr(state, "phase_hermes", None)
    raw_map = getattr(hermes, "calibrated_forecasts", None) or {}
    out: dict[str, CalibratedForecast] = {}
    for ticker, payload in raw_map.items():
        if not isinstance(payload, dict):
            continue
        try:
            out[str(ticker)] = CalibratedForecast.model_validate(payload)
        except Exception:
            continue
    return out


def _prior_weights_from_state(state: Any) -> tuple[dict[str, float], float]:
    prefs = getattr(getattr(state, "config", None), "preferences", None) or {}
    current = dict(prefs.get("current_weights") or {})
    risky: dict[str, float] = {}
    cash = 0.0
    for key, value in current.items():
        try:
            weight = float(value)
        except (TypeError, ValueError):
            continue
        if _is_cash(str(key)):
            cash += weight
            continue
        if weight > 0:
            risky[str(key)] = weight
    if cash <= 0:
        invested = sum(risky.values())
        cash = max(0.0, 100.0 - invested)
    return risky, cash


def _cost_hashes_from_state(state: Any) -> dict[str, str]:
    hermes = getattr(state, "phase_hermes", None)
    estimates = getattr(hermes, "action_cost_estimates", None) or {}
    by_symbol: dict[str, str] = {}
    for payload in estimates.values():
        if not isinstance(payload, dict):
            continue
        symbol = payload.get("symbol")
        digest = payload.get("content_hash")
        if isinstance(symbol, str) and isinstance(digest, str) and digest:
            by_symbol[symbol.upper()] = digest
    return by_symbol


def assemble_allocation_input_bundle_from_state(
    state: Any,
    *,
    risk_policy: RiskPolicy | None = None,
    covariance: CovarianceSnapshot | None = None,
    expected_horizon_sessions: int | None = None,
) -> AllocationInputBundle | None:
    """Shadow assembler for H8 entry — returns ``None`` when inputs are incomplete.

    Never raises into the sizing path: incomplete memo / missing policy → ``None``.
    """
    hermes = getattr(state, "phase_hermes", None)
    memo_raw = getattr(hermes, "pm_direction_memo", None)
    if memo_raw is None:
        return None
    memo = (
        memo_raw
        if isinstance(memo_raw, PMDirectionMemo)
        else PMDirectionMemo.model_validate(memo_raw)
    )
    if risk_policy is None:
        raw_policy = getattr(hermes, "risk_policy", None)
        if not isinstance(raw_policy, dict):
            return None
        try:
            risk_policy = RiskPolicy.model_validate(raw_policy)
        except Exception:
            return None
    if covariance is None:
        raw_cov = getattr(hermes, "covariance_snapshot", None)
        if isinstance(raw_cov, dict):
            try:
                covariance = CovarianceSnapshot.model_validate(raw_cov)
            except Exception:
                covariance = None

    cutoff = getattr(state, "knowledge_cutoff_at", None)
    if cutoff is None:
        return None
    prior, cash = _prior_weights_from_state(state)
    horizons = _horizons_from_state(state)
    order = _canonical_asset_order(memo)
    fill_horizon = expected_horizon_sessions
    if fill_horizon is None:
        observed = {horizons[ticker] for ticker in order if ticker in horizons}
        if len(observed) == 1:
            fill_horizon = next(iter(observed))
        else:
            fill_horizon = DEFAULT_FORECAST_HORIZON_SESSIONS
    for ticker in order:
        horizons.setdefault(ticker, fill_horizon)

    try:
        return assemble_allocation_input_bundle(
            memo=memo,
            run_id=str(getattr(state, "run_id")),
            session_date=state.run_date,
            cutoff_at=cutoff,
            calibrated_by_ticker=_calibrated_from_state(state),
            horizon_by_ticker=horizons,
            risk_policy=risk_policy,
            covariance=covariance,
            prior_risky_weights=prior,
            cash_weight_pct=cash,
            cost_hashes_by_ticker=_cost_hashes_from_state(state) or None,
            expected_horizon_sessions=fill_horizon,
        )
    except (AllocationInputAssemblyError, ValueError, TypeError):
        return None


__all__ = [
    "AllocationInputAssemblyError",
    "DEFAULT_FORECAST_HORIZON_SESSIONS",
    "assemble_allocation_input_bundle",
    "assemble_allocation_input_bundle_from_state",
]
