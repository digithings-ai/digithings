"""Phase 7D — Portfolio Manager review.

Two-step sequence per ARCHITECTURE.md:
  B. Clean-slate (blinded to current weights) → recommended portfolio
  C. Comparison (weights unlocked)          → rebalance decision

Both are single LLM calls over Phase 7C analyst payloads. Emitted as a
single ``RebalanceDecision`` per run into ``state.phase7d_rebalance``.
"""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field

from digiquant_atlas.phases._node_factory import _shared_context
from digiquant_atlas.state import AtlasResearchState


class TargetWeight(BaseModel):
    ticker: str = Field(max_length=16)
    target_pct: float = Field(ge=0.0, le=100.0)


class RebalanceAction(BaseModel):
    ticker: str = Field(max_length=16)
    action: Literal["hold", "add", "trim", "exit", "new"]
    current_pct: float | None = None
    target_pct: float
    rationale: str = Field(max_length=500)


class RebalanceDecision(BaseModel):
    """Phase 7D final output — lands in state.phase7d_rebalance."""

    recommended_portfolio: list[TargetWeight] = Field(default_factory=list)
    actions: list[RebalanceAction] = Field(default_factory=list)
    notes: str = Field(default="", max_length=1200)


def _pm_node(state: AtlasResearchState) -> dict[str, Any]:
    """Single LLM call that does clean-slate + comparison in one pass.

    Splitting into two LLM calls was considered; folded into one because
    the comparison step needs both the blinded output and the current
    weights to form the action list. Passing current weights as a
    separate ``phase_inputs.current_weights`` field is explicit enough
    to preserve the blinded-analysis semantics at the prompt level.
    """
    from digigraph.graph.research_agent import run_research_agent

    from digiquant_atlas.skills import load_skill

    # Prefer the dedicated pm skill; fall back to portfolio-manager if present.
    skill_text = _load_pm_skill(load_skill)
    phase_inputs: dict[str, Any] = {
        "segment": "pm-rebalance",
        "bias_row": state.phase6_bias_row or {},
        "analyst_payloads": dict(state.phase7c_analysts),
        "current_weights": _current_weights_from_config(state),
        "preferences": dict(state.config.preferences),
    }
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=_shared_context(state),
        output_model=RebalanceDecision,
    )
    return {"phase7d_rebalance": result.model_dump(mode="json")}


def _load_pm_skill(loader: Any) -> str:
    """Prefer ``pm-allocation-memo`` skill; fall back to ``portfolio-manager``.

    Only a genuinely-missing skill falls through to the next slug. Parse
    errors (malformed frontmatter) or I/O errors propagate immediately —
    we must not pretend the skill is "missing" when the real issue is
    corruption on disk.
    """
    from digiquant_atlas.skills import SkillNotFoundError

    for slug in ("pm-allocation-memo", "portfolio-manager"):
        try:
            return loader(slug)
        except SkillNotFoundError:
            continue
    raise RuntimeError("neither 'pm-allocation-memo' nor 'portfolio-manager' skill present")


def _current_weights_from_config(state: AtlasResearchState) -> dict[str, float]:
    """Pull current portfolio weights from state.config.preferences.

    The upstream config loader (in commit 9's graph assembly) is expected
    to merge ``config/portfolio.json`` into preferences. For now, return
    an empty map on missing data — the PM skill handles that case.
    """
    raw = state.config.preferences.get("current_weights") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def build_phase7d() -> PipelinePhase:
    return PipelinePhase(
        name="phase7d_pm",
        nodes=[NodeSpec(name="pm-rebalance", run=_pm_node)],
    )


__all__ = [
    "RebalanceAction",
    "RebalanceDecision",
    "TargetWeight",
    "build_phase7d",
]
