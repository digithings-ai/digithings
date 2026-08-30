"""BTC power-law (RAQQR) valuation rails — the first concrete ``RiskModel`` (#1082).

Fits 7 quantile rails (1/10/25/50/75/95/99%) as a power-law in log-time, mirroring
the artifact's frozen model but refit from real history rather than trusting its
baked-in coefficients:

    price_q(t) = 10 ** (c + a*x + b*x**2),  x = ln(days_since_genesis(t)) - mu

Each quantile's ``(c, a, b)`` is fit independently via quantile regression
(``statsmodels.regression.quantile_regression.QuantReg``, lazily imported so this
module has no hard dependency on it at import time — see the ``nautilus``/
``indicators`` extras in ``pyproject.toml``). ``mu`` centers ``x`` on the fit
sample and must travel with the coefficients so later predictions use the same
centering. Fitting is exposed here as a plain function; the ``digiquant_fit_btc_power_law``
MCP tool (``mcp_server.py``) is the orchestration layer that sources price history
and calls it — this module has zero data-fetching or MCP dependency, matching the
rest of the ``sdca`` package.

The QuantReg loop, rearrangement, history-length guards, and
``QuantileCoefficients`` live in ``quantile_rails.py`` (#3175). This module is
the BTC-specific configuration: genesis-anchored log-time and quadratic basis.

**Independently-fit quantile curves can cross** (a lower quantile's curve
overtaking a higher one at some ``x``), which would violate ``low < median < high``
downstream in ``valuation.py``. ``rails()``/``rails_full()`` fix this with the
standard rearrangement method (Chernozhukov et al.): sort each row's 7 quantile
values ascending before returning them, rather than trusting the raw regression
output to already be monotonic.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, field_validator

from digiquant.strategies.sdca.quantile_rails import (
    LABEL_BY_QUANTILE,
    MIN_FIT_HISTORY_DAYS,
    QUANTILE_LABELS,
    QUANTILES,
    QuantileCoefficients,
    evaluate_quadratic_log10,
    fit_quantile_regression,
    quantile_frame,
    validate_fit_series,
)

logger = logging.getLogger(__name__)

# Standard convention for public BTC power-law valuation models (e.g. Giovanni
# Santostasi's / PlanB-adjacent corridor charts). Not derived from data — it's the
# origin of the log-time axis, chosen once and then fixed for reproducibility.
BTC_GENESIS_DATE: date = date(2009, 1, 3)

_LABEL_BY_QUANTILE = LABEL_BY_QUANTILE

_COEFFICIENTS_PATH = Path(__file__).parent / "btc_power_law_coefficients.json"
_COEFFICIENTS_EXAMPLE_PATH = Path(__file__).parent / "btc_power_law_coefficients.example.json"


class BtcPowerLawCoefficients(BaseModel):
    """A full 7-quantile BTC power-law fit, with the provenance to reproduce it.

    ``mu`` is the mean of ``ln(days_since_genesis)`` over the fit sample — it must
    be reused (not recomputed) when evaluating the fitted curves on new dates, or
    predictions silently drift off the fit's centering.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    genesis: date
    mu: float
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


def fit_btc_power_law(
    dates: pl.Series,
    price: pl.Series,
    *,
    genesis: date = BTC_GENESIS_DATE,
    notes: str = "",
) -> BtcPowerLawCoefficients:
    """Fit the 7 quantile power-law curves from BTC daily close history.

    ``dates`` must be ``pl.Date``, non-null, strictly increasing, and entirely
    after ``genesis`` (``ln(days_since_genesis)`` is undefined at or before it).
    ``price`` must be non-null, finite, and positive. Raises ``ValueError`` with
    the reason on any violation, including too little history (see
    ``MIN_FIT_HISTORY_DAYS``) — the data-sufficiency guard #1082 asks for.
    """
    date_list = validate_fit_series(
        dates,
        price,
        caller="fit_btc_power_law",
        fit_kind="quadratic-in-log-time",
    )
    if date_list[0] <= genesis:
        raise ValueError(
            f"fit_btc_power_law requires all dates after genesis ({genesis}), "
            f"got a date {date_list[0]} on or before it"
        )

    import numpy as np

    days_since_genesis = np.array([(d - genesis).days for d in date_list], dtype=float)
    raw_x = np.log(days_since_genesis)
    mu = float(raw_x.mean())
    x = raw_x - mu
    y = np.log10(np.array(price.to_list(), dtype=float))
    design = np.column_stack([np.ones_like(x), x, x**2])
    quantile_coeffs = fit_quantile_regression(design, y, caller="fit_btc_power_law")

    return BtcPowerLawCoefficients(
        genesis=genesis,
        mu=mu,
        fit_start=date_list[0],
        fit_end=date_list[-1],
        fit_rows=len(date_list),
        notes=notes,
        quantiles=quantile_coeffs,
    )


