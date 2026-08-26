"""Deterministic PreTradeRiskReport builders (#2746 / WP9.2).

Pure functions only — consume exact WP6 covariance, WP7 cost/liquidity scalars,
and a final book. Never re-estimate covariance/cost, never mutate weights, never
fabricate unsupported factor/scenario values. H8 attachment is WP9.3; H9
persistence is WP9.4.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from digiquant.olympus.hermes.allocation_contracts import (
    AlteredTarget,
    BindingConstraint,
    BookWeightsView,
    ConcentrationBlock,
    ControlOutcomesBlock,
    CostLiquidityReportBlock,
    ExposureBlock,
    ForecastQualityBlock,
    MetricProvenance,
    NameSectorFactorScenarioBlock,
    PerAssetRiskContribution,
    PortfolioRiskBlock,
    PreTradeRiskReport,
    RejectedTarget,
    ReportMetricStatus,
    ReportWeightEntry,
    ScalarMetric,
    TradeDeltaEntry,
)
from digiquant.olympus.hermes.allocation_hashes import (
    pretrade_risk_report_content_hash,
    weights_fingerprint,
)
from digiquant.olympus.hermes.models.risk_policy import (
    CovarianceSnapshot,
    PolicyArtifactStatus,
)

_CRC_RECONCILE_ABS_TOL = 1e-9
_CRC_RECONCILE_REL_TOL = 1e-9


@dataclass(frozen=True)
class CostLiquidityScalars:
    """Already-estimated observational cost/liquidity — builder does not re-price."""

    expected_cost: float | None = None
    adv_participation_pct: float | None = None
    days_to_liquidate: float | None = None
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class ForecastQualityScalars:
    """Forecast freshness/uncertainty already bound into the allocation bundle."""

    staleness_sessions: float | None = None
    forecast_uncertainty: float | None = None
    degraded_input_count: float | None = None


@dataclass(frozen=True)
class PreTradeRiskBuildRequest:
    """Inputs for one observational pre-trade risk report.

    Weights are percent of NAV (0–100). Correlation comes from the exact WP6
    :class:`CovarianceSnapshot`; annualized vols are supplied by the caller and
    are never estimated here.
    """

    run_id: str
    session_date: date
    allocation_input_bundle_hash: str
    risk_policy_hash: str
    prior_risky_weights_pct: Mapping[str, float]
    prior_cash_weight_pct: float
    final_risky_weights_pct: Mapping[str, float]
    final_cash_weight_pct: float
    covariance_snapshot: CovarianceSnapshot | None = None
    annualized_vol_pct: Mapping[str, float] | None = None
    sector_by_ticker: Mapping[str, str] | None = None
    factor_exposure: float | None = None
    scenario_stress_pct: float | None = None
    cost_liquidity: CostLiquidityScalars | None = None
    forecast_quality: ForecastQualityScalars | None = None
    binding_constraints: Sequence[BindingConstraint] = ()
    altered_targets: Sequence[AlteredTarget] = ()
    rejected_targets: Sequence[RejectedTarget] = ()
    force_unavailable_reason: str | None = None


def _available(value: float, provenance: MetricProvenance) -> ScalarMetric:
    return ScalarMetric(
        status=ReportMetricStatus.AVAILABLE,
        value=value,
        provenance=provenance,
    )


def _degraded(value: float, reason: str, provenance: MetricProvenance) -> ScalarMetric:
    return ScalarMetric(
        status=ReportMetricStatus.DEGRADED,
        value=value,
        provenance=provenance,
        unavailable_reason=reason,
    )


def _unavailable(reason: str) -> ScalarMetric:
    return ScalarMetric(
        status=ReportMetricStatus.UNAVAILABLE,
        unavailable_reason=reason,
    )


def _book_view(risky_pct: Mapping[str, float], cash_pct: float) -> BookWeightsView:
    entries = tuple(
        ReportWeightEntry(ticker=ticker, weight_pct=float(risky_pct[ticker]))
        for ticker in sorted(risky_pct)
    )
    return BookWeightsView(
        entries=entries,
        cash_weight_pct=float(cash_pct),
        weights_fingerprint=weights_fingerprint(
            {entry.ticker: entry.weight_pct for entry in entries}
        ),
    )


def _trade_deltas(
    prior: Mapping[str, float],
    final: Mapping[str, float],
) -> tuple[TradeDeltaEntry, ...]:
    tickers = sorted(set(prior) | set(final))
    return tuple(
        TradeDeltaEntry(
            ticker=ticker,
            delta_weight_pct=float(final.get(ticker, 0.0) - prior.get(ticker, 0.0)),
        )
        for ticker in tickers
    )


def _turnover_pct(
    prior_risky: Mapping[str, float],
    prior_cash: float,
    final_risky: Mapping[str, float],
    final_cash: float,
) -> float:
    """One-way turnover (%) = ½ Σ|Δw| over risky names and cash."""
    abs_sum = abs(float(final_cash) - float(prior_cash))
    for ticker in set(prior_risky) | set(final_risky):
        abs_sum += abs(float(final_risky.get(ticker, 0.0) - prior_risky.get(ticker, 0.0)))
    return 0.5 * abs_sum


def _fractional_weights(risky_pct: Mapping[str, float]) -> dict[str, float]:
    return {ticker: float(weight) / 100.0 for ticker, weight in sorted(risky_pct.items())}


def _build_covariance_matrix(
    tickers: Sequence[str],
    correlation: Mapping[tuple[str, str], float],
    vols_fraction: Mapping[str, float],
) -> list[list[float]]:
    n = len(tickers)
    sigma = [[0.0] * n for _ in range(n)]
    for i, ti in enumerate(tickers):
        for j, tj in enumerate(tickers):
            if i == j:
                rho = 1.0
            else:
                rho = correlation[(ti, tj)] if (ti, tj) in correlation else correlation[(tj, ti)]
            sigma[i][j] = vols_fraction[ti] * vols_fraction[tj] * rho
    return sigma


def _portfolio_variance_and_contributions(
    *,
    weights_frac: Mapping[str, float],
    correlation: Mapping[tuple[str, str], float],
    vols_fraction: Mapping[str, float],
) -> tuple[float, float, dict[str, tuple[float, float]]]:
    """Return variance (fraction²), σ_p (fraction), and ticker → (MRC, CRC)."""
    tickers = [t for t, w in weights_frac.items() if w != 0.0]
    if not tickers:
        return 0.0, 0.0, {}

    sigma = _build_covariance_matrix(tickers, correlation, vols_fraction)
    w = [weights_frac[t] for t in tickers]
    n = len(tickers)
    sigma_w = [sum(sigma[i][j] * w[j] for j in range(n)) for i in range(n)]
    variance = sum(w[i] * sigma_w[i] for i in range(n))
    if variance < 0.0 and abs(variance) <= _CRC_RECONCILE_ABS_TOL:
        variance = 0.0
    if variance < 0.0:
        raise ValueError("portfolio variance must be non-negative")
    vol = math.sqrt(variance)
    contributions: dict[str, tuple[float, float]] = {}
    if vol == 0.0:
        for ticker in tickers:
            contributions[ticker] = (0.0, 0.0)
        return variance, vol, contributions

    crc_sum = 0.0
    for i, ticker in enumerate(tickers):
        mrc = sigma_w[i] / vol
        crc = w[i] * mrc
        contributions[ticker] = (mrc, crc)
        crc_sum += crc

    if not math.isclose(
        crc_sum, vol, rel_tol=_CRC_RECONCILE_REL_TOL, abs_tol=_CRC_RECONCILE_ABS_TOL
    ):
        raise ValueError(
            f"component risks must reconcile to portfolio volatility "
            f"(crc_sum={crc_sum}, sigma_p={vol})"
        )
    return variance, vol, contributions


def _correlation_lookup(
    snapshot: CovarianceSnapshot,
) -> Mapping[tuple[str, str], float]:
    lookup: dict[tuple[str, str], float] = {}
    tickers = list(snapshot.tickers)
    for i, ti in enumerate(tickers):
        for j, tj in enumerate(tickers):
            lookup[(ti, tj)] = float(snapshot.matrix[i][j])
    return lookup


def _build_portfolio_risk(
    *,
    final_risky_pct: Mapping[str, float],
    snapshot: CovarianceSnapshot | None,
    annualized_vol_pct: Mapping[str, float] | None,
) -> tuple[PortfolioRiskBlock, list[str]]:
    """Build portfolio risk block; return block + degradation reasons."""
    reasons: list[str] = []
    weights_frac = _fractional_weights(final_risky_pct)

    if not weights_frac:
        return (
            PortfolioRiskBlock(
                variance=_available(0.0, MetricProvenance.FINAL_BOOK),
                volatility_annualized_pct=_available(0.0, MetricProvenance.FINAL_BOOK),
                contributions=(),
            ),
            reasons,
        )

    if snapshot is None:
        reasons.append("covariance snapshot missing")
        unavailable = _unavailable("covariance snapshot missing")
        return (
            PortfolioRiskBlock(
                variance=unavailable,
                volatility_annualized_pct=_unavailable("covariance snapshot missing"),
                contributions=tuple(
                    PerAssetRiskContribution(
                        ticker=ticker,
                        marginal_risk=_unavailable("covariance snapshot missing"),
                        component_risk=_unavailable("covariance snapshot missing"),
                    )
                    for ticker in sorted(weights_frac)
                ),
            ),
            reasons,
        )

    if snapshot.status is PolicyArtifactStatus.UNAVAILABLE:
        reason = snapshot.unavailable_reason or "covariance snapshot unavailable"
        reasons.append(reason)
        unavailable = _unavailable(reason)
        return (
            PortfolioRiskBlock(
                variance=unavailable,
                volatility_annualized_pct=_unavailable(reason),
                contributions=tuple(
                    PerAssetRiskContribution(
                        ticker=ticker,
                        marginal_risk=_unavailable(reason),
                        component_risk=_unavailable(reason),
                    )
                    for ticker in sorted(weights_frac)
                ),
            ),
            reasons,
        )

    if annualized_vol_pct is None:
        reasons.append("annualized vols missing")
        unavailable = _unavailable("annualized vols missing")
        return (
            PortfolioRiskBlock(
                variance=unavailable,
                volatility_annualized_pct=_unavailable("annualized vols missing"),
                contributions=tuple(
                    PerAssetRiskContribution(
                        ticker=ticker,
                        marginal_risk=_unavailable("annualized vols missing"),
                        component_risk=_unavailable("annualized vols missing"),
                    )
                    for ticker in sorted(weights_frac)
                ),
            ),
            reasons,
        )

    cov_tickers = set(snapshot.tickers)
    missing_cov = sorted(t for t in weights_frac if t not in cov_tickers)
    missing_vol = sorted(
        t for t in weights_frac if t not in annualized_vol_pct or float(annualized_vol_pct[t]) < 0.0
    )
    if missing_cov or missing_vol:
        parts: list[str] = []
        if missing_cov:
            parts.append(f"tickers missing from covariance: {','.join(missing_cov)}")
        if missing_vol:
            parts.append(f"tickers missing annualized vol: {','.join(missing_vol)}")
        reason = "; ".join(parts)
        reasons.append(reason)
        unavailable = _unavailable(reason)
        return (
            PortfolioRiskBlock(
                variance=unavailable,
                volatility_annualized_pct=_unavailable(reason),
                contributions=tuple(
                    PerAssetRiskContribution(
                        ticker=ticker,
                        marginal_risk=_unavailable(reason),
                        component_risk=_unavailable(reason),
                    )
                    for ticker in sorted(weights_frac)
                ),
            ),
            reasons,
        )

    vols_fraction = {ticker: float(annualized_vol_pct[ticker]) / 100.0 for ticker in weights_frac}
    # Zero individual vol is allowed (zero-volatility book); negative rejected above.
    correlation = _correlation_lookup(snapshot)
    variance, vol, contrib_map = _portfolio_variance_and_contributions(
        weights_frac=weights_frac,
        correlation=correlation,
        vols_fraction=vols_fraction,
    )
    vol_pct = vol * 100.0

    degraded = snapshot.status is PolicyArtifactStatus.DEGRADED
    degrade_reason = snapshot.unavailable_reason or "covariance snapshot degraded"
    if degraded:
        reasons.append(degrade_reason)
        variance_metric = _degraded(variance, degrade_reason, MetricProvenance.COVARIANCE_SNAPSHOT)
        vol_metric = _degraded(vol_pct, degrade_reason, MetricProvenance.COVARIANCE_SNAPSHOT)
    else:
        variance_metric = _available(variance, MetricProvenance.COVARIANCE_SNAPSHOT)
        vol_metric = _available(vol_pct, MetricProvenance.COVARIANCE_SNAPSHOT)

    if vol == 0.0:
        # MRC is undefined when σ_p = 0 with non-zero residual covariance structure;
        # for a true zero-vol book contributions are zero with FINAL_BOOK provenance.
        contributions = tuple(
            PerAssetRiskContribution(
                ticker=ticker,
                marginal_risk=_available(0.0, MetricProvenance.COVARIANCE_SNAPSHOT)
                if not degraded
                else _degraded(0.0, degrade_reason, MetricProvenance.COVARIANCE_SNAPSHOT),
                component_risk=_available(0.0, MetricProvenance.COVARIANCE_SNAPSHOT)
                if not degraded
                else _degraded(0.0, degrade_reason, MetricProvenance.COVARIANCE_SNAPSHOT),
            )
            for ticker in sorted(weights_frac)
        )
    else:
        contributions = tuple(
            PerAssetRiskContribution(
                ticker=ticker,
                marginal_risk=(
                    _degraded(
                        contrib_map[ticker][0], degrade_reason, MetricProvenance.COVARIANCE_SNAPSHOT
                    )
                    if degraded
                    else _available(contrib_map[ticker][0], MetricProvenance.COVARIANCE_SNAPSHOT)
                ),
                component_risk=(
                    _degraded(
                        contrib_map[ticker][1], degrade_reason, MetricProvenance.COVARIANCE_SNAPSHOT
                    )
                    if degraded
                    else _available(contrib_map[ticker][1], MetricProvenance.COVARIANCE_SNAPSHOT)
                ),
            )
            for ticker in sorted(weights_frac)
        )

    return (
        PortfolioRiskBlock(
            variance=variance_metric,
            volatility_annualized_pct=vol_metric,
            contributions=contributions,
        ),
        reasons,
    )


def _build_concentration(
    final_risky_pct: Mapping[str, float],
) -> ConcentrationBlock:
    weights_frac = _fractional_weights(final_risky_pct)
    if not weights_frac:
        return ConcentrationBlock(
            herfindahl=_available(0.0, MetricProvenance.FINAL_BOOK),
            effective_bets=_unavailable("no risky weights"),
            max_name_weight_pct=_available(0.0, MetricProvenance.FINAL_BOOK),
        )

    gross = sum(weights_frac.values())
    if gross <= 0.0:
        return ConcentrationBlock(
            herfindahl=_available(0.0, MetricProvenance.FINAL_BOOK),
            effective_bets=_unavailable("no risky weights"),
            max_name_weight_pct=_available(0.0, MetricProvenance.FINAL_BOOK),
        )

    # Effective bets over renormalized risky weights (cash excluded).
    norm = {t: w / gross for t, w in weights_frac.items()}
    herfindahl = sum(w * w for w in norm.values())
    max_name = max(final_risky_pct.values()) if final_risky_pct else 0.0
    if herfindahl <= 0.0:
        bets = _unavailable("herfindahl is zero")
    else:
        bets = _available(1.0 / herfindahl, MetricProvenance.FINAL_BOOK)

    return ConcentrationBlock(
        herfindahl=_available(herfindahl, MetricProvenance.FINAL_BOOK),
        effective_bets=bets,
        max_name_weight_pct=_available(float(max_name), MetricProvenance.FINAL_BOOK),
    )


def _build_name_sector_factor_scenario(
    *,
    final_risky_pct: Mapping[str, float],
    sector_by_ticker: Mapping[str, str] | None,
    factor_exposure: float | None,
    scenario_stress_pct: float | None,
) -> NameSectorFactorScenarioBlock:
    max_name = max(final_risky_pct.values()) if final_risky_pct else 0.0
    name_metric = _available(float(max_name), MetricProvenance.FINAL_BOOK)

    if sector_by_ticker is None:
        sector_metric = _unavailable("sector map not bound")
    else:
        sector_totals: dict[str, float] = {}
        unknown = False
        for ticker, weight in final_risky_pct.items():
            sector = sector_by_ticker.get(ticker)
            if sector is None:
                unknown = True
                sector = "unknown"
            sector_totals[sector] = sector_totals.get(sector, 0.0) + float(weight)
        if not sector_totals:
            sector_metric = _available(0.0, MetricProvenance.FINAL_BOOK)
        elif unknown:
            sector_metric = _degraded(
                max(sector_totals.values()),
                "sector map incomplete for one or more tickers",
                MetricProvenance.FINAL_BOOK,
            )
        else:
            sector_metric = _available(max(sector_totals.values()), MetricProvenance.FINAL_BOOK)

    factor_metric = (
        _available(float(factor_exposure), MetricProvenance.RISK_POLICY)
        if factor_exposure is not None
        else _unavailable("factor model not configured")
    )
    scenario_metric = (
        _available(float(scenario_stress_pct), MetricProvenance.RISK_POLICY)
        if scenario_stress_pct is not None
        else _unavailable("scenario library not configured")
    )
    return NameSectorFactorScenarioBlock(
        name_max_weight_pct=name_metric,
        sector_max_weight_pct=sector_metric,
        factor_exposure=factor_metric,
        scenario_stress_pct=scenario_metric,
    )


def _build_cost_liquidity(
    *,
    turnover_pct: float,
    cost_liquidity: CostLiquidityScalars | None,
) -> tuple[CostLiquidityReportBlock, list[str]]:
    reasons: list[str] = []
    turnover = _available(turnover_pct, MetricProvenance.DERIVED)

    if cost_liquidity is None:
        reasons.append("cost/liquidity inputs missing")
        return (
            CostLiquidityReportBlock(
                expected_cost=_unavailable("cost/liquidity inputs missing"),
                turnover_pct=turnover,
                adv_participation_pct=_unavailable("cost/liquidity inputs missing"),
                days_to_liquidate=_unavailable("cost/liquidity inputs missing"),
            ),
            reasons,
        )

    if cost_liquidity.unavailable_reason and cost_liquidity.expected_cost is None:
        reasons.append(cost_liquidity.unavailable_reason)
        unavailable = _unavailable(cost_liquidity.unavailable_reason)
        return (
            CostLiquidityReportBlock(
                expected_cost=unavailable,
                turnover_pct=turnover,
                adv_participation_pct=_unavailable(cost_liquidity.unavailable_reason),
                days_to_liquidate=_unavailable(cost_liquidity.unavailable_reason),
            ),
            reasons,
        )

    if cost_liquidity.expected_cost is None:
        reasons.append("expected cost unavailable")
        expected = _unavailable("expected cost unavailable")
    else:
        expected = _available(float(cost_liquidity.expected_cost), MetricProvenance.COST_LIQUIDITY)

    if cost_liquidity.adv_participation_pct is None:
        reasons.append("ADV participation unavailable")
        adv = _unavailable(cost_liquidity.unavailable_reason or "ADV participation unavailable")
    else:
        adv = _available(
            float(cost_liquidity.adv_participation_pct), MetricProvenance.COST_LIQUIDITY
        )

    if cost_liquidity.days_to_liquidate is None:
        reasons.append("days to liquidate unavailable")
        days = _unavailable(cost_liquidity.unavailable_reason or "days to liquidate unavailable")
    else:
        days = _available(float(cost_liquidity.days_to_liquidate), MetricProvenance.COST_LIQUIDITY)

    return (
        CostLiquidityReportBlock(
            expected_cost=expected,
            turnover_pct=turnover,
            adv_participation_pct=adv,
            days_to_liquidate=days,
        ),
        reasons,
    )


def _build_forecast_quality(
    forecast_quality: ForecastQualityScalars | None,
) -> tuple[ForecastQualityBlock, list[str]]:
    reasons: list[str] = []
    if forecast_quality is None:
        reasons.append("forecast quality inputs missing")
        unavailable = _unavailable("forecast quality inputs missing")
        return (
            ForecastQualityBlock(
                staleness_sessions=unavailable,
                forecast_uncertainty=unavailable,
                degraded_input_count=unavailable,
            ),
            reasons,
        )

    def _one(value: float | None, label: str) -> ScalarMetric:
        if value is None:
            reasons.append(f"{label} unavailable")
            return _unavailable(f"{label} unavailable")
        return _available(float(value), MetricProvenance.ALLOCATION_BUNDLE)

    return (
        ForecastQualityBlock(
            staleness_sessions=_one(forecast_quality.staleness_sessions, "staleness_sessions"),
            forecast_uncertainty=_one(
                forecast_quality.forecast_uncertainty, "forecast_uncertainty"
            ),
            degraded_input_count=_one(
                forecast_quality.degraded_input_count, "degraded_input_count"
            ),
        ),
        reasons,
    )


def _report_status(
    *,
    force_unavailable_reason: str | None,
    degradation_reasons: Sequence[str],
) -> tuple[ReportMetricStatus, str | None]:
    if force_unavailable_reason:
        return ReportMetricStatus.UNAVAILABLE, force_unavailable_reason
    if degradation_reasons:
        # Stable, deterministic join for hash identity.
        return ReportMetricStatus.DEGRADED, "; ".join(sorted(set(degradation_reasons)))
    return ReportMetricStatus.AVAILABLE, None


def build_pretrade_risk_report(request: PreTradeRiskBuildRequest) -> PreTradeRiskReport:
    """Build a frozen :class:`PreTradeRiskReport` from exact observational inputs.

    Does not mutate ``request`` weight maps. Does not estimate covariance or cost.
    Unsupported factor/scenario metrics stay typed-unavailable unless supplied.
    """
    # Snapshot weight maps so callers cannot observe mutation through aliases.
    prior_risky = {str(k): float(v) for k, v in request.prior_risky_weights_pct.items()}
    final_risky = {str(k): float(v) for k, v in request.final_risky_weights_pct.items()}
    prior_cash = float(request.prior_cash_weight_pct)
    final_cash = float(request.final_cash_weight_pct)

    prior_weights = _book_view(prior_risky, prior_cash)
    final_weights = _book_view(final_risky, final_cash)
    trade_deltas = _trade_deltas(prior_risky, final_risky)
    turnover = _turnover_pct(prior_risky, prior_cash, final_risky, final_cash)

    gross = sum(final_risky.values())
    exposures = ExposureBlock(
        gross_exposure_pct=_available(gross, MetricProvenance.FINAL_BOOK),
        net_exposure_pct=_available(gross, MetricProvenance.FINAL_BOOK),
        cash_weight_pct=_available(final_cash, MetricProvenance.FINAL_BOOK),
    )

    degradation: list[str] = []
    portfolio_risk, risk_reasons = _build_portfolio_risk(
        final_risky_pct=final_risky,
        snapshot=request.covariance_snapshot,
        annualized_vol_pct=request.annualized_vol_pct,
    )
    degradation.extend(risk_reasons)

    concentration = _build_concentration(final_risky)
    name_sector = _build_name_sector_factor_scenario(
        final_risky_pct=final_risky,
        sector_by_ticker=request.sector_by_ticker,
        factor_exposure=request.factor_exposure,
        scenario_stress_pct=request.scenario_stress_pct,
    )
    # Unbound sector/factor/scenario stay typed-unavailable without degrading the
    # report. Incomplete maps (caller supplied a map missing names) do degrade.
    if name_sector.sector_max_weight_pct.status is ReportMetricStatus.DEGRADED:
        degradation.append(
            name_sector.sector_max_weight_pct.unavailable_reason or "sector map degraded"
        )

    cost_block, cost_reasons = _build_cost_liquidity(
        turnover_pct=turnover, cost_liquidity=request.cost_liquidity
    )
    degradation.extend(cost_reasons)

    forecast_block, forecast_reasons = _build_forecast_quality(request.forecast_quality)
    degradation.extend(forecast_reasons)

    controls = ControlOutcomesBlock(
        binding_constraints=tuple(
            sorted(
                request.binding_constraints,
                key=lambda item: (item.constraint_id, item.ticker or ""),
            )
        ),
        altered_targets=tuple(sorted(request.altered_targets, key=lambda item: item.ticker)),
        rejected_targets=tuple(sorted(request.rejected_targets, key=lambda item: item.ticker)),
    )

    status, unavailable_reason = _report_status(
        force_unavailable_reason=request.force_unavailable_reason,
        degradation_reasons=degradation,
    )

    covariance_hash = (
        None if request.covariance_snapshot is None else request.covariance_snapshot.content_hash
    )

    draft = PreTradeRiskReport.model_construct(
        schema_version="1.0",
        run_id=request.run_id,
        session_date=request.session_date,
        status=status,
        unavailable_reason=unavailable_reason,
        allocation_input_bundle_hash=request.allocation_input_bundle_hash,
        final_book_weights_fingerprint=final_weights.weights_fingerprint,
        prior_weights=prior_weights,
        final_weights=final_weights,
        trade_deltas=trade_deltas,
        exposures=exposures,
        portfolio_risk=portfolio_risk,
        concentration=concentration,
        name_sector_factor_scenario=name_sector,
        cost_liquidity=cost_block,
        forecast_quality=forecast_block,
        controls=controls,
        risk_policy_hash=request.risk_policy_hash,
        covariance_hash=covariance_hash,
        report_content_hash="",
    )
    report_hash = pretrade_risk_report_content_hash(payload=draft._hash_payload())
    return PreTradeRiskReport.model_validate(
        {
            **draft.model_dump(mode="python"),
            "report_content_hash": report_hash,
        }
    )


__all__ = [
    "CostLiquidityScalars",
    "ForecastQualityScalars",
    "PreTradeRiskBuildRequest",
    "build_pretrade_risk_report",
]
