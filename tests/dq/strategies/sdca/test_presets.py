"""Tests for SDCA public strategy-personality presets (#1081)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestPresets:
    def test_list_presets_has_at_least_three(self) -> None:
        from digiquant.strategies.sdca.presets import list_presets

        names = list_presets()
        assert len(names) >= 3

    def test_load_preset_returns_21_curve_nodes(self) -> None:
        from digiquant.strategies.sdca.presets import list_presets, load_preset

        for name in list_presets():
            preset = load_preset(name)
            assert len(preset["curve_nodes"]) == 21
            assert isinstance(preset["long_only"], bool)
            assert preset["description"]

    def test_load_unknown_preset_raises(self) -> None:
        from digiquant.strategies.sdca.presets import load_preset

        with pytest.raises(ValueError, match="Unknown preset"):
            load_preset("not_a_real_preset")

    def test_long_only_preset_never_sells(self) -> None:
        """A long_only preset's curve must never go negative, or the flag is redundant/misleading."""
        from digiquant.strategies.sdca.presets import list_presets, load_preset

        long_only_presets = [load_preset(n) for n in list_presets() if load_preset(n)["long_only"]]
        assert long_only_presets, "expected at least one long-only preset"
        for preset in long_only_presets:
            assert all(node >= 0 for node in preset["curve_nodes"])

    def test_distribution_preset_has_signed_curve(self) -> None:
        """At least one non-long-only preset must actually sell at high risk."""
        from digiquant.strategies.sdca.presets import list_presets, load_preset

        distribution_presets = [
            load_preset(n) for n in list_presets() if not load_preset(n)["long_only"]
        ]
        assert distribution_presets, "expected at least one distribution preset"
        assert any(any(node < 0 for node in p["curve_nodes"]) for p in distribution_presets)
