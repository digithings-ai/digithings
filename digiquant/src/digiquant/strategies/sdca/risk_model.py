"""RiskModel protocol — the SDCA engine's sole dependency on an asset's valuation rails.

Deliberately holds zero asset-specific constants: providers (e.g. a BTC power-law
model, per issue #1082) implement this structurally and are handed to the engine
at call time. Any object exposing a matching ``rails`` method satisfies it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import polars as pl


@runtime_checkable
class RiskModel(Protocol):
    """Supplies valuation rails for a series of dates.

    ``rails(dates)`` returns a ``pl.DataFrame`` with ``low``, ``median``, and
    ``high`` columns (one row per input date), in the same price units as the
    engine's price series.
    """

    def rails(self, dates: pl.Series) -> pl.DataFrame: ...


__all__ = ["RiskModel"]
