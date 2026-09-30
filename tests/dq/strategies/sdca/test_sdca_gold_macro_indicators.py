"""Gold macro legs: model fields, maps, and guards (#4804)."""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca.indicator_catalog import (
    MACRO_INDICATOR_NAMES,
    WEIGHT_PARAM_BY_NAME,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    breakeven_5y_z,
    build_extra_indicators,
    composite_weights_from_params,
    extra_z_vectors,
    gvz_z,
    hy_oas_z,
    indicator_display_name,
    walcl_liquidity_z,
)
from digiquant.strategies.sdca.optimize import (
    drop_extras_missing_sources,
    load_sdca_extra_sources,
)

pytestmark = pytest.mark.unit

NEW_MACRO = ("gvz", "walcl", "hy_oas", "ig_oas", "breakeven_5y", "nfci")


def test_new_macro_weights_default_zero() -> None:
    w = SdcaCompositeWeights()
    for name in NEW_MACRO:
        assert getattr(w, name) == 0.0
    assert w.enabled_extras() == {}


def test_new_macro_names_in_macro_tuple_and_param_map() -> None:
    for name in NEW_MACRO:
        assert name in MACRO_INDICATOR_NAMES
        assert WEIGHT_PARAM_BY_NAME[name] == f"{name}_weight"
    assert indicator_display_name("gvz") == "gold volatility (GVZ)"
    assert indicator_display_name("breakeven_5y") == "5Y breakeven"


def test_composite_weights_from_params_reads_new_legs() -> None:
    w = composite_weights_from_params({"gvz_weight": 0.5, "nfci_weight": 0.25})
    assert w.gvz == 0.5
    assert w.nfci == 0.25
    assert w.walcl == 0.0


def test_empty_sources_carry_no_new_series() -> None:
    sources = ExtraIndicatorSources()
    for name in NEW_MACRO:
        assert getattr(sources, f"{name}_dates") is None
        assert getattr(sources, f"{name}_values") is None


def _daily(n: int) -> pl.Series:
    start = date(2020, 1, 1)
    return pl.Series("date", [start + timedelta(days=i) for i in range(n)], dtype=pl.Date)


def test_gvz_rising_level_votes_positive() -> None:
    dates = _daily(300)
    src = pl.Series("v", [10.0 + 0.05 * i for i in range(300)], dtype=pl.Float64)
    z = gvz_z(dates, dates, src, window=30, min_samples=10)
    assert z[-1] > 1.0


def test_walcl_accelerating_growth_votes_positive() -> None:
    dates = _daily(500)
    src = pl.Series("v", [math.exp(2e-6 * i * i) for i in range(500)], dtype=pl.Float64)
    z = walcl_liquidity_z(dates, dates, src, window=30, min_samples=10)
    assert z[-1] > 0.0


def test_spread_and_breakeven_levels_vote_positive_when_rising() -> None:
    dates = _daily(300)
    src = pl.Series("v", [1.0 + 0.01 * i for i in range(300)], dtype=pl.Float64)
    assert hy_oas_z(dates, dates, src, window=30, min_samples=10)[-1] > 1.0
    assert breakeven_5y_z(dates, dates, src, window=30, min_samples=10)[-1] > 1.0


def test_positive_weight_without_source_raises() -> None:
    dates = _daily(300)
    price = pl.Series("p", [100.0] * 300, dtype=pl.Float64)
    weights = SdcaCompositeWeights(valuation=1.0, gvz=0.5)
    with pytest.raises(ValueError, match="gvz"):
        build_extra_indicators(dates, price, weights, ExtraIndicatorSources())


def test_drop_extras_zeroes_new_legs_without_sources() -> None:
    weights = SdcaCompositeWeights(
        valuation=1.0,
        gvz=0.5,
        walcl=0.5,
        hy_oas=0.25,
        ig_oas=0.25,
        breakeven_5y=0.25,
        nfci=0.25,
    )
    dropped = drop_extras_missing_sources(weights, ExtraIndicatorSources())
    assert dropped.valuation == 1.0
    for name in NEW_MACRO:
        assert getattr(dropped, name) == 0.0


def test_loader_picks_up_new_sibling_csvs(tmp_path: Path) -> None:
    root = tmp_path
    (root / "GVZCLS.csv").write_text(
        "observation_date,GVZCLS\n2024-01-02,18.5\n2024-01-03,19.0\n", encoding="utf-8"
    )
    sources = load_sdca_extra_sources(root)
    assert sources.gvz_dates is not None and len(sources.gvz_dates) == 2
    assert sources.m2_dates is None and sources.dxy_dates is None


def test_btc_vectors_unchanged_without_new_weights() -> None:
    dates = _daily(400)
    price = pl.Series("p", [100.0 + 0.1 * i for i in range(400)], dtype=pl.Float64)
    sources = ExtraIndicatorSources()
    before = extra_z_vectors(dates, price, SdcaCompositeWeights(valuation=1.0, m2=0.0), sources)
    after = extra_z_vectors(dates, price, SdcaCompositeWeights(valuation=1.0, m2=0.0), sources)
    assert before == after
    assert all(k not in before for k in NEW_MACRO)
