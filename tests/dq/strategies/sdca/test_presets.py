"""Tests for SDCA public strategy-personality presets (#1081)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

EXPECTED_PRESET_NAMES = {
    "conservative_hold",
    "balanced",
    "aggressive_accumulate",
    "accumulate_and_distribute",
}


class TestPresets:
    def test_list_presets_matches_documented_names(self) -> None:
        from digiquant.strategies.sdca.presets import list_presets

        assert set(list_presets()) == EXPECTED_PRESET_NAMES

    def test_load_preset_returns_21_curve_nodes(self) -> None:
        from digiquant.strategies.sdca.presets import list_presets, load_preset

        for name in list_presets():
            preset = load_preset(name)
            assert len(preset.curve_nodes) == 21
            assert isinstance(preset.long_only, bool)
            assert preset.description

    def test_load_unknown_preset_raises(self) -> None:
        from digiquant.strategies.sdca.presets import load_preset

        with pytest.raises(ValueError, match="Unknown preset"):
            load_preset("not_a_real_preset")

    def test_long_only_preset_never_sells(self) -> None:
        """A long_only preset's curve must never go negative, or the flag is redundant/misleading."""
        from digiquant.strategies.sdca.presets import list_presets, load_preset

        long_only_presets = [load_preset(n) for n in list_presets() if load_preset(n).long_only]
        assert long_only_presets, "expected at least one long-only preset"
        for preset in long_only_presets:
            assert all(node >= 0 for node in preset.curve_nodes)

    def test_distribution_preset_has_signed_curve(self) -> None:
        """At least one non-long-only preset must actually sell at high risk."""
        from digiquant.strategies.sdca.presets import list_presets, load_preset

        distribution_presets = [
            load_preset(n) for n in list_presets() if not load_preset(n).long_only
        ]
        assert distribution_presets, "expected at least one distribution preset"
        assert any(any(node < 0 for node in p.curve_nodes) for p in distribution_presets)


class TestSdcaPresetModel:
    """Validation rules on the SdcaPreset model itself (#1081 CodeRabbit review)."""

    def test_rejects_wrong_node_count(self) -> None:
        from digiquant.strategies.sdca.presets import SdcaPreset

        with pytest.raises(ValueError, match="21"):
            SdcaPreset(curve_nodes=(1.0, 2.0), long_only=False, description="x")

    def test_rejects_negative_node_when_long_only(self) -> None:
        from digiquant.strategies.sdca.presets import SdcaPreset

        nodes = tuple(-1.0 if i == 0 else 0.0 for i in range(21))
        with pytest.raises(ValueError, match="long_only"):
            SdcaPreset(curve_nodes=nodes, long_only=True, description="x")

    def test_is_frozen(self) -> None:
        from digiquant.strategies.sdca.presets import SdcaPreset

        preset = SdcaPreset(
            curve_nodes=tuple(0.0 for _ in range(21)), long_only=True, description="x"
        )
        with pytest.raises(ValueError):
            preset.long_only = False