def save_coefficients(coefficients: BtcPowerLawCoefficients, path: Path | None = None) -> Path:
    """Persist fitted coefficients as JSON. Defaults to the checked-in real-fit path."""
    p = path or _COEFFICIENTS_PATH
    p.write_text(coefficients.model_dump_json(indent=2) + "\n")
    return p


def load_coefficients(path: Path | None = None) -> BtcPowerLawCoefficients:
    """Load fitted BTC power-law coefficients.

    Without an explicit ``path``, prefers the real fit
    (``btc_power_law_coefficients.json``) and falls back to the checked-in
    placeholder (``btc_power_law_coefficients.example.json`` — synthetic, NOT
    fit to real BTC history) when the real file hasn't been produced yet. Run
    the ``digiquant_fit_btc_power_law`` MCP tool (or ``fit_btc_power_law`` +
    ``save_coefficients`` directly) to produce the real one — see #1082.
    """
    p = path or (_COEFFICIENTS_PATH if _COEFFICIENTS_PATH.exists() else _COEFFICIENTS_EXAMPLE_PATH)
    if not p.exists():
        raise FileNotFoundError(p)
    # model_validate_json (not model_validate(json.loads(...))): JSON mode parses
    # ISO date strings even under strict=True; python mode would reject them.
    coefficients = BtcPowerLawCoefficients.model_validate_json(p.read_text())
    if p == _COEFFICIENTS_EXAMPLE_PATH:
        logger.warning(
            "Loaded placeholder BTC power-law coefficients from %s — synthetic, NOT fit "
            "to real BTC history. See #1082.",
            p,
        )
    return coefficients


def _evaluate_rails(coefficients: BtcPowerLawCoefficients, dates: pl.Series) -> pl.DataFrame:
    if dates.dtype != pl.Date:
        raise ValueError(f"rails requires dates to be pl.Date, got {dates.dtype}")
    if dates.len() == 0:
        raise ValueError("rails requires at least one row")
    if dates.is_null().any():
        raise ValueError("rails requires dates to have no null values")

    import numpy as np

    date_list: list[date] = dates.to_list()
    days_since_genesis = np.array([(d - coefficients.genesis).days for d in date_list], dtype=float)
    # Pre/at-genesis dates have undefined log-time (ln(<=0)) — refused as a null row
    # rather than raising, matching the engine's existing no-data-day convention
    # (valuation.py/composite_risk.py/backtest.py all treat a null row as no-trade).
    valid = days_since_genesis > 0

    raw_x = np.full_like(days_since_genesis, np.nan)
    raw_x[valid] = np.log(days_since_genesis[valid])
    x = raw_x - coefficients.mu
    values = evaluate_quadratic_log10(coefficients.quantiles, x)
    return quantile_frame(values)


class BtcPowerLawRiskModel:
    """``RiskModel`` provider backed by a fitted BTC power-law (RAQQR).

    ``rails()`` satisfies the ``RiskModel`` protocol (low/median/high, for
    ``valuation.py``); ``rails_full()`` additionally exposes all 7 fitted
    quantile rails (#1082's "optional full 7-quantile set") for callers that
    want the wider corridor. ``low_quantile``/``high_quantile`` pick which of
    the 7 fitted rails map to "low"/"high" — median is always ``q50``. The
    default (10th/95th) is a documented judgment call, not validated against
    the reference artifact (network access to it is blocked in the environment
    this was built in — see #1082); revisit once the artifact is reachable.
    """

    def __init__(
        self,
        coefficients: BtcPowerLawCoefficients,
        *,
        low_quantile: float = 0.10,
        high_quantile: float = 0.95,
    ) -> None:
        if low_quantile not in _LABEL_BY_QUANTILE or high_quantile not in _LABEL_BY_QUANTILE:
            raise ValueError(f"low/high quantile must be one of {QUANTILES}")
        if not (low_quantile < 0.50 < high_quantile):
            raise ValueError("low_quantile must be < median (0.50) < high_quantile")
        self.coefficients = coefficients
        self._low_label = _LABEL_BY_QUANTILE[low_quantile]
        self._high_label = _LABEL_BY_QUANTILE[high_quantile]

    def rails_full(self, dates: pl.Series) -> pl.DataFrame:
        """All 7 fitted quantile rails (``q01``..``q99``), non-crossing."""
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
    "BTC_GENESIS_DATE",
    "QUANTILES",
    "QUANTILE_LABELS",
    "MIN_FIT_HISTORY_DAYS",
    "QuantileCoefficients",
    "BtcPowerLawCoefficients",
    "fit_btc_power_law",
    "save_coefficients",
    "load_coefficients",
    "BtcPowerLawRiskModel",
]
