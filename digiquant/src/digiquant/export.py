"""Strategy export to target platforms. Writes real artifact (JSON); platform deploy not implemented for all targets."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from digiquant.models import ExportResult

logger = logging.getLogger(__name__)

SUPPORTED_TARGETS = ("nautilus", "tradingview", "alpaca", "quantconnect")

_DEFAULT_EXPORT_DIR = "digiquant/results/exports"


def _validate_export_dir(out_dir: Path) -> Path:
    """Resolve and validate output_dir is within the allowed export root. Raises ValueError if not."""
    allowed_root = Path(os.environ.get("EXPORT_OUTPUT_DIR", _DEFAULT_EXPORT_DIR)).resolve()
    resolved = out_dir.resolve()
    try:
        resolved.relative_to(allowed_root)
        return resolved
    except ValueError:
        raise ValueError(
            f"output_dir '{resolved}' is outside the allowed export root '{allowed_root}'. "
            f"Set EXPORT_OUTPUT_DIR to change the allowed root."
        )


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
    raw_dir = Path(output_dir) if output_dir else Path(_DEFAULT_EXPORT_DIR)
    out_dir = _validate_export_dir(raw_dir)
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
