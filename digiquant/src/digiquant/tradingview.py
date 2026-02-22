"""TradingView / PyneCore import-export. Not implemented; returns explicit result."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PineExportResult(BaseModel):
    """Result of exporting strategy to Pine (TradingView)."""

    success: bool = Field(False, description="True if export succeeded")
    artifact_path: str | None = Field(None, description="Path to .pine or script")
    message: str = Field("", description="Status or error message")


class PineImportResult(BaseModel):
    """Result of importing strategy from Pine."""

    success: bool = Field(False, description="True if import succeeded")
    strategy_name: str | None = Field(None, description="Parsed strategy name")
    message: str = Field("", description="Status or error message")


def export_to_pine(strategy_name: str, params: dict[str, float | int | str] | None = None) -> PineExportResult:
    """PyneCore/TradingView Pine export not implemented."""
    return PineExportResult(
        success=False,
        artifact_path=None,
        message="Pine/TradingView export not implemented.",
    )


def import_from_pine(pine_path: str) -> PineImportResult:
    """PyneCore Pine import not implemented."""
    return PineImportResult(
        success=False,
        strategy_name=None,
        message="Pine/TradingView import not implemented.",
    )
