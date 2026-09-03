#!/usr/bin/env python3
"""Emit one real SDCA tearsheet JSON for a research trial — zero production writes.

Part of the SDCA research loop (see ``src/digiquant/strategies/sdca/RESEARCH_STATE.md``):
one CLI call → one real ``TearsheetData`` JSON, generated through the exact same
Nautilus + DCA-shaping + serialization path that produces the published
``btc_sdca`` tearsheet, but with arbitrary indicator weights / curve / price
source and writing only to a gitignored scratch directory. Never touches
``settings.json``, any preset file, ``btc_optimized_provenance.json``, or
Supabase (``push_supabase`` is hardcoded false; there is no flag for it).

Preview a trial in the browser:

    python scripts/emit_sdca_trial_tearsheet.py --trial-id my_trial \\
        --indicator-weights '{"power_law": 1.0, "m2": 0.5, "dxy": 0.5}'
    cd ../frontend/digiquant-web && npm run dev
    open http://127.0.0.1:3000/strategies/preview/?file=my_trial

Reuses ``generate_tearsheets.run_and_write`` as-is. Two of its internals are
monkeypatched in-process (not touching the file on disk) only when the
corresponding flag is passed, since ``run_and_write`` does not expose these
knobs as parameters:
  - ``--curve-nodes``: ``run_and_write`` always resolves the curve by preset
    *name* via ``presets.load_preset``; a raw 21-node curve needs a synthetic
    preset injected under that lookup.
  - ``--rolling-window``: ``materialize_sdca_risk_index`` (in
    generate_tearsheets.py) does not forward ``composite_rolling_window`` to
    ``build_risk_index``, even though ``build_risk_index`` itself supports it.
Both patches are local to this process and this one call.

The Nautilus strategy registry is keyed by fixed strings ("btc_sdca"/"sdca"),
not by trial id — so ``run_and_write`` always runs under the "sdca" registry
alias internally, writing "sdca.json"; this script then copies that file to
"<trial-id>.json" in the requested output dir.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_YAHOO = DIGIQUANT_ROOT / "data" / "price-history"
DEFAULT_CACHE_COINBASE = DIGIQUANT_ROOT / "data" / "price-history-coinbase"
DEFAULT_OUTPUT_DIR = DIGIQUANT_ROOT / ".scratch" / "tearsheets"

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_TRIAL_STRATEGY_KEY = "sdca"  # registry alias for SdcaStrategy — see module docstring
_CUSTOM_PRESET_NAME = "_trial_custom_curve"


def _install_curve_nodes_patch(curve_nodes: list[float], long_only: bool) -> None:
    """Make ``presets.load_preset(_CUSTOM_PRESET_NAME)`` return a synthetic preset.

    ``run_and_write`` imports ``load_preset`` fresh (``from ...presets import
    load_preset``) on every call, so patching the module attribute before
    calling it is picked up — this process only ever makes one such call.
    """
    from digiquant.strategies.sdca import presets as presets_mod
    from digiquant.strategies.sdca.presets import SdcaPreset

    custom = SdcaPreset(
        curve_nodes=tuple(float(n) for n in curve_nodes),
        long_only=long_only,
        description="Trial curve — ad-hoc nodes from emit_sdca_trial_tearsheet.py, not a catalog preset.",
    )
    original_load_preset = presets_mod.load_preset

    def patched_load_preset(name: str):
        if name == _CUSTOM_PRESET_NAME:
            return custom
        return original_load_preset(name)

    presets_mod.load_preset = patched_load_preset


def _install_rolling_window_patch(rolling_window: int, rolling_min_samples: int | None) -> None:
    """Forward ``composite_rolling_window``/``_min_samples`` into risk-index build.

    ``generate_tearsheets.materialize_sdca_risk_index`` is called by bare name
    from within ``run_and_write`` (same module), so patching the module
    attribute here is picked up the same way as the preset patch above.
    """
    import generate_tearsheets as gt
    import polars as pl

    from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
    from digiquant.strategies.sdca.risk_index import build_risk_index, write_risk_index

    def patched_materialize(
        ohlcv,
        output_path,
        *,
        coefficients_path=None,
        extra_indicators=None,
        power_law_weight: float = 1.0,
    ):
        ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
        dates = ohlcv[ts_col]
        if dates.dtype != pl.Date:
            dates = dates.cast(pl.Date)
        model = BtcPowerLawRiskModel(load_coefficients(coefficients_path))
        index = build_risk_index(
            dates,
            ohlcv["close"],
            model,
            extra_indicators=extra_indicators,
            power_law_weight=power_law_weight,
            composite_rolling_window=rolling_window,
            composite_rolling_min_samples=rolling_min_samples,
        )
        write_risk_index(index, output_path)
        return index

    gt.materialize_sdca_risk_index = patched_materialize


def build_synthetic_settings(
    *,
    symbol: str,
    label: str,
    preset_name: str,
    long_only: bool,
    indicator_weights: dict,
    risk_model: str,
) -> dict:
    """settings.json shape, defaults copied from disk, strategies replaced by one trial entry."""
    import generate_tearsheets as gt

    base = gt.load_settings()
    settings = {"defaults": copy.deepcopy(base["defaults"])}
    settings["strategies"] = {
        _TRIAL_STRATEGY_KEY: {
            "symbol": symbol,
            "label": label,
            "kind": "dca",
            "strategy_type": "sdca",
            "sdca": {
                "preset": preset_name,
                "risk_model": risk_model,
                "long_only": long_only,
                "initial_cash": float(settings["defaults"]["initial_capital"]),
                "indicator_weights": indicator_weights,
            },
        }
    }
    return settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trial-id", required=True, help="Output basename, e.g. 'rolling_v2' -> rolling_v2.json")
    parser.add_argument("--symbol", default="BTC-USD", help="Instrument symbol (default: BTC-USD)")
    parser.add_argument(
        "--indicator-weights",
        required=True,
        help='JSON object, e.g. \'{"power_law": 1.0, "m2": 0.5, "dxy": 0.5}\'. '
        "Unlisted fields default to 0.0 (power_law defaults to 1.0).",
    )
    preset_group = parser.add_mutually_exclusive_group()
    preset_group.add_argument("--preset", help="Named preset from presets.json, e.g. btc_optimized")
    preset_group.add_argument(
        "--curve-nodes", help="JSON array of 21 floats (risk 0..100 in steps of 5) — an ad-hoc curve"
    )
    parser.add_argument(
        "--long-only",
        action="store_true",
        help="Only used with --curve-nodes (a named --preset carries its own long_only).",
    )
    parser.add_argument("--risk-model", default="btc_power_law", help="Risk model id (default: btc_power_law)")
    parser.add_argument("--price-source", choices=("yahoo", "coinbase"), default="yahoo")
    parser.add_argument("--cache-dir", type=Path, help="Override the --price-source default cache dir")
    parser.add_argument("--rolling-window", type=int, help="Composite rolling-z window in days (default: off)")
    parser.add_argument(
        "--rolling-min-samples",
        type=int,
        help="Rolling min_samples (default: max(20, window // 2)); only meaningful with --rolling-window",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if not args.preset and not args.curve_nodes:
        parser.error("one of --preset or --curve-nodes is required")
    if args.long_only and not args.curve_nodes:
        parser.error("--long-only only applies to --curve-nodes (a --preset carries its own long_only)")
    if args.rolling_min_samples is not None and args.rolling_window is None:
        parser.error("--rolling-min-samples requires --rolling-window")

    try:
        indicator_weights = json.loads(args.indicator_weights)
    except json.JSONDecodeError as exc:
        parser.error(f"--indicator-weights is not valid JSON: {exc}")
    if not isinstance(indicator_weights, dict):
        parser.error("--indicator-weights must be a JSON object")

    curve_nodes = None
    if args.curve_nodes:
        try:
            curve_nodes = json.loads(args.curve_nodes)
        except json.JSONDecodeError as exc:
            parser.error(f"--curve-nodes is not valid JSON: {exc}")
        if not isinstance(curve_nodes, list) or len(curve_nodes) != 21:
            parser.error(f"--curve-nodes must be a JSON array of 21 floats, got {curve_nodes!r}")

    cache_dir = args.cache_dir or (
        DEFAULT_CACHE_COINBASE if args.price_source == "coinbase" else DEFAULT_CACHE_YAHOO
    )
    if not cache_dir.exists():
        parser.error(f"cache dir does not exist: {cache_dir}")

    import generate_tearsheets as gt
    from _env import load_repo_env

    load_repo_env()

    preset_name = _CUSTOM_PRESET_NAME if curve_nodes is not None else str(args.preset)
    if curve_nodes is not None:
        _install_curve_nodes_patch(curve_nodes, args.long_only)
    if args.rolling_window is not None:
        _install_rolling_window_patch(args.rolling_window, args.rolling_min_samples)

    settings = build_synthetic_settings(
        symbol=args.symbol,
        label=args.trial_id,
        preset_name=preset_name,
        long_only=args.long_only,
        indicator_weights=indicator_weights,
        risk_model=args.risk_model,
    )

    logger.info(
        "Trial %s: symbol=%s price_source=%s cache_dir=%s preset=%s weights=%s rolling_window=%s",
        args.trial_id,
        args.symbol,
        args.price_source,
        cache_dir,
        preset_name,
        indicator_weights,
        args.rolling_window,
    )

    with tempfile.TemporaryDirectory(prefix="sdca_trial_") as tmp_out:
        entry = gt.run_and_write(
            _TRIAL_STRATEGY_KEY,
            args.symbol,
            settings,
            cache_dir,
            Path(tmp_out),
            cal_source="n/a",
            push_supabase=False,
            signal_delay_days=0,
        )
        if entry is None:
            logger.error("run_and_write produced no tearsheet — see logs above")
            raise SystemExit(1)

        args.output_dir.mkdir(parents=True, exist_ok=True)
        dest = args.output_dir / f"{args.trial_id}.json"
        shutil.copyfile(Path(tmp_out) / f"{_TRIAL_STRATEGY_KEY}.json", dest)

    logger.info(
        "Wrote %s | net %.1f%% | maxDD %.1f%% | vs_flat_dca %s%%",
        dest,
        entry["net_profit_pct"],
        entry["max_drawdown_pct"],
        f"{entry['vs_flat_dca_pct']:.1f}" if entry.get("vs_flat_dca_pct") is not None else "n/a",
    )
    logger.info(
        "Preview: npm run dev (in frontend/digiquant-web), then open "
        "http://127.0.0.1:3000/strategies/preview/?file=%s",
        args.trial_id,
    )


if __name__ == "__main__":
    main()
