# score:allow pandas, pd.
"""Unit tests for digiquant strategy registry and strategies.

pandas is used only inside TestSdcaStrategyNautilusParity and
TestSdcaRiskIndexNautilusChain, at the same Nautilus BarDataWrangler
boundary as nautilus_runner.py::_prepare_bar_data (see the pandas
allowlist in digiquant/AGENTS.md).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from digiquant.backtest import run_backtest
from digiquant.data.loader import generate_synthetic_ohlcv
from digiquant.strategies import get_strategy, list_strategies

from tests.dq.conftest import SKIP_NATIVE_CRASH


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


@SKIP_NATIVE_CRASH
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


@SKIP_NATIVE_CRASH
@pytest.mark.unit
class TestSdcaStrategyNautilusParity:
    """SdcaStrategy driven through a real BacktestEngine vs. the standalone
    sdca.backtest.run_backtest() engine (#1081). SDCA is deliberately
    unregistered (see nautilus_strategy.py), so this builds its own
    BacktestEngine rather than reusing run_backtest()/get_strategy().
    """

    def test_nautilus_backtest_matches_standalone_engine(self, tmp_path) -> None:
        pytest.importorskip("nautilus_trader")
        import datetime as _dt
        from datetime import date

        import pandas as pd
        from digiquant.strategies.sdca.backtest import run_backtest as sdca_run_backtest
        from digiquant.strategies.sdca.curve import DEFAULT_BTC_NODES, AccumDistCurve
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig
        from nautilus_trader.backtest.engine import BacktestEngine
        from nautilus_trader.model.currencies import USDT
        from nautilus_trader.model.data import BarSpecification, BarType
        from nautilus_trader.model.enums import AccountType, BarAggregation, OmsType, PriceType
        from nautilus_trader.model.objects import Money
        from nautilus_trader.persistence.wranglers import BarDataWrangler
        from nautilus_trader.test_kit.providers import TestInstrumentProvider

        n = 40
        start = date(2020, 1, 1)
        dates = [start + _dt.timedelta(days=i) for i in range(n)]
        prices = [100.0 + i * 2.0 for i in range(n)]
        risks = [i * 100.0 / (n - 1) for i in range(n)]
        initial_cash = 100_000.0

        # Standalone reference engine (#1080) — the source of truth for the
        # allocation math this wrapper must reproduce.
        standalone_report, _ = sdca_run_backtest(
            dates=pl.Series(dates, dtype=pl.Date),
            price=pl.Series(prices, dtype=pl.Float64),
            risk=pl.Series(risks, dtype=pl.Float64),
            curve=AccumDistCurve(DEFAULT_BTC_NODES),
            initial_cash=initial_cash,
        )
        # Risk sweeps 0->100 over the run, so both accumulation and
        # distribution segments of the signed curve must fire.
        assert standalone_report.buy_days > 0
        assert standalone_report.sell_days > 0

        risk_path = tmp_path / "risk.parquet"
        pl.DataFrame({"date": dates, "risk": pl.Series(risks, dtype=pl.Float64)}).write_parquet(
            risk_path
        )

        instrument = TestInstrumentProvider.btcusdt_binance()
        bar_type = BarType(instrument.id, BarSpecification(1, BarAggregation.DAY, PriceType.LAST))

        config = SdcaStrategyConfig(
            instrument_id=instrument.id,
            bar_type=bar_type,
            initial_cash=initial_cash,
            risk_path=str(risk_path),
            curve_nodes=DEFAULT_BTC_NODES,
        )
        strategy = SdcaStrategy(config)

        engine = BacktestEngine()
        engine.add_venue(
            venue=instrument.id.venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            # Multi-currency cash account (base_currency=None): required for a
            # CurrencyPair spot instrument, which settles in both legs (BTC/USDT).
            base_currency=None,
            starting_balances=[Money(initial_cash, USDT)],
        )
        engine.add_instrument(instrument)

        # Polars -> pandas via .to_pandas() (Nautilus API boundary), matching
        # nautilus_runner.py::_prepare_bar_data — a plain-python-list ->
        # pd.to_datetime() index produces read-only backing arrays under this
        # pandas version, which BarDataWrangler's Cython buffer rejects.
        ohlcv_df = pl.DataFrame(
            {
                "timestamp": [_dt.datetime.combine(d, _dt.time.min) for d in dates],
                "open": prices,
                "high": prices,
                "low": prices,
                "close": prices,
            }
        )
        pd_df = ohlcv_df.select(["open", "high", "low", "close"]).to_pandas()
        pd_df.index = pd.to_datetime(ohlcv_df["timestamp"].to_pandas(), utc=True)
        pd_df.index.name = "timestamp"
        pd_df["volume"] = 1.0
        wrangler = BarDataWrangler(bar_type=bar_type, instrument=instrument)
        bars = wrangler.process(pd_df)
        engine.add_data(bars)
        engine.add_strategy(strategy)

        engine.run()

        final_price = prices[-1]
        nautilus_portfolio_value = strategy._cash + strategy._asset_units * final_price
        standalone_portfolio_value = initial_cash + standalone_report.total_pnl

        assert nautilus_portfolio_value == pytest.approx(standalone_portfolio_value, rel=0.01)

        engine.dispose()


@SKIP_NATIVE_CRASH
@pytest.mark.unit
class TestSdcaRiskIndexNautilusChain:
    """Full #3168 chain: BtcPowerLawRiskModel → build_risk_index → parquet →
    SdcaStrategy in a real BacktestEngine that submits at least one order.
    """

    def test_synthetic_fixture_submits_at_least_one_order(self, tmp_path) -> None:
        pytest.importorskip("nautilus_trader")
        import datetime as _dt
        from datetime import date

        import pandas as pd
        from digiquant.strategies.sdca.btc_power_law import (
            BtcPowerLawRiskModel,
            load_coefficients,
        )
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig
        from digiquant.strategies.sdca.risk_index import build_risk_index, write_risk_index
        from nautilus_trader.backtest.engine import BacktestEngine
        from nautilus_trader.model.currencies import USDT
        from nautilus_trader.model.data import BarSpecification, BarType
        from nautilus_trader.model.enums import AccountType, BarAggregation, OmsType, PriceType
        from nautilus_trader.model.objects import Money
        from nautilus_trader.persistence.wranglers import BarDataWrangler
        from nautilus_trader.test_kit.providers import TestInstrumentProvider

        n = 40
        start = date(2020, 1, 1)
        dates = pl.Series(
            "date", [start + _dt.timedelta(days=i) for i in range(n)], dtype=pl.Date
        )
        model = BtcPowerLawRiskModel(load_coefficients())
        rails = model.rails(dates)
        # Price at the low rail → valuation-z = +3 → risk = 0 → max buy.
        price = rails["low"].alias("price")
        frame = build_risk_index(dates, price, model)
        assert frame["risk"].drop_nulls().min() == pytest.approx(0.0)
        risk_path = write_risk_index(frame, tmp_path / "risk.parquet")

        instrument = TestInstrumentProvider.btcusdt_binance()
        bar_type = BarType(instrument.id, BarSpecification(1, BarAggregation.DAY, PriceType.LAST))
        initial_cash = 100_000.0
        strategy = SdcaStrategy(
            SdcaStrategyConfig(
                instrument_id=instrument.id,
                bar_type=bar_type,
                initial_cash=initial_cash,
                risk_path=str(risk_path),
            )
        )

        engine = BacktestEngine()
        engine.add_venue(
            venue=instrument.id.venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            base_currency=None,
            starting_balances=[Money(initial_cash, USDT)],
        )
        engine.add_instrument(instrument)

        prices = price.to_list()
        ohlcv_df = pl.DataFrame(
            {
                "timestamp": [
                    _dt.datetime.combine(d, _dt.time.min) for d in dates.to_list()
                ],
                "open": prices,
                "high": prices,
                "low": prices,
                "close": prices,
            }
        )
        pd_df = ohlcv_df.select(["open", "high", "low", "close"]).to_pandas()
        pd_df.index = pd.to_datetime(ohlcv_df["timestamp"].to_pandas(), utc=True)
        pd_df.index.name = "timestamp"
        pd_df["volume"] = 1.0
        wrangler = BarDataWrangler(bar_type=bar_type, instrument=instrument)
        bars = wrangler.process(pd_df)
        engine.add_data(bars)
        engine.add_strategy(strategy)
        engine.run()

        assert strategy._asset_units > 0, "cheap-rail buy must fill at least once"
        engine.dispose()
