"""Tests for SdcaStrategyConfig and SdcaStrategy instantiation (#1081)."""

from __future__ import annotations

import datetime as _dt
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock

import polars as pl
import pytest

try:
    from nautilus_trader.core.datetime import dt_to_unix_nanos
    from nautilus_trader.model.currencies import BTC, USDT
    from nautilus_trader.model.data import Bar, BarSpecification, BarType
    from nautilus_trader.model.enums import BarAggregation, OrderSide, PriceType
    from nautilus_trader.model.identifiers import InstrumentId
    from nautilus_trader.model.instruments import Instrument
    from nautilus_trader.model.objects import Money
    from nautilus_trader.test_kit.providers import TestInstrumentProvider

    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False

if TYPE_CHECKING:
    # Only for the _strategy() helper's return-type annotation below — every
    # test imports SdcaStrategy locally instead, so collection never triggers
    # the unconditional `nautilus_trader` import in nautilus_strategy.py before
    # the skipif above has a chance to apply.
    from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed"),
]


def _write_risk_parquet(tmp_path: Path, n: int = 60, with_null: bool = False) -> tuple[str, int]:
    """Write a synthetic risk-index parquet (date, risk), returning (path, row_count)."""
    dates = [date(2020, 1, 1) + _dt.timedelta(days=i) for i in range(n)]
    risks: list[float | None] = [float(i % 101) for i in range(n)]
    if with_null:
        risks[0] = None
    df = pl.DataFrame({"date": dates, "risk": pl.Series(risks, dtype=pl.Float64)})
    path = tmp_path / "risk.parquet"
    df.write_parquet(path)
    return str(path), n


def _make_bar(bar_type: BarType, instrument: Instrument, day: date, price: float) -> Bar:
    """Build a single real Bar for a given day/price, for on_bar() unit tests."""
    ts = dt_to_unix_nanos(_dt.datetime.combine(day, _dt.time.min, tzinfo=_dt.timezone.utc))
    p = instrument.make_price(price)
    q = instrument.make_qty(1.0)
    return Bar(bar_type, p, p, p, p, q, ts, ts)


@pytest.fixture()
def instrument() -> Instrument:
    return TestInstrumentProvider.btcusdt_binance()


@pytest.fixture()
def instrument_id(instrument: Instrument) -> InstrumentId:
    return instrument.id


@pytest.fixture()
def bar_type(instrument_id: InstrumentId) -> BarType:
    spec = BarSpecification(1, BarAggregation.DAY, PriceType.LAST)
    return BarType(instrument_id, spec)


class TestSdcaStrategyConfig:
    def test_defaults(self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path) -> None:
        from digiquant.strategies.sdca.curve import DEFAULT_BTC_NODES
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=path,
        )
        assert cfg.curve_nodes == DEFAULT_BTC_NODES
        assert cfg.long_only is False

    def test_custom_curve_nodes_and_long_only(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path)
        nodes = tuple(5.0 for _ in range(21))
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=50_000.0,
            risk_path=path,
            curve_nodes=nodes,
            long_only=True,
        )
        assert cfg.curve_nodes == nodes
        assert cfg.long_only is True

    def test_rejects_wrong_node_count(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path)
        with pytest.raises(ValueError, match="21"):
            SdcaStrategyConfig(
                instrument_id=instrument_id,
                bar_type=bar_type,
                initial_cash=100_000.0,
                risk_path=path,
                curve_nodes=(1.0, 2.0, 3.0),
            )


