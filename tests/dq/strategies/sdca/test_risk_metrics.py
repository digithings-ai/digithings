"""Tests for risk-adjusted equity metrics (#4804) — hand-derived numbers, no engine.

Every expected value is hand-derived from the documented conventions in
``sdca/risk_metrics.py`` (252 annualization, risk-free 0, Sortino on downside
deviation with a full-period denominator, drawdown magnitude reused from
``walk_forward``). A 100× or 1/N error must move these numbers.
"""

from __future__ import annotations

import math
import statistics

import pytest
from digiquant.strategies.sdca.risk_metrics import RiskMetrics, equity_metrics
from digiquant.strategies.sdca.walk_forward import max_drawdown_magnitude_pct

pytestmark = pytest.mark.unit

# Daily returns used by the hand-computed Sharpe / Sortino pins.
#   mean            = (0.10 - 0.05 + 0.20 - 0.10 + 0.05) / 5 = 0.04
#   sample stdev    = sqrt(0.057 / 4)                       = 0.11937336386313323
#   downside dev    = sqrt((0.0025 + 0.01) / 5)             = 0.05
#   sharpe          = 0.04 / 0.11937336386313323 * sqrt(252)  = 5.31927972963495
#   sortino         = 0.04 / 0.05            * sqrt(252)  = 12.699606293110035
_PIN_RETURNS = (0.10, -0.05, 0.20, -0.10, 0.05)
_PIN_SHARPE = 5.31927972963495
_PIN_SORTINO = 12.699606293110035


def _path_from_returns(start: float, returns: tuple[float, ...]) -> list[float]:
    values = [float(start)]
    for r in returns:
        values.append(values[-1] * (1.0 + r))
    return values


def test_total_return_and_cagr_on_a_one_year_doubling_path() -> None:
    """253 bars = 252 periods = exactly one year, so CAGR == total return."""
    values = [100.0 * (2.0 ** (i / 252.0)) for i in range(253)]
    metrics = equity_metrics(values, annualization=252)
    assert metrics.total_return_pct == pytest.approx(100.0)
    assert metrics.cagr_pct == pytest.approx(100.0, rel=1e-9)
    # 100× bug guard: a fraction-valued total return must not survive.
    assert metrics.total_return_pct != pytest.approx(1.0)


def test_sharpe_matches_hand_computed_daily_returns() -> None:
    metrics = equity_metrics(_path_from_returns(100.0, _PIN_RETURNS), annualization=252)
    assert metrics.sharpe == pytest.approx(_PIN_SHARPE, rel=1e-9)
    # Independent cross-check: stdlib sample stdev, not the module's own path.
    expected = statistics.fmean(_PIN_RETURNS) / statistics.stdev(_PIN_RETURNS) * math.sqrt(252)
    assert metrics.sharpe == pytest.approx(expected, rel=1e-12)


def test_sortino_uses_downside_deviation_not_total_volatility() -> None:
    metrics = equity_metrics(_path_from_returns(100.0, _PIN_RETURNS), annualization=252)
    assert metrics.sortino == pytest.approx(_PIN_SORTINO, rel=1e-9)
    # Downside deviation (0.05) is below total stdev here, so Sortino > Sharpe.
    assert metrics.sortino > metrics.sharpe


def test_annualization_scales_sharpe_by_sqrt() -> None:
    values = _path_from_returns(100.0, _PIN_RETURNS)
    annual = equity_metrics(values, annualization=252)
    weekly = equity_metrics(values, annualization=63)
    # sqrt(63 / 252) = 0.5
    assert weekly.sharpe == pytest.approx(annual.sharpe * 0.5, rel=1e-12)
    # Period-return statistics themselves do not depend on annualization.
    assert weekly.sortino == pytest.approx(annual.sortino * 0.5, rel=1e-12)
    assert weekly.max_drawdown_pct == pytest.approx(annual.max_drawdown_pct)


def test_flat_series_reports_zeroes_instead_of_infinities() -> None:
    metrics = equity_metrics([100.0] * 30, annualization=252)
    assert metrics.total_return_pct == pytest.approx(0.0)
    assert metrics.cagr_pct == pytest.approx(0.0)
    assert metrics.sharpe == pytest.approx(0.0)
    assert metrics.sortino == pytest.approx(0.0)
    # No drawdown means no Calmar denominator — 0.0, never inf.
    assert metrics.calmar == pytest.approx(0.0)
    assert metrics.max_drawdown_pct == pytest.approx(0.0)


