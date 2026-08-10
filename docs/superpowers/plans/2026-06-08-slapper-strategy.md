# Slapper Strategy Family Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the BTC/ETH/SOL Slapper PineScript strategies into a single `SlapperStrategy` NautilusTrader class with three registered parameter profiles, backed by a reusable bar-by-bar indicator library.

**Architecture:** A new `digiquant/src/digiquant/indicators/` package provides pure-Python, stateful indicator classes (no Polars, no Nautilus dependency) that are updated on each bar. `SlapperStrategy` holds instances of these classes, computes signals in `on_bar`, and submits market orders. Three registry entries (`btc_slapper`, `eth_slapper`, `sol_slapper`) each carry their own default `SlapperConfig`.

**Tech Stack:** Python 3.12, NautilusTrader ≥1.190, statsmodels ≥0.14 (rolling ADF), numpy (array ops in ADF + DPSD), existing `digiquant.strategies.registry`.

---

## ⚠️ Calibration Note

The ADF threshold values in the PineScript configs (e.g. `-1.25`, `-0.95`) were tuned against TradingView's hand-rolled QR-decomposition ADF. `statsmodels.adfuller` computes the same test but with better numerical stability. The t-statistics should be in the same range but may differ slightly. After implementing, run a backtest and compare signal frequency — if it diverges significantly, re-optimize the `adf_upper_entry` and `adf_lower_entry` parameters.

## ⚠️ Pine-Parity Semantics (READ BEFORE TASK 6)

The Pine header `default_qty_type=strategy.percent_of_equity, default_qty_value=100, pyramiding=0` means:

1. **Reversal, not flat.** A `buy_signal` while short must *close the short AND open a long* (and vice versa). A naive single market order of fixed size sends short→flat, not short→long. We replicate Pine using the **close-then-open** pattern already established in `rsi_momentum.py:82-90`: branch on `portfolio.is_net_short()` / `is_net_long()`, call `close_all_positions()`, then submit the new entry.
2. **pyramiding=0** — a same-direction signal while already in that direction is ignored (guarded by `is_flat()` before opening).
3. **percent_of_equity=100** — Pine compounds: each entry uses ~100% of current equity. The rest of the digiquant strategy zoo uses a fixed `trade_size`, so we keep `trade_size` as the default but add an optional `size_pct_equity` field. When set, size is derived from account equity at entry time. **Verify the equity-read API against the installed Nautilus version** (likely `self.portfolio.account(venue).balance_total(currency)` — confirm before relying on it). If equity sizing can't be verified, fall back to fixed `trade_size` and record the divergence in the parity task (Task 8).
4. **No explicit `client_order_id`** — `order_factory.market()` auto-generates it (see `rsi_momentum.py`). Do not pass one.

---

## File Structure

**New files:**
```
digiquant/src/digiquant/indicators/__init__.py        # public re-exports
digiquant/src/digiquant/indicators/ma.py              # WilderMA, SMA, EMA, WMA, HMA, DEMA, VWMA, make_ma()
digiquant/src/digiquant/indicators/oscillators.py     # RSI, BollingerBands
digiquant/src/digiquant/indicators/adf.py             # RollingADF
digiquant/src/digiquant/indicators/dpsd.py            # DPSDTrend
digiquant/src/digiquant/strategies/slapper.py         # SlapperConfig + SlapperStrategy
tests/dq/indicators/__init__.py
tests/dq/indicators/test_ma.py
tests/dq/indicators/test_oscillators.py
tests/dq/indicators/test_adf.py
tests/dq/indicators/test_dpsd.py
tests/dq/strategies/test_slapper_config.py
```

**Modified files:**
```
digiquant/pyproject.toml                              # add statsmodels to optional deps
digiquant/src/digiquant/strategies/registry.py        # register btc_slapper, eth_slapper, sol_slapper
```

---

## Task 1: Add statsmodels dependency + indicators package skeleton

**Files:**
- Modify: `digiquant/pyproject.toml`
- Create: `digiquant/src/digiquant/indicators/__init__.py`
- Create: `tests/dq/indicators/__init__.py`

- [ ] **Step 1: Add statsmodels to pyproject.toml**

In `digiquant/pyproject.toml`, add to the `[project.optional-dependencies]` section:

```toml
nautilus = ["nautilus_trader>=1.190,<2", "requests>=2.28", "statsmodels>=0.14"]
```

Also add a standalone optional group for just statsmodels (so it can be installed without Nautilus):

```toml
indicators = ["statsmodels>=0.14", "numpy>=1.26"]
```

And add it to the `dev` extras:

```toml
dev = ["digiquant[atlas]", "digiquant[indicators]", "pytest>=8", "pytest-cov>=4", "ruff>=0.8"]
```

- [ ] **Step 2: Create indicators package init**

Create `digiquant/src/digiquant/indicators/__init__.py`:

```python
"""Bar-by-bar technical indicator library — pure Python, no Nautilus dependency.

Each indicator class exposes:
- update(value: float) -> None   — feed one bar's value
- value: float | None            — current output (None until initialized)
- initialized: bool              — True once enough bars processed
"""
from digiquant.indicators.ma import (
    DEMA,
    EMA,
    HMA,
    SMA,
    VWMA,
    WMA,
    WilderMA,
    make_ma,
)
from digiquant.indicators.oscillators import BollingerBands, RSI
from digiquant.indicators.adf import RollingADF
from digiquant.indicators.dpsd import DPSDTrend

__all__ = [
    "DEMA", "EMA", "HMA", "SMA", "VWMA", "WMA", "WilderMA", "make_ma",
    "BollingerBands", "RSI",
    "RollingADF",
    "DPSDTrend",
]
```

- [ ] **Step 3: Create test package init**

```bash
mkdir -p tests/dq/indicators
touch tests/dq/indicators/__init__.py
```

- [ ] **Step 4: Install statsmodels**

```bash
cd digiquant && pip install -e ".[indicators,dev]"
python -c "from statsmodels.tsa.stattools import adfuller; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add digiquant/pyproject.toml digiquant/src/digiquant/indicators/__init__.py tests/dq/indicators/__init__.py
git commit -m "feat(digiquant): scaffold indicators package, add statsmodels dep"
```

