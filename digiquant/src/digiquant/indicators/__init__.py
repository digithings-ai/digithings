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

__all__ = [
    "DEMA",
    "EMA",
    "HMA",
    "SMA",
    "VWMA",
    "WMA",
    "WilderMA",
    "make_ma",
]

# The following submodules are added by later tasks. Import them lazily so that
# `import digiquant.indicators` (and submodule imports such as
# `digiquant.indicators.ma`) keep working before those modules land.
try:
    from digiquant.indicators.oscillators import BollingerBands, RSI

    __all__ += ["BollingerBands", "RSI"]
except ImportError:
    pass

try:
    from digiquant.indicators.adf import RollingADF

    __all__ += ["RollingADF"]
except ImportError:
    pass

try:
    from digiquant.indicators.dpsd import DPSDTrend

    __all__ += ["DPSDTrend"]
except ImportError:
    pass