def test_monotonic_series_has_no_drawdown_and_stays_sortino_guarded() -> None:
    values = [100.0 * 1.001**i for i in range(300)]
    metrics = equity_metrics(values, annualization=252)
    assert metrics.max_drawdown_pct == pytest.approx(0.0)
    assert metrics.calmar == pytest.approx(0.0)
    assert metrics.sortino == pytest.approx(0.0)
    assert metrics.sharpe > 0.0
    assert metrics.cagr_pct > 0.0


def test_max_drawdown_reuses_walk_forward_magnitude_pct() -> None:
    # Running peak is 120 all the way down: 60 → −50%, 45 → −62.5%. The 90
    # rebound never lowers the running peak, so the worst is measured from 120.
    values = [100.0, 120.0, 60.0, 90.0, 45.0]
    metrics = equity_metrics(values, annualization=252)
    assert metrics.max_drawdown_pct == pytest.approx(62.5)
    assert metrics.max_drawdown_pct == max_drawdown_magnitude_pct(values)


def test_drawdown_is_a_positive_magnitude_even_after_recovery() -> None:
    # A new high after the trough must not shrink the worst drawdown.
    values = [100.0, 150.0, 50.0, 200.0]
    metrics = equity_metrics(values, annualization=252)
    assert metrics.max_drawdown_pct == pytest.approx(max_drawdown_magnitude_pct(values))
    assert metrics.max_drawdown_pct > 0.0


def test_loss_path_reports_negative_cagr() -> None:
    values = _path_from_returns(100.0, (-0.10, -0.10, -0.10, -0.10, -0.10))
    metrics = equity_metrics(values, annualization=252)
    assert metrics.total_return_pct == pytest.approx(-40.951, rel=1e-4)
    assert metrics.cagr_pct < 0.0
    assert metrics.sharpe < 0.0
    # Every period is negative: downside deviation is the full-period RMS (0.1),
    # so Sortino is finite and negative rather than zero or undefined.
    assert metrics.sortino == pytest.approx(-1.0 * math.sqrt(252), rel=1e-9)
    assert metrics.calmar < 0.0


def test_calmar_is_cagr_over_drawdown_and_needs_no_annualization() -> None:
    # 253 bars doubling 100 → 200, with one bar dropped to half the prior peak:
    # CAGR is +100% and the drop is exactly a 50% peak-to-trough drawdown.
    values = [100.0 * (2.0 ** (i / 252.0)) for i in range(253)]
    values[126] = values[125] * 0.5
    metrics = equity_metrics(values, annualization=252)
    assert metrics.cagr_pct == pytest.approx(100.0, rel=1e-9)
    assert metrics.max_drawdown_pct == pytest.approx(50.0)
    assert metrics.calmar == pytest.approx(2.0, rel=1e-9)
    assert metrics.calmar == pytest.approx(metrics.cagr_pct / metrics.max_drawdown_pct)


def test_model_is_frozen_and_documents_every_float() -> None:
    metrics = equity_metrics([100.0, 101.0], annualization=252)
    assert isinstance(metrics, RiskMetrics)
    with pytest.raises(Exception, match="frozen|immutable"):
        metrics.sharpe = 1.0  # type: ignore[misc]
    for name, field in RiskMetrics.model_fields.items():
        assert field.description, f"{name} has no description"


@pytest.mark.parametrize(
    ("values", "annualization", "match"),
    [
        ([], 252, "at least two"),
        ([100.0], 252, "at least two"),
        ([100.0, 101.0], 0, "annualization"),
        ([100.0, 101.0], -1, "annualization"),
        ([0.0, 101.0], 252, "positive"),
        ([100.0, 0.0], 252, "positive"),
        ([100.0, float("nan")], 252, "finite"),
        ([100.0, float("inf")], 252, "finite"),
    ],
)
def test_invalid_inputs_raise(values: list[float], annualization: int, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        equity_metrics(values, annualization=annualization)