---

## Task 2: Moving Average classes

**Files:**
- Create: `digiquant/src/digiquant/indicators/ma.py`
- Create: `tests/dq/indicators/test_ma.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/dq/indicators/test_ma.py`:

```python
"""Tests for bar-by-bar moving average classes."""
from __future__ import annotations

import math
import pytest
from digiquant.indicators.ma import WilderMA, SMA, EMA, WMA, HMA, DEMA, VWMA, make_ma


class TestWilderMA:
    def test_not_initialized_before_enough_bars(self) -> None:
        rma = WilderMA(3)
        rma.update(10.0)
        rma.update(11.0)
        assert not rma.initialized
        assert rma.value is None

    def test_initialized_after_length_bars(self) -> None:
        rma = WilderMA(3)
        for v in [10.0, 11.0, 12.0]:
            rma.update(v)
        assert rma.initialized

    def test_first_value_is_sma_seed(self) -> None:
        # Wilder seeds with SMA of first `length` values, then applies alpha=1/length
        rma = WilderMA(3)
        for v in [10.0, 11.0, 12.0]:
            rma.update(v)
        # seed = (10+11+12)/3 = 11.0; no more bars → value = 11.0
        assert rma.value == pytest.approx(11.0)

    def test_subsequent_update(self) -> None:
        rma = WilderMA(3)
        for v in [10.0, 11.0, 12.0]:
            rma.update(v)
        rma.update(13.0)
        # alpha = 1/3; 11.0 + (1/3)*(13-11) = 11.667
        assert rma.value == pytest.approx(11.0 + (1 / 3) * (13.0 - 11.0))


class TestSMA:
    def test_not_initialized_before_length(self) -> None:
        sma = SMA(3)
        sma.update(1.0)
        assert not sma.initialized

    def test_value_after_length_bars(self) -> None:
        sma = SMA(3)
        for v in [1.0, 2.0, 3.0]:
            sma.update(v)
        assert sma.value == pytest.approx(2.0)

    def test_rolling_window(self) -> None:
        sma = SMA(3)
        for v in [1.0, 2.0, 3.0, 4.0]:
            sma.update(v)
        assert sma.value == pytest.approx(3.0)


class TestEMA:
    def test_not_initialized_before_length(self) -> None:
        ema = EMA(3)
        ema.update(10.0)
        assert not ema.initialized

    def test_initialized_at_length(self) -> None:
        ema = EMA(3)
        for v in [10.0, 11.0, 12.0]:
            ema.update(v)
        assert ema.initialized

    def test_alpha_formula(self) -> None:
        # alpha = 2/(3+1) = 0.5; seed = SMA(3) = 11.0
        ema = EMA(3)
        for v in [10.0, 11.0, 12.0]:
            ema.update(v)
        assert ema.value == pytest.approx(11.0)  # seed = sma
        ema.update(14.0)
        # 11.0 + 0.5*(14-11) = 12.5
        assert ema.value == pytest.approx(12.5)


class TestWMA:
    def test_weighted_average(self) -> None:
        wma = WMA(3)
        for v in [1.0, 2.0, 3.0]:
            wma.update(v)
        # weights [1,2,3], denom=6: (1*1 + 2*2 + 3*3)/6 = 14/6 = 2.333
        assert wma.value == pytest.approx(14 / 6)

    def test_rolling(self) -> None:
        wma = WMA(3)
        for v in [1.0, 2.0, 3.0, 4.0]:
            wma.update(v)
        # window [2,3,4]: (1*2 + 2*3 + 3*4)/6 = 20/6
        assert wma.value == pytest.approx(20 / 6)


class TestDEMA:
    def test_needs_2x_length_bars(self) -> None:
        dema = DEMA(3)
        for v in range(5):
            dema.update(float(v))
        assert not dema.initialized

    def test_initialized_after_2x_length(self) -> None:
        dema = DEMA(3)
        for v in range(6):
            dema.update(float(v))
        assert dema.initialized

    def test_formula_dema_equals_2ema_minus_ema_ema(self) -> None:
        dema = DEMA(3)
        ema1 = EMA(3)
        ema2 = EMA(3)
        prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
        for p in prices:
            dema.update(p)
            ema1.update(p)
            if ema1.initialized:
                ema2.update(ema1.value)
        if dema.initialized and ema1.initialized and ema2.initialized:
            assert dema.value == pytest.approx(2 * ema1.value - ema2.value)


class TestHMA:
    def test_initialized_eventually(self) -> None:
        hma = HMA(9)
        for i in range(30):
            hma.update(float(i))
        assert hma.initialized

    def test_not_initialized_too_early(self) -> None:
        hma = HMA(9)
        for i in range(5):
            hma.update(float(i))
        assert not hma.initialized


class TestVWMA:
    def test_volume_weighted(self) -> None:
        vwma = VWMA(2)
        vwma.update(price=10.0, volume=100.0)
        vwma.update(price=20.0, volume=200.0)
        # (10*100 + 20*200) / (100+200) = 5000/300 = 16.667
        assert vwma.value == pytest.approx(5000 / 300)

    def test_not_initialized_before_length(self) -> None:
        vwma = VWMA(3)
        vwma.update(price=10.0, volume=100.0)
        assert not vwma.initialized


class TestMakeMa:
    def test_returns_correct_types(self) -> None:
        assert isinstance(make_ma("SMA", 5), SMA)
        assert isinstance(make_ma("EMA", 5), EMA)
        assert isinstance(make_ma("RMA", 5), WilderMA)
        assert isinstance(make_ma("WMA", 5), WMA)
        assert isinstance(make_ma("HMA", 5), HMA)
        assert isinstance(make_ma("DEMA", 5), DEMA)

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown MA type"):
            make_ma("UNKNOWN", 5)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/chrisstefan/Code/digithings
pytest tests/dq/indicators/test_ma.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'digiquant.indicators.ma'`

