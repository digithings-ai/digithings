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

# The submodules below are re-exported only when their imports resolve, so that
# `import digiquant.indicators` (and submodule imports such as
# `digiquant.indicators.ma`) keep working on a core install without the
# `indicators` extra (numpy).
try:
    from digiquant.indicators.oscillators import RSI, BollingerBands

    __all__ += ["BollingerBands", "RSI"]
except ImportError:
    pass  # oscillators needs numpy (`indicators` extra)

try:
    from digiquant.indicators.adf import RollingADF

    __all__ += ["RollingADF"]
except ImportError:
    pass  # adf needs numpy (`indicators` extra)

try:
    from digiquant.indicators.dpsd import DPSDTrend

    __all__ += ["DPSDTrend"]
except ImportError:
    pass  # dpsd needs numpy (`indicators` extra)

try:
    from digiquant.indicators.macro_liquidity import (
        MacroLiquidityConfig,
        MacroLiquidityModel,
        RegimeState,
    )

    __all__ += ["MacroLiquidityConfig", "MacroLiquidityModel", "RegimeState"]
except ImportError:
    pass  # macro_liquidity uses core deps only; guarded like its siblings
