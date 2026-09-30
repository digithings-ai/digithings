"""Gold macro legs: model fields, maps, and guards (#4804)."""

from __future__ import annotations

import pytest
from digiquant.strategies.sdca.indicator_catalog import (
    MACRO_INDICATOR_NAMES,
    WEIGHT_PARAM_BY_NAME,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    composite_weights_from_params,
    indicator_display_name,
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
