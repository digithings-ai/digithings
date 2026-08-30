"""SDCA ``RiskModel`` selector — bespoke power-law → generic trend → rolling z (#3175).

``digiquant_build_sdca_risk_index`` dispatches on a string so new providers
can be added without changing the MCP signature. This module is the one
place that maps those strings onto constructors.

To add a provider:

1. Implement ``rails(dates) -> DataFrame[low, median, high]`` (satisfies
   ``RiskModel`` structurally — no subclass required).
2. Append the selector name to ``KNOWN_SDCA_RISK_MODELS``.
3. Branch in ``resolve_sdca_risk_model``.
4. Cover it with a ``build_risk_index`` test via this selector.

Do not add RS-driven risk here — that belongs with the RS rotation layer
(#1084), not this WP.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel
from digiquant.strategies.sdca.btc_power_law import load_coefficients as load_btc_coefficients
from digiquant.strategies.sdca.generic_valuation import (
    GenericValuationRiskModel,
    ValuationForm,
    fit_generic_valuation,
)
from digiquant.strategies.sdca.generic_valuation import (
    load_coefficients as load_generic_coefficients,
)
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.rolling_z import DEFAULT_ROLLING_WINDOW, RollingZRiskModel

KNOWN_SDCA_RISK_MODELS: tuple[str, ...] = (
    "btc_power_law",
    "generic_valuation",
    "rolling_z",
)

SdcaRiskModelName = Literal["btc_power_law", "generic_valuation", "rolling_z"]


def resolve_sdca_risk_model(
    name: str,
    *,
    dates: pl.Series,
    price: pl.Series,
    coefficients_path: Path | None = None,
    form: str = "log_quadratic",
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
) -> RiskModel:
    """Construct a ``RiskModel`` from the MCP/selector name.

    Raises ``ValueError`` with ``unknown risk_model '...'`` for a name not
    in ``KNOWN_SDCA_RISK_MODELS`` — the MCP tool surfaces that as error JSON.
    """
    if name not in KNOWN_SDCA_RISK_MODELS:
        raise ValueError(f"unknown risk_model {name!r}")
    if name == "btc_power_law":
        return BtcPowerLawRiskModel(load_btc_coefficients(coefficients_path))
    if name == "generic_valuation":
        if form not in ("log_linear", "log_quadratic"):
            raise ValueError(f"unknown valuation_form {form!r}")
        if coefficients_path is not None:
            return GenericValuationRiskModel(load_generic_coefficients(coefficients_path))
        chosen: ValuationForm = "log_linear" if form == "log_linear" else "log_quadratic"
        return GenericValuationRiskModel(fit_generic_valuation(dates, price, form=chosen))
    return RollingZRiskModel(dates, price, window=rolling_window)


__all__ = [
    "KNOWN_SDCA_RISK_MODELS",
    "SdcaRiskModelName",
    "resolve_sdca_risk_model",
]
