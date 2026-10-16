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
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.risk_index import build_risk_index
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.walk_forward import SdcaTrialMetrics

DEFAULT_TRIAL_CASH = 100_000.0


def evaluate_sdca_trial_curve_sim(
    dates: Sequence[date],
    prices: Sequence[float],
    risk_model: RiskModel,
    shape: SdcaCurveShape,
    valuation_weight: float,
    extra_indicators: Sequence[IndicatorWeight] | None = None,
    *,
    initial_cash: float = DEFAULT_TRIAL_CASH,
) -> SdcaTrialMetrics:
    """Score one window via ``run_backtest`` (no NautilusTrader import)."""
    if len(dates) != len(prices) or not dates:
        raise ValueError("evaluate_sdca_trial_curve_sim needs aligned non-empty dates/prices")
    date_s = pl.Series("date", list(dates), dtype=pl.Date)
    price_s = pl.Series("price", list(prices), dtype=pl.Float64)
    index = build_risk_index(
        date_s,
        price_s,
        risk_model,
        extra_indicators=list(extra_indicators) if extra_indicators is not None else None,
        valuation_weight=valuation_weight,
    )
    report, _frame = run_backtest(
        date_s,
        price_s,
        index["risk"],
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
