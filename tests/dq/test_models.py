"""Unit tests for digiquant Pydantic models."""

from __future__ import annotations

import pytest
from digiquant.models import BacktestResult, ExportResult, OptimizeResult
from digiquant.stats import HonestRateBlock
from pydantic import ValidationError


@pytest.mark.unit
class TestBacktestResult:
    """BacktestResult model validation and serialization."""

    def test_minimal_valid(self) -> None:
        r = BacktestResult(
            run_id="r1",
            strategy_name="s1",
            symbols=[],
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-12-31T23:59:59Z",
        )
        assert r.run_id == "r1"
        assert r.status == "ok"
        assert r.total_pnl == 0.0
        assert r.num_trades == 0

    def test_full_valid(self) -> None:
        r = BacktestResult(
            run_id="r1",
            strategy_name="mean_reversion",
            symbols=["AAPL", "MSFT"],
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-12-31T23:59:59Z",
            total_pnl=1000.0,
            total_return_pct=0.1,
            sharpe_ratio=1.2,
            max_drawdown_pct=-1.5,
            num_trades=10,
            status="ok",
            message="Done",
        )
        assert r.sharpe_ratio == 1.2
        assert r.max_drawdown_pct == -1.5

    def test_missing_required_raises(self) -> None:
        with pytest.raises(ValidationError):
            BacktestResult(
                run_id="r1",
                strategy_name="s1",
                symbols=[],
            )

    def test_serialize_roundtrip(self) -> None:
        r = BacktestResult(
            run_id="r1",
            strategy_name="s1",
            symbols=["AAPL"],
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-12-31T23:59:59Z",
            status="error",
            message="fail",
        )
        data = r.model_dump()
        r2 = BacktestResult.model_validate(data)
        assert r2.run_id == r.run_id
        assert r2.message == r.message

    def test_success_means_not_error(self) -> None:
        def make(status: str) -> BacktestResult:
            return BacktestResult(
                run_id="r1",
                strategy_name="s1",
                symbols=[],
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-12-31T23:59:59Z",
                status=status,
            )

        assert make("ok").success is True
        assert make("partial").success is True
        assert make("error").success is False

    def test_honest_rate_fields_default_empty(self) -> None:
        r = BacktestResult(
            run_id="r1",
            strategy_name="s1",
            symbols=[],
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-12-31T23:59:59Z",
        )
        assert r.honest_rate is None
        assert r.honest_rate_by_symbol == {}

    def test_num_trades_is_labelled_a_fill_count(self) -> None:
        d = BacktestResult.model_fields["num_trades"].description or ""
        assert "Fill count" in d
        assert "NOT a win-rate denominator" in d


@pytest.mark.unit
class TestOptimizeResult:
    """OptimizeResult model."""

    def test_minimal_valid(self) -> None:
        o = OptimizeResult(run_id="opt-1", strategy_name="s1", symbols=["AAPL"])
        assert o.run_id == "opt-1"
        assert o.num_evaluations == 0
        assert o.best_params == {}
        assert o.status == "ok"

    def test_serialize_roundtrip(self) -> None:
        o = OptimizeResult(
            run_id="opt-1",
            strategy_name="s1",
            symbols=[],
            best_params={"fast": 10},
            num_evaluations=2,
        )
        data = o.model_dump()
        o2 = OptimizeResult.model_validate(data)
        assert o2.best_params == o.best_params

    def test_best_backtest_carries_the_block(self) -> None:
        b = BacktestResult(
            run_id="r1",
            strategy_name="s1",
            symbols=["AAPL"],
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-12-31T23:59:59Z",
            honest_rate=HonestRateBlock(k=3, n=4),
        )
        o = OptimizeResult(run_id="o1", strategy_name="s1", symbols=["AAPL"], best_backtest=b)
        assert (o.best_backtest.honest_rate.k, o.best_backtest.honest_rate.n) == (3, 4)
        rt = OptimizeResult.model_validate(o.model_dump())
        assert rt.best_backtest.honest_rate.n == 4


@pytest.mark.unit
class TestExportResult:
    """ExportResult model."""

    def test_minimal_valid(self) -> None:
        e = ExportResult(run_id="ex-1", target="nautilus", strategy_name="s1")
        assert e.target == "nautilus"
        assert e.status == "ok"

    def test_serialize_roundtrip(self) -> None:
        e = ExportResult(
            run_id="ex-1",
            target="tradingview",
            strategy_name="s1",
            artifact_path="/tmp/out.json",
        )
        data = e.model_dump()
        e2 = ExportResult.model_validate(data)
        assert e2.artifact_path == e.artifact_path
