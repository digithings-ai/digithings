"""Gold price-family ratio legs: model fields, maps, and guards (#4804)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca.indicator_catalog import (
    GOLD_MACRO_NAMES,
    MACRO_INDICATOR_NAMES,
    WEIGHT_PARAM_BY_NAME,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    build_extra_indicators,
    composite_weights_from_params,
    extra_z_vectors,
    gdx_gld_z,
    gld_slv_z,
    indicator_display_name,
    parse_indicator_weights_json,
)
from digiquant.strategies.sdca.optimize import (
    drop_extras_missing_sources,
    load_sdca_extra_sources,
)

pytestmark = pytest.mark.unit

NEW_RATIOS = ("gdx_gld", "gld_slv")


def test_new_ratio_weights_default_zero() -> None:
    w = SdcaCompositeWeights()
    assert w.gdx_gld == 0.0
    assert w.gld_slv == 0.0
    assert w.enabled_extras() == {}


def test_new_ratio_names_in_tuples_and_param_map() -> None:
    for name in NEW_RATIOS:
        assert name in MACRO_INDICATOR_NAMES
        assert name in GOLD_MACRO_NAMES
        assert WEIGHT_PARAM_BY_NAME[name] == f"{name}_weight"
    assert indicator_display_name("gdx_gld") == "GDX/GLD participation"
    assert indicator_display_name("gld_slv") == "gold/silver ratio"


def test_composite_weights_from_params_reads_new_ratios() -> None:
    w = composite_weights_from_params({"gdx_gld_weight": 0.5, "gld_slv_weight": 0.25})
    assert w.gdx_gld == 0.5
    assert w.gld_slv == 0.25
    assert w.gvz == 0.0


def test_parse_indicator_weights_json_reads_new_ratios() -> None:
    w = parse_indicator_weights_json('{"gdx_gld": 0.5, "gld_slv": 0.25}')
    assert w.gdx_gld == 0.5
    assert w.gld_slv == 0.25
    assert w.gvz == 0.0


def test_empty_sources_carry_no_ratio_series() -> None:
    sources = ExtraIndicatorSources()
    assert sources.gdx_dates is None and sources.gdx_close is None
    assert sources.slv_dates is None and sources.slv_close is None


def _daily(n: int) -> pl.Series:
    start = date(2020, 1, 1)
    return pl.Series("date", [start + timedelta(days=i) for i in range(n)], dtype=pl.Date)


def test_gdx_ripping_vs_flat_gld_votes_positive() -> None:
    dates = _daily(300)
    gld = pl.Series("p", [100.0] * 300, dtype=pl.Float64)
    gdx = pl.Series("v", [20.0 * (1.002**i) for i in range(300)], dtype=pl.Float64)
    z = gdx_gld_z(dates, gld, dates, gdx, window=30, min_samples=10)
    assert z[-1] > 1.0


def test_slv_crashing_vs_flat_gld_votes_positive() -> None:
    dates = _daily(300)
    gld = pl.Series("p", [100.0] * 300, dtype=pl.Float64)
    slv = pl.Series("v", [25.0 * (0.998**i) for i in range(300)], dtype=pl.Float64)
    z = gld_slv_z(dates, gld, dates, slv, window=30, min_samples=10)
    assert z[-1] > 1.0


def test_positive_ratio_weight_without_source_raises() -> None:
    dates = _daily(300)
    price = pl.Series("p", [100.0] * 300, dtype=pl.Float64)
    weights = SdcaCompositeWeights(valuation=1.0, gdx_gld=0.5)
    with pytest.raises(ValueError, match="gdx_gld"):
        build_extra_indicators(dates, price, weights, ExtraIndicatorSources())


def test_drop_extras_zeroes_ratios_without_sources() -> None:
    weights = SdcaCompositeWeights(valuation=1.0, gdx_gld=0.5, gld_slv=0.5)
    dropped = drop_extras_missing_sources(weights, ExtraIndicatorSources())
    assert dropped.valuation == 1.0
    assert dropped.gdx_gld == 0.0
    assert dropped.gld_slv == 0.0


def test_loader_picks_up_ratio_sibling_csvs(tmp_path: Path) -> None:
    (tmp_path / "GDX-USD.csv").write_text(
        "timestamp,open,high,low,close,volume,symbol\n"
        "2024-01-02,40,41,39,40.5,1000,GDX-USD\n"
        "2024-01-03,40.5,41.5,40,41.0,1100,GDX-USD\n",
        encoding="utf-8",
    )
    (tmp_path / "SLV.csv").write_text(
        "timestamp,open,high,low,close,volume,symbol\n"
        "2024-01-02,25,25.5,24.5,25.2,2000,SLV\n"
        "2024-01-03,25.2,25.8,25,25.6,2100,SLV\n",
        encoding="utf-8",
    )
    sources = load_sdca_extra_sources(tmp_path)
    assert sources.gdx_dates is not None and len(sources.gdx_dates) == 2
    assert sources.gdx_close is not None and len(sources.gdx_close) == 2
    assert sources.slv_dates is not None and len(sources.slv_dates) == 2
    assert sources.slv_close is not None and len(sources.slv_close) == 2


def test_btc_vectors_ignore_ratio_files_on_disk(tmp_path: Path) -> None:
    (tmp_path / "GDX-USD.csv").write_text(
        "timestamp,open,high,low,close,volume,symbol\n2024-01-02,40,41,39,40.5,1000,GDX-USD\n",
        encoding="utf-8",
    )
    sources = load_sdca_extra_sources(tmp_path)
    dates = _daily(400)
    price = pl.Series("p", [100.0 + 0.1 * i for i in range(400)], dtype=pl.Float64)
    vectors = extra_z_vectors(dates, price, SdcaCompositeWeights(valuation=1.0), sources)
    assert "gdx_gld" not in vectors and "gld_slv" not in vectors
