"""Injected SDCA trial evaluator that uses the CI curve simulator, not Nautilus.

Production fitness is still Nautilus fills (``nautilus_evaluator``). Linux
BacktestEngine may SIGABRT (#42); Stage B then uses this simulator and
records ``evaluator=curve_simulator`` in provenance. ``SdcaBacktestReport``
is mapped into ``SdcaTrialMetrics`` only — it is never published as a
backtest result.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.composite_risk import IndicatorWeight
from digiquant.strategies.sdca.crash_override import apply_crash_override
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.indicator_catalog import fast_crash_vol_z
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.walk_forward import SdcaTrialMetrics

DEFAULT_TRIAL_CASH = 100_000.0


def evaluate_sdca_trial_curve_sim(
    dates: Sequence[date],
    prices: Sequence[float],
    risk_model: RiskModel,
    shape: SdcaCurveShape,
    power_law_weight: float,
    extra_indicators: Sequence[IndicatorWeight] | None = None,
    *,
    initial_cash: float = DEFAULT_TRIAL_CASH,
    composite_rolling_window: int | None = None,
    composite_rolling_min_samples: int | None = None,
    crash_override_enabled: bool = False,
    crash_override_window: int = 14,
    crash_override_min_samples: int = 7,
    crash_override_trigger_z: float = -2.0,
    crash_override_ramp_z: float = 1.0,
    crash_override_risk: float = 95.0,
) -> SdcaTrialMetrics:
    """Score one window via ``run_backtest`` (no NautilusTrader import).

    ``composite_rolling_window`` forwards to ``build_risk_index`` — not part
    of ``SdcaTrialEvaluator``'s Protocol signature, so bind it with
    ``functools.partial`` before passing this evaluator into Stage A /
    walk-forward search, the same way callers already bind ``initial_cash``.

    ``crash_override_*`` (default: disabled, a no-op) applies
    ``crash_override.apply_crash_override`` to the finalized composite risk,
    immediately before the curve-shape rate mapping consumes it. This is an
    independent circuit-breaker on top of ``fast_crash_vol_z`` — it is not a
    weighted-composite indicator and never lowers risk. Like
    ``composite_rolling_window`` it is outside the Protocol signature; bind
    with ``functools.partial`` to use it in search.
    """
    if len(dates) != len(prices) or not dates:
        raise ValueError("evaluate_sdca_trial_curve_sim needs aligned non-empty dates/prices")
    date_s = pl.Series("date", list(dates), dtype=pl.Date)
    price_s = pl.Series("price", list(prices), dtype=pl.Float64)
    index = build_risk_index(
        date_s,
        price_s,
        risk_model,
        extra_indicators=list(extra_indicators) if extra_indicators is not None else None,
        power_law_weight=power_law_weight,
        composite_rolling_window=composite_rolling_window,
        composite_rolling_min_samples=composite_rolling_min_samples,
    )
    risk_series = index["risk"]
    if crash_override_enabled:
        crash_z = fast_crash_vol_z(
            date_s,
            price_s,
            window=crash_override_window,
            min_samples=crash_override_min_samples,
        )
        risk_series = pl.Series(
            "risk",
            apply_crash_override(
                risk_series,
                crash_z,
                trigger_z=crash_override_trigger_z,
                ramp_z=crash_override_ramp_z,
                override_risk=crash_override_risk,
            ),
        )
    report, _frame = run_backtest(
        date_s,
        price_s,
        risk_series,
        AccumDistCurve(shape.to_nodes()),
        initial_cash,
    )
    return SdcaTrialMetrics(
        vs_flat_dca_pct=report.vs_flat_dca_pct,
        vs_lump_pct=report.vs_lump_pct,
        capital_deployed_pct=report.capital_deployed_pct,
        max_drawdown_pct=abs(report.dca_max_drawdown_pct) * 100.0,
    )


__all__ = ["DEFAULT_TRIAL_CASH", "evaluate_sdca_trial_curve_sim"]
