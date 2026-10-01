"""Real-rate leg: DFII10 washout z, model, maps, sign, guards (#4804)."""

from __future__ import annotations

import inspect
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
    indicator_display_name,
    parse_indicator_weights_json,
    real_rate_z,
    uup_z,
)
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    drop_extras_missing_sources,
    load_sdca_extra_sources,
)

pytestmark = pytest.mark.unit


def test_real_rate_defaults_zero_and_mapped() -> None:
    w = SdcaCompositeWeights()
    assert w.real_rate == 0.0
    assert w.enabled_extras() == {}
    assert "real_rate" in MACRO_INDICATOR_NAMES
    assert "real_rate" in GOLD_MACRO_NAMES
    assert WEIGHT_PARAM_BY_NAME["real_rate"] == "real_rate_weight"
    assert indicator_display_name("real_rate") == "real yield (DFII10)"
    assert composite_weights_from_params({"real_rate_weight": 0.5}).real_rate == 0.5
    assert parse_indicator_weights_json('{"real_rate": 0.5}').real_rate == 0.5


def test_real_rate_default_window_is_1260() -> None:
    assert inspect.signature(real_rate_z).parameters["window"].default == 1260


def _daily(n: int) -> pl.Series:
    start = date(2020, 1, 1)
    return pl.Series("date", [start + timedelta(days=i) for i in range(n)], dtype=pl.Date)


def test_high_real_yield_votes_positive_cheap_at_default_window() -> None:
    dates = _daily(1400)
    yields = pl.Series("v", [1.0 + 0.002 * i for i in range(1400)], dtype=pl.Float64)
    z = real_rate_z(dates, dates, yields)
    assert z[-1] > 1.0


def test_cratered_real_yield_votes_negative_rich_no_flip() -> None:
    dates = _daily(1400)
    rising = pl.Series("v", [1.0 + 0.002 * i for i in range(1400)], dtype=pl.Float64)
    falling = pl.Series("v", [4.0 - 0.002 * i for i in range(1400)], dtype=pl.Float64)
    # Washout semantics: cratered yields = crowded fear-bid = rich (negative z).
    assert real_rate_z(dates, dates, falling)[-1] < -1.0
    # No-flip SIGN proof: the same rising series is +z here but −z under the
    # uup-style headwind flip — real_rate must NOT be flipped like uup.
    assert real_rate_z(dates, dates, rising)[-1] > 1.0
    assert uup_z(dates, dates, rising)[-1] < -1.0


def test_positive_real_rate_weight_without_source_raises() -> None:
    dates = _daily(300)
    price = pl.Series("p", [100.0] * 300, dtype=pl.Float64)
    with pytest.raises(ValueError, match="real_rate"):
        build_extra_indicators(
            dates,
            price,
            SdcaCompositeWeights(valuation=1.0, real_rate=0.5),
            ExtraIndicatorSources(),
        )


def test_drop_extras_zeroes_real_rate_without_source() -> None:
    dropped = drop_extras_missing_sources(
        SdcaCompositeWeights(valuation=1.0, real_rate=0.5), ExtraIndicatorSources()
    )
    assert dropped.real_rate == 0.0 and dropped.valuation == 1.0


def test_loader_picks_up_dfii10_csv(tmp_path: Path) -> None:
    (tmp_path / "DFII10.csv").write_text(
        "observation_date,DFII10\n2024-01-02,1.85\n2024-01-03,1.87\n",
        encoding="utf-8",
    )
    sources = load_sdca_extra_sources(tmp_path)
    assert sources.real_rate_dates is not None and len(sources.real_rate_dates) == 2


def test_btc_and_gold_published_paths_stay_inert() -> None:
    assert SDCA_SHAPE_DEFAULTS["real_rate_weight"] == 0.0
    dates = _daily(400)
    price = pl.Series("p", [100.0 + 0.1 * i for i in range(400)], dtype=pl.Float64)
    vectors = extra_z_vectors(
        dates, price, SdcaCompositeWeights(valuation=1.0), ExtraIndicatorSources()
    )
    assert "real_rate" not in vectors
