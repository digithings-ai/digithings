# score:allow pandas, pd.
"""Nautilus trial evaluator for SDCA walk-forward (#3174).

Fitness is Nautilus fills → ``dca_metrics``, never ``SdcaBacktestReport``.
pandas is used only at the BarDataWrangler boundary (same as
``nautilus_runner._prepare_bar_data``).
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from datetime import date, datetime, time, timezone
from pathlib import Path

import pandas as pd
import polars as pl
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarSpecification, BarType
from nautilus_trader.model.enums import AccountType, BarAggregation, OmsType, PriceType
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.dca_metrics import (
    breakdown_from_daily,
    daily_state_from_fills,
    fills_from_nautilus_report,
)
from digiquant.strategies.sdca.nautilus_strategy import SdcaStrategy, SdcaStrategyConfig
from digiquant.strategies.sdca.risk_index import build_risk_index, write_risk_index
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.walk_forward import SdcaTrialMetrics, max_drawdown_magnitude_pct

DEFAULT_TRIAL_CASH = 100_000.0


def _ohlcv_for_wrangler(dates: Sequence[date], prices: Sequence[float]) -> pd.DataFrame:
    """Polars OHLCV → pandas indexed by UTC timestamp (BarDataWrangler)."""
    stamps = [datetime.combine(d, time.min, tzinfo=timezone.utc) for d in dates]
    frame = pl.DataFrame(
        {
            "timestamp": stamps,
            "open": list(prices),
            "high": list(prices),
            "low": list(prices),
            "close": list(prices),
        }
    )
    pd_df = frame.select(["open", "high", "low", "close"]).to_pandas()
    pd_df.index = pd.to_datetime(frame["timestamp"].to_pandas(), utc=True)
    pd_df.index.name = "timestamp"
    pd_df["volume"] = 1.0
    return pd_df


def _metrics_from_fills(
    fills_report: object,
    dates: Sequence[date],
    prices: Sequence[float],
    risk: Sequence[float | None],
    initial_cash: float,
) -> SdcaTrialMetrics:
    fills = fills_from_nautilus_report(fills_report)
    bars = [(str(d), float(p)) for d, p in zip(dates, prices, strict=True)]
    state = daily_state_from_fills(fills, bars, initial_cash)
    dca = breakdown_from_daily(
        prices=state["prices"],
        portfolio_values=state["portfolio_values"],
        daily_trade_usd=state["daily_trade_usd"],
        net_deployed=state["net_deployed"],
        asset_units=state["asset_units"],
        risk=list(risk),
        rate=[None] * len(dates),
        initial_cash=initial_cash,
    )
    return SdcaTrialMetrics(
        vs_flat_dca_pct=dca.vs_flat_dca_pct,
        vs_lump_pct=dca.vs_lump_pct,
        capital_deployed_pct=dca.capital_deployed_pct,
        max_drawdown_pct=max_drawdown_magnitude_pct(state["portfolio_values"]),
    )


def evaluate_sdca_trial_nautilus(
    dates: Sequence[date],
    prices: Sequence[float],
    risk_model: RiskModel,
    shape: SdcaCurveShape,
    valuation_weight: float,
    *,
    initial_cash: float = DEFAULT_TRIAL_CASH,
) -> SdcaTrialMetrics:
    """Run one Nautilus ``BacktestEngine`` trial and return DCA-native metrics."""
    if len(dates) != len(prices) or not dates:
        raise ValueError("evaluate_sdca_trial_nautilus needs aligned non-empty dates/prices")
    date_s = pl.Series("date", list(dates), dtype=pl.Date)
    price_s = pl.Series("price", list(prices), dtype=pl.Float64)
    index = build_risk_index(date_s, price_s, risk_model, valuation_weight=valuation_weight)
    instrument = TestInstrumentProvider.btcusdt_binance()
    bar_type = BarType(instrument.id, BarSpecification(1, BarAggregation.DAY, PriceType.LAST))
    with tempfile.TemporaryDirectory(prefix="sdca-opt-") as tmp:
        risk_path = write_risk_index(index, Path(tmp) / "risk.parquet")
        strategy = SdcaStrategy(
            SdcaStrategyConfig(
                instrument_id=instrument.id,
                bar_type=bar_type,
                initial_cash=initial_cash,
                risk_path=str(risk_path),
                curve_nodes=shape.to_nodes(),
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
        wrangler = BarDataWrangler(bar_type=bar_type, instrument=instrument)
        engine.add_data(wrangler.process(_ohlcv_for_wrangler(dates, prices)))
        engine.add_strategy(strategy)
        engine.run()
        metrics = _metrics_from_fills(
            engine.trader.generate_fills_report(),
            dates,
            prices,
            index["risk"].to_list(),
            initial_cash,
        )
        engine.dispose()
    return metrics


__all__ = ["DEFAULT_TRIAL_CASH", "evaluate_sdca_trial_nautilus"]
