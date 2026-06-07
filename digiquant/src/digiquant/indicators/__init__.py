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
