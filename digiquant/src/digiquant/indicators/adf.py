"""Rolling Augmented Dickey-Fuller test — Pine-faithful QR decomposition.

Direct port of the TradingView Pine Script ADF implementation. Uses the same
QR decomposition pseudo-inverse regression and buffer ordering (newest-first)
to produce identical test statistics as the Pine version.

Buffer ordering: prices are stored newest-first, matching Pine's close[i] loop.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from digiquant.indicators.ma import EMA, make_ma


def _qr_adftest(a: np.ndarray, nlag: int) -> float:
    """Compute ADF test statistic using QR-decomposition OLS, matching Pine exactly.

    Parameters
    ----------
    a : np.ndarray
        Price array, newest-first (a[0] = most recent close).
    nlag : int
        Maximum lag. 0 = no lags.

    Returns
    -------
    float
        The ADF tau statistic.
    """
    n = len(a)
    if nlag >= n / 2 - 2:
        raise ValueError("ADF: Maximum lag must be less than (Length/2 - 2)")

    nobs = n - nlag - 1

    y = np.empty(nobs)
    x = np.empty(nobs)
    for i in range(nobs):
        y[i] = a[i] - a[i + 1]
        x[i] = a[i + 1]

    ncols = 2 + nlag
    X = np.empty((nobs, ncols))
    X[:, 0] = x
    X[:, 1] = 1.0

    for lag in range(1, nlag + 1):
        for i in range(nobs):
            X[i, 1 + lag] = a[i + lag] - a[i + lag + 1]

    # QR decomposition → pseudo-inverse → OLS
    Q, R = np.linalg.qr(X, mode="reduced")
    Rinv = np.linalg.inv(R)
    pinv = Rinv @ Q.T
    coeff = pinv @ y

    # Standard error of the first coefficient
    yhat = X @ coeff
    mean_x = np.mean(x)
    sum1 = np.sum((y - yhat) ** 2) / (nobs - ncols)
    sum2 = np.sum((x - mean_x) ** 2)
    se = np.sqrt(sum1 / sum2)

    return coeff[0] / se


class RollingADF:
    """Rolling ADF test with optional MA smoothing on the tau series.

    Uses Pine-faithful QR decomposition and newest-first buffer ordering
    to match TradingView results exactly.

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
        self._lookback = lookback
        self._nlag = nlag
        self._use_ma = use_ma
        self._tau_ema7 = EMA(7)
        self._ma = make_ma(ma_type, ma_length) if use_ma else None
        self._tau: float | None = None
        self._dynamic_adf: float | None = None
        self._prev_dynamic_adf: float | None = None
        self._prices: deque[float] = deque(maxlen=lookback)

    def update(self, close: float) -> None:
        self._prev_dynamic_adf = self._dynamic_adf
        self._prices.append(close)
        if len(self._prices) < self._lookback:
            return

        # Build newest-first array matching Pine's close[i] loop
        a = np.array(list(reversed(self._prices)))

        try:
            self._tau = _qr_adftest(a, self._nlag)
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
        # bool() normalizes the numpy comparison to a native bool for callers/tests.
        return bool(self._tau_ema7.initialized and self._tau_ema7.value < 0)  # type: ignore[operator]

    @property
    def initialized(self) -> bool:
        return self._dynamic_adf is not None

    def crossover(self, level: float) -> bool:
        """True on the bar when dynamic_adf crosses above `level` AND tau_ema7 < 0."""
        return bool(
            self._prev_dynamic_adf is not None
            and self._dynamic_adf is not None
            and self._prev_dynamic_adf < level
            and self._dynamic_adf >= level
            and self.tau_ema7_negative
        )

    def crossunder(self, level: float) -> bool:
        """True on the bar when dynamic_adf crosses below `level`."""
        return bool(
            self._prev_dynamic_adf is not None
            and self._dynamic_adf is not None
            and self._prev_dynamic_adf > level
            and self._dynamic_adf <= level
        )
