"""Unit tests for DigiQuant strategy registry and strategies."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from digiquant.backtest import run_backtest
from digiquant.data.loader import generate_synthetic_ohlcv
from digiquant.strategies import get_strategy, list_strategies

# Real Nautilus engines can't share a process: NautilusTrader initializes its
# Rust logging once per interpreter (see #1389), so a second real engine aborts
# (exit 134) regardless of OS. The CI lane runs every dq file in one pytest
# process, so gate real-engine tests behind CI. See #42.
_SKIP_NATIVE_CRASH = pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Real Nautilus engine aborts as a second in-process engine (exit 134) — see #42",
)


@pytest.mark.unit
class TestStrategyRegistry:
    """Strategy registry: list_strategies, get_strategy, aliases."""

    def test_list_strategies_returns_non_empty(self) -> None:
        strategies = list_strategies()
        assert len(strategies) >= 1
        names = [s["name"] for s in strategies]
        assert "ema_cross" in names

    def test_list_strategies_has_expected_keys(self) -> None:
        strategies = list_strategies()
        for s in strategies:
            assert "name" in s
            assert "aliases" in s
            assert "description" in s
            assert "default_params" in s

    def test_get_strategy_ema_cross_returns_strategy_and_config(self) -> None:
        pytest.importorskip("nautilus_trader")
        from nautilus_trader.model import BarType
        from nautilus_trader.test_kit.providers import TestInstrumentProvider

        inst = TestInstrumentProvider.equity(symbol="AAPL", venue="SIM")
        bar_type = BarType.from_str("AAPL.SIM-1-DAY-LAST-EXTERNAL")
        strategy, config = get_strategy(
            strategy_name="ema_cross",
            instrument_id=inst.id,
            bar_type=bar_type,
        )
        assert strategy is not None
        assert config is not None
        assert config.instrument_id == inst.id
        assert config.bar_type == bar_type

    def test_get_strategy_resolves_alias_momentum_tech_to_ema_cross(self) -> None:
        pytest.importorskip("nautilus_trader")
        from nautilus_trader.model import BarType
        from nautilus_trader.test_kit.providers import TestInstrumentProvider

        inst = TestInstrumentProvider.equity(symbol="AAPL", venue="SIM")
        bar_type = BarType.from_str("AAPL.SIM-1-DAY-LAST-EXTERNAL")
        strategy, config = get_strategy(
            strategy_name="momentum_tech",
            instrument_id=inst.id,
            bar_type=bar_type,
        )
        assert strategy is not None
        assert "EMACross" in type(strategy).__name__

    def test_get_strategy_unknown_raises(self) -> None:
        """Unknown strategy raises ValueError; no fallback."""
        pytest.importorskip("nautilus_trader")
        from nautilus_trader.model import BarType
        from nautilus_trader.test_kit.providers import TestInstrumentProvider

        inst = TestInstrumentProvider.equity(symbol="AAPL", venue="SIM")
        bar_type = BarType.from_str("AAPL.SIM-1-DAY-LAST-EXTERNAL")
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy(
                strategy_name="unknown_strategy_xyz",
                instrument_id=inst.id,
                bar_type=bar_type,
            )


@_SKIP_NATIVE_CRASH
@pytest.mark.unit
class TestStrategyBacktestSmoke:
    """Smoke tests: backtest returns ok for each strategy."""

    def _run_smoke(self, strategy_name: str) -> None:
        pytest.importorskip("nautilus_trader")
        df = generate_synthetic_ohlcv(["AAPL"], freq="1d")
        with __import__("tempfile").TemporaryDirectory() as tmp:
            df.write_csv(Path(tmp) / "AAPL.csv")
            result = run_backtest(
                strategy_name=strategy_name,
                symbols=["AAPL"],
                data_dir=tmp,
            )
        assert result is not None
        assert result.status == "ok"

    def test_ema_cross_smoke(self) -> None:
        self._run_smoke("ema_cross")

    def test_ema_cross_long_smoke(self) -> None:
        self._run_smoke("ema_cross_long")

    def test_ema_cross_trailing_smoke(self) -> None:
        self._run_smoke("ema_cross_trailing")

    def test_rsi_momentum_smoke(self) -> None:
        self._run_smoke("rsi_momentum")

    def test_bollinger_mr_smoke(self) -> None:
        self._run_smoke("bollinger_mr")

    def test_macd_trend_smoke(self) -> None:
        self._run_smoke("macd_trend")
