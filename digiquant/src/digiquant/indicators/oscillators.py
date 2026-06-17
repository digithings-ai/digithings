"""RSI and Bollinger Bands — bar-by-bar stateful computation matching PineScript behavior."""

from __future__ import annotations

from collections import deque

import numpy as np

from digiquant.indicators.ma import WilderMA, make_ma


class RSI:
    """RSI using Wilder's smoothing (RMA), matching ta.rsi() in PineScript.

    update() takes the price source (close by default). Internally tracks
    the previous price to compute bar-to-bar changes.
    """

    def __init__(self, length: int) -> None:
        self._gain = WilderMA(length)
        self._loss = WilderMA(length)
        self._prev: float | None = None
        self._value: float | None = None

    def update(self, price: float) -> None:
        if self._prev is None:
            self._prev = price
            return
        change = price - self._prev
        self._prev = price
        self._gain.update(max(change, 0.0))
        self._loss.update(max(-change, 0.0))
        if self._gain.initialized and self._loss.initialized:
            up = self._gain.value
            down = self._loss.value
            if down == 0.0:
                self._value = 100.0
            elif up == 0.0:
                self._value = 0.0
            else:
                self._value = 100.0 - (100.0 / (1.0 + up / down))

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def initialized(self) -> bool:
        return self._value is not None


class BollingerBands:
    """Bollinger Bands with configurable MA basis type.

    Uses sample standard deviation (ddof=1) matching PineScript's ta.stdev
    which applies Bessel's correction.

    update() takes the price source. After `length` bars:
      - middle: MA of source
      - upper:  middle + mult * std
      - lower:  middle - mult * std
    """

    def __init__(self, length: int, mult: float, ma_type: str = "SMA") -> None:
        self._length = length
        self._mult = mult
        self._buffer: deque[float] = deque(maxlen=length)
        self._ma = make_ma(ma_type, length)
        self.middle: float | None = None
        self.upper: float | None = None
        self.lower: float | None = None

    def update(self, value: float) -> None:
        self._buffer.append(value)
        self._ma.update(value)
        if not self._ma.initialized or len(self._buffer) < self._length:
            return
        arr = np.array(list(self._buffer))
        std = float(np.std(arr, ddof=1))
        self.middle = self._ma.value
        self.upper = self.middle + self._mult * std
        self.lower = self.middle - self._mult * std

    @property
    def initialized(self) -> bool:
        return self.middle is not None