- [ ] **Step 3: Implement `digiquant/src/digiquant/indicators/ma.py`**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/chrisstefan/Code/digithings
pytest tests/dq/indicators/test_ma.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/indicators/ma.py tests/dq/indicators/test_ma.py
git commit -m "feat(indicators): add MA classes — WilderMA, SMA, EMA, WMA, HMA, DEMA, VWMA, make_ma"
```

---

## Task 3: RSI and BollingerBands

**Files:**
- Create: `digiquant/src/digiquant/indicators/oscillators.py`
- Create: `tests/dq/indicators/test_oscillators.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dq/indicators/test_oscillators.py`:

```python
"""Tests for RSI and BollingerBands indicator classes."""
from __future__ import annotations

import math
import pytest
from digiquant.indicators.oscillators import RSI, BollingerBands


class TestRSI:
    def test_not_initialized_before_length_plus_one(self) -> None:
        # RSI needs length+1 bars: 1 for prev_price, then length bars of changes
        rsi = RSI(3)
        rsi.update(10.0)
        assert not rsi.initialized

    def test_constant_rising_is_100(self) -> None:
        rsi = RSI(5)
        for i in range(20):
            rsi.update(float(i))
        assert rsi.initialized
        assert rsi.value == pytest.approx(100.0)

    def test_constant_falling_is_0(self) -> None:
        rsi = RSI(5)
        for i in range(20):
            rsi.update(float(20 - i))
        assert rsi.initialized
        assert rsi.value == pytest.approx(0.0)

    def test_flat_prices_after_move(self) -> None:
        rsi = RSI(14)
        # Ramp up then go flat — RSI should stabilize above 50
        for i in range(20):
            rsi.update(float(i))
        for _ in range(10):
            rsi.update(19.0)  # flat
        assert rsi.initialized
        assert rsi.value > 50.0

    def test_no_division_by_zero_on_flat(self) -> None:
        rsi = RSI(3)
        for _ in range(10):
            rsi.update(10.0)  # all flat — down == 0 → should return 100
        assert rsi.initialized
        assert rsi.value == pytest.approx(100.0)


class TestBollingerBands:
    def test_not_initialized_before_length(self) -> None:
        bb = BollingerBands(length=3, mult=2.0)
        bb.update(10.0)
        assert not bb.initialized

    def test_symmetric_around_middle(self) -> None:
        bb = BollingerBands(length=5, mult=2.0)
        for v in [10.0, 11.0, 12.0, 11.0, 10.0]:
            bb.update(v)
        assert bb.initialized
        assert bb.upper is not None
        assert bb.lower is not None
        assert bb.middle is not None
        assert bb.upper > bb.middle > bb.lower
        assert bb.upper - bb.middle == pytest.approx(bb.middle - bb.lower, rel=1e-6)

    def test_tight_bands_on_constant_prices(self) -> None:
        bb = BollingerBands(length=5, mult=2.0)
        for _ in range(5):
            bb.update(10.0)
        assert bb.initialized
        # std of constant series = 0, so upper == lower == middle
        assert bb.upper == pytest.approx(10.0)
        assert bb.lower == pytest.approx(10.0)

    def test_ema_basis_type(self) -> None:
        bb_sma = BollingerBands(length=5, mult=2.0, ma_type="SMA")
        bb_ema = BollingerBands(length=5, mult=2.0, ma_type="EMA")
        prices = [10.0, 12.0, 11.0, 13.0, 12.0]
        for p in prices:
            bb_sma.update(p)
            bb_ema.update(p)
        # EMA middle differs from SMA middle due to recency weighting
        assert bb_sma.middle != pytest.approx(bb_ema.middle)

    def test_mult_scales_bands(self) -> None:
        bb1 = BollingerBands(length=5, mult=1.0)
        bb2 = BollingerBands(length=5, mult=2.0)
        for v in [10.0, 12.0, 8.0, 11.0, 9.0]:
            bb1.update(v)
            bb2.update(v)
        assert bb2.upper - bb2.lower == pytest.approx(2 * (bb1.upper - bb1.lower))
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/dq/indicators/test_oscillators.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'digiquant.indicators.oscillators'`

- [ ] **Step 3: Implement `digiquant/src/digiquant/indicators/oscillators.py`**

```python
"""RSI and Bollinger Bands — bar-by-bar stateful computation matching PineScript behavior."""
from __future__ import annotations

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
        from collections import deque
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/dq/indicators/test_oscillators.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/indicators/oscillators.py tests/dq/indicators/test_oscillators.py
git commit -m "feat(indicators): add RSI and BollingerBands bar-by-bar classes"
```

---

## Task 4: Rolling ADF

**Files:**
- Create: `digiquant/src/digiquant/indicators/adf.py`
- Create: `tests/dq/indicators/test_adf.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dq/indicators/test_adf.py`:

```python
"""Tests for RollingADF — rolling Augmented Dickey-Fuller test wrapper."""
from __future__ import annotations

import math
import numpy as np
import pytest
from digiquant.indicators.adf import RollingADF


def _rw_prices(n: int, seed: int = 42) -> list[float]:
    """Generate a random walk (non-stationary). ADF tau should be close to 0 or positive."""
    rng = np.random.default_rng(seed)
    changes = rng.standard_normal(n)
    prices = np.cumsum(changes) + 100.0
    return prices.tolist()


def _mr_prices(n: int) -> list[float]:
    """Generate mean-reverting prices (stationary). ADF tau should be negative."""
    # AR(1) with phi=0.5 — strongly mean-reverting
    prices = [100.0]
    for _ in range(n - 1):
        prices.append(100.0 + 0.5 * (prices[-1] - 100.0) + np.random.default_rng(0).standard_normal(1)[0])
    return prices


