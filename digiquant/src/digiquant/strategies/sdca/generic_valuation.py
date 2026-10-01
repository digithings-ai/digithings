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
    MIN_FIT_HISTORY_DAYS,
    QUANTILE_LABELS,
    QUANTILES,
    QuantileCoefficients,
    evaluate_quadratic_log10,
    evenly_spaced_fit_indices,
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
    max_fit_rows: int | None = None,
    fit_lookback_days: int | None = None,
    max_annual_trend: float | None = None,
) -> GenericValuationCoefficients:
    """Fit 7 quantile rails of log10(price) vs calendar time from the first bar.

    ``max_fit_rows`` subsamples *evenly across the full span* (endpoints
    kept) when QuantReg would be slow on a decade of daily bars. Rails are
    still evaluated on every input date — never a 900-day prefix clip.
    ``fit_start``/``fit_end`` remain the full window; ``fit_rows`` is the
    QuantReg sample size. If ``log_quadratic`` IRLS does not converge,
    the fit retries as ``log_linear`` and records that in ``notes``.

    ``fit_lookback_days`` keeps only rows with
    ``(last_date - d).days < fit_lookback_days`` — a trailing window of the
    caller-passed series, sliced BEFORE ``origin``/``mu``/design
    construction so all provenance derives from the sliced window and
    ``notes`` records ``lookback={fit_lookback_days}d``. The slice stays
    within the in-sample series the caller passed, so per-fold refits
    (#3173) remain OOS-clean by construction: the fitter never sees bars
    beyond what the caller hands it, regardless of lookback. A sliced
    window spanning fewer than ``MIN_FIT_HISTORY_DAYS`` raises
    ``ValueError``. ``None`` (default) fits the full passed series —
    existing callers' outputs are unchanged.

    ``max_annual_trend`` post-fit caps the median rail's implied annual
    growth at fit-end: with median ``(c, a, b)`` and ``x_last`` the last
    fit bar's centered time, ``slope_per_day = a + 2*b*x_last`` (linear
    form stores ``b=0``, same formula) and ``g = 10**(slope*365.25) - 1``.
    If ``g`` exceeds the cap, every rail's ``(a, b)`` is scaled by
    ``s = log10(1+cap)/log10(1+g)`` (``c`` kept — level preserved, growth
    bounded, exact for linear) and ``notes`` records
    ``trend_cap={cap} (scaled {s:.3f})``. Guarantee scope: post-scale
    median-rail annualized growth *at fit-end* is ≤ cap by construction
    (rescaling math); OOS evaluated rails inherit it only approximately —
    quadratic curvature and span widening can add slack. ``None`` (default)
    leaves fitted coefficients untouched.
    """
    if form not in ("log_linear", "log_quadratic"):
        raise ValueError(f"form must be 'log_linear' or 'log_quadratic', got {form!r}")
    date_list = validate_fit_series(
        dates,
        price,
        caller="fit_generic_valuation",
        fit_kind="log-price trend",
    )
    if max_annual_trend is not None and max_annual_trend < 0:
        raise ValueError(f"max_annual_trend must be >= 0, got {max_annual_trend!r}")
    if fit_lookback_days is not None and fit_lookback_days <= 0:
        raise ValueError(f"fit_lookback_days must be > 0, got {fit_lookback_days!r}")
    lookback_note = ""
    if fit_lookback_days is not None:
        last_date = date_list[-1]
        start_pos = len(date_list)
        for i, d in enumerate(date_list):
            if (last_date - d).days < fit_lookback_days:
                start_pos = i
                break
        date_list = date_list[start_pos:]
        price = price.slice(start_pos, len(date_list))
        window_days = (date_list[-1] - date_list[0]).days if len(date_list) >= 2 else 0
        if window_days < MIN_FIT_HISTORY_DAYS:
            raise ValueError(
                f"fit_lookback_days={fit_lookback_days} leaves a {window_days}-day window "
                f"({len(date_list)} rows), below MIN_FIT_HISTORY_DAYS={MIN_FIT_HISTORY_DAYS}"
            )
        lookback_note = f"lookback={fit_lookback_days}d"
    origin = date_list[0]
    fit_span_days = (date_list[-1] - origin).days
    idx = evenly_spaced_fit_indices(len(date_list), max_fit_rows)

    import numpy as np

    price_list = price.to_list()
    fit_dates = [date_list[i] for i in idx]
    t = np.array([(d - origin).days for d in fit_dates], dtype=float)
    mu = float(t.mean())
    x = t - mu
    y = np.log10(np.array([price_list[i] for i in idx], dtype=float))
    chosen_form: ValuationForm = form
    if chosen_form == "log_linear":
        design = np.column_stack([np.ones_like(x), x])
    else:
        design = np.column_stack([np.ones_like(x), x, x**2])
    fallback_note = ""
    try:
        quantile_coeffs = fit_quantile_regression(design, y, caller="fit_generic_valuation")
    except ValueError as exc:
        if chosen_form != "log_quadratic" or "QuantReg failed to converge" not in str(exc):
            raise
        # Decade-scale ETH (and similar) quadratic rails often fail IRLS on
        # the tail quantiles. Linear trend on the same full window still
        # scores every day; a 900-day prefix is not an acceptable workaround.
        chosen_form = "log_linear"
        design = np.column_stack([np.ones_like(x), x])
        quantile_coeffs = fit_quantile_regression(design, y, caller="fit_generic_valuation")
        fallback_note = (
            "log_quadratic QuantReg did not converge on this window; fitted log_linear instead."
        )
    subsample_note = ""
    if len(idx) < len(date_list):
        subsample_note = (
            f"QuantReg subsample {len(idx)}/{len(date_list)} evenly spaced bars; "
            "scored on every day in range."
        )
    trend_cap_note = ""
    if max_annual_trend is not None:
        import math

        median = quantile_coeffs[LABEL_BY_QUANTILE[0.50]]
        x_last = float((date_list[-1] - origin).days) - mu
        slope_per_day = median.a + 2.0 * median.b * x_last
        implied_growth = 10.0 ** (slope_per_day * 365.25) - 1.0
        if implied_growth > max_annual_trend:
            scale = math.log10(1.0 + max_annual_trend) / math.log10(1.0 + implied_growth)
            quantile_coeffs = {
                label: qc.model_copy(update={"a": qc.a * scale, "b": qc.b * scale})
                for label, qc in quantile_coeffs.items()
            }
            trend_cap_note = f"trend_cap={max_annual_trend} (scaled {scale:.3f})"
    combined_notes = " ".join(
        p
        for p in (notes.strip(), fallback_note, lookback_note, trend_cap_note, subsample_note)
        if p
    )
    return GenericValuationCoefficients(
        origin=origin,
        mu=mu,
        form=chosen_form,
        widen_factor=rail_span_widen_factor(fit_span_days),
        fit_start=date_list[0],
        fit_end=date_list[-1],
        fit_rows=len(idx),
        notes=combined_notes,
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
