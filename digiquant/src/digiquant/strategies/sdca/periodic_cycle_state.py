"""Small persisted state for the periodic self-optimization cycle (Task 8).

Plain JSON, not a walk-forward interface -- read/written only by
run_periodic_self_optimization_cycle.py between successive invocations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

CycleType = Literal["ablation", "curve"]

# Canonical 17-name pool. Provenance: run_aggregate_reweight_full17_fixed_index.py
# defines SURVIVING_INDICATORS with exactly these names, but scripts/ is not an
# importable package, so the src-side state module carries its own copy. Task 7's
# driver (run_full17_tiered_reweight.py) uses the script-side tuple via
# cross-script import; both must stay in sync at 17 names.
SURVIVING_INDICATORS: tuple[str, ...] = (
    "power_law",
    "m2",
    "rs_eth",
    "dxy",
    "onchain_mvrv",
    "onchain_asopr",
    "onchain_puell",
    "onchain_rhodl",
    "onchain_addr_ratio",
    "fear_greed",
    "weekly_monthly_rsi",
    "weekly_monthly_macd",
    "weekly_rsi",
    "weekly_macd",
    "sma_band",
    "monthly_rsi",
    "monthly_macd",
)


class CycleState(BaseModel, frozen=True):
    cycle_count: int
    next_cycle_type: CycleType
    ablation_pool_remaining: tuple[str, ...]
    best_seen: dict[str, object] | None


def load_cycle_state(path: Path) -> CycleState:
    if not path.exists():
        return CycleState(
            cycle_count=0,
            next_cycle_type="ablation",
            ablation_pool_remaining=tuple(SURVIVING_INDICATORS),
            best_seen=None,
        )
    raw = json.loads(path.read_text())
    pool = tuple(raw["ablation_pool_remaining"])
    if len(pool) < 2:
        pool = tuple(SURVIVING_INDICATORS)
    return CycleState(
        cycle_count=raw["cycle_count"],
        next_cycle_type=raw["next_cycle_type"],
        ablation_pool_remaining=pool,
        best_seen=raw.get("best_seen"),
    )


def save_cycle_state(path: Path, state: CycleState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.model_dump(), indent=2))
