"""Unit tests for the canonical strategy alias map (#1185)."""

from __future__ import annotations

import pytest
from digiquant.strategy_aliases import (
    STRATEGY_ALIASES,
    aliases_for,
    resolve_param_spec_name,
    resolve_strategy_name,
)


@pytest.mark.unit
class TestStrategyAliases:
    def test_registry_canonical(self) -> None:
        assert resolve_strategy_name("ema") == "ema_cross"
        assert resolve_strategy_name("sdca") == "btc_sdca"
        assert resolve_strategy_name("btc_sdca") == "btc_sdca"

    def test_param_spec_key_differs_for_sdca(self) -> None:
        assert resolve_param_spec_name("btc_sdca") == "sdca"
        assert resolve_param_spec_name("sdca") == "sdca"
        assert resolve_param_spec_name("ema") == "ema_cross"

    def test_aliases_for_lists_static(self) -> None:
        assert "momentum_tech" in aliases_for("ema_cross")
        assert "ema" in aliases_for("ema_cross")

    def test_no_alias_points_at_itself(self) -> None:
        for alias, canonical in STRATEGY_ALIASES.items():
            assert alias != canonical
