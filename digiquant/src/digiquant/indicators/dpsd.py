"""DPSD (DEMA Percentile Standard Deviation) trend state machine.

Matches the DPSD block in the Slapper PineScript strategies. Key properties:
- `T` and `Trend` are latching variables — they only change when their conditions
  are met, not on every bar (PineScript `var` semantics).
- `crossed_up()` and `crossed_down()` return True only on the transition bar.

Calibration note: Pine's ta.stdev uses Bessel's correction (ddof=1). numpy's
default is ddof=0; we explicitly pass ddof=1 here to match.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from digiquant.indicators.ma import DEMA, EMA


def _percentile_nearest_rank(values: list[float], pct: float) -> float:
    """Nearest-rank percentile matching PineScript ta.percentile_nearest_rank.

    rank = ceil(pct/100 * n), return sorted_values[rank-1].
    """
    n = len(values)
    if n == 0:
        return float("nan")
    rank = max(1, math.ceil(pct / 100.0 * n))
    return sorted(values)[rank - 1]


def _parse_percentile_type(ptype: str) -> tuple[float, float]:
    """Return (up_pct, down_pct) from a type string like '55/45'."""
    parts = ptype.split("/")
    return float(parts[0]), float(parts[1])


class DPSDTrend:
    """DEMA Percentile Standard Deviation trend indicator.

    Parameters
    ----------
    dema_length : int
        Length for the DEMA computation on the source price.
    percentile_length : int
        Rolling window for percentile computation of DEMA values.
    percentile_type : str
        Upper/lower percentile pair: '60/45', '60/40', '55/45', or '55/40'.
    sd_length : int
        Rolling window for standard deviation of PerDown.
    ema_length : int
        EMA length applied to PT (momentum value) for confluence.
    include_ema : bool
        If True, PT must also be above/below EMA(PT) for trend to flip.
    """

    def __init__(
        self,
        dema_length: int,
        percentile_length: int,
        percentile_type: str,
        sd_length: int,
        ema_length: int,
        include_ema: bool,
    ) -> None:
        self._dema = DEMA(dema_length)
        self._dema_buf: deque[float] = deque(maxlen=percentile_length)
        self._perdown_buf: deque[float] = deque(maxlen=sd_length)
        self._pt_ema = EMA(ema_length)
        self._up_pct, self._down_pct = _parse_percentile_type(percentile_type)
        self._include_ema = include_ema

        # PineScript `var` latching state
        self._t: float = 0.0
        self._trend: float = 0.0
        self._prev_trend: float = 0.0

        self._initialized: bool = False

    def update(self, src: float, close: float) -> None:
        """Feed one bar. `src` is the DEMA source (hl2 or hlcc4); `close` is bar close."""
        self._prev_trend = self._trend

        self._dema.update(src)
        if not self._dema.initialized:
            return

        self._dema_buf.append(self._dema.value)
        if len(self._dema_buf) < self._dema_buf.maxlen:
            return

        per_up = _percentile_nearest_rank(list(self._dema_buf), self._up_pct)
        per_down = _percentile_nearest_rank(list(self._dema_buf), self._down_pct)

        self._perdown_buf.append(per_down)
        if len(self._perdown_buf) < self._perdown_buf.maxlen:
            return

        arr = np.array(list(self._perdown_buf))
        sd = float(np.std(arr, ddof=1))
        sdl = per_down + sd

        # T: latching state (only updates when conditions met)
        if close > per_up and close > sdl:
            self._t = 1.0
        if close < per_down:
            self._t = -1.0

        # PT: momentum value relative to band
        if self._t == 1.0:
            pt = close - per_down
        elif per_up > sdl:
            pt = close - per_up
        else:
            pt = close - sdl

        self._pt_ema.update(pt)

        # Trend: latching state
        if self._include_ema and self._pt_ema.initialized:
            if pt > 0 and pt > self._pt_ema.value:
                self._trend = 1.0
            if pt < 0 and pt < self._pt_ema.value:
                self._trend = -1.0
        else:
            if pt > 0:
                self._trend = 1.0
            if pt < 0:
                self._trend = -1.0

        self._initialized = True

    @property
    def trend(self) -> float:
        """Current trend state: 1.0 = uptrend, -1.0 = downtrend, 0.0 = unset."""
        return self._trend

    @property
    def initialized(self) -> bool:
        return self._initialized and self._pt_ema.initialized

    def crossed_up(self) -> bool:
        """True on the bar when trend transitions from <=0 to 1."""
        return self._prev_trend <= 0.0 and self._trend == 1.0

    def crossed_down(self) -> bool:
        """True on the bar when trend transitions from >=0 to -1."""
        return self._prev_trend >= 0.0 and self._trend == -1.0
