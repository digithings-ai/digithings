"""The one empty Polars frame every on-chain provider returns on no data.

Each provider (bitview, fear_greed, coinmetrics, bgeometrics) used to build its
own ``date: Date`` / ``value: Float64`` frame, byte for byte. A dtype change in
one provider drifted silently until a downstream join noticed — assert the
contract here once.
"""

from __future__ import annotations

import polars as pl


def empty_series_frame() -> pl.DataFrame:
    """Empty ``date``/``value`` frame with the on-chain series contract dtypes."""
    return pl.DataFrame(
        {
            "date": pl.Series("date", [], dtype=pl.Date),
            "value": pl.Series("value", [], dtype=pl.Float64),
        }
    )
