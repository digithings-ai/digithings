"""REM-101: in-memory backtest cache enforces LRU cap."""

from __future__ import annotations

import pytest

from digiquant import backtest as bt
from digiquant.models import BacktestResult


def _fake_result(name: str) -> BacktestResult:
    return BacktestResult(
        run_id=f"run-{name}",
        strategy_name="ema_cross",
        symbols=["AAPL"],
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-12-31T00:00:00Z",
        total_return_pct=10.0,
        sharpe_ratio=1.0,
        max_drawdown_pct=-5.0,
        num_trades=3,
    )


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_BACKTEST_CACHE", "true")
    monkeypatch.setenv("DIGIQUANT_BACKTEST_CACHE_MAX", "2")
    bt.clear_backtest_cache()


@pytest.mark.unit
def test_backtest_cache_evicts_oldest_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_run(**kwargs):  # type: ignore[no-untyped-def]
        tag = (kwargs.get("strategy_params") or {}).get("tag", "x")
        calls.append(tag)
        return _fake_result(tag)

    monkeypatch.setattr(bt, "run_nautilus_backtest", fake_run)

    for name in ("s1", "s2", "s3"):
        bt.run_backtest(
            strategy_name="ema_cross",
            symbols=["AAPL"],
            data_path="digiquant/data/AAPL_real.csv",
            strategy_params={"tag": name},
        )

    assert calls == ["s1", "s2", "s3"]
    assert len(bt._backtest_cache) == 2
