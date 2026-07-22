"""Unit tests for the persisted Olympus cumulative-return contract (#1615)."""

from __future__ import annotations

import pytest

from digiquant.olympus.performance_returns import calculate_performance_returns

pytestmark = pytest.mark.unit


def test_calculates_portfolio_benchmark_and_relative_returns() -> None:
    returns = calculate_performance_returns(
        nav_values=[100.0, 105.0, 110.0],
        benchmark_closes=[400.0, 410.0, 420.0],
        benchmark_ticker="SPY",
    )

    assert returns.net_return_pct == pytest.approx(10.0)
    assert returns.benchmark_return_pct == pytest.approx(5.0)
    assert returns.relative_return_pct == pytest.approx(5.0)
    assert returns.benchmark_ticker == "SPY"


def test_uses_first_observed_nav_instead_of_assuming_base_100() -> None:
    returns = calculate_performance_returns(
        nav_values=[125.0, 137.5],
        benchmark_closes=[500.0, 550.0],
    )

    assert returns.net_return_pct == pytest.approx(10.0)
    assert returns.benchmark_return_pct == pytest.approx(10.0)
    assert returns.relative_return_pct == pytest.approx(0.0)


def test_missing_benchmark_preserves_portfolio_return_only() -> None:
    returns = calculate_performance_returns(
        nav_values=[100.0, 108.0],
        benchmark_closes=[],
    )

    assert returns.net_return_pct == pytest.approx(8.0)
    assert returns.benchmark_return_pct is None
    assert returns.relative_return_pct is None


@pytest.mark.parametrize(
    ("nav_values", "benchmark_closes"),
    [
        ([], []),
        ([100.0], [400.0]),
        ([0.0, 100.0], [0.0, 400.0]),
    ],
)
def test_insufficient_or_invalid_series_returns_nulls(
    nav_values: list[float], benchmark_closes: list[float]
) -> None:
    returns = calculate_performance_returns(
        nav_values=nav_values,
        benchmark_closes=benchmark_closes,
    )

    assert returns.net_return_pct is None
    assert returns.benchmark_return_pct is None
    assert returns.relative_return_pct is None
