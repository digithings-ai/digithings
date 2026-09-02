"""Two-stage SDCA fit: Stage A weights, Stage B curve, then a regularized copy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.cycle_windows import CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import WEIGHT_PARAM_BY_NAME, SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import (
    RAILS_PROTOCOL,
    SdcaWalkForwardResult,
    run_sdca_walk_forward,
)
from digiquant.strategies.sdca.regularize import regularize_curve_shape, regularize_weights
from digiquant.strategies.sdca.walk_forward import (
    RailsFitter,
    SdcaTrialEvaluator,
    shape_from_params,
)

OVERFIT_NOTES = (
    "Two-stage fit will overfit: Stage A targets a handful of documented cycle "
    "windows and Stage B then tunes the curve on the same history. Keep the "
    "regularized variant (rounded weights, shrunk max rates) as the less "
    "aggressive copy. Not a published digiquant.io number. Do not --push-supabase."
)


class SdcaTwoStageProvenance(BaseModel):
    """Checked-in sidecar for ``btc_composite_aggressive`` / ``_regularized``."""

    model_config = ConfigDict(frozen=True, strict=True)

    variant: Literal["aggressive", "regularized"]
    evaluator: str
    stage_a_weights: dict[str, float]
    stage_b_params: dict[str, float | int | str]
    windows: list[CycleWindow]
    mean_is_vs_flat_dca_pct: float
    mean_oos_vs_flat_dca_pct: float
    beats_flat_dca_oos: bool
    rails_protocol: str
    notes: str
    oos_from_aggressive: bool = Field(
        default=False,
        description="True when OOS numbers were copied from the aggressive run (not re-scored).",
    )


class TwoStagePersistResult(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    aggressive: SdcaTwoStageProvenance
    regularized: SdcaTwoStageProvenance


def freeze_weight_params(weights: SdcaCompositeWeights) -> dict[str, float]:
    """Map a weight model onto the ``*_weight`` keys walk-forward already searches."""
    payload = weights.model_dump()
    return {WEIGHT_PARAM_BY_NAME[name]: value for name, value in payload.items()}


def stage_b_trials(
    weights: SdcaCompositeWeights,
    shape_trials: Sequence[Mapping[str, float | int | str]],
) -> list[dict[str, float | int | str]]:
    """Copy shape trials with Stage A weights frozen (overwriting any weight keys)."""
    frozen = freeze_weight_params(weights)
    return [{**dict(trial), **frozen} for trial in shape_trials]


def run_stage_b_frozen(
    dates: Sequence[date],
    prices: Sequence[float],
    trials: Sequence[Mapping[str, float | int | str]],
    *,
    rails_fitter: RailsFitter,
    evaluator: SdcaTrialEvaluator,
    evaluator_label: str,
    extra_z: Mapping[str, Sequence[float | None]] | None = None,
) -> SdcaWalkForwardResult:
    """Walk-forward curve search with indicator weights already chosen in Stage A."""
    return run_sdca_walk_forward(
        list(dates),
        list(prices),
        [dict(t) for t in trials],
        rails_fitter=rails_fitter,
        evaluator=evaluator,
        evaluator_label=evaluator_label,
        extra_z=dict(extra_z) if extra_z is not None else None,
    )


def persist_two_stage(
    *,
    stage_a_weights: SdcaCompositeWeights,
    stage_b: SdcaWalkForwardResult,
    windows: SdcaCycleWindows,
    dest_dir: Path,
    notes: str = "",
) -> TwoStagePersistResult:
    """Write aggressive + regularized provenance JSON. Does not overwrite btc_optimized."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    extra = (notes + " " + OVERFIT_NOTES).strip()
    aggressive = SdcaTwoStageProvenance(
        variant="aggressive",
        evaluator=stage_b.evaluator_label,
        stage_a_weights=stage_a_weights.model_dump(),
        stage_b_params=dict(stage_b.best_params),
        windows=list(windows.windows),
        mean_is_vs_flat_dca_pct=stage_b.mean_is_vs_flat_dca_pct,
        mean_oos_vs_flat_dca_pct=stage_b.mean_oos_vs_flat_dca_pct,
        beats_flat_dca_oos=stage_b.beats_flat_dca_oos,
        rails_protocol=RAILS_PROTOCOL,
        notes=extra,
        oos_from_aggressive=False,
    )
    reg_weights = regularize_weights(stage_a_weights)
    reg_shape = regularize_curve_shape(shape_from_params(dict(stage_b.best_params)))
    reg_params = {
        **dict(stage_b.best_params),
        **freeze_weight_params(reg_weights),
        "buy_max_rate": reg_shape.buy_max_rate,
        "sell_max_rate": reg_shape.sell_max_rate,
        "buy_knee_risk": reg_shape.buy_knee_risk,
        "sell_knee_risk": reg_shape.sell_knee_risk,
        "buy_curvature": reg_shape.buy_curvature,
        "sell_curvature": reg_shape.sell_curvature,
    }
    regularized = SdcaTwoStageProvenance(
        variant="regularized",
        evaluator=stage_b.evaluator_label,
        stage_a_weights=reg_weights.model_dump(),
        stage_b_params=reg_params,
        windows=list(windows.windows),
        mean_is_vs_flat_dca_pct=stage_b.mean_is_vs_flat_dca_pct,
        mean_oos_vs_flat_dca_pct=stage_b.mean_oos_vs_flat_dca_pct,
        beats_flat_dca_oos=stage_b.beats_flat_dca_oos,
        rails_protocol=RAILS_PROTOCOL,
        notes=(
            extra + " Regularized OOS vs-flat-DCA is copied from the aggressive run "
            "(rounded weights / shrunk rates were not re-scored)."
        ),
        oos_from_aggressive=True,
    )
    (dest_dir / "btc_composite_aggressive.json").write_text(
        aggressive.model_dump_json(indent=2) + "\n"
    )
    (dest_dir / "btc_composite_regularized.json").write_text(
        regularized.model_dump_json(indent=2) + "\n"
    )
    return TwoStagePersistResult(aggressive=aggressive, regularized=regularized)


__all__ = [
    "OVERFIT_NOTES",
    "SdcaTwoStageProvenance",
    "TwoStagePersistResult",
    "freeze_weight_params",
    "persist_two_stage",
    "run_stage_b_frozen",
    "stage_b_trials",
]
