"""ADDM drift detection. Not implemented: returns explicit not-implemented result."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AddmResult(BaseModel):
    """Result of drift check."""

    drift_detected: bool = Field(False, description="True if model/strategy drift detected")
    implemented: bool = Field(False, description="True if drift check was performed")
    score: float | None = Field(None, description="Drift score if computed")
    message: str = Field("", description="Optional detail")


def check_drift(strategy_id: str, baseline_run_id: str | None = None) -> AddmResult:
    """
    Drift check placeholder. No detection implemented; returns implemented=False.
    """
    return AddmResult(
        drift_detected=False,
        implemented=False,
        score=None,
        message="Drift detection not implemented; no check performed.",
    )
