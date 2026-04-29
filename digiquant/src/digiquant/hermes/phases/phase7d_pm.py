"""Phase 7D — Portfolio Manager review with risk temperament debate.

Sub-phase order (each is one node, sequential):

    risk-aggressive → risk-conservative → pm-rebalance

The two debaters argue the growth and capital-preservation cases for the
proposed rebalance. Their synthesis (``RiskDebateSummary``) is injected
into the PM's ``phase_inputs`` so the final decision incorporates both
framings. One round, portfolio-level (not per-ticker).

The PM step is two logical operations folded into one LLM call:
  B. Clean-slate (blinded to current weights) → recommended portfolio
  C. Comparison (weights unlocked)            → rebalance decision

Emitted as a single ``RebalanceDecision`` per run into
``state.phase7d_rebalance``. Risk debate output lands in
``state.phase7d_risk_debate``.
"""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field

from digiquant.atlas.phases._node_factory import _shared_context
from digiquant.hermes.state import HermesState


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


class RiskCase(BaseModel):
    """One side of the risk-temperament debate."""

    case: str = Field(max_length=600)


class RiskDebateSummary(BaseModel):
    """Synthesis of one round of aggressive vs. conservative debate.

    Lands in ``state.phase7d_risk_debate`` and is consumed by the PM
    rebalance node as a sibling of the analyst payloads.
    """

    aggressive_case: str = Field(max_length=600)
    conservative_case: str = Field(max_length=600)
    key_tension: str = Field(max_length=300)


def _build_risk_phase_inputs(state: HermesState, role: str) -> dict[str, Any]:
    """Common inputs for both debater nodes.

    Both debaters read the same upstream context (analyst payloads + bias
    row + preferences). Only the ``role`` differs — the skill text drives
    the temperament difference.
    """
    return {
        "segment": "risk-debate",
        "role": role,
        "bias_row": state.phase6_bias_row or {},
        "analyst_payloads": dict(state.phase7c_analysts),
        "preferences": dict(state.config.preferences),
        "current_weights": _current_weights_from_config(state),
    }


def _risk_aggressive_node(state: HermesState) -> dict[str, Any]:
    """Argues the growth/upside case for the proposed rebalance.

    One LLM call. The output is a ``RiskCase`` whose text seeds the
    aggressive arm of the debate summary.
    """
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.hermes.skills import load_skill

    skill_text = load_skill("risk-aggressive")
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=_build_risk_phase_inputs(state, role="aggressive"),
        shared_context=_shared_context(state),
        output_model=RiskCase,
        phase_slug="risk-aggressive",
    )
    # Prior summary (if any) is None on first debate node; conservative
    # node fills in its half + key_tension.
    return {
        "phase7d_risk_debate": {
            "aggressive_case": result.case,
            "conservative_case": "",
            "key_tension": "",
        }
    }


def _risk_conservative_node(state: HermesState) -> dict[str, Any]:
    """Argues the capital-preservation case + synthesizes the debate.

    Reads ``state.phase7d_risk_debate.aggressive_case`` written by the
    aggressive node and emits the conservative case plus a one-line
    ``key_tension`` synthesis.
    """
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.hermes.skills import load_skill

    aggressive = (state.phase7d_risk_debate or {}).get("aggressive_case", "")
    inputs = _build_risk_phase_inputs(state, role="conservative")
    inputs["aggressive_case"] = aggressive

    skill_text = load_skill("risk-conservative")
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=inputs,
        shared_context=_shared_context(state),
        output_model=RiskDebateSummary,
        phase_slug="risk-conservative",
    )
    return {"phase7d_risk_debate": result.model_dump(mode="json")}


