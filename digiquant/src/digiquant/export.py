"""Strategy export to target platforms. Writes real artifact (JSON); platform deploy not implemented for all targets."""

from __future__ import annotations

import io
import json
import logging
import os
import uuid
import zipfile
from pathlib import Path

from digiquant.models import ExportResult
from digiquant.strategy_specs import _ALIAS_TO_CANONICAL

logger = logging.getLogger(__name__)

SUPPORTED_TARGETS = ("nautilus", "nautilus_bundle", "tradingview", "alpaca", "quantconnect")

_BUNDLE_SUPPORTED_CANONICAL = frozenset({"ema_cross"})

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


def _canonical_strategy_name(strategy_name: str) -> str:
    s = str(strategy_name).strip()
    return _ALIAS_TO_CANONICAL.get(s, s)


def _write_nautilus_bundle_zip(
    *,
    strategy_name: str,
    params: dict[str, float | int | str],
    out_dir: Path,
    run_id: str,
) -> Path:
    canonical = _canonical_strategy_name(strategy_name)
    if canonical not in _BUNDLE_SUPPORTED_CANONICAL:
        raise ValueError(
            f"nautilus_bundle export supports {sorted(_BUNDLE_SUPPORTED_CANONICAL)} only; "
            f"got {strategy_name!r} (canonical {canonical!r})."
        )
    artifact_path = out_dir / f"{strategy_name}_nautilus_bundle_{run_id[:8]}.zip"
    readme = (
        "DigiQuant Nautilus bundle (DigiClone)\n"
        "====================================\n\n"
        f"strategy_name: {strategy_name}\n"
        f"canonical: {canonical}\n\n"
        "params.json — key/value overrides for strategy config.\n"
        "Wire the registered Nautilus strategy from digiquant.strategies.registry.\n\n"
        "Live trading requires explicit human approval per SECURITY.md.\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        zf.writestr("params.json", json.dumps(params, indent=2))
        manifest = {
            "strategy_name": strategy_name,
            "canonical": canonical,
            "digiquant_registry": "digiquant.strategies.registry:get_strategy",
            "python_module": "digiquant.strategies.ema_cross",
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    artifact_path.write_bytes(buf.getvalue())
    return artifact_path


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
    default_write_dir = os.environ.get("EXPORT_OUTPUT_DIR", _DEFAULT_EXPORT_DIR)
    raw_dir = Path(output_dir) if output_dir else Path(default_write_dir)
    out_dir = _validate_export_dir(raw_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if target == "nautilus_bundle":
        artifact_path = _write_nautilus_bundle_zip(
            strategy_name=str(strategy_name),
            params=params,
            out_dir=out_dir,
            run_id=run_id,
        )
        return ExportResult(
            run_id=run_id,
            target=target,
            strategy_name=str(strategy_name),
            artifact_path=str(artifact_path),
            status="ok",
            message="Nautilus-oriented bundle (zip) written; review manifest and params before deploy.",
        )
    artifact_path = out_dir / f"{strategy_name}_{target}_{run_id[:8]}.json"
    payload = {"strategy_name": strategy_name, "target": target, "params": params}
    artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return ExportResult(
        run_id=run_id,
        target=target,
        strategy_name=str(strategy_name),
        artifact_path=str(artifact_path),
        status="ok",
        message="Config exported to artifact; platform deploy not implemented for this target.",
    )
