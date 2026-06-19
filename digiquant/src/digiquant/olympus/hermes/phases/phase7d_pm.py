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

from digiquant.olympus.atlas.data.queries import MARKET_DATA_TABLES
from digiquant.olympus.atlas.phases._node_factory import _shared_context, build_grounding
from digiquant.olympus.hermes.candidates import holdings_from_prior_book
from digiquant.olympus.hermes.state import HermesState


def _pm_tools(state: HermesState):
    """Full-scope query_data + computed tools for the PM. As the decision-maker it MAY
    read the book (positions/nav_history/theses) for rebalance + sizing context — it is
    not blinded like the analysts/debaters."""
    return build_grounding(use_data_tools=True, live_search=False, run_date=state.run_date)


def _risk_tools(state: HermesState):
    """Market-data-scoped tools for the risk debaters (blinded to the book)."""
    return build_grounding(
        use_data_tools=True,
        live_search=False,
        run_date=state.run_date,
        data_tool_tables=MARKET_DATA_TABLES,
    )


class TargetWeight(BaseModel):
    ticker: str = Field()
    target_pct: float = Field(ge=0.0, le=100.0)


class RebalanceAction(BaseModel):
    ticker: str = Field()
    action: Literal["hold", "add", "trim", "exit", "new"]
    current_pct: float | None = None
    target_pct: float
    rationale: str = Field()


class RebalanceDecision(BaseModel):
    """Phase 7D final output — lands in state.phase7d_rebalance."""

    recommended_portfolio: list[TargetWeight] = Field(default_factory=list)
    actions: list[RebalanceAction] = Field(default_factory=list)
    notes: str = Field(default="")


class RiskCase(BaseModel):
    """One side of the risk-temperament debate."""

    case: str = Field()


class RiskDebateSummary(BaseModel):
    """Synthesis of one round of aggressive vs. conservative debate.

    Lands in ``state.phase7d_risk_debate`` and is consumed by the PM
    rebalance node as a sibling of the analyst payloads.
    """

    aggressive_case: str = Field()
    conservative_case: str = Field()
    key_tension: str = Field()


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

    from digiquant.olympus.hermes.skills import load_skill

    skill_text = load_skill("risk-aggressive")
    tools, execute_tool, _ = _risk_tools(state)
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=_build_risk_phase_inputs(state, role="aggressive"),
        shared_context=_shared_context(
            state, context_keys=("pm-rebalance", "digest-delta", "digest-baseline")
        ),
        output_model=RiskCase,
        phase_slug="risk-aggressive",
        tools=tools,
        execute_tool=execute_tool,
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

    from digiquant.olympus.hermes.skills import load_skill

    aggressive = (state.phase7d_risk_debate or {}).get("aggressive_case", "")
    inputs = _build_risk_phase_inputs(state, role="conservative")
    inputs["aggressive_case"] = aggressive

    skill_text = load_skill("risk-conservative")
    tools, execute_tool, _ = _risk_tools(state)
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=inputs,
        shared_context=_shared_context(
            state, context_keys=("pm-rebalance", "digest-delta", "digest-baseline")
        ),
        output_model=RiskDebateSummary,
        phase_slug="risk-conservative",
        tools=tools,
        execute_tool=execute_tool,
    )
    return {"phase7d_risk_debate": result.model_dump(mode="json")}


def _prior_rebalance_payload(state: HermesState) -> dict[str, Any]:
    """Latest published pm-rebalance document body, if any."""
    row = (state.prior_context.latest_segments or {}).get("pm-rebalance") or {}
    payload = row.get("payload") if isinstance(row, dict) else {}
    return dict(payload) if isinstance(payload, dict) else {}


def _prior_analyst_gaps(state: HermesState) -> dict[str, dict[str, Any]]:
    """Held tickers with no fresh analyst output — carry slim prior summaries."""
    held = set(holdings_from_prior_book(state.prior_context.prior_book))
    gaps = held - set(state.phase7c_analysts.keys())
    by_ticker = state.prior_context.prior_analyst_by_ticker
    return {ticker: dict(by_ticker[ticker]) for ticker in gaps if ticker in by_ticker}


def _pm_node(state: HermesState) -> dict[str, Any]:
    """Single LLM call that does clean-slate + comparison in one pass.

    Splitting into two LLM calls was considered; folded into one because
    the comparison step needs both the blinded output and the current
    weights to form the action list. Passing current weights as a
    separate ``phase_inputs.current_weights`` field is explicit enough
    to preserve the blinded-analysis semantics at the prompt level.
    """
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.olympus.hermes.skills import load_skill

    # Prefer the dedicated pm skill; fall back to portfolio-manager if present.
    skill_text = _load_pm_skill(load_skill)
    current_weights = _current_weights_from_config(state)
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
        "current_weights": current_weights,
        "evolution_mode": bool(current_weights),
        "prior_rebalance": _prior_rebalance_payload(state),
        "prior_book": list(state.prior_context.prior_book),
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
        "active_theses": list(state.prior_context.active_theses),
        "portfolio_performance": dict(state.prior_context.portfolio_performance),
        "prior_analyst_gaps": _prior_analyst_gaps(state),
        # Fed rate-decision odds forwarded from the bias_row for the PM's
        # macro-policy awareness. Already fail-soft (None when unavailable).
        "fed_odds": (state.phase6_bias_row or {}).get("fed_odds"),
    }
    tools, execute_tool, _ = _pm_tools(state)
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=_shared_context(
            state, context_keys=("pm-rebalance", "digest-delta", "digest-baseline")
        ),
        output_model=RebalanceDecision,
        phase_slug="pm-rebalance",
        tools=tools,
        execute_tool=execute_tool,
    )
    # An empty recommended_portfolio is a valid 100% CASH stance; Phase 9D books
    # it as a CASH position (#713). No cash-proxy padding here.
    return {"phase7d_rebalance": result.model_dump(mode="json")}


def _load_pm_skill(loader: Any) -> str:
    """Prefer the DB-first ``pm-rebalance-decision`` allocation skill (#713).

    Fallback order: ``pm-rebalance-decision`` (the authoritative node skill that
    matches this node's I/O and the ``RebalanceDecision`` output, always building
    a full ~100% book) → ``portfolio-manager`` (the human-session allocation
    skill) → ``pm-allocation-memo`` (legacy memo skill, kept last for back-compat).

    Only a genuinely-missing skill falls through to the next slug. Parse
    errors (malformed frontmatter) or I/O errors propagate immediately —
    we must not pretend the skill is "missing" when the real issue is
    corruption on disk.
    """
    from digiquant.olympus.hermes.skills import SkillNotFoundError

    tried = ("pm-rebalance-decision", "portfolio-manager", "pm-allocation-memo")
    for slug in tried:
        try:
            return loader(slug)
        except SkillNotFoundError:
            continue
    raise RuntimeError(f"no PM skill found; tried {tried}")


def _current_weights_from_config(state: HermesState) -> dict[str, float]:
    """Pull current portfolio weights from state.config.preferences."""
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
