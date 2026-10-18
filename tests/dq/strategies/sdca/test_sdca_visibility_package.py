"""The SDCA "visibility package": staged-but-unweighted series, and ``btc_gold``.

Part 2 lets the tearsheet DRAW a series whose source is staged on disk while its
weight stays ``0.0``, without touching the composite risk column. Part 3 adds
the BTC/GLD ratio slot at weight ``0``.

Both are display-only by construction, and these tests pin the two legs of that:

* ``build_extra_indicators(..., include_display_only=True)`` materializes a
  weight-0 member **only** when its source pair is present (or it needs no
  source at all), and never for an ordinary modelling caller;
* ``compute_composite_risk`` filters ``weight != 0.0``, so the ``risk`` column
  is identical with or without those members, and ``write_risk_index`` persists
  only ``date``/``risk``.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca.chart_series import catalog_indicator_curves, z_from_risk_index
from digiquant.strategies.sdca.composite_risk import IndicatorWeight, compute_composite_risk
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    INDICATOR_DISPLAY_NAMES,
    MACRO_INDICATOR_NAMES,
    SOURCE_PAIR_BY_NAME,
    SOURCELESS_EXTRA_NAMES,
    WEIGHT_PARAM_BY_NAME,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    btc_gold_z,
    build_extra_indicators,
    composite_weights_from_params,
    parse_indicator_weights_json,
)
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    drop_extras_missing_sources,
    load_sdca_extra_sources,
)
from digiquant.strategies.sdca.risk_index import build_risk_index

pytestmark = pytest.mark.unit

_N = 420


def _daily(n: int = _N) -> pl.Series:
    start = date(2021, 1, 1)
    return pl.Series("date", [start + timedelta(days=i) for i in range(n)], dtype=pl.Date)


def _flat(dates: pl.Series, value: float = 100.0) -> pl.Series:
    return pl.Series("v", [value] * dates.len(), dtype=pl.Float64)


def _m2_sources(dates: pl.Series) -> ExtraIndicatorSources:
    return ExtraIndicatorSources(
        m2_dates=dates,
        m2_values=pl.Series("v", [1000.0 * (1.001**i) for i in range(dates.len())], dtype=pl.Float64),
    )


def _full_sources(dates: pl.Series) -> ExtraIndicatorSources:
    """Every ``ExtraIndicatorSources`` pair the loader can stage from CSVs."""
    values = pl.Series("v", [100.0] * dates.len(), dtype=pl.Float64)
    return ExtraIndicatorSources(
        m2_dates=dates,
        m2_values=values,
        dxy_dates=dates,
        dxy_values=values,
        uup_dates=dates,
        uup_close=values,
        gvz_dates=dates,
        gvz_values=values,
        walcl_dates=dates,
        walcl_values=values,
        hy_oas_dates=dates,
        hy_oas_values=values,
        ig_oas_dates=dates,
        ig_oas_values=values,
        breakeven_5y_dates=dates,
        breakeven_5y_values=values,
        nfci_dates=dates,
        nfci_values=values,
        gdx_dates=dates,
        gdx_close=values,
        slv_dates=dates,
        slv_close=values,
        gld_dates=dates,
        gld_close=values,
        real_rate_dates=dates,
        real_rate_values=values,
    )


class TestDisplayOnlyIsOptIn:
    def test_default_caller_still_omits_weight_zero_series(self) -> None:
        dates = _daily()
        price = _flat(dates)
        assert build_extra_indicators(dates, price, SdcaCompositeWeights(), _m2_sources(dates)) == []

    def test_display_only_materializes_the_staged_series_at_zero(self) -> None:
        dates = _daily()
        price = _flat(dates)
        shown = build_extra_indicators(
            dates,
            price,
            SdcaCompositeWeights(),
            _m2_sources(dates),
            include_display_only=True,
        )
        names = [extra.name for extra in shown]
        assert "m2" in names
        # The sourceless extras ride along; nothing else has a staged pair here.
        assert set(names) - SOURCELESS_EXTRA_NAMES == {"m2"}
        assert all(extra.weight == 0.0 for extra in shown)
        m2 = next(extra for extra in shown if extra.name == "m2")
        assert m2.z.null_count() < dates.len()

    def test_every_staged_pair_is_shown_and_every_absent_one_is_skipped(self) -> None:
        dates = _daily()
        price = _flat(dates)
        shown = build_extra_indicators(
            dates,
            price,
            SdcaCompositeWeights(),
            _full_sources(dates),
            include_display_only=True,
        )
        names = {extra.name for extra in shown}
        # Present pairs, including the four irregular prefixes.
        assert {"m2", "dxy", "uup", "gvz", "walcl", "hy_oas", "ig_oas"} <= names
        assert {"breakeven_5y", "nfci", "gdx_gld", "gld_slv", "btc_gold", "real_rate"} <= names
        # No source on this bag -> never materialized, never raised.
        assert {"rs_eth", "onchain_mvrv", "onchain_asopr", "onchain_puell"} & names == set()
        assert {"onchain_rhodl", "onchain_addr_ratio", "fear_greed"} & names == set()
        assert all(extra.weight == 0.0 for extra in shown)

    def test_sourceless_extras_are_always_staged(self) -> None:
        """The oscillators read the asset close, not a CSV -- and they are published.

        ``fast_crash_vol`` is sourceless too but research-only (absent from
        ``EXTRA_INDICATOR_NAMES``), so it has no display slot and is skipped.
        """
        assert {"weekly_rsi", "weekly_macd", "sma_band"} <= SOURCELESS_EXTRA_NAMES
        assert "fast_crash_vol" not in EXTRA_INDICATOR_NAMES
        dates = _daily()
        shown = build_extra_indicators(
            dates,
            _flat(dates),
            SdcaCompositeWeights(),
            ExtraIndicatorSources(),
            include_display_only=True,
        )
        assert [extra.name for extra in shown] == ["weekly_rsi", "weekly_macd", "sma_band"]

    def test_a_half_present_pair_is_not_staged(self) -> None:
        dates = _daily()
        half = ExtraIndicatorSources(m2_dates=dates, m2_values=None)
        shown = build_extra_indicators(
            dates,
            _flat(dates),
            SdcaCompositeWeights(),
            half,
            include_display_only=True,
        )
        assert "m2" not in {extra.name for extra in shown}

    def test_positive_weight_without_a_source_still_raises(self) -> None:
        """The widening must not soften the real-weight path."""
        dates = _daily()
        weights = SdcaCompositeWeights(valuation=1.0, gvz=0.5)
        with pytest.raises(ValueError, match="gvz"):
            build_extra_indicators(
                dates, _flat(dates), weights, ExtraIndicatorSources(), include_display_only=True
            )


class TestDisplayOnlyHonoursTheAllowlist:
    def test_unlisted_staged_names_are_dropped_not_raised(self) -> None:
        dates = _daily()
        shown = build_extra_indicators(
            dates,
            _flat(dates),
            SdcaCompositeWeights(),
            _full_sources(dates),
            allowlist=("m2", "weekly_rsi"),
            include_display_only=True,
        )
        assert {extra.name for extra in shown} == {"m2", "weekly_rsi"}

    def test_an_unlisted_positive_weight_still_raises(self) -> None:
        dates = _daily()
        weights = SdcaCompositeWeights(valuation=1.0, m2=0.5)
        with pytest.raises(ValueError, match="allowlist"):
            build_extra_indicators(
                dates, _flat(dates), weights, _m2_sources(dates), allowlist=("dxy",)
            )


class TestRiskIsUnchanged:
    """The whole point: more columns, identical risk."""

    def _composite(self, dates: pl.Series, extras: list[IndicatorWeight]) -> pl.DataFrame:
        valuation = IndicatorWeight(
            name="valuation",
            z=pl.Series("z", [0.5] * dates.len(), dtype=pl.Float64),
            weight=1.0,
        )
        return compute_composite_risk([valuation, *extras])

    def test_composite_risk_is_identical_with_and_without_display_only(self) -> None:
        dates = _daily()
        price = pl.Series("p", [100.0 + 0.3 * i for i in range(dates.len())], dtype=pl.Float64)
        weights = SdcaCompositeWeights()
        narrow = build_extra_indicators(dates, price, weights, _full_sources(dates))
        wide = build_extra_indicators(
            dates, price, weights, _full_sources(dates), include_display_only=True
        )
        assert narrow == []
        assert len(wide) > 5

        base = self._composite(dates, narrow)
        widened = self._composite(dates, wide)
        assert base.equals(widened)
        assert base["risk"].null_count() == 0

    def test_a_weight_zero_member_cannot_null_the_day(self) -> None:
        """``0 x null`` is excluded by the weight filter, not merely multiplied away."""
        dates = _daily()
        all_null = pl.Series("z", [None] * dates.len(), dtype=pl.Float64)
        extras = [IndicatorWeight(name="m2", z=all_null, weight=0.0)]
        composite = self._composite(dates, extras)
        assert composite["risk"].null_count() == 0


class _FlatRails:
    """Duck-typed ``RiskModel``: constant rails, so ``build_risk_index`` needs no fit."""

    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = dates.len()
        return pl.DataFrame(
            {
                "low": [50.0] * n,
                "median": [100.0] * n,
                "high": [200.0] * n,
            }
        )


class TestTheCurveIsActuallyDrawn:
    def test_staged_weight_zero_series_yields_points(self) -> None:
        dates = _daily(60)
        z = [0.25] * dates.len()
        curves = catalog_indicator_curves(
            dates=[day.isoformat() for day in dates.to_list()],
            z_by_name={"valuation": z, "m2": z, "btc_gold": z},
            weights=SdcaCompositeWeights(valuation=1.0),
        )
        by_name = {curve.name: curve for curve in curves}
        assert by_name["m2"].points, "a staged weight-0 series must reach the chart"
        assert by_name["m2"].in_index is False
        assert by_name["m2"].weight == 0.0
        assert by_name["btc_gold"].points
        # Control: a name with no z column still renders an empty (layout-only) curve.
        assert by_name["dxy"].points == []

    def test_mutation_control_an_absent_z_is_empty(self) -> None:
        """The previous test can fail: without the z map there are no points."""
        dates = _daily(20)
        curves = catalog_indicator_curves(
            dates=[day.isoformat() for day in dates.to_list()],
            z_by_name={},
            weights=SdcaCompositeWeights(valuation=1.0),
        )
        assert all(curve.points == [] for curve in curves)

    def test_the_widening_is_what_puts_the_series_on_the_chart(self) -> None:
        """End-to-end: flag OFF leaves the curve empty, flag ON draws it.

        This is the node that pins the *widening* rather than the chart layer:
        making ``include_display_only`` a no-op empties the curve again, so the
        user-visible outcome cannot pass on a reverted implementation.
        """
        dates = _daily()
        price = _flat(dates)
        sources = _m2_sources(dates)
        weights = SdcaCompositeWeights(valuation=1.0)

        def m2_points(include_display_only: bool) -> int:
            extras = build_extra_indicators(
                dates,
                price,
                weights,
                sources,
                include_display_only=include_display_only,
            )
            index = build_risk_index(
                dates, price, _FlatRails(), extra_indicators=extras or None
            )
            curves = catalog_indicator_curves(
                dates=[day.isoformat() for day in dates.to_list()],
                z_by_name=z_from_risk_index(index),
                weights=weights,
            )
            return {curve.name: len(curve.points) for curve in curves}["m2"]

        assert m2_points(False) == 0, "the ordinary modelling path must not stage a weight-0 name"
        assert m2_points(True) > 0, "a staged weight-0 series must reach the chart"


class TestBtcGoldSlot:
    def test_registered_in_every_catalogue_site(self) -> None:
        assert "btc_gold" in MACRO_INDICATOR_NAMES
        assert "btc_gold" in EXTRA_INDICATOR_NAMES
        assert WEIGHT_PARAM_BY_NAME["btc_gold"] == "btc_gold_weight"
        assert INDICATOR_DISPLAY_NAMES["btc_gold"] == "BTC/gold ratio"
        assert SOURCE_PAIR_BY_NAME["btc_gold"] == ("gld_dates", "gld_close")
        assert set(SdcaCompositeWeights.model_fields) == set(WEIGHT_PARAM_BY_NAME)

    def test_defaults_are_zero_everywhere(self) -> None:
        assert SdcaCompositeWeights().btc_gold == 0.0
        assert SdcaCompositeWeights().enabled_extras() == {}
        assert composite_weights_from_params({}).btc_gold == 0.0
        assert parse_indicator_weights_json("{}").btc_gold == 0.0
        assert SDCA_SHAPE_DEFAULTS["btc_gold_weight"] == 0.0

    def test_param_readers_carry_the_value(self) -> None:
        assert composite_weights_from_params({"btc_gold_weight": 0.25}).btc_gold == 0.25
        assert parse_indicator_weights_json('{"btc_gold": 0.4}').btc_gold == 0.4

    def test_a_positive_weight_needs_the_gld_pair(self) -> None:
        dates = _daily()
        weights = SdcaCompositeWeights(valuation=1.0, btc_gold=0.5)
        with pytest.raises(ValueError, match="btc_gold"):
            build_extra_indicators(dates, _flat(dates), weights, ExtraIndicatorSources())

    def test_the_ratio_reads_gld_not_the_asset_leg(self) -> None:
        dates = _daily(320)
        btc = pl.Series("p", [100.0 * (1.004**i) for i in range(320)], dtype=pl.Float64)
        gld = _flat(dates)
        z = btc_gold_z(dates, btc, dates, gld, window=40, min_samples=20)
        assert z[-1] > 1.0
        # The inverse: BTC falling against a flat gold leg votes negative.
        falling = pl.Series("p", [100.0 * (0.996**i) for i in range(320)], dtype=pl.Float64)
        assert btc_gold_z(dates, falling, dates, gld, window=40, min_samples=20)[-1] < -1.0

    def test_drop_extras_zeroes_btc_gold_without_a_source(self) -> None:
        raw = SdcaCompositeWeights(valuation=1.0, btc_gold=0.5)
        assert drop_extras_missing_sources(raw, ExtraIndicatorSources()).btc_gold == 0.0

    def test_loader_reads_the_gld_csv(self, tmp_path: Path) -> None:
        (tmp_path / "GLD-USD.csv").write_text(
            "timestamp,open,high,low,close,volume,symbol\n"
            "2024-01-02,180,181,179,180.5,1000,GLD-USD\n"
            "2024-01-03,180.5,181.5,180,181.0,1100,GLD-USD\n",
            encoding="utf-8",
        )
        sources = load_sdca_extra_sources(tmp_path)
        assert sources.gld_dates is not None and len(sources.gld_dates) == 2
        assert sources.gld_close is not None and len(sources.gld_close) == 2

    def test_btc_gold_is_not_a_gold_asset_leg(self) -> None:
        """For a gold asset the ``btc_price`` leg IS GLD, so the ratio degenerates."""
        from digiquant.strategies.sdca.indicator_catalog import GOLD_MACRO_NAMES

        assert "btc_gold" not in GOLD_MACRO_NAMES


def test_checked_in_blocks_are_json_serialisable() -> None:
    """Every new name round-trips through the sidecar shape the tearsheet reads."""
    payload = json.loads(json.dumps(SdcaCompositeWeights(valuation=1.0).model_dump()))
    assert payload["btc_gold"] == 0.0
