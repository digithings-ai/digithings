"""Delta triage — deterministic rules that decide which segments regenerate
on a weekday delta run vs. carry forward from the baseline.

Mirrors the priority table in ``apps/digiquant-atlas/docs/agentic/ARCHITECTURE.md``
§Mon–Sat — Daily Delta. Table-driven so the rules are readable and the
Phase 9 post-mortem can see exactly why a segment ran or didn't.

Tier vocabulary:
- **mandatory** — always regenerate (macro, US equities, crypto).
- **high** — regenerate when a material price / yield / policy trigger fires.
- **standard** — regenerate on major regional event or flow shift.
- **low** — regenerate on bias shift in prior digest or tracked-name move >1.5%.

The rules intentionally stay coarse at this layer. Finer per-sector
logic lives in the caller (Phase 9 can propose new rules without code
changes if the rule set is YAML-driven in a later commit).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Literal  # noqa: F401 — heterogeneous rule signatures

from digiquant_atlas.sectors_config import load_sectors
from digiquant_atlas.state import (
    AtlasResearchState,
    Carried,
    DeltaTriageDecision,
    DeltaTriageResult,
)


Tier = Literal["mandatory", "high", "standard", "low"]


@dataclass(frozen=True)
class TriageRule:
    """Per-segment rule. ``evaluator`` returns (regenerate, reason)."""

    segment: str
    tier: Tier
    evaluator: Callable[[AtlasResearchState], tuple[bool, str]]


# ─── Rule primitives ─────────────────────────────────────────────────────────


def _always(_: AtlasResearchState) -> tuple[bool, str]:
    return True, "mandatory_tier"


def _price_move_trigger(threshold_pct: float):
    """Trigger if price_technicals freshness says the data layer is current
    AND prior digest indicates a move ≥ threshold_pct in this segment.

    The state today does not carry per-segment price deltas; we rely on
    the data-layer freshness probe as a proxy. When staleness forces a
    fallback, we default to regenerate (caller preference: prefer LLM
    cost over stale reads on delta days with stale data).
    """

    def _inner(state: AtlasResearchState) -> tuple[bool, str]:
        if state.data_layer.fallback_used != "supabase":
            return True, f"data_layer_fallback={state.data_layer.fallback_used}"
        prior_bias = _prior_bias_for_segment_from_snapshots(state)
        if prior_bias is None:
            return True, "no_prior_bias_observation"
        # Placeholder for per-segment price move: until a separate feed
        # is wired, we regenerate when the prior digest signals bias
        # stronger than neutral. This is conservative.
        if prior_bias not in {"neutral", "mixed"}:
            return True, f"prior_bias={prior_bias}_threshold={threshold_pct}pct"
        return False, f"prior_bias={prior_bias}_below_threshold"

    return _inner


def _bias_shifted(state: AtlasResearchState) -> tuple[bool, str]:
    """Low-tier rule: regenerate if the prior digest's bias row shows movement."""
    prior_bias = _prior_bias_for_segment_from_snapshots(state)
    if prior_bias is None:
        return True, "no_prior_bias"
    if prior_bias in {"bullish", "bearish", "strong_bullish", "strong_bearish"}:
        return True, f"bias_shift_candidate_{prior_bias}"
    return False, f"prior_bias_quiet_{prior_bias}"


def _prior_bias_for_segment_from_snapshots(state: AtlasResearchState) -> str | None:
    """Look up yesterday's bias row, if any, and return a coarse stance."""
    if not state.prior_context.last_snapshots:
        return None
    latest = state.prior_context.last_snapshots[0]
    snap = latest.get("snapshot") or {}
    if isinstance(snap, dict):
        return str(snap.get("bias") or "") or None
    return None


# ─── Canonical rule table ────────────────────────────────────────────────────


def _default_rules() -> list[TriageRule]:
    rules: list[TriageRule] = [
        # Phase 1 alt-data — low tier; bias-shift driven.
        TriageRule("alt-sentiment-news", "low", _bias_shifted),
        TriageRule("alt-cta-positioning", "low", _bias_shifted),
        TriageRule("alt-options-derivatives", "low", _bias_shifted),
        TriageRule("alt-politician-signals", "low", _bias_shifted),
        # Phase 2 institutional — standard tier.
        TriageRule("inst-institutional-flows", "standard", _bias_shifted),
        TriageRule("inst-hedge-fund-intel", "standard", _bias_shifted),
        # Phase 3 macro — mandatory.
        TriageRule("macro", "mandatory", _always),
        # Phase 4 asset classes — mandatory (crypto) + high (others).
        TriageRule("bonds", "high", _price_move_trigger(0.5)),
        TriageRule("commodities", "high", _price_move_trigger(0.5)),
        TriageRule("forex", "high", _price_move_trigger(0.5)),
        TriageRule("crypto", "mandatory", _always),
        TriageRule("international", "standard", _bias_shifted),
        # Phase 5 equities — mandatory top-down + low per-sector.
        TriageRule("equity", "mandatory", _always),
    ]
    # 11 sectors are low-tier by default.
    for sector in load_sectors():
        rules.append(TriageRule(sector.slug, "low", _bias_shifted))
    return rules


# ─── Public API ──────────────────────────────────────────────────────────────


def evaluate(state: AtlasResearchState) -> DeltaTriageResult:
    """Return per-segment regenerate/carry decisions for a delta run.

    Safe to call on baseline / monthly states too — caller decides whether
    to use the result. On non-delta runs the rules degenerate to "all
    mandatory" via the default rule set; by convention callers only
    invoke this when ``state.run_type == 'delta'``.
    """
    if state.run_type != "delta":
        # Degenerate result: caller must not use triage outputs on baseline.
        return DeltaTriageResult(
            evaluated_at=state.run_date,
            baseline_date=state.baseline_date or state.run_date,
            decisions=[],
        )
    if state.baseline_date is None:
        raise ValueError("triage.evaluate: delta run requires baseline_date on state")

    decisions: list[DeltaTriageDecision] = []
    for rule in _default_rules():
        regenerate, reason = rule.evaluator(state)
        decisions.append(
            DeltaTriageDecision(
                segment=rule.segment,
                decision="regenerate" if regenerate else "carry",
                reason=reason,
                tier=rule.tier,
            )
        )
    return DeltaTriageResult(
        evaluated_at=state.run_date,
        baseline_date=state.baseline_date,
        decisions=decisions,
    )


def make_triage_gate(
    result: DeltaTriageResult,
) -> Callable[[AtlasResearchState, str], Carried | None]:
    """Return a gate callable compatible with phases._node_factory.build_segment_node.

    For each (state, segment) the gate returns either None (regenerate) or
    a Carried marker (short-circuit). Phase nodes that build via the
    generic factory accept this callable through ``triage_gate=``.
    """
    lookup: dict[str, DeltaTriageDecision] = {d.segment: d for d in result.decisions}

    def _gate(state: AtlasResearchState, segment: str) -> Carried | None:
        decision = lookup.get(segment)
        if decision is None or decision.decision == "regenerate":
            return None
        baseline = state.baseline_date or state.run_date
        return Carried(baseline_date=baseline, reason=decision.reason)

    return _gate


__all__ = [
    "Tier",
    "TriageRule",
    "evaluate",
    "make_triage_gate",
]
