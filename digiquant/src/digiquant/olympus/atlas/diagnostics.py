"""Build the per-run diagnostics row (usage / cost / success rates) — #663.

Reads the digigraph usage accumulator + the final pipeline state and produces a flat
row for the ``atlas_run_diagnostics`` table. ``est_cost_usd`` is an ESTIMATE from a
tunable rate table (verify against console.x.ai).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any  # noqa  # scored-lint suppression: heterogeneous state + row payloads

from digigraph import usage

logger = logging.getLogger(__name__)

# OpenRouter Auto Router pricing varies by routed model. These are weighted
# estimates based on OpenRouter's mid-tier model costs (2026-06); verify
# against your OpenRouter usage dashboard. est_cost_usd is explicitly an
# estimate, not a billed figure (#694).
_PRICING = {"input_per_mtok": 1.00, "output_per_mtok": 2.00, "per_source": 0.0075}

# State containers holding SegmentSlots (dict slug->slot) + the scalar macro slot.
_DICT_OUTPUT_FIELDS = (
    "phase1_outputs",
    "phase2_outputs",
    "phase4_outputs",
    "phase5_outputs",
    "phase7c_analysts",
)


def _slot_source(slot: Any) -> str | None:
    return getattr(getattr(slot, "payload", None), "source", None)


def segment_counts(state: Any) -> dict[str, int]:
    """Count produced segments by freshness (today=ok, carried). Failures crash the run,
    so within a run all present segments are ok/carried; run-level failure is the status."""
    ok = carried = 0
    if state is None:
        return {"total": 0, "ok": 0, "carried": 0, "failed": 0}
    slots: list[Any] = []
    for field in _DICT_OUTPUT_FIELDS:
        d = getattr(state, field, None)
        if isinstance(d, dict):
            slots.extend(d.values())
    scalar = getattr(state, "phase3_output", None)
    if scalar is not None:
        slots.append(scalar)
    for slot in slots:
        src = _slot_source(slot)
        if src == "carried":
            carried += 1
        elif src is not None:
            ok += 1
    return {"total": ok + carried, "ok": ok, "carried": carried, "failed": 0}


def estimate_cost_usd(snap: dict[str, Any], pricing: dict[str, float] | None = None) -> float:
    p = pricing or _PRICING
    return (
        snap["prompt_tokens"] / 1e6 * p["input_per_mtok"]
        + snap["completion_tokens"] / 1e6 * p["output_per_mtok"]
        + snap["sources_used"] * p["per_source"]
    )


def build_row(
    *,
    run_id: str,
    run_type: str,
    run_date: date,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    state: Any = None,
    error: str | None = None,
    model: str | None = None,
    pricing: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Assemble the flat ``atlas_run_diagnostics`` row from usage + state + run metadata."""
    snap = usage.snapshot()
    seg = segment_counts(state)
    duration_s = round((finished_at - started_at).total_seconds(), 1)
    return {
        "run_id": run_id,
        "run_type": run_type,
        "run_date": run_date.isoformat(),
        "model": model or (",".join(snap["models"]) or None),
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_s": duration_s,
        "llm_calls": snap["llm_calls"],
        "prompt_tokens": snap["prompt_tokens"],
        "completion_tokens": snap["completion_tokens"],
        "total_tokens": snap["total_tokens"],
        "search_calls": snap["search_calls"],
        "sources_used": snap["sources_used"],
        "grounding_ok": snap["grounding_ok"],
        "grounding_failed": snap["grounding_failed"],
        "est_cost_usd": round(estimate_cost_usd(snap, pricing), 4),
        "segments_total": seg["total"],
        "segments_ok": seg["ok"],
        "segments_carried": seg["carried"],
        "segments_failed": seg["failed"],
        "error_summary": (error or "")[:1000],
        "breakdown": {"by_kind": snap["by_kind"], "segments": seg, "models": snap["models"]},
    }


def write_row(client: Any, row: dict[str, Any]) -> bool:
    """Upsert the diagnostics row on ``run_id``. Fail-soft — never raises (returns False),
    so a missing table or transient write error can't break a pipeline run."""
    try:
        client.table("atlas_run_diagnostics").upsert(row, on_conflict="run_id").execute()
        return True
    except Exception as exc:  # noqa: BLE001 — diagnostics must never break a run
        logger.warning("run diagnostics write failed (%s); skipping", exc)
        return False
