"""Generic per-asset valuation-z ``RiskModel`` (#3175).

Rails from log-price against a fitted long-term trend. Time basis is the
asset's own first cached bar (not a genesis date). Form is ``log_linear``
or ``log_quadratic`` and is recorded on the coefficients. When the fit
span is shorter than ``REFERENCE_SPAN_DAYS`` (~8 years), log-space rail
spreads are widened so a poorly-constrained fit is less confident rather
than confidently wrong.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, field_validator

from digiquant.strategies.sdca.quantile_rails import (
    LABEL_BY_QUANTILE,
    QUANTILE_LABELS,
    QUANTILES,
    QuantileCoefficients,
    evaluate_quadratic_log10,
    fit_quantile_regression,
    quantile_frame,
    rail_span_widen_factor,
    validate_fit_series,
    widen_quantile_matrix,
)

ValuationForm = Literal["log_linear", "log_quadratic"]


class GenericValuationCoefficients(BaseModel):
    """A 7-quantile log-price trend fit, with the provenance to reproduce it.

    ``origin`` is the first fit bar (``t = 0``). ``mu`` is the mean of
    ``(date - origin).days`` over the fit sample and must be reused when
    evaluating on new dates. ``form`` selects the basis; ``widen_factor`` is
    applied in log-space after rearrangement.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    origin: date
    mu: float
    form: ValuationForm
    widen_factor: float = Field(gt=0)
    fit_start: date
    fit_end: date
    fit_rows: int
    notes: str
    quantiles: dict[str, QuantileCoefficients]

    @field_validator("quantiles")
    @classmethod
    def _validate_quantile_keys(
        cls, v: dict[str, QuantileCoefficients]
    ) -> dict[str, QuantileCoefficients]:
        expected = set(QUANTILE_LABELS)
        if set(v) != expected:
            raise ValueError(f"quantiles must cover exactly {sorted(expected)}, got {sorted(v)}")
        return v


def fit_generic_valuation(
    dates: pl.Series,
    price: pl.Series,
    *,
    form: ValuationForm = "log_quadratic",
    notes: str = "",
) -> GenericValuationCoefficients:
    """Fit 7 quantile rails of log10(price) vs calendar time from the first bar."""
    if form not in ("log_linear", "log_quadratic"):
        raise ValueError(f"form must be 'log_linear' or 'log_quadratic', got {form!r}")
    date_list = validate_fit_series(
        dates,
        price,
        caller="fit_generic_valuation",
        fit_kind="log-price trend",
    )
    origin = date_list[0]
    fit_span_days = (date_list[-1] - origin).days

    import numpy as np

    t = np.array([(d - origin).days for d in date_list], dtype=float)
    mu = float(t.mean())
    x = t - mu
    y = np.log10(np.array(price.to_list(), dtype=float))
    if form == "log_linear":
        design = np.column_stack([np.ones_like(x), x])
    else:
        design = np.column_stack([np.ones_like(x), x, x**2])
    quantile_coeffs = fit_quantile_regression(design, y, caller="fit_generic_valuation")
    return GenericValuationCoefficients(
        origin=origin,
        mu=mu,
        form=form,
        widen_factor=rail_span_widen_factor(fit_span_days),
        fit_start=date_list[0],
        fit_end=date_list[-1],
        fit_rows=len(date_list),
        notes=notes,
        quantiles=quantile_coeffs,
    )


def save_coefficients(coefficients: GenericValuationCoefficients, path: Path) -> Path:
    """Persist fitted generic-valuation coefficients as JSON."""
    path.write_text(coefficients.model_dump_json(indent=2) + "\n")
    return path


def load_coefficients(path: Path) -> GenericValuationCoefficients:
    """Load generic-valuation coefficients. JSON mode so ISO dates parse under strict."""
    if not path.exists():
        raise FileNotFoundError(path)
    return GenericValuationCoefficients.model_validate_json(path.read_text())


def _evaluate_rails(coefficients: GenericValuationCoefficients, dates: pl.Series) -> pl.DataFrame:
    if dates.dtype != pl.Date:
        raise ValueError(f"rails requires dates to be pl.Date, got {dates.dtype}")
    if dates.len() == 0:
        raise ValueError("rails requires at least one row")
    if dates.is_null().any():
        raise ValueError("rails requires dates to have no null values")

    import numpy as np

    date_list: list[date] = dates.to_list()
    t = np.array([(d - coefficients.origin).days for d in date_list], dtype=float)
    x = t - coefficients.mu
    values = evaluate_quadratic_log10(coefficients.quantiles, x)
    values = widen_quantile_matrix(values, coefficients.widen_factor)
    return quantile_frame(values)


class GenericValuationRiskModel:
    """``RiskModel`` provider: log-price trend rails, first-bar time basis."""

    def __init__(
        self,
        coefficients: GenericValuationCoefficients,
        *,
        low_quantile: float = 0.10,
        high_quantile: float = 0.95,
    ) -> None:
        if low_quantile not in LABEL_BY_QUANTILE or high_quantile not in LABEL_BY_QUANTILE:
            raise ValueError(f"low/high quantile must be one of {QUANTILES}")
        if not (low_quantile < 0.50 < high_quantile):
            raise ValueError("low_quantile must be < median (0.50) < high_quantile")
        self.coefficients = coefficients
        self._low_label = LABEL_BY_QUANTILE[low_quantile]
        self._high_label = LABEL_BY_QUANTILE[high_quantile]

    def rails_full(self, dates: pl.Series) -> pl.DataFrame:
        """All 7 fitted quantile rails (``q01``..``q99``), non-crossing, widened."""
        return _evaluate_rails(self.coefficients, dates)

    def rails(self, dates: pl.Series) -> pl.DataFrame:
        """``RiskModel`` protocol: ``low``/``median``/``high`` columns."""
        full = self.rails_full(dates)
        return full.select(
            pl.col(self._low_label).alias("low"),
            pl.col("q50").alias("median"),
            pl.col(self._high_label).alias("high"),
        )


__all__ = [
    "ValuationForm",
    "GenericValuationCoefficients",
    "fit_generic_valuation",
    "save_coefficients",
    "load_coefficients",
    "GenericValuationRiskModel",
]