class TestSdcaStrategyInstantiation:
    def test_can_instantiate(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=path,
        )
        strategy = SdcaStrategy(cfg)
        assert strategy is not None

    def test_risk_index_loaded_matches_row_count(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        path, n = _write_risk_parquet(tmp_path, n=200)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=path,
        )
        strategy = SdcaStrategy(cfg)
        index = strategy._load_risk_index()
        assert len(index) == n

    def test_risk_index_preserves_null(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path, n=10, with_null=True)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=path,
        )
        strategy = SdcaStrategy(cfg)
        index = strategy._load_risk_index()
        assert index[date(2020, 1, 1)] is None

    def test_risk_index_rejects_duplicate_dates(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        one_date = date(2020, 1, 1)
        df = pl.DataFrame(
            {
                "date": [one_date, one_date, date(2020, 1, 2)],
                "risk": pl.Series([1.0, 2.0, 3.0], dtype=pl.Float64),
            }
        )
        path = tmp_path / "risk_dupe.parquet"
        df.write_parquet(path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=str(path),
        )
        strategy = SdcaStrategy(cfg)
        with pytest.raises(ValueError, match="duplicate"):
            strategy._load_risk_index()

    def test_risk_index_rejects_missing_columns(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        df = pl.DataFrame({"date": [date(2020, 1, 1)], "value": [1.0]})
        path = tmp_path / "risk_bad_cols.parquet"
        df.write_parquet(path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=str(path),
        )
        strategy = SdcaStrategy(cfg)
        with pytest.raises(ValueError, match="missing"):
            strategy._load_risk_index()

    def test_initial_state_matches_config(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=77_000.0,
            risk_path=path,
        )
        strategy = SdcaStrategy(cfg)
        assert strategy._cash == pytest.approx(77_000.0)
        assert strategy._asset_units == pytest.approx(0.0)

    def test_risk_index_normalizes_datetime_date_column(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        """A `pl.Datetime` date column must be usable with on_bar()'s `datetime.date`
        lookups (#1081 CodeRabbit review) — iter_rows() otherwise yields
        `datetime.datetime` keys, which never equal a `datetime.date` lookup key.
        """
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        df = pl.DataFrame(
            {"date": [date(2020, 1, 1), date(2020, 1, 2)], "risk": [1.0, 2.0]},
            schema={"date": pl.Datetime("us"), "risk": pl.Float64},
        )
        path = tmp_path / "risk_datetime.parquet"
        df.write_parquet(path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=str(path),
        )
        strategy = SdcaStrategy(cfg)
        index = strategy._load_risk_index()
        assert all(type(k) is date for k in index)
        assert index[date(2020, 1, 1)] == pytest.approx(1.0)
        assert index[date(2020, 1, 2)] == pytest.approx(2.0)

    def test_risk_index_rejects_non_date_dtype(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        df = pl.DataFrame({"date": ["2020-01-01"], "risk": [1.0]})
        path = tmp_path / "risk_bad_date_dtype.parquet"
        df.write_parquet(path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=str(path),
        )
        strategy = SdcaStrategy(cfg)
        with pytest.raises(ValueError, match="pl.Date"):
            strategy._load_risk_index()

    def test_risk_index_rejects_non_numeric_risk_dtype(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        """A string ``risk`` column must be rejected at load time (#1081 CodeRabbit
        review) — otherwise it reaches ``AccumDistCurve.value_at_risk()`` as a
        Python ``str`` and raises ``TypeError`` deep in the curve math on the
        first matching bar instead of failing fast here.
        """
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        df = pl.DataFrame({"date": [date(2020, 1, 1)], "risk": ["50.0"]})
        path = tmp_path / "risk_bad_risk_dtype.parquet"
        df.write_parquet(path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=str(path),
        )
        strategy = SdcaStrategy(cfg)
        with pytest.raises(ValueError, match="numeric"):
            strategy._load_risk_index()

    def test_risk_index_rejects_null_date(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        """A null ``date`` becomes a ``None`` dict key that on_bar()'s
        ``datetime.date`` lookups can never match (#1081 CodeRabbit review) —
        rejected at load time instead of silently becoming a dead row.
        """
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        df = pl.DataFrame(
            {"date": [date(2020, 1, 1), None], "risk": [1.0, 2.0]},
            schema={"date": pl.Date, "risk": pl.Float64},
        )
        path = tmp_path / "risk_null_date.parquet"
        df.write_parquet(path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=str(path),
        )
        strategy = SdcaStrategy(cfg)
        with pytest.raises(ValueError, match="null date"):
            strategy._load_risk_index()

    def test_risk_index_rejects_non_finite_risk(
        self, instrument_id: InstrumentId, bar_type: BarType, tmp_path: Path
    ) -> None:
        """NaN/inf pass ``is_numeric()`` but reach
        ``AccumDistCurve.value_at_risk()`` as a non-finite float (#1081
        CodeRabbit review) — rejected at load time instead. A null risk value
        (see ``test_risk_index_preserves_null``) is a distinct, valid
        no-data day and must still be preserved.
        """
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        df = pl.DataFrame(
            {
                "date": [date(2020, 1, 1), date(2020, 1, 2)],
                "risk": pl.Series([float("nan"), 2.0], dtype=pl.Float64),
            }
        )
        path = tmp_path / "risk_non_finite.parquet"
        df.write_parquet(path)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=str(path),
        )
        strategy = SdcaStrategy(cfg)
        with pytest.raises(ValueError, match="non-finite"):
            strategy._load_risk_index()


class TestSdcaStrategyOrderPendingGuard:
    """#1081 CodeRabbit review: on_bar() must not size a new order off unreserved
    cash/asset_units while a prior order is still open. Two bars could otherwise
    submit overlapping buys/sells beyond available capacity if a fill isn't
    instantaneous. Verified at the flag level rather than through a live
    engine/registration, since `_submit_market()` needs `order_factory`, which is
    only wired up once a strategy is registered with a trader.
    """

    def _strategy(
        self,
        instrument: Instrument,
        instrument_id: InstrumentId,
        bar_type: BarType,
        tmp_path: Path,
    ) -> SdcaStrategy:
        from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig

        path, _ = _write_risk_parquet(tmp_path, n=5)
        cfg = SdcaStrategyConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            initial_cash=100_000.0,
            risk_path=path,
        )
        strategy = SdcaStrategy(cfg)
        strategy._instrument = instrument
        strategy._risk_index = {date(2020, 1, 1): 0.0}  # risk 0 -> max buy rate
        return strategy

    def test_on_bar_skips_when_order_pending(
        self,
        instrument: Instrument,
        instrument_id: InstrumentId,
        bar_type: BarType,
        tmp_path: Path,
    ) -> None:
        strategy = self._strategy(instrument, instrument_id, bar_type, tmp_path)
        strategy._order_pending = True
        bar = _make_bar(bar_type, instrument, date(2020, 1, 1), 100.0)

        strategy.on_bar(bar)  # would raise (order_factory is None) if the guard were missing

        assert strategy._cash == pytest.approx(100_000.0)
        assert strategy._asset_units == pytest.approx(0.0)

    def test_submit_market_skips_dust_below_size_increment(
        self,
        instrument: Instrument,
        instrument_id: InstrumentId,
        bar_type: BarType,
        tmp_path: Path,
    ) -> None:
        """Remaining-book dust must not raise inside make_qty (publish path)."""
        strategy = self._strategy(instrument, instrument_id, bar_type, tmp_path)
        increment = instrument.size_increment.as_double()
        assert increment > 0
        strategy._submit_market(OrderSide.BUY, increment / 2.0)
        assert strategy._order_pending is False
        assert strategy._cash == pytest.approx(100_000.0)

    def test_on_stop_leaves_dca_book_open(
        self,
        instrument: Instrument,
        instrument_id: InstrumentId,
        bar_type: BarType,
        tmp_path: Path,
    ) -> None:
        """Engine stop must not flatten remaining holdings into a fake round-trip."""
        strategy = self._strategy(instrument, instrument_id, bar_type, tmp_path)
        strategy.cancel_all_orders = Mock()
        strategy.close_all_positions = Mock()
        strategy.on_stop()
        strategy.cancel_all_orders.assert_called_once_with(instrument_id)
        strategy.close_all_positions.assert_not_called()

    def test_order_filled_clears_pending_after_full_qty(
        self,
        instrument: Instrument,
        instrument_id: InstrumentId,
        bar_type: BarType,
        tmp_path: Path,
    ) -> None:
        strategy = self._strategy(instrument, instrument_id, bar_type, tmp_path)
        strategy._order_pending = True
        strategy._pending_qty = 1.0
        event = Mock(is_buy=True, commission=Money(0.0, USDT))
        event.last_qty.as_double.return_value = 1.0
        event.last_px.as_double.return_value = 100.0

        strategy.on_order_filled(event)

        assert strategy._order_pending is False

    def test_order_filled_keeps_pending_after_partial_qty(
        self,
        instrument: Instrument,
        instrument_id: InstrumentId,
        bar_type: BarType,
        tmp_path: Path,
    ) -> None:
        strategy = self._strategy(instrument, instrument_id, bar_type, tmp_path)
        strategy._order_pending = True
        strategy._pending_qty = 2.0
        event = Mock(is_buy=True, commission=Money(0.0, USDT))
        event.last_qty.as_double.return_value = 1.0
        event.last_px.as_double.return_value = 100.0

        strategy.on_order_filled(event)

        assert strategy._order_pending is True
        assert strategy._pending_qty == pytest.approx(1.0)

    @pytest.mark.parametrize(
        "handler_name", ["on_order_canceled", "on_order_rejected", "on_order_expired"]
    )
    def test_terminal_non_fill_event_clears_pending(
        self,
        instrument: Instrument,
        instrument_id: InstrumentId,
        bar_type: BarType,
        tmp_path: Path,
        handler_name: str,
    ) -> None:
        strategy = self._strategy(instrument, instrument_id, bar_type, tmp_path)
        strategy._order_pending = True
        strategy._pending_qty = 1.0

        getattr(strategy, handler_name)(Mock())

        assert strategy._order_pending is False
        assert strategy._pending_qty == pytest.approx(0.0)

    def test_on_order_denied_clears_pending(
        self,
        instrument: Instrument,
        instrument_id: InstrumentId,
        bar_type: BarType,
        tmp_path: Path,
    ) -> None:
        """A denied order never reaches the venue, so it must clear pending
        state the same as canceled/rejected/expired (#1081 CodeRabbit review) —
        otherwise on_bar() stays stuck skipping every subsequent bar.
        """
        strategy = self._strategy(instrument, instrument_id, bar_type, tmp_path)
        strategy._order_pending = True
        strategy._pending_qty = 1.0

        strategy.on_order_denied(Mock())

        assert strategy._order_pending is False
        assert strategy._pending_qty == pytest.approx(0.0)

    def test_order_filled_subtracts_same_currency_commission(
        self,
        instrument: Instrument,
        instrument_id: InstrumentId,
        bar_type: BarType,
        tmp_path: Path,
    ) -> None:
        """Commission in the instrument's quote currency (USDT, same as
        _cash) must be deducted, or shadow _cash drifts from real account
        cash by the fees paid on every fill (#1081 CodeRabbit review).
        """
        strategy = self._strategy(instrument, instrument_id, bar_type, tmp_path)
        strategy._pending_qty = 1.0
        event = Mock(is_buy=True, commission=Money(0.5, USDT))
        event.last_qty.as_double.return_value = 1.0
        event.last_px.as_double.return_value = 100.0

        strategy.on_order_filled(event)

        assert strategy._cash == pytest.approx(100_000.0 - 100.0 - 0.5)

    def test_order_filled_ignores_different_currency_commission(
        self,
        instrument: Instrument,
        instrument_id: InstrumentId,
        bar_type: BarType,
        tmp_path: Path,
    ) -> None:
        """A fee paid in a currency other than the tracked quote currency
        (e.g. the base asset) can't be folded into a single-currency _cash
        figure without a conversion rate this strategy doesn't have, so it
        must be left untouched rather than misapplied (#1081 CodeRabbit
        review).
        """
        strategy = self._strategy(instrument, instrument_id, bar_type, tmp_path)
        strategy._pending_qty = 1.0
        event = Mock(is_buy=True, commission=Money(0.001, BTC))
        event.last_qty.as_double.return_value = 1.0
        event.last_px.as_double.return_value = 100.0

        strategy.on_order_filled(event)

        assert strategy._cash == pytest.approx(100_000.0 - 100.0)
