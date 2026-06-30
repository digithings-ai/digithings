"""Load Slapper calibrations from disk or the DigiQuant strategy store (#1064)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

_STRATEGIES_DIR = Path(__file__).parent
CALIBRATIONS_FILE = _STRATEGIES_DIR / "calibrations.json"
CALIBRATIONS_EXAMPLE = _STRATEGIES_DIR / "calibrations.example.json"

CalibrationSource = Literal["file", "supabase", "example"]


def load_calibrations_file(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Read the gitignored ``calibrations.json`` (or an explicit path)."""
    p = path or CALIBRATIONS_FILE
    if not p.exists():
        raise FileNotFoundError(p)
    data = json.loads(p.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"calibrations file must be a JSON object, got {type(data)}")
    return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}


def load_calibrations_example() -> dict[str, dict[str, Any]]:
    """Placeholder calibrations — not production parity."""
    data = json.loads(CALIBRATIONS_EXAMPLE.read_text())
    return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}


def load_calibrations_from_supabase(
    strategy_ids: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch private calibrations via the service-role client."""
    from digiquant.data.store.client import build_digiquant_client
    from digiquant.data.store.strategies import read_calibration

    client = build_digiquant_client()
    if client is None:
        raise RuntimeError(
            "Supabase credentials missing — set CORE_SUPABASE_URL + CORE_SUPABASE_SERVICE_KEY"
        )

    ids = strategy_ids or []
    if not ids:
        settings_path = _STRATEGIES_DIR / "settings.json"
        settings = json.loads(settings_path.read_text())
        ids = list(settings.get("strategies", {}).keys())

    out: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for sid in ids:
        cal = read_calibration(client, sid)
        if cal:
            out[sid] = dict(cal)
        else:
            missing.append(sid)
    if missing:
        raise RuntimeError(
            f"No calibration rows in strategy_calibrations for: {', '.join(missing)}"
        )
    return out


def merge_trade_start(
    calibration: dict[str, Any], trade_start: str | None
) -> dict[str, Any]:
    """Layer public ``trade_start`` from settings.json onto a calibration dict."""
    merged = dict(calibration)
    if trade_start:
        merged.setdefault("trade_start", trade_start)
    return merged


def resolve_calibrations(
    strategy_id: str,
    *,
    source: CalibrationSource,
    trade_start: str | None = None,
    file_path: Path | None = None,
) -> dict[str, Any]:
    """Return merged calibration params for one strategy."""
    if source == "file":
        all_cals = load_calibrations_file(file_path)
    elif source == "supabase":
        all_cals = load_calibrations_from_supabase([strategy_id])
    else:
        all_cals = load_calibrations_example()
    if strategy_id not in all_cals:
        raise KeyError(f"No calibration for strategy {strategy_id!r}")
    return merge_trade_start(all_cals[strategy_id], trade_start)


def pick_calibration_source(
    *,
    prefer_supabase: bool = False,
    allow_example: bool = False,
) -> CalibrationSource:
    """Choose file → supabase → example/error."""
    if prefer_supabase:
        try:
            load_calibrations_from_supabase()
            return "supabase"
        except Exception as exc:
            logger.warning("Supabase calibrations unavailable: %s", exc)
    if CALIBRATIONS_FILE.exists():
        return "file"
    try:
        load_calibrations_from_supabase()
        return "supabase"
    except Exception as exc:
        logger.debug("Supabase calibrations unavailable: %s", exc)
    if allow_example:
        logger.warning("Using calibrations.example.json — NOT production parity")
        return "example"
    raise FileNotFoundError(
        f"Missing {CALIBRATIONS_FILE} and no Supabase calibrations — "
        "upload with scripts/sync_strategy_calibrations.py or pass --allow-example-calibrations"
    )
