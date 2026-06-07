"""Bar-by-bar moving average classes for use inside NautilusTrader strategies."""

from __future__ import annotations

import math
from collections import deque


class WilderMA:
    """Wilder's smoothing (RMA). alpha = 1/length. Seeds from SMA of first `length` bars."""

    def __init__(self, length: int) -> None:
        self._length = length
        self._seed_buffer: deque[float] = deque(maxlen=length)
        self._seeded = False
        self._value: float | None = None

    def update(self, value: float) -> None:
        if not self._seeded:
            self._seed_buffer.append(value)
            if len(self._seed_buffer) == self._length:
                self._value = sum(self._seed_buffer) / self._length
                self._seeded = True
        else:
            assert self._value is not None
            self._value = self._value + (1.0 / self._length) * (value - self._value)

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def initialized(self) -> bool:
        return self._value is not None


class SMA:
    """Simple moving average over a rolling window."""

    def __init__(self, length: int) -> None:
        self._buffer: deque[float] = deque(maxlen=length)
        self._length = length
        self._value: float | None = None

    def update(self, value: float) -> None:
        self._buffer.append(value)
        if len(self._buffer) == self._length:
            self._value = sum(self._buffer) / self._length

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def initialized(self) -> bool:
        return self._value is not None


class EMA:
    """Exponential moving average. alpha = 2/(length+1). Seeds from SMA of first `length` bars."""

    def __init__(self, length: int) -> None:
        self._length = length
        self._alpha = 2.0 / (length + 1)
        self._seed_buffer: deque[float] = deque(maxlen=length)
        self._seeded = False
        self._value: float | None = None

    def update(self, value: float) -> None:
        if not self._seeded:
            self._seed_buffer.append(value)
            if len(self._seed_buffer) == self._length:
                self._value = sum(self._seed_buffer) / self._length
                self._seeded = True
        else:
            assert self._value is not None
            self._value = self._value + self._alpha * (value - self._value)

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def initialized(self) -> bool:
        return self._value is not None


class WMA:
    """Weighted moving average. Weights = [1, 2, ..., length] (oldest to newest)."""

    def __init__(self, length: int) -> None:
        self._buffer: deque[float] = deque(maxlen=length)
        self._length = length
        self._weights = list(range(1, length + 1))
        self._denom = float(sum(self._weights))
        self._value: float | None = None

    def update(self, value: float) -> None:
        self._buffer.append(value)
        if len(self._buffer) == self._length:
            self._value = sum(w * v for w, v in zip(self._weights, self._buffer)) / self._denom

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def initialized(self) -> bool:
        return self._value is not None


class DEMA:
    """Double EMA. dema = 2*EMA(n) - EMA(EMA(n)). Takes ~2*length bars to initialize."""

    def __init__(self, length: int) -> None:
        self._ema1 = EMA(length)
        self._ema2 = EMA(length)
        self._value: float | None = None

    def update(self, value: float) -> None:
        self._ema1.update(value)
        if not self._ema1.initialized:
            return
        self._ema2.update(self._ema1.value)
        if self._ema2.initialized:
            self._value = 2.0 * self._ema1.value - self._ema2.value

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def initialized(self) -> bool:
        return self._value is not None


class HMA:
    """Hull Moving Average. HMA(n) = WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""

    def __init__(self, length: int) -> None:
        self._wma_half = WMA(max(1, length // 2))
        self._wma_full = WMA(length)
        sqrt_len = max(1, round(math.sqrt(length)))
        self._wma_sqrt = WMA(sqrt_len)
        self._value: float | None = None

    def update(self, value: float) -> None:
        self._wma_half.update(value)
        self._wma_full.update(value)
        if not (self._wma_half.initialized and self._wma_full.initialized):
            return
        raw = 2.0 * self._wma_half.value - self._wma_full.value
        self._wma_sqrt.update(raw)
        if self._wma_sqrt.initialized:
            self._value = self._wma_sqrt.value

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def initialized(self) -> bool:
        return self._value is not None


class VWMA:
    """Volume-weighted moving average. update() requires both price and volume."""

    def __init__(self, length: int) -> None:
        self._price_buf: deque[float] = deque(maxlen=length)
        self._vol_buf: deque[float] = deque(maxlen=length)
        self._length = length
        self._value: float | None = None

    def update(self, price: float, volume: float) -> None:  # type: ignore[override]
        self._price_buf.append(price)
        self._vol_buf.append(volume)
        if len(self._price_buf) == self._length:
            vol_sum = sum(self._vol_buf)
            if vol_sum > 0:
                self._value = sum(p * v for p, v in zip(self._price_buf, self._vol_buf)) / vol_sum

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def initialized(self) -> bool:
        return self._value is not None


def make_ma(ma_type: str, length: int) -> WilderMA | SMA | EMA | WMA | HMA | DEMA:
    """Factory for non-volume MA types. For VWMA, instantiate directly."""
    match ma_type.upper():
        case "SMA":
            return SMA(length)
        case "EMA":
            return EMA(length)
        case "RMA" | "SMMA (RMA)":
            return WilderMA(length)
        case "WMA":
            return WMA(length)
        case "HMA":
            return HMA(length)
        case "DEMA":
            return DEMA(length)
        case _:
            raise ValueError(f"Unknown MA type: {ma_type!r}. Use SMA/EMA/RMA/WMA/HMA/DEMA.")
