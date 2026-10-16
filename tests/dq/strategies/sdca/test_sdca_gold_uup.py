"""UUP dollar-proxy leg: model, maps, sign, guards (#4804)."""

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
    indicator_display_name,
    uup_z,
)
from digiquant.strategies.sdca.optimize import (
    drop_extras_missing_sources,
    load_sdca_extra_sources,
)

pytestmark = pytest.mark.unit


def test_uup_defaults_zero_and_mapped() -> None:
    w = SdcaCompositeWeights()
    assert w.uup == 0.0
    assert "uup" in MACRO_INDICATOR_NAMES
    assert "uup" in GOLD_MACRO_NAMES
    assert WEIGHT_PARAM_BY_NAME["uup"] == "uup_weight"
    assert indicator_display_name("uup") == "dollar proxy (UUP)"
    assert composite_weights_from_params({"uup_weight": 0.5}).uup == 0.5


def _daily(n: int) -> pl.Series:
    start = date(2020, 1, 1)
    return pl.Series("date", [start + timedelta(days=i) for i in range(n)], dtype=pl.Date)


def test_uup_ripping_vs_flat_gld_votes_negative() -> None:
    dates = _daily(300)
    uup = pl.Series("v", [20.0 * (1.002**i) for i in range(300)], dtype=pl.Float64)
    z = uup_z(dates, dates, uup, window=30, min_samples=10)
    assert z[-1] < -1.0


def test_positive_uup_weight_without_source_raises() -> None:
    dates = _daily(300)
    price = pl.Series("p", [100.0] * 300, dtype=pl.Float64)
    with pytest.raises(ValueError, match="uup"):
        build_extra_indicators(
            dates, price, SdcaCompositeWeights(valuation=1.0, uup=0.5), ExtraIndicatorSources()
        )


def test_drop_extras_zeroes_uup_without_source() -> None:
    dropped = drop_extras_missing_sources(
        SdcaCompositeWeights(valuation=1.0, uup=0.5), ExtraIndicatorSources()
    )
    assert dropped.uup == 0.0 and dropped.valuation == 1.0


def test_loader_picks_up_uup_csv(tmp_path: Path) -> None:
    (tmp_path / "UUP.csv").write_text(
        "timestamp,open,high,low,close,volume,symbol\n"
        "2024-01-02,28,28.1,27.9,28.05,1000,UUP\n"
        "2024-01-03,28.05,28.2,28,28.1,1100,UUP\n",
        encoding="utf-8",
    )
    sources = load_sdca_extra_sources(tmp_path)
    assert sources.uup_dates is not None and len(sources.uup_dates) == 2
