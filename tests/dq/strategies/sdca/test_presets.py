"""Tests for SDCA public strategy-personality presets (#1081)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

EXPECTED_PRESET_NAMES = {
    "conservative_hold",
    "balanced",
    "aggressive_accumulate",
    "accumulate_and_distribute",
    "btc_optimized",
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


class TestPresetShapeAuthoring:
    def test_every_preset_has_a_shape_and_generated_nodes(self) -> None:
        from digiquant.strategies.sdca.curve import AccumDistCurve
        from digiquant.strategies.sdca.presets import list_presets, load_preset

        for name in list_presets():
            preset = load_preset(name)
            assert preset.shape is not None
            assert preset.curve_nodes == preset.shape.to_nodes()
            AccumDistCurve(preset.curve_nodes)

    def test_hand_authored_node_diff_is_documented(self) -> None:
        """Pin the node-by-node diff vs. the pre-#3169 hand-authored lists.

        The shape cannot reproduce a plateau-then-decay (curvature >= 1 has
        no flat region at the extreme). Documented in the #3169 PR body.
        """
        from digiquant.strategies.sdca.presets import load_preset

        previous = {
            "conservative_hold": (
                3.0,
                3.0,
                3.0,
                2.5,
                2.0,
                1.5,
                1.0,
                0.5,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            ),
            "balanced": (
                8.0,
                8.0,
                7.0,
                6.0,
                5.0,
                3.5,
                2.0,
                1.0,
                0.3,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            ),
            "aggressive_accumulate": (
                15.0,
                15.0,
                14.0,
                13.0,
                11.0,
                9.0,
                7.0,
                5.0,
                3.0,
                1.5,
                0.5,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            ),
            "accumulate_and_distribute": (
                10.0,
                10.0,
                10.0,
                10.0,
                6.5,
                4.0,
                1.2,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                -0.5,
                -1.5,
                -3.0,
                -10.0,
            ),
        }
        diffs: dict[str, list[tuple[float, float, float]]] = {}
        for name, old in previous.items():
            new = load_preset(name).curve_nodes
            diffs[name] = [
                (old[i], new[i], new[i] - old[i]) for i in range(21) if abs(new[i] - old[i]) > 1e-9
            ]
        # The shape is a different authoring surface — diffs are expected and
        # must stay non-empty so a silent exact-match rewrite is noticed.
        assert all(diffs[name] for name in previous)


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
