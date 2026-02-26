"""Strategy export to target platforms. Writes real artifact (JSON); platform deploy not implemented for all targets."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from digiquant.models import ExportResult

SUPPORTED_TARGETS = ("nautilus", "tradingview", "alpaca", "quantconnect")


def run_export(
    strategy_name: str,
    params: dict[str, float | int | str] | None = None,
    target: str = "nautilus",
    output_dir: str | Path | None = None,
) -> ExportResult:
    """
    Export strategy + params to a real JSON artifact. Writes file; platform-specific
    deployment (TradingView/Alpaca/QuantConnect) is not implemented.
    """
    params = params or {}
    target = target.lower()
    if target not in SUPPORTED_TARGETS:
        raise ValueError(f"Unsupported target: {target}. Supported: {SUPPORTED_TARGETS}.")
    run_id = f"export-{uuid.uuid4().hex[:8]}"
    default_export_dir = os.environ.get("EXPORT_OUTPUT_DIR", "digiquant/results/exports")
    out_dir = Path(output_dir) if output_dir else Path(default_export_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / f"{strategy_name}_{target}_{run_id[:8]}.json"
    payload = {"strategy_name": strategy_name, "target": target, "params": params}
    artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return ExportResult(
        run_id=run_id,
        target=target,
        strategy_name=strategy_name,
        artifact_path=str(artifact_path),
        status="ok",
        message="Config exported to artifact; platform deploy not implemented for this target.",
    )
