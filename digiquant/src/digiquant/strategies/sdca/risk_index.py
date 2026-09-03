"""Risk-index builder — glue from a ``RiskModel`` to the Nautilus ``risk_path`` parquet.

Closes the #3168 integration gap: every piece (rails, power-law-z, composite
risk, ``SdcaStrategy`` loading a ``date``/``risk`` parquet) already existed,
but nothing joined them. This module is pure wiring — no new maths.

``build_risk_index()`` runs the already-written pipeline (rails → power-law-z
→ composite risk) and returns the two columns ``SdcaStrategy`` needs plus
diagnostic columns for an auditable tearsheet (#3172). ``write_risk_index()``
persists the two-column parquet under every validation
``SdcaStrategy._load_risk_index()`` already enforces, so the writer and the
reader cannot drift apart.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.composite_risk import IndicatorWeight, compute_composite_risk
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z

_REQUIRED_RAIL_COLUMNS = ("low", "median", "high")
_DIAGNOSTIC_COLUMNS = (
    "date",
    "risk",
    "price",
    "low",
    "median",
    "high",
    "power_law_z",
    "composite_z",
)


class RiskIndexBuildResult(BaseModel):
    """JSON-serializable summary returned by ``digiquant_build_sdca_risk_index``."""

    model_config = ConfigDict(strict=True, frozen=True)

    path: str
    row_count: int = Field(ge=0)
    date_start: date
    date_end: date
    null_risk_days: int = Field(ge=0)


def build_risk_index(
    dates: pl.Series,
    price: pl.Series,
    risk_model: RiskModel,
    extra_indicators: list[IndicatorWeight] | None = None,
    power_law_weight: float = 1.0,
    oscillators: SdcaOscillatorSpec | None = None,
    *,
    composite_rolling_window: int | None = None,
    composite_rolling_min_samples: int | None = None,
) -> pl.DataFrame:
    """Join a ``RiskModel`` + price series into the SDCA risk index.

    Returns a frame with ``date``, ``risk``, and diagnostic columns
    (``price``, ``low``, ``median``, ``high``, ``power_law_z``, ``composite_z``).
    Null semantics are inherited from ``power_law_confluence_z`` /
    ``compute_composite_risk``: a null in any enabled indicator makes that
    day's ``risk`` null (an explicit no-trade day for ``SdcaStrategy``).
    ``power_law_z`` here is ``power_law_confluence_z``'s output (whole-history
    power-law leg blended with a rolling trend leg) — ``oscillators`` (default
    ``SdcaOscillatorSpec()``) configures the trend leg's window.
    ``composite_rolling_window`` (default ``None``, off) forwards to
    ``compute_composite_risk``'s rolling re-normalization of the blended
    composite — see that function's docstring.
    """
    dates = _require_date_series(dates, name="dates")
    if price.len() != dates.len():
        raise ValueError(
            f"build_risk_index requires dates and price to have the same length, "
            f"got {dates.len()}, {price.len()}"
        )
    rails = risk_model.rails(dates)
    missing = set(_REQUIRED_RAIL_COLUMNS) - set(rails.columns)
    if missing:
        raise ValueError(f"risk_model.rails() is missing columns: {sorted(missing)}")
    if rails.height != dates.len():
        raise ValueError(
            f"risk_model.rails() must return one row per date, "
            f"got {rails.height} rows for {dates.len()} dates"
        )

    spec = oscillators or SdcaOscillatorSpec()
    power_law_z = power_law_confluence_z(
        dates,
        price,
        rails["low"],
        rails["median"],
        rails["high"],
        trend_window=spec.power_law_trend_window,
    )
    indicators = [
        IndicatorWeight(name="power_law", z=power_law_z, weight=power_law_weight),
        *(extra_indicators or []),
    ]
    composite = compute_composite_risk(
        indicators,
        rolling_window=composite_rolling_window,
        rolling_min_samples=composite_rolling_min_samples,
    )
    payload: dict[str, pl.Series] = {
        "date": dates,
        "risk": composite["risk"],
        "price": price,
        "low": rails["low"],
        "median": rails["median"],
        "high": rails["high"],
        "power_law_z": power_law_z,
        "composite_z": composite["composite_z"],
    }
    extra_z_cols: list[str] = []
    for ind in extra_indicators or []:
        col = f"{ind.name}_z"
        payload[col] = ind.z
        if col not in _DIAGNOSTIC_COLUMNS:
            extra_z_cols.append(col)
    return pl.DataFrame(payload).select([*_DIAGNOSTIC_COLUMNS, *extra_z_cols])


def write_risk_index(df: pl.DataFrame, path: Path | str) -> Path:
    """Write the two-column parquet ``SdcaStrategy._load_risk_index()`` expects.

    Validates ``date`` is ``pl.Date`` (casting ``pl.Datetime``), ``risk`` is
    numeric, there are no null dates, no duplicate dates, and no non-finite
    risk values. Null risk is kept as an explicit no-data day.
    """
    validated = _validate_risk_index_frame(df)
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    validated.write_parquet(dest)
    return dest


def _require_date_series(dates: pl.Series, *, name: str) -> pl.Series:
    if dates.dtype == pl.Date:
        return dates
    if isinstance(dates.dtype, pl.Datetime):
        return dates.cast(pl.Date)
    raise ValueError(f"{name} must be pl.Date, got {dates.dtype}")


def _validate_risk_index_frame(df: pl.DataFrame) -> pl.DataFrame:
    """Return the two-column ``date``/``risk`` frame after reader-side checks."""
    missing = {"date", "risk"} - set(df.columns)
    if missing:
        raise ValueError(f"risk index frame is missing required columns: {sorted(missing)}")
    out = df.select(["date", "risk"])
    date_dtype = out.schema["date"]
    if date_dtype != pl.Date:
        if isinstance(date_dtype, pl.Datetime):
            out = out.with_columns(pl.col("date").cast(pl.Date))
        else:
            raise ValueError(f"risk index 'date' column must be pl.Date, got {date_dtype}")
    risk_dtype = out.schema["risk"]
    if not risk_dtype.is_numeric():
        raise ValueError(f"risk index 'risk' column must be numeric, got {risk_dtype}")
    if out["date"].null_count() > 0:
        raise ValueError("risk index has null date value(s)")
    non_finite = out.filter(pl.col("risk").is_not_null() & ~pl.col("risk").is_finite())
    if non_finite.height > 0:
        bad_dates = non_finite["date"].to_list()
        raise ValueError(f"risk index has non-finite risk value(s) on: {bad_dates}")
    dupes = out.filter(out["date"].is_duplicated())["date"].unique().sort().to_list()
    if dupes:
        raise ValueError(f"risk index has duplicate date(s): {dupes}")
    return out


__all__ = [
    "RiskIndexBuildResult",
    "build_risk_index",
    "write_risk_index",
]
