"""Gold price-family ratio legs: model fields, maps, and guards (#4804)."""

from __future__ import annotations

import pytest
from digiquant.strategies.sdca.indicator_catalog import (
    GOLD_MACRO_NAMES,
    MACRO_INDICATOR_NAMES,
    WEIGHT_PARAM_BY_NAME,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    composite_weights_from_params,
    indicator_display_name,
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


def test_empty_sources_carry_no_ratio_series() -> None:
    sources = ExtraIndicatorSources()
    assert sources.gdx_dates is None and sources.gdx_close is None
    assert sources.slv_dates is None and sources.slv_close is None
