"""Rolling Augmented Dickey-Fuller test using statsmodels.

The PineScript ADF implementation hand-rolls QR decomposition because PineScript
has no stats libraries. Here we delegate to statsmodels.adfuller which is more
numerically stable. The test statistic (tau) is in the same range, but the
threshold values in each strategy config (e.g. -1.25, -0.95) may need slight
recalibration after comparing backtests against TradingView results.

Buffer ordering: prices are appended chronologically (oldest first).
statsmodels.adfuller expects chronological order — no reversal needed.
"""

from __future__ import annotations

from collections import deque

import numpy as np
from statsmodels.tsa.stattools import adfuller

from digiquant.indicators.ma import EMA, make_ma


class RollingADF:
    """Rolling ADF test with optional MA smoothing on the tau series.

    Parameters
    ----------
    lookback : int
        Window size for the ADF test (Pine: `adf_lookback`).
    nlag : int
        Maximum lag for ADF (Pine: `adf_nlag`). 0 = no lags.
    use_ma : bool
        If True, smooth tau with an MA before comparing to entry levels.
    ma_type : str
        MA type for smoothing: SMA/EMA/RMA/WMA/HMA.
    ma_length : int
        Length for the smoothing MA.
    """

    def __init__(
        self,
        lookback: int,
        nlag: int,
        use_ma: bool,
        ma_type: str,
        ma_length: int,
    ) -> None:
        self._buffer: deque[float] = deque(maxlen=lookback)
        self._nlag = nlag
        self._use_ma = use_ma
        self._tau_ema7 = EMA(7)
        self._ma = make_ma(ma_type, ma_length) if use_ma else None
        self._tau: float | None = None
        self._dynamic_adf: float | None = None
        self._prev_dynamic_adf: float | None = None

    def update(self, close: float) -> None:
        self._prev_dynamic_adf = self._dynamic_adf
        self._buffer.append(close)
        if len(self._buffer) < self._buffer.maxlen:
            return
        arr = np.array(list(self._buffer))
        try:
            result = adfuller(arr, maxlag=self._nlag, regression="c", autolag=None)
            self._tau = float(result[0])
        except Exception:
            return
        self._tau_ema7.update(self._tau)
        if self._use_ma and self._ma is not None:
            self._ma.update(self._tau)
            self._dynamic_adf = self._ma.value if self._ma.initialized else None
        else:
            self._dynamic_adf = self._tau

    @property
    def tau(self) -> float | None:
        return self._tau

    @property
    def dynamic_adf(self) -> float | None:
        return self._dynamic_adf

    @property
    def tau_ema7_negative(self) -> bool:
        """True when the 7-bar EMA of raw tau is below zero (ADF long entry guard)."""
        return self._tau_ema7.initialized and self._tau_ema7.value < 0  # type: ignore[operator]

    @property
    def initialized(self) -> bool:
        return self._dynamic_adf is not None

    def crossover(self, level: float) -> bool:
        """True on the bar when dynamic_adf crosses above `level` AND tau_ema7 < 0."""
        return (
            self._prev_dynamic_adf is not None
            and self._dynamic_adf is not None
            and self._prev_dynamic_adf < level
            and self._dynamic_adf >= level
            and self.tau_ema7_negative
        )

    def crossunder(self, level: float) -> bool:
        """True on the bar when dynamic_adf crosses below `level`."""
        return (
            self._prev_dynamic_adf is not None
            and self._dynamic_adf is not None
            and self._prev_dynamic_adf > level
            and self._dynamic_adf <= level
        )
