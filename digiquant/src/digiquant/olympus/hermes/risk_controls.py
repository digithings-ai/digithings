"""Drawdown circuit breaker (Pillar 2).

A defensive overlay on the sizer: as the paper book's drawdown from its recent peak
deepens, the breaker returns a ``scale ≤ 1.0`` that the sizer applies to gross exposure
— it only ever *reduces* gross / raises cash and can never lever up (paper-safe). Below
the ``soft`` drawdown the book is untouched (scale 1.0); at/below the ``hard`` drawdown
the cut reaches its configured maximum; between the two it ramps linearly.

The pure half — :func:`compute_breaker_scale` — takes a chronological NAV series and the
config; the I/O half — :func:`breaker_scale_from_nav_history` — reads the recent
``nav_history`` window (fail-soft → a neutral 1.0 scale) and computes it. The phase7e
enforcement node calls the I/O half and passes ``scale`` to
:func:`~digiquant.olympus.hermes.sizing.size_portfolio`.

NAV is the base-100 paper index written by ``portfolio_materialize`` (``nav_history.nav``);
drawdown is measured against the peak within a bounded lookback window so a single ancient
peak can't pin the breaker on forever.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint: duck-typed Supabase client + rows

logger = logging.getLogger(__name__)

_DEFAULT_LOOKBACK_DAYS = 365  # calendar window for the peak (≈ 1y of the paper index)


@dataclass(frozen=True)
class BreakerConfig:
    """Drawdown-breaker thresholds (all drawdowns are negative %)."""

    soft_dd_pct: float = -8.0  # reduction begins once drawdown is worse than this
    hard_dd_pct: float = -20.0  # full reduction reached at/below this
    max_reduction: float = 0.5  # deepest cut: scale floor = 1 − max_reduction
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS

    @classmethod
    def from_preferences(cls, prefs: Mapping[str, Any]) -> BreakerConfig:
        """Build from the investor ``preferences`` dict; absent keys keep defaults.

        Reads ``breaker_soft_dd_pct`` / ``breaker_hard_dd_pct`` / ``breaker_max_reduction``
        / ``breaker_lookback_days``. Drawdown thresholds are normalized to negative.
        """

        def _num(key: str, default: float) -> float:
            try:
                val = prefs.get(key)
                return float(val) if val is not None else default
            except (TypeError, ValueError):
                return default

        soft = -abs(_num("breaker_soft_dd_pct", cls.soft_dd_pct))
        hard = -abs(_num("breaker_hard_dd_pct", cls.hard_dd_pct))
        reduction = min(1.0, max(0.0, _num("breaker_max_reduction", cls.max_reduction)))
        lookback = int(_num("breaker_lookback_days", float(cls.lookback_days)))
        return cls(
            soft_dd_pct=soft,
            hard_dd_pct=min(hard, soft),  # hard must be at least as deep as soft
            max_reduction=reduction,
            lookback_days=max(1, lookback),
        )


@dataclass(frozen=True)
class BreakerState:
    """Outcome of one breaker evaluation (scale + the drawdown that drove it)."""

    scale: float
    drawdown_pct: float  # current NAV vs peak, ≤ 0
    peak_nav: float | None
    current_nav: float | None
    reason: str


def compute_breaker_scale(
    navs: Sequence[float], *, config: BreakerConfig | None = None
) -> BreakerState:
    """Map a chronological NAV series to a gross-exposure ``scale`` in [floor, 1.0].

    Fewer than two points (a freshly launched book) → 1.0 (nothing to measure yet). The
    drawdown is ``(current − peak) / peak``; ``scale`` ramps linearly from 1.0 at
    ``soft_dd_pct`` to ``1 − max_reduction`` at ``hard_dd_pct`` (and stays at the floor
    below it). Never exceeds 1.0 — the breaker only reduces.
    """
    config = config or BreakerConfig()
    clean = [float(n) for n in navs if n is not None and float(n) > 0.0]
    if len(clean) < 2:
        return BreakerState(
            1.0, 0.0, None, (clean[-1] if clean else None), "insufficient NAV history"
        )

    peak = max(clean)
    current = clean[-1]
    drawdown = (current - peak) / peak * 100.0 if peak > 0 else 0.0

    soft, hard = config.soft_dd_pct, config.hard_dd_pct
    if drawdown >= soft:
        scale, reason = 1.0, f"drawdown {drawdown:.1f}% shallower than soft {soft:.0f}% — no cut"
    elif drawdown <= hard:
        scale = 1.0 - config.max_reduction
        reason = f"drawdown {drawdown:.1f}% at/below hard {hard:.0f}% — gross cut to {scale:.0%}"
    else:
        # Linear ramp between soft (frac 0) and hard (frac 1).
        frac = (soft - drawdown) / (soft - hard) if soft != hard else 1.0
        scale = 1.0 - config.max_reduction * frac
        reason = f"drawdown {drawdown:.1f}% between soft/hard — gross scaled to {scale:.0%}"

    return BreakerState(
        scale=round(max(0.0, min(1.0, scale)), 4),
        drawdown_pct=round(drawdown, 2),
        peak_nav=round(peak, 4),
        current_nav=round(current, 4),
        reason=reason,
    )


def _recent_navs(client: Any, as_of: date, lookback_days: int) -> list[float]:
    """Chronological NAV values in ``(as_of − lookback, as_of]``; ``[]`` on any read error.

    Look-ahead-guarded (``.lte(as_of)``): a future NAV row can never enter the window.
    """
    since = (as_of - timedelta(days=max(1, lookback_days))).isoformat()
    resp = (
        client.table("nav_history")
        .select("date,nav")
        .lte("date", as_of.isoformat())
        .gte("date", since)
        .order("date", desc=False)  # ascending → chronological, current = last
        .limit(lookback_days + 8)
        .execute()
    )
    navs: list[float] = []
    for row in getattr(resp, "data", None) or []:
        value = row.get("nav")
        if value is not None:
            try:
                navs.append(float(value))
            except (TypeError, ValueError):
                continue
    return navs


def breaker_scale_from_nav_history(
    client: Any, as_of: date, *, config: BreakerConfig | None = None
) -> BreakerState:
    """Read the recent ``nav_history`` window and compute the breaker. Fail-soft: a
    read error degrades to a neutral 1.0 scale (the breaker never blocks a run)."""
    config = config or BreakerConfig()
    try:
        navs = _recent_navs(client, as_of, config.lookback_days)
    except Exception as exc:  # noqa: BLE001 — breaker is best-effort; never fail the run
        logger.warning("breaker: nav_history read failed (%s); neutral scale", exc)
        return BreakerState(1.0, 0.0, None, None, f"nav_history read failed: {exc}")
    return compute_breaker_scale(navs, config=config)


__all__ = [
    "BreakerConfig",
    "BreakerState",
    "breaker_scale_from_nav_history",
    "compute_breaker_scale",
]
