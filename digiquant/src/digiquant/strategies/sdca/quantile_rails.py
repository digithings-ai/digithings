"""Shared quantile-rail fitting for SDCA ``RiskModel`` providers (#3175).

Extracts the machinery that was BTC-specific only in its time basis and
basis functions: seven-quantile regression, IRLS non-convergence
escalation, rearrangement so independently-fit curves never cross, and
the history-length / calendar-span guards. Concrete providers
(``btc_power_law``, ``generic_valuation``) supply the design matrix and
the ``caller`` / ``fit_kind`` strings so their public error messages stay
stable.

``numpy`` and ``statsmodels`` are imported inside the fit/evaluate
functions — same lazy pattern as ``btc_power_law.py``, so importing this
module does not require the ``nautilus`` / ``indicators`` extras.
"""

from __future__ import annotations

from datetime import date

import polars as pl
from pydantic import BaseModel, ConfigDict

QUANTILES: tuple[float, ...] = (0.01, 0.10, 0.25, 0.50, 0.75, 0.95, 0.99)
QUANTILE_LABELS: tuple[str, ...] = ("q01", "q10", "q25", "q50", "q75", "q95", "q99")
LABEL_BY_QUANTILE: dict[float, str] = dict(zip(QUANTILES, QUANTILE_LABELS, strict=True))
MEDIAN_INDEX: int = QUANTILE_LABELS.index("q50")

# Shared floor for trend-style fits (BTC power-law and generic valuation).
# Rolling-z does not use this — it is the fallback for series below it.
MIN_FIT_HISTORY_DAYS = 730

# Span at which a generic trend fit is treated as fully constrained. Shorter
# fits widen log-space rail spreads by ``REFERENCE_SPAN_DAYS / fit_span_days``
# so a poorly-constrained model is less confident, not more.
REFERENCE_SPAN_DAYS = 2922  # 8 * 365.25, truncated to int days


