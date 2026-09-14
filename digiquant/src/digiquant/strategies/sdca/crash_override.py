"""Independent crash circuit-breaker -- not a weighted-composite indicator.

``apply_crash_override`` sits outside ``compute_composite_risk``'s weighted
blend entirely. It force-pushes the daily risk score UP (more sell-favorable)
when a fast, short-window volatility spike (``indicator_catalog.fast_crash_vol_z``)
signals a crash, regardless of what the slow macro composite says. It can
only raise risk, never lower it, so it never fights the buy side or
interferes with catching long-term bottoms.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

__all__ = ["apply_crash_override"]


def apply_crash_override(
    risk: pl.Series | Sequence[float | None],
    fast_crash_z: pl.Series | Sequence[float | None],
    *,
    trigger_z: float,
    ramp_z: float,
    override_risk: float,
) -> list[float | None]:
    """Force ``risk`` toward ``override_risk`` where ``fast_crash_z`` is very negative.

    ``fast_crash_z`` is sign-flipped (see ``fast_crash_vol_z``) so a vol spike
    reads negative. At or below ``trigger_z - ramp_z`` the output is fully
    ``override_risk``. Between ``trigger_z - ramp_z`` and ``trigger_z`` it
    ramps linearly from the unmodified ``risk`` up toward ``override_risk``.
    Above ``trigger_z``, or where ``fast_crash_z`` is ``None`` (e.g. still
    warming up), this is a no-op -- output equals ``risk`` unchanged.

    The result is always ``max(risk, ramped)`` at every point: this override
    can only push risk UP (force more selling), never down (never force more
    buying). A ``None`` entry in ``risk`` (an explicit no-trade/no-data day)
    stays ``None`` regardless of ``fast_crash_z`` -- the override never
    manufactures a value the composite itself didn't produce.
    """
    risk_list = risk.to_list() if isinstance(risk, pl.Series) else list(risk)
    z_list = fast_crash_z.to_list() if isinstance(fast_crash_z, pl.Series) else list(fast_crash_z)
    if len(risk_list) != len(z_list):
        raise ValueError(
            f"apply_crash_override requires risk and fast_crash_z to have the same "
            f"length, got {len(risk_list)}, {len(z_list)}"
        )
    if ramp_z < 0:
        raise ValueError(f"apply_crash_override ramp_z must be >= 0, got {ramp_z}")

    lower = trigger_z - ramp_z
    out: list[float | None] = []
    for base, z in zip(risk_list, z_list, strict=True):
        if base is None:
            out.append(None)
            continue
        base = float(base)
        if z is None or z > trigger_z:
            out.append(base)
            continue
        if ramp_z <= 0.0 or z <= lower:
            fraction = 1.0
        else:
            fraction = (trigger_z - z) / ramp_z
        ramped = base + fraction * (override_risk - base)
        out.append(min(100.0, max(base, ramped)))
    return out
