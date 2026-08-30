"""Risk-index builder — glue from a ``RiskModel`` to the Nautilus ``risk_path`` parquet.

Closes the #3168 integration gap: every piece (rails, valuation-z, composite
risk, ``SdcaStrategy`` loading a ``date``/``risk`` parquet) already existed,
but nothing joined them. This module is pure wiring — no new maths.

``build_risk_index()`` runs the already-written pipeline (rails → valuation-z
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
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.valuation import valuation_z_score

_REQUIRED_RAIL_COLUMNS = ("low", "median", "high")
_DIAGNOSTIC_COLUMNS = (
    "date",
    "risk",
    "price",
    "low",
    "median",
    "high",
    "valuation_z",
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
    valuation_weight: float = 1.0,
) -> pl.DataFrame:
    """Join a ``RiskModel`` + price series into the SDCA risk index.

    Returns a frame with ``date``, ``risk``, and diagnostic columns
    (``price``, ``low``, ``median``, ``high``, ``valuation_z``, ``composite_z``).
    Null semantics are inherited from ``valuation_z_score`` /
    ``compute_composite_risk``: a null in any enabled indicator makes that
    day's ``risk`` null (an explicit no-trade day for ``SdcaStrategy``).
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

    valuation_z = valuation_z_score(price, rails["low"], rails["median"], rails["high"])
    indicators = [
        IndicatorWeight(name="valuation", z=valuation_z, weight=valuation_weight),
        *(extra_indicators or []),
    ]
    composite = compute_composite_risk(indicators)
    return pl.DataFrame(
        {
            "date": dates,
            "risk": composite["risk"],
            "price": price,
            "low": rails["low"],
            "median": rails["median"],
            "high": rails["high"],
            "valuation_z": valuation_z,
            "composite_z": composite["composite_z"],
        }
    ).select(list(_DIAGNOSTIC_COLUMNS))


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
