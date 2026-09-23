"""Multiprocessing worker module for the full-17 aggregate reweight coarse pass.

Mirrors ``stage_a.optimize_stage_a_weights_combined``'s per-combo logic
exactly (same ``SdcaCompositeWeights`` construction, same
``risk_from_weighted_z`` + ``cycle_overlap_score`` calls) so results are
identical to calling the real function -- only the outer loop is
parallelized (fork-based multiprocessing, workers share the loaded data via
copy-on-write instead of re-pickling it per task).

Kept as a separate module (not inlined in the driver script) because
fork-based multiprocessing workers import this module fresh in each child;
module-level globals set by ``init_worker`` before the pool forks are then
inherited via COW, not re-sent per task.
"""

from __future__ import annotations

from datetime import date

from digiquant.strategies.sdca.cycle_windows import SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.stage_a import cycle_overlap_score, risk_from_weighted_z

_DATES: list[date] | None = None
_POWER_LAW_Z: list | None = None
_EXTRA_Z: dict | None = None
_LONG_WINDOWS: SdcaCycleWindows | None = None
_MEDIUM_WINDOWS: SdcaCycleWindows | None = None
_EXTRA_NAMES: tuple[str, ...] | None = None


def init_globals(dates, power_law_z, extra_z, long_windows, medium_windows, extra_names) -> None:
    global _DATES, _POWER_LAW_Z, _EXTRA_Z, _LONG_WINDOWS, _MEDIUM_WINDOWS, _EXTRA_NAMES
    _DATES = dates
    _POWER_LAW_Z = power_law_z
    _EXTRA_Z = extra_z
    _LONG_WINDOWS = long_windows
    _MEDIUM_WINDOWS = medium_windows
    _EXTRA_NAMES = extra_names


def score_chunk(chunk: list[tuple[float, tuple[float, ...]]]):
    """chunk: list of (power_law_value, extra_combo_tuple). Returns list of
    (power_law_value, extra_combo_tuple, long_objective, medium_objective) --
    only the scalars needed to reconstruct any long:medium ratio's combined
    objective downstream, keeping IPC payload small."""
    assert _DATES is not None and _EXTRA_NAMES is not None
    out = []
    for pl_val, combo in chunk:
        payload = dict(zip(_EXTRA_NAMES, combo, strict=True))
        weights = SdcaCompositeWeights(power_law=pl_val, **payload)
        if any(name not in _EXTRA_Z for name in weights.enabled_extras()):
            continue
        try:
            risk = risk_from_weighted_z(_DATES, _POWER_LAW_Z, _EXTRA_Z, weights)
            long_score = cycle_overlap_score(_DATES, risk, _LONG_WINDOWS)
            medium_score = cycle_overlap_score(_DATES, risk, _MEDIUM_WINDOWS)
        except ValueError:
            # Warmup / missing extra z can leave windows all-null; skip, same
            # as optimize_stage_a_weights_combined's own except-continue.
            continue
        out.append((pl_val, combo, long_score.objective, medium_score.objective))
    return out