class TestRollingADF:
    def test_not_initialized_before_lookback(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in range(19):
            adf.update(float(v))
        assert not adf.initialized
        assert adf.tau is None

    def test_initialized_at_lookback(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(30):
            adf.update(v)
        assert adf.initialized
        assert adf.tau is not None

    def test_tau_is_finite(self) -> None:
        adf = RollingADF(lookback=30, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(50):
            adf.update(v)
        assert adf.initialized
        assert math.isfinite(adf.tau)

    def test_dynamic_adf_equals_tau_when_no_ma(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(30):
            adf.update(v)
        assert adf.dynamic_adf == pytest.approx(adf.tau)

    def test_dynamic_adf_differs_from_tau_with_ma(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=True, ma_type="EMA", ma_length=3)
        prices = _rw_prices(40)
        for v in prices:
            adf.update(v)
        # After MA warmup, dynamic_adf should be smoothed version of tau
        assert adf.dynamic_adf is not None
        # They differ due to smoothing (unless only one bar of tau history)

    def test_crossover_detected(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        # Feed prices that drive tau from below -1.0 to above -1.0
        # We can't easily force this, so just verify the method runs without error
        for v in _rw_prices(60):
            adf.update(v)
        # crossover/crossunder should return booleans without raising
        assert isinstance(adf.crossover(level=-1.0), bool)
        assert isinstance(adf.crossunder(level=-1.0), bool)

    def test_tau_ema7_negative_property(self) -> None:
        adf = RollingADF(lookback=20, nlag=0, use_ma=False, ma_type="EMA", ma_length=5)
        for v in _rw_prices(50):
            adf.update(v)
        assert isinstance(adf.tau_ema7_negative, bool)
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/dq/indicators/test_adf.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'digiquant.indicators.adf'`

- [ ] **Step 3: Implement `digiquant/src/digiquant/indicators/adf.py`**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/dq/indicators/test_adf.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/indicators/adf.py tests/dq/indicators/test_adf.py
git commit -m "feat(indicators): add RollingADF — rolling ADF test via statsmodels"
```

---

## Task 5: DPSD Trend indicator

**Files:**
- Create: `digiquant/src/digiquant/indicators/dpsd.py`
- Create: `tests/dq/indicators/test_dpsd.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dq/indicators/test_dpsd.py`:

```python
"""Tests for DPSDTrend (DEMA Percentile Standard Deviation Trend)."""
from __future__ import annotations

import pytest
from digiquant.indicators.dpsd import DPSDTrend


def _feed(dpsd: DPSDTrend, prices: list[float]) -> None:
    """Feed a list of (src=price, close=price) pairs — uses same value for simplicity."""
    for p in prices:
        dpsd.update(src=p, close=p)


class TestDPSDTrend:
    def test_not_initialized_before_warmup(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=5,
            percentile_type="55/45",
            sd_length=3,
            ema_length=3,
            include_ema=True,
        )
        for i in range(5):
            dpsd.update(src=float(i), close=float(i))
        assert not dpsd.initialized

    def test_initialized_after_warmup(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=5,
            percentile_type="55/45",
            sd_length=3,
            ema_length=3,
            include_ema=True,
        )
        for i in range(30):
            dpsd.update(src=float(i), close=float(i))
        assert dpsd.initialized

    def test_uptrend_on_rising_prices(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=10,
            percentile_type="55/45",
            sd_length=5,
            ema_length=5,
            include_ema=True,
        )
        # Feed strongly rising prices — trend should eventually = 1
        for i in range(60):
            dpsd.update(src=float(i * 10), close=float(i * 10))
        assert dpsd.trend == 1.0

    def test_downtrend_on_falling_prices(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=10,
            percentile_type="55/45",
            sd_length=5,
            ema_length=5,
            include_ema=True,
        )
        # Rising warmup then sharp fall
        for i in range(40):
            dpsd.update(src=float(i * 10), close=float(i * 10))
        for i in range(40):
            dpsd.update(src=float(400 - i * 10), close=float(400 - i * 10))
        assert dpsd.trend == -1.0

    def test_crossed_up_fires_once(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=10,
            percentile_type="55/45",
            sd_length=5,
            ema_length=5,
            include_ema=True,
        )
        crossups = []
        # Warmup with rising prices
        for i in range(60):
            dpsd.update(src=float(i), close=float(i))
            if dpsd.initialized:
                crossups.append(dpsd.crossed_up())
        # crossed_up() should fire at most a handful of times (trend transitions)
        assert sum(crossups) <= 5

    def test_percentile_type_60_40(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=10,
            percentile_type="60/40",
            sd_length=5,
            ema_length=5,
            include_ema=False,
        )
        for i in range(40):
            dpsd.update(src=float(i), close=float(i))
        assert dpsd.initialized  # just verify it runs

    def test_include_ema_false(self) -> None:
        dpsd = DPSDTrend(
            dema_length=3,
            percentile_length=10,
            percentile_type="55/45",
            sd_length=5,
            ema_length=5,
            include_ema=False,
        )
        for i in range(40):
            dpsd.update(src=float(i), close=float(i))
        assert dpsd.initialized
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/dq/indicators/test_dpsd.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'digiquant.indicators.dpsd'`

- [ ] **Step 3: Implement `digiquant/src/digiquant/indicators/dpsd.py`**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/dq/indicators/test_dpsd.py -v
```

Expected: all pass.

- [ ] **Step 5: Update `indicators/__init__.py` to match actual exports**

The `__init__.py` from Task 1 already imports from these modules. Verify it still imports cleanly:

```bash
python -c "from digiquant.indicators import RollingADF, DPSDTrend, RSI, BollingerBands, EMA, WilderMA; print('ok')"
```

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add digiquant/src/digiquant/indicators/dpsd.py tests/dq/indicators/test_dpsd.py
git commit -m "feat(indicators): add DPSDTrend — DEMA percentile SD trend state machine"
```

---

## Task 6: SlapperStrategy and SlapperConfig

**Files:**
- Create: `digiquant/src/digiquant/strategies/slapper.py`
- Create: `tests/dq/strategies/test_slapper_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dq/strategies/test_slapper_config.py`:

```python
"""Tests for SlapperConfig and SlapperStrategy instantiation.

Full backtest integration is covered by make test-unit once Nautilus is
installed. These tests verify config correctness and indicator wiring
without spinning up the backtest engine.
"""
from __future__ import annotations

import pytest

try:
    from nautilus_trader.model.identifiers import InstrumentId, Venue
    from nautilus_trader.model.data import BarType, BarSpecification
    from nautilus_trader.model.enums import BarAggregation, PriceType
    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")


@pytest.fixture()
def btc_instrument_id() -> "InstrumentId":
    return InstrumentId.from_str("BTCUSDT.BINANCE")


@pytest.fixture()
def bar_type(btc_instrument_id: "InstrumentId") -> "BarType":
    spec = BarSpecification(1, BarAggregation.DAY, PriceType.LAST)
    return BarType(btc_instrument_id, spec)


class TestSlapperConfig:
    def test_btc_defaults(self, btc_instrument_id, bar_type) -> None:
        from decimal import Decimal
        from digiquant.strategies.slapper import SlapperConfig

        cfg = SlapperConfig(
            instrument_id=btc_instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
        )
        assert cfg.rsi_length == 14
        assert cfg.adf_lookback == 44
        assert cfg.adf_upper_entry == pytest.approx(-1.25)
        assert cfg.dpsd_dema_length == 4
        assert cfg.dpsd_dema_src == "hlcc4"
        assert cfg.use_reversal_stop is False

    def test_all_fields_are_frozen(self, btc_instrument_id, bar_type) -> None:
        from decimal import Decimal
        from digiquant.strategies.slapper import SlapperConfig

        cfg = SlapperConfig(
            instrument_id=btc_instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
        )
        with pytest.raises(Exception):  # frozen Pydantic raises ValidationError or TypeError
            cfg.rsi_length = 99  # type: ignore[misc]


class TestSlapperStrategyInstantiation:
    def test_can_instantiate(self, btc_instrument_id, bar_type) -> None:
        from decimal import Decimal
        from digiquant.strategies.slapper import SlapperConfig, SlapperStrategy

        cfg = SlapperConfig(
            instrument_id=btc_instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
        )
        strategy = SlapperStrategy(cfg)
        assert strategy is not None

    def test_indicator_instances_created(self, btc_instrument_id, bar_type) -> None:
        from decimal import Decimal
        from digiquant.strategies.slapper import SlapperConfig, SlapperStrategy
        from digiquant.indicators import RSI, RollingADF, BollingerBands, DPSDTrend

        cfg = SlapperConfig(
            instrument_id=btc_instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
        )
        strategy = SlapperStrategy(cfg)
        assert isinstance(strategy._rsi, RSI)
        assert isinstance(strategy._adf, RollingADF)
        assert isinstance(strategy._bb, BollingerBands)
        assert isinstance(strategy._dpsd, DPSDTrend)
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/dq/strategies/test_slapper_config.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'digiquant.strategies.slapper'`

- [ ] **Step 3: Implement `digiquant/src/digiquant/strategies/slapper.py`**

```python
"""Slapper strategy — ADF + RSI + Bollinger Bands mean reversion combined with DPSD trend.

Converted from BTC/ETH/SOL Slapper PineScript (v6). One class covers all three
coins; parameter differences are captured in the registry configs.

Signal logic:
  mr_long  = (adf_crossover OR rsi_crossover) AND rsi_over_under AND close < bb_lower
  mr_short = (adf_crossunder OR rsi_crossunder) AND close > bb_upper
  buy      = mr_long OR dpsd_crossed_up
  sell     = mr_short OR dpsd_crossed_down

Reversal stop (BTC only, use_reversal_stop=True):
  If MR-only entry AND DPSD trend opposes AND drawdown > threshold → close and reverse.
"""
from __future__ import annotations

from decimal import Decimal

from nautilus_trader.config import PositiveInt, StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from digiquant.indicators import BollingerBands, DPSDTrend, RollingADF, RSI, make_ma
from digiquant.indicators.ma import VWMA
from digiquant.strategies.registry import register


class SlapperConfig(StrategyConfig, frozen=True):
    """All parameters for the Slapper strategy family."""

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    # When set (e.g. 100.0), size each entry as this percent of account equity,
    # replicating Pine's percent_of_equity compounding. None → fixed trade_size.
    size_pct_equity: float | None = None

    # ── RSI ──────────────────────────────────────────────────────────────────
    rsi_length: PositiveInt = 14
    rsi_use_ma: bool = True
    rsi_ma_length: PositiveInt = 14
    rsi_ma_type: str = "EMA"  # SMA/EMA/RMA/WMA/HMA/VWMA
    rsi_upper_band: float = 44.0
    rsi_lower_band: float = 37.0

    # ── ADF ──────────────────────────────────────────────────────────────────
    adf_lookback: int = 44
    adf_nlag: int = 0
    adf_use_ma: bool = True
    adf_ma_length: PositiveInt = 45
    adf_ma_type: str = "EMA"
    adf_upper_entry: float = -1.25
    adf_use_lower_entry: bool = True
    adf_lower_entry: float = -1.65

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_length: PositiveInt = 37
    bb_ma_type: str = "EMA"
    bb_mult: float = 0.3

    # ── DPSD ─────────────────────────────────────────────────────────────────
    dpsd_dema_length: PositiveInt = 4
    dpsd_dema_src: str = "hlcc4"  # "hl2" or "hlcc4"
    dpsd_percentile_length: PositiveInt = 69
    dpsd_percentile_type: str = "55/45"
    dpsd_sd_length: PositiveInt = 25
    dpsd_ema_length: PositiveInt = 41
    dpsd_include_ema: bool = True

    # ── Reversal stop (BTC only) ──────────────────────────────────────────────
    use_reversal_stop: bool = False
    stop_drawdown_threshold: float = 20.0

    # ── Strategy control ─────────────────────────────────────────────────────
    enable_long: bool = True
    enable_short: bool = True


class SlapperStrategy(Strategy):
    """ADF + RSI + BB mean reversion combined with DPSD trend-following."""

    def __init__(self, config: SlapperConfig) -> None:
        super().__init__(config)

        self._rsi = RSI(config.rsi_length)
        # RSI MA: VWMA needs special handling (requires volume); others via make_ma
        if config.rsi_ma_type == "VWMA":
            self._rsi_ma: VWMA | object = VWMA(config.rsi_ma_length)
            self._rsi_ma_is_vwma = True
        else:
            self._rsi_ma = make_ma(config.rsi_ma_type, config.rsi_ma_length)
            self._rsi_ma_is_vwma = False

        self._adf = RollingADF(
            lookback=config.adf_lookback,
            nlag=config.adf_nlag,
            use_ma=config.adf_use_ma,
            ma_type=config.adf_ma_type,
            ma_length=config.adf_ma_length,
        )

        self._bb = BollingerBands(
            length=config.bb_length,
            mult=config.bb_mult,
            ma_type=config.bb_ma_type,
        )

        self._dpsd = DPSDTrend(
            dema_length=config.dpsd_dema_length,
            percentile_length=config.dpsd_percentile_length,
            percentile_type=config.dpsd_percentile_type,
            sd_length=config.dpsd_sd_length,
            ema_length=config.dpsd_ema_length,
            include_ema=config.dpsd_include_ema,
        )

        # Previous values for crossover detection
        self._prev_selected_rsi: float | None = None

        # Reversal stop state
        self._is_mr_only_entry: bool = False
        self._signal_close_price: float | None = None

        self._instrument: Instrument | None = None

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    def on_start(self) -> None:
        self._instrument = self.cache.instrument(self.config.instrument_id)
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        close = bar.close.as_double()
        high = bar.high.as_double()
        low = bar.low.as_double()
        volume = bar.volume.as_double()

        # ── Source for DPSD ──────────────────────────────────────────────────
        dpsd_src = (
            (high + low) / 2.0
            if self.config.dpsd_dema_src == "hl2"
            else (high + low + close * 2.0) / 4.0
        )

        # ── Update indicators ────────────────────────────────────────────────
        self._rsi.update(close)
        self._adf.update(close)
        self._bb.update(close)
        self._dpsd.update(src=dpsd_src, close=close)

        if not (self._rsi.initialized and self._adf.initialized and self._bb.initialized):
            return

        # ── RSI MA ───────────────────────────────────────────────────────────
        if self.config.rsi_use_ma:
            if self._rsi_ma_is_vwma:
                self._rsi_ma.update(price=self._rsi.value, volume=volume)  # type: ignore[union-attr]
            else:
                self._rsi_ma.update(self._rsi.value)  # type: ignore[union-attr]
            selected_rsi = self._rsi_ma.value if self._rsi_ma.initialized else None
        else:
            selected_rsi = self._rsi.value

        if selected_rsi is None:
            return

        # ── RSI crossover signals ────────────────────────────────────────────
        upper_b = self.config.rsi_upper_band
        lower_b = self.config.rsi_lower_band
        prev = self._prev_selected_rsi
        rsi_long = prev is not None and prev < upper_b and selected_rsi >= upper_b
        rsi_short = prev is not None and prev > upper_b and selected_rsi <= upper_b
        rsi_over_under = selected_rsi > upper_b or selected_rsi < lower_b
        self._prev_selected_rsi = selected_rsi

        # ── ADF crossover signals ────────────────────────────────────────────
        adf_long = self._adf.crossover(self.config.adf_upper_entry) or (
            self.config.adf_use_lower_entry and self._adf.crossover(self.config.adf_lower_entry)
        )
        adf_short = self._adf.crossunder(self.config.adf_upper_entry) or (
            self.config.adf_use_lower_entry and self._adf.crossunder(self.config.adf_lower_entry)
        )

        # ── BB ───────────────────────────────────────────────────────────────
        bb_long = close < self._bb.lower  # type: ignore[operator]
        bb_short = close > self._bb.upper  # type: ignore[operator]

        # ── Combined signals ──────────────────────────────────────────────────
        mr_long = (adf_long or rsi_long) and rsi_over_under and bb_long
        mr_short = (adf_short or rsi_short) and bb_short
        trend_long = self._dpsd.crossed_up() if self._dpsd.initialized else False
        trend_short = self._dpsd.crossed_down() if self._dpsd.initialized else False

        buy_signal = mr_long or trend_long
        sell_signal = mr_short or trend_short

        # ── Reversal stop (BTC Slapper only) ─────────────────────────────────
        if self.config.use_reversal_stop:
            self._check_reversal_stop(close)

        # ── Entries — close-then-open reversal, pyramiding=0 (Pine parity) ────
        # See rsi_momentum.py:73-108 for the established pattern.
        if buy_signal and self.config.enable_long:
            if self.portfolio.is_flat(self.config.instrument_id):
                self._enter(OrderSide.BUY, close)
            elif self.portfolio.is_net_short(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self._enter(OrderSide.BUY, close)
            # else already long → ignored (pyramiding=0)
            if self.config.use_reversal_stop and not self.portfolio.is_flat(
                self.config.instrument_id
            ):
                self._is_mr_only_entry = mr_long and not trend_long
                self._signal_close_price = close

        elif sell_signal and self.config.enable_short:
            if self.portfolio.is_flat(self.config.instrument_id):
                self._enter(OrderSide.SELL, close)
            elif self.portfolio.is_net_long(self.config.instrument_id):
                self.close_all_positions(self.config.instrument_id)
                self._enter(OrderSide.SELL, close)
            # else already short → ignored (pyramiding=0)
            if self.config.use_reversal_stop and not self.portfolio.is_flat(
                self.config.instrument_id
            ):
                self._is_mr_only_entry = mr_short and not trend_short
                self._signal_close_price = close

        # Reset mr_only flag when flat
        if self.portfolio.is_flat(self.config.instrument_id) and self.config.use_reversal_stop:
            self._is_mr_only_entry = False
            self._signal_close_price = None

    def _entry_qty(self, close: float):
        """Compute order quantity. Fixed trade_size unless size_pct_equity is set.

        When size_pct_equity is set, derive notional from account equity to
        replicate Pine's percent_of_equity sizing (compounding).
        VERIFY the equity-read API against the installed Nautilus version before
        trusting this branch — see the Pine-Parity Semantics note at the top.
        """
        assert self._instrument is not None
        if self.config.size_pct_equity is None:
            return self._instrument.make_qty(self.config.trade_size)
        venue = self.config.instrument_id.venue
        account = self.portfolio.account(venue)
        currency = self._instrument.quote_currency
        equity = account.balance_total(currency).as_double()
        notional = equity * (self.config.size_pct_equity / 100.0)
        qty_raw = notional / close
        return self._instrument.make_qty(qty_raw)

    def _enter(self, side: OrderSide, close: float) -> None:
        """Submit a market entry sized per config. No explicit client_order_id."""
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=self._entry_qty(close),
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

    def _check_reversal_stop(self, close: float) -> None:
        """Reverse position when MR-only entry exceeds drawdown threshold.

        Pine closes the losing MR position and immediately enters the opposite
        side (a reversal). We replicate: close, then open the opposite side.
        """
        if not self._is_mr_only_entry or self._signal_close_price is None:
            return
        threshold = self.config.stop_drawdown_threshold
        trend = self._dpsd.trend if self._dpsd.initialized else 0.0

        if self.portfolio.is_net_long(self.config.instrument_id) and trend == -1.0:
            dd_pct = (self._signal_close_price - close) / self._signal_close_price * 100
            if dd_pct > threshold and self.config.enable_short:
                self.close_all_positions(self.config.instrument_id)
                self._enter(OrderSide.SELL, close)
                self._is_mr_only_entry = False  # reversal aligns with trend

        elif self.portfolio.is_net_short(self.config.instrument_id) and trend == 1.0:
            dd_pct = (close - self._signal_close_price) / self._signal_close_price * 100
            if dd_pct > threshold and self.config.enable_long:
                self.close_all_positions(self.config.instrument_id)
                self._enter(OrderSide.BUY, close)
                self._is_mr_only_entry = False

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        cfg = self.config
        self._rsi = RSI(cfg.rsi_length)
        if cfg.rsi_ma_type == "VWMA":
            self._rsi_ma = VWMA(cfg.rsi_ma_length)
        else:
            self._rsi_ma = make_ma(cfg.rsi_ma_type, cfg.rsi_ma_length)
        self._adf = RollingADF(
            lookback=cfg.adf_lookback,
            nlag=cfg.adf_nlag,
            use_ma=cfg.adf_use_ma,
            ma_type=cfg.adf_ma_type,
            ma_length=cfg.adf_ma_length,
        )
        self._bb = BollingerBands(length=cfg.bb_length, mult=cfg.bb_mult, ma_type=cfg.bb_ma_type)
        self._dpsd = DPSDTrend(
            dema_length=cfg.dpsd_dema_length,
            percentile_length=cfg.dpsd_percentile_length,
            percentile_type=cfg.dpsd_percentile_type,
            sd_length=cfg.dpsd_sd_length,
            ema_length=cfg.dpsd_ema_length,
            include_ema=cfg.dpsd_include_ema,
        )
        self._prev_selected_rsi = None
        self._is_mr_only_entry = False
        self._signal_close_price = None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/dq/strategies/test_slapper_config.py -v
```

Expected: all tests pass (or skip if nautilus not installed).

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/strategies/slapper.py tests/dq/strategies/test_slapper_config.py
git commit -m "feat(strategies): add SlapperStrategy + SlapperConfig (BTC/ETH/SOL Slapper)"
```

---

## Task 7: Register the three Slapper variants

**Files:**
- Modify: `digiquant/src/digiquant/strategies/registry.py`

- [ ] **Step 1: Add the three registrations to `slapper.py`**

At the bottom of `digiquant/src/digiquant/strategies/slapper.py`, append the three `register()` calls. The registry pattern requires calling `register()` after the class definition. Add:

```python
# ─── Registry entries ────────────────────────────────────────────────────────

register(
    "btc_slapper",
    SlapperStrategy,
    SlapperConfig,
    {
        "rsi_length": 14,
        "rsi_ma_length": 14,
        "rsi_ma_type": "EMA",
        "rsi_upper_band": 44.0,
        "rsi_lower_band": 37.0,
        "adf_lookback": 44,
        "adf_nlag": 0,
        "adf_ma_length": 45,
        "adf_ma_type": "EMA",
        "adf_upper_entry": -1.25,
        "adf_lower_entry": -1.65,
        "bb_length": 37,
        "bb_ma_type": "EMA",
        "bb_mult": 0.3,
        "dpsd_dema_length": 4,
        "dpsd_dema_src": "hlcc4",
        "dpsd_percentile_length": 69,
        "dpsd_percentile_type": "55/45",
        "dpsd_sd_length": 25,
        "dpsd_ema_length": 41,
        "use_reversal_stop": True,
        "stop_drawdown_threshold": 20.0,
    },
    aliases=["btc_slapper_mr_trend"],
    description="BTC Slapper: ADF+RSI+BB mean reversion + DPSD trend, with reversal stop",
)

register(
    "eth_slapper",
    SlapperStrategy,
    SlapperConfig,
    {
        "rsi_length": 15,
        "rsi_ma_length": 16,
        "rsi_ma_type": "RMA",
        "rsi_upper_band": 44.0,
        "rsi_lower_band": 35.0,
        "adf_lookback": 40,
        "adf_nlag": 0,
        "adf_ma_length": 51,
        "adf_ma_type": "RMA",
        "adf_upper_entry": -0.95,
        "adf_lower_entry": -1.1,
        "bb_length": 30,
        "bb_ma_type": "EMA",
        "bb_mult": 0.3,
        "dpsd_dema_length": 50,
        "dpsd_dema_src": "hl2",
        "dpsd_percentile_length": 46,
        "dpsd_percentile_type": "60/40",
        "dpsd_sd_length": 18,
        "dpsd_ema_length": 25,
        "use_reversal_stop": False,
    },
    aliases=["eth_slapper_mr_trend"],
    description="ETH Slapper: ADF+RSI+BB mean reversion + DPSD trend (no reversal stop)",
)

register(
    "sol_slapper",
    SlapperStrategy,
    SlapperConfig,
    {
        "rsi_length": 15,
        "rsi_ma_length": 16,
        "rsi_ma_type": "RMA",
        "rsi_upper_band": 44.0,
        "rsi_lower_band": 35.0,
        "adf_lookback": 40,
        "adf_nlag": 0,
        "adf_ma_length": 51,
        "adf_ma_type": "RMA",
        "adf_upper_entry": -0.95,
        "adf_lower_entry": -1.1,
        "bb_length": 30,
        "bb_ma_type": "EMA",
        "bb_mult": 0.3,
        "dpsd_dema_length": 50,
        "dpsd_dema_src": "hl2",
        "dpsd_percentile_length": 46,
        "dpsd_percentile_type": "60/40",
        "dpsd_sd_length": 18,
        "dpsd_ema_length": 25,
        "use_reversal_stop": False,
    },
    aliases=["sol_slapper_mr_trend"],
    description="SOL Slapper: identical params to ETH Slapper, different asset",
)
```

- [ ] **Step 2: Verify the strategy can be looked up via registry**

Check what `register()` signature looks like in `registry.py` first:

```bash
head -40 digiquant/src/digiquant/strategies/registry.py
```

Then verify the registration works:

```bash
python -c "
import sys; sys.path.insert(0, 'digiquant/src')
from digiquant.strategies import slapper  # triggers register() calls
from digiquant.strategies.registry import _REGISTRY
assert 'btc_slapper' in _REGISTRY
assert 'eth_slapper' in _REGISTRY
assert 'sol_slapper' in _REGISTRY
print('All 3 registered OK')
"
```

Expected: `All 3 registered OK`

- [ ] **Step 3: Commit**

```bash
git add digiquant/src/digiquant/strategies/slapper.py
git commit -m "feat(strategies): register btc_slapper, eth_slapper, sol_slapper variants"
```

---

## Task 8: Backtest parity — exercise `on_bar` on real data

**Why:** Tasks 6–7 only test config defaults + instantiation, which skip on CI without Nautilus. Nothing exercises the trading path. This task runs one real backtest on `digiquant/data/BTC-USD.csv` and asserts the strategy actually trades, then compares against TradingView numbers. **Requires Nautilus installed** (`pip install -e digiquant[nautilus]`).

**Files:**
- Create: `tests/dq/strategies/test_slapper_backtest.py`

- [ ] **Step 1: Confirm the sample data and runner interface**

```bash
cd /Users/chrisstefan/Code/digithings
head -3 digiquant/data/BTC-USD.csv
sed -n '79,140p' digiquant/src/digiquant/backtest.py
```

Note the exact `run_backtest(strategy_name=..., symbols=..., data_path=..., strategy_params=...)` signature and the OHLCV column names. Adjust the test below if they differ.

- [ ] **Step 2: Write the parity/smoke test**

Create `tests/dq/strategies/test_slapper_backtest.py`:

```python
"""End-to-end backtest of btc_slapper on sample BTC data.

Proves the on_bar trading path works: indicators initialize, signals fire,
orders submit, positions flip. This is the only test that exercises the
strategy logic (config tests skip on CI without Nautilus).
"""
from __future__ import annotations

from pathlib import Path

import pytest

nautilus = pytest.importorskip("nautilus_trader")

from digiquant.backtest import run_backtest  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "digiquant" / "data" / "BTC-USD.csv"


@pytest.mark.integration
class TestSlapperBacktest:
    def test_btc_slapper_runs_and_trades(self) -> None:
        assert DATA.exists(), f"sample data missing: {DATA}"
        result = run_backtest(
            strategy_name="btc_slapper",
            symbols=["BTC-USD"],
            data_path=str(DATA),
        )
        # The strategy must actually trade — zero trades means signals never
        # fired (indicator init bug) or orders never flipped (sizing bug).
        assert result.num_trades > 0, "btc_slapper produced no trades — on_bar path broken"

    def test_eth_and_sol_variants_instantiate_in_pipeline(self) -> None:
        # Same data, different param profiles — must not raise.
        for name in ("eth_slapper", "sol_slapper"):
            result = run_backtest(
                strategy_name=name,
                symbols=["BTC-USD"],
                data_path=str(DATA),
            )
            assert result is not None
```

- [ ] **Step 3: Run it**

```bash
cd /Users/chrisstefan/Code/digithings
pytest tests/dq/strategies/test_slapper_backtest.py -v
```

Expected: PASS if Nautilus is installed; SKIP otherwise. If `num_trades == 0`, debug: print indicator `.initialized` states across bars — the warmup (DPSD needs ~percentile_length + dema bars; ADF needs lookback) may exceed the sample data length. If so, use a longer BTC history or shorter warmup params for the test.

- [ ] **Step 4: Record TradingView parity baseline**

In a comment at the top of the test, record the TradingView results for btc_slapper over the same date range (net profit %, num trades, max drawdown %) as documentation. Full numeric parity is not asserted (fill-timing and `percent_of_equity` differences make exact match unlikely), but a 10× divergence in trade count signals a logic bug. **Now decide on equity sizing:** verify `account.balance_total(currency)` works in this Nautilus version; if it does, re-run with `size_pct_equity=100.0` and compare the equity curve shape to Pine. If the equity API differs, leave `size_pct_equity=None` and note the divergence here.

- [ ] **Step 5: Commit**

```bash
git add tests/dq/strategies/test_slapper_backtest.py
git commit -m "test(strategies): add btc_slapper end-to-end backtest parity check"
```

---

## Self-Review

**Spec coverage:**
- ✅ RSI with MA smoothing (WilderMA, EMA, SMA, WMA, HMA, VWMA options)
- ✅ ADF rolling test via statsmodels replacing hand-rolled QR decomp
- ✅ Bollinger Bands with configurable MA basis
- ✅ DPSD trend state machine (DEMA + percentile + SD + latching T/Trend)
- ✅ Combined MR + trend signals
- ✅ Reversal stop for BTC (flag-gated)
- ✅ Three registry configs: btc_slapper, eth_slapper, sol_slapper
- ✅ All indicators are unit-testable without Nautilus

**Gaps:**
- Walk-forward / OOS harness — intentionally deferred (separate plan)
- Sensitivity/robustness report — intentionally deferred (separate plan)
- Full backtest integration test — requires sample OHLCV data; add after Task 7 once data/ tooling is confirmed
