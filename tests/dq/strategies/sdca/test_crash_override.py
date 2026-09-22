"""Tests for the independent fast-crash circuit-breaker (crash_override.py)."""

from __future__ import annotations

import polars as pl
import pytest
from digiquant.strategies.sdca.crash_override import apply_crash_override

pytestmark = pytest.mark.unit


class TestApplyCrashOverride:
    def test_no_op_when_fast_crash_z_stays_above_trigger(self) -> None:
        risk = [50.0, 40.0, 60.0]
        fast_crash_z = [0.0, -1.0, -1.9]  # all above trigger_z=-2.0
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=95.0)
        assert out == pytest.approx(risk)

    def test_full_override_well_below_trigger_minus_ramp(self) -> None:
        risk = [50.0]
        fast_crash_z = [-10.0]  # well below trigger_z - ramp_z = -3.0
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=95.0)
        assert out[0] == pytest.approx(95.0)

    def test_full_override_at_or_below_lower_boundary(self) -> None:
        risk = [50.0]
        fast_crash_z = [-3.0]  # exactly trigger_z - ramp_z
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=95.0)
        assert out[0] == pytest.approx(95.0)

    def test_monotonic_ramp_in_transition_band(self) -> None:
        risk = [50.0] * 5
        # z sweeps from just above trigger_z down through the ramp band.
        fast_crash_z = [-2.0, -2.25, -2.5, -2.75, -3.0]
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=95.0)
        # Non-decreasing as z drops (more negative -> more override).
        for earlier, later in zip(out, out[1:]):
            assert later >= earlier - 1e-9
        assert out[0] == pytest.approx(50.0)  # z == trigger_z -> still a no-op
        assert out[-1] == pytest.approx(95.0)  # z == trigger_z - ramp_z -> fully overridden
        # Strictly between the endpoints the ramp is strictly increasing.
        assert out[1] < out[2] < out[3]

    def test_ramp_midpoint_is_halfway_between_risk_and_override(self) -> None:
        risk = [50.0]
        fast_crash_z = [-2.5]  # halfway between trigger_z=-2.0 and trigger_z-ramp_z=-3.0
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=95.0)
        assert out[0] == pytest.approx(72.5)  # 50 + 0.5 * (95 - 50)

    def test_output_never_falls_below_input_risk(self) -> None:
        # override_risk below the current composite risk must never pull risk down.
        risk = [80.0, 90.0, 99.0]
        fast_crash_z = [-10.0, -2.5, -2.0]
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=70.0)
        for base, overridden in zip(risk, out, strict=True):
            assert overridden >= base - 1e-9

    def test_never_decreases_across_a_full_sweep(self) -> None:
        risk = [10.0, 25.0, 50.0, 75.0, 95.0]
        fast_crash_z = [-5.0, -3.0, -2.0, -1.0, None]
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=95.0)
        for base, overridden in zip(risk, out, strict=True):
            assert overridden >= base - 1e-9

    def test_none_fast_crash_z_is_no_op_not_a_crash(self) -> None:
        risk = [50.0, 50.0]
        fast_crash_z = [None, None]  # e.g. still warming up
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=95.0)
        assert out == pytest.approx(risk)
        assert all(v is not None for v in out)

    def test_null_base_risk_stays_null_regardless_of_crash_signal(self) -> None:
        risk = [None, 50.0]
        fast_crash_z = [-10.0, -10.0]  # deep crash on both rows
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=95.0)
        assert out[0] is None
        assert out[1] == pytest.approx(95.0)

    def test_accepts_polars_series_inputs(self) -> None:
        risk = pl.Series([50.0, 50.0])
        fast_crash_z = pl.Series([-10.0, 0.0])
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=95.0)
        assert out[0] == pytest.approx(95.0)
        assert out[1] == pytest.approx(50.0)

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            apply_crash_override([50.0, 50.0], [-1.0], trigger_z=-2.0, ramp_z=1.0, override_risk=95.0)

    def test_zero_ramp_is_a_hard_step_at_trigger_z(self) -> None:
        risk = [50.0, 50.0]
        fast_crash_z = [-2.0, -1.999]
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=0.0, override_risk=95.0)
        assert out[0] == pytest.approx(95.0)  # z <= trigger_z -> full override
        assert out[1] == pytest.approx(50.0)  # z > trigger_z -> no-op

    def test_result_respects_upper_bound_when_override_risk_exceeds_100(self) -> None:
        risk = [50.0]
        fast_crash_z = [-10.0]
        out = apply_crash_override(risk, fast_crash_z, trigger_z=-2.0, ramp_z=1.0, override_risk=150.0)
        assert out[0] == pytest.approx(100.0)