class QuantileCoefficients(BaseModel):
    """One quantile's fitted ``(c, a, b)`` for ``10 ** (c + a*x + b*x**2)``.

    Linear fits store ``b=0``.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    c: float
    a: float
    b: float


def validate_fit_series(
    dates: pl.Series,
    price: pl.Series,
    *,
    caller: str,
    fit_kind: str,
) -> list[date]:
    """Validate date/price series for a trend-style quantile fit.

    ``caller`` and ``fit_kind`` are interpolated into the ``ValueError``
    messages so BTC's existing strings stay byte-stable.
    """
    if dates.dtype != pl.Date:
        raise ValueError(f"{caller} requires dates to be pl.Date, got {dates.dtype}")
    if dates.len() == 0:
        raise ValueError(f"{caller} requires at least one row")
    if price.len() != dates.len():
        raise ValueError(
            f"{caller} requires dates and price to have the same length, "
            f"got {dates.len()}, {price.len()}"
        )
    if dates.is_null().any():
        raise ValueError(f"{caller} requires dates to have no null values")
    date_list: list[date] = dates.to_list()
    if any(date_list[i] >= date_list[i + 1] for i in range(len(date_list) - 1)):
        raise ValueError(f"{caller} requires dates to be strictly increasing")
    if price.is_null().any():
        raise ValueError(f"{caller} requires price to have no null values")
    if not price.is_finite().all():
        raise ValueError(f"{caller} requires price to be finite")
    if not (price > 0).all():
        raise ValueError(f"{caller} requires price to be positive")
    if len(date_list) < MIN_FIT_HISTORY_DAYS:
        raise ValueError(
            f"{caller} requires at least {MIN_FIT_HISTORY_DAYS} daily "
            f"observations for a reliable {fit_kind} fit, got {len(date_list)}"
        )
    fit_span_days = (date_list[-1] - date_list[0]).days
    if fit_span_days < MIN_FIT_HISTORY_DAYS:
        raise ValueError(
            f"{caller} requires at least {MIN_FIT_HISTORY_DAYS} calendar "
            f"days between the first and last date for a reliable {fit_kind} "
            f"fit, got a {fit_span_days}-day span ({date_list[0]} to {date_list[-1]}) "
            f"across {len(date_list)} rows"
        )
    return date_list


def fit_quantile_regression(
    design: object,
    log_prices: object,
    *,
    caller: str,
    max_iter: int = 2000,
) -> dict[str, QuantileCoefficients]:
    """Fit one QuantReg per rail. Escalates IRLS non-convergence to ``ValueError``."""
    import warnings

    from statsmodels.regression.quantile_regression import QuantReg
    from statsmodels.tools.sm_exceptions import ConvergenceWarning, IterationLimitWarning

    quantile_coeffs: dict[str, QuantileCoefficients] = {}
    for q, label in zip(QUANTILES, QUANTILE_LABELS, strict=True):
        # QuantReg.fit's IRLS solver never raises on non-convergence — it
        # silently returns whatever beta the loop was on at max_iter, with
        # only a warnings.warn as the signal. Catch and escalate instead.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = QuantReg(log_prices, design).fit(q=q, max_iter=max_iter)
        non_convergence = [
            w for w in caught if issubclass(w.category, (IterationLimitWarning, ConvergenceWarning))
        ]
        if non_convergence:
            raise ValueError(
                f"{caller}: QuantReg failed to converge for quantile {q} "
                f"({label}): {non_convergence[0].message}"
            )
        params = [float(v) for v in result.params]
        c, a = params[0], params[1]
        b = params[2] if len(params) > 2 else 0.0
        quantile_coeffs[label] = QuantileCoefficients(c=c, a=a, b=b)
    return quantile_coeffs


def evaluate_quadratic_log10(
    quantiles: dict[str, QuantileCoefficients],
    x: object,
) -> object:
    """Evaluate ``10 ** (c + a*x + b*x**2)`` per rail and rearrange (sort) rows."""
    import numpy as np

    x_arr = np.asarray(x, dtype=float)
    n = x_arr.shape[0]
    values = np.full((n, len(QUANTILE_LABELS)), np.nan)
    finite = np.isfinite(x_arr)
    xf = x_arr[finite]
    for j, label in enumerate(QUANTILE_LABELS):
        coeff = quantiles[label]
        values[finite, j] = 10.0 ** (coeff.c + coeff.a * xf + coeff.b * xf**2)
    if finite.any():
        values[finite, :] = np.sort(values[finite, :], axis=1)
    return values


def widen_quantile_matrix(values: object, widen_factor: float) -> object:
    """Scale each row's log-space spread from the median by ``widen_factor``.

    ``widen_factor == 1`` is a no-op. Applied after rearrangement so the
    low < median < high order is preserved.
    """
    import numpy as np

    arr = np.asarray(values, dtype=float)
    if widen_factor == 1.0:
        return arr
    out = arr.copy()
    finite = np.isfinite(out).all(axis=1)
    if not finite.any():
        return out
    log_v = np.log(out[finite])
    log_med = log_v[:, MEDIAN_INDEX]
    log_v = log_med[:, None] + (log_v - log_med[:, None]) * widen_factor
    out[finite] = np.exp(log_v)
    out[finite] = np.sort(out[finite], axis=1)
    return out


def quantile_frame(values: object) -> pl.DataFrame:
    """Turn an ``(n, 7)`` quantile matrix into a labeled Polars frame."""
    import numpy as np

    arr = np.asarray(values, dtype=float)
    return pl.DataFrame(
        {
            label: pl.Series(label, arr[:, j]).fill_nan(None)
            for j, label in enumerate(QUANTILE_LABELS)
        }
    )


def rail_span_widen_factor(fit_span_days: int) -> float:
    """``max(1, REFERENCE_SPAN_DAYS / fit_span_days)`` — 1 once history is long enough."""
    if fit_span_days <= 0:
        raise ValueError(f"fit_span_days must be positive, got {fit_span_days}")
    return max(1.0, REFERENCE_SPAN_DAYS / float(fit_span_days))


__all__ = [
    "QUANTILES",
    "QUANTILE_LABELS",
    "LABEL_BY_QUANTILE",
    "MEDIAN_INDEX",
    "MIN_FIT_HISTORY_DAYS",
    "REFERENCE_SPAN_DAYS",
    "QuantileCoefficients",
    "validate_fit_series",
    "fit_quantile_regression",
    "evaluate_quadratic_log10",
    "widen_quantile_matrix",
    "quantile_frame",
    "rail_span_widen_factor",
]