def _pm_node(state: HermesState) -> dict[str, Any]:
    """Single LLM call that does clean-slate + comparison in one pass.

    Splitting into two LLM calls was considered; folded into one because
    the comparison step needs both the blinded output and the current
    weights to form the action list. Passing current weights as a
    separate ``phase_inputs.current_weights`` field is explicit enough
    to preserve the blinded-analysis semantics at the prompt level.
    """
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.hermes.skills import load_skill

    # Prefer the dedicated pm skill; fall back to portfolio-manager if present.
    skill_text = _load_pm_skill(load_skill)
    phase_inputs: dict[str, Any] = {
        "segment": "pm-rebalance",
        "bias_row": state.phase6_bias_row or {},
        "analyst_payloads": dict(state.phase7c_analysts),
        # Per-ticker Bull/Bear debate summaries (#429). Empty dict on
        # legacy graphs that skip the debate phase. The PM skill reads
        # ``net_stance`` / ``conviction_delta`` per ticker when present
        # to adjust the analyst conviction at decision time.
        "debate_summaries": {
            ticker: dict(summary) for ticker, summary in state.phase7cd_debates.items()
        },
        "current_weights": _current_weights_from_config(state),
        "preferences": dict(state.config.preferences),
        # Risk temperament debate (#431). When either debater node was
        # skipped (test fixtures, partial graph) the dict is empty/None
        # and the PM skill treats the absence as "no debate context
        # provided" without failing.
        "risk_debate": dict(state.phase7d_risk_debate) if state.phase7d_risk_debate else {},
        # Closed-loop reflection (#432). Empty list on first run; populated
        # by preflight from ``decision_log`` thereafter. Included here so
        # the PM skill can reference past-decision lessons in its
        # rationale field — see ``skills/decision-reflector/SKILL.md`` for
        # the lesson shape.
        "past_context": list(state.prior_context.decision_lessons),
    }
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=_shared_context(state),
        output_model=RebalanceDecision,
        phase_slug="pm-rebalance",
    )
    return {"phase7d_rebalance": result.model_dump(mode="json")}


def _load_pm_skill(loader: Any) -> str:
    """Prefer ``pm-allocation-memo`` skill; fall back to ``portfolio-manager``.

    Only a genuinely-missing skill falls through to the next slug. Parse
    errors (malformed frontmatter) or I/O errors propagate immediately —
    we must not pretend the skill is "missing" when the real issue is
    corruption on disk.
    """
    from digiquant.hermes.skills import SkillNotFoundError

    for slug in ("pm-allocation-memo", "portfolio-manager"):
        try:
            return loader(slug)
        except SkillNotFoundError:
            continue
    raise RuntimeError("neither 'pm-allocation-memo' nor 'portfolio-manager' skill present")


def _current_weights_from_config(state: HermesState) -> dict[str, float]:
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


def build_phase7d_risk_aggressive() -> PipelinePhase:
    """Phase 7D-i: aggressive risk debater (1 LLM call)."""
    return PipelinePhase(
        name="phase7d_risk_aggressive",
        nodes=[NodeSpec(name="risk-aggressive", run=_risk_aggressive_node)],
    )


def build_phase7d_risk_conservative() -> PipelinePhase:
    """Phase 7D-ii: conservative risk debater + debate synthesis."""
    return PipelinePhase(
        name="phase7d_risk_conservative",
        nodes=[NodeSpec(name="risk-conservative", run=_risk_conservative_node)],
    )


def build_phase7d_pm() -> PipelinePhase:
    """Phase 7D-iii: PM rebalance (consumes both upstream debates)."""
    return PipelinePhase(
        name="phase7d_pm",
        nodes=[NodeSpec(name="pm-rebalance", run=_pm_node)],
    )


def build_phase7d() -> list[PipelinePhase]:
    """Return the three sub-phases in execution order.

    Phase 7D is decomposed because the LangGraph pipeline builder runs
    nodes WITHIN a phase in parallel; we need strict sequential order
    (aggressive → conservative → pm) so each LLM call sees the prior
    one's output. Returning three single-node phases is the established
    pattern (see Phase 5).
    """
    return [
        build_phase7d_risk_aggressive(),
        build_phase7d_risk_conservative(),
        build_phase7d_pm(),
    ]


__all__ = [
    "RebalanceAction",
    "RebalanceDecision",
    "RiskCase",
    "RiskDebateSummary",
    "TargetWeight",
    "build_phase7d",
    "build_phase7d_pm",
    "build_phase7d_risk_aggressive",
    "build_phase7d_risk_conservative",
]
