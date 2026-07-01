"""Unit tests for ADDM drift detection wiring."""

from __future__ import annotations

import pytest

from digiquant.addm import check_drift, clear_history, record_sharpe


@pytest.fixture(autouse=True)
def _clear_addm_history() -> None:
    clear_history()
    yield
    clear_history()


@pytest.mark.unit
def test_check_drift_implemented_with_current_sharpe() -> None:
    for sharpe in (1.0, 1.1, 1.2):
        record_sharpe("demo", sharpe)
    result = check_drift("demo", current_sharpe=1.3)
    assert result.implemented is True
    assert result.score is not None


@pytest.mark.unit
def test_check_drift_insufficient_history() -> None:
    result = check_drift("fresh", current_sharpe=1.5)
    assert result.implemented is False
