"""Delta triage — deterministic rules that decide which segments regenerate
on a weekday delta run vs. carry forward from the baseline.

Mirrors the priority table in ``apps/digiquant-atlas/docs/agentic/ARCHITECTURE.md``
§Mon–Sat — Daily Delta. Table-driven so the rules are readable and the
Phase 9 post-mortem can see exactly why a segment ran or didn't.

Tier vocabulary (from the ARCHITECTURE.md §Mon-Sat Daily Delta table):
- **mandatory** — always regenerate (macro, US equities, crypto).
- **high** — regenerate when a material price / yield / policy trigger fires
  (bonds / commodities / forex, threshold >0.5% OR new CB signal).
- **standard** — regenerate on major regional event or flow shift
  (international, institutional).
- **low** — regenerate on per-segment bias shift OR tracked-name move >1.5%
  (alt-data, 11 sectors).

**Correctness boundary (important):** until per-segment price deltas and
per-segment bias rows are wired in, high-tier rules default to **regenerate**
— the rubric says "regen on yield/price move >0.5% OR new CB signal," and
we have neither the price-delta nor CB-signal feed plumbed today. Carrying
on insufficient evidence would suppress a regen the rubric mandates. Low-tier
rules likewise default to regen when no per-segment bias signal is available.
This is conservative in the correct direction for these tiers: extra LLM cost
on a delta day is a smaller loss than a missed material move on bonds.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
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


def _per_segment_bias(state: AtlasResearchState, segment: str) -> str | None:
    """Return yesterday's per-segment bias if the prior digest recorded one.

    Prefers ``snapshot.bias_by_segment[segment]`` when the schema ships that
    field, falls back to the per-segment ``documents`` payload, then to
    ``latest_segments[segment].payload.bias``. Returns None when nothing is
    available — callers treat None as "insufficient evidence, regenerate."
    """
    if not state.prior_context.last_snapshots:
        # Check the latest-segments mapping as a secondary source.
        return _bias_from_latest_segments(state, segment)

    snap = state.prior_context.last_snapshots[0].get("snapshot") or {}
    if isinstance(snap, dict):
        by_seg = snap.get("bias_by_segment")
        if isinstance(by_seg, dict):
            val = by_seg.get(segment)
            if isinstance(val, str) and val:
                return val
    return _bias_from_latest_segments(state, segment)


def _bias_from_latest_segments(state: AtlasResearchState, segment: str) -> str | None:
    """Extract the per-segment bias from the latest published document, if any."""
    # latest_segments is keyed by document_key; segment slug may match doc_type.
    for row in state.prior_context.latest_segments.values():
        if not isinstance(row, dict):
            continue
        if row.get("doc_type") == segment or row.get("segment") == segment:
            payload = row.get("payload") or {}
            if isinstance(payload, dict):
                bias = payload.get("bias")
                if isinstance(bias, str) and bias:
                    return bias
    return None


def _rule_for_segment(
    segment: str, tier: Tier, rule_kind: Literal["always", "price_move", "bias"]
) -> TriageRule:
    """Construct a TriageRule specialized to ``segment``.

    Each rule kind is a function of (state, segment) → (bool, reason); we
    partial-apply the segment here so the evaluator matches the type alias.
    """
    if rule_kind == "always":
        return TriageRule(segment=segment, tier=tier, evaluator=_always)
    if rule_kind == "price_move":
        return TriageRule(
            segment=segment,
            tier=tier,
            evaluator=_bind_segment(_price_move_evaluator(threshold_pct=0.5), segment),
        )
    if rule_kind == "bias":
        return TriageRule(
            segment=segment,
            tier=tier,
            evaluator=_bind_segment(_bias_shifted_evaluator, segment),
        )
    raise ValueError(f"unknown rule kind: {rule_kind}")


def _bind_segment(
    evaluator: Callable[[AtlasResearchState, str], tuple[bool, str]],
    segment: str,
) -> Callable[[AtlasResearchState], tuple[bool, str]]:
    """Currying helper: lock ``segment`` into an evaluator."""

    def _bound(state: AtlasResearchState) -> tuple[bool, str]:
        return evaluator(state, segment)

    return _bound


def _price_move_evaluator(threshold_pct: float):
    """Segment-aware high-tier evaluator."""

    def _eval(state: AtlasResearchState, segment: str) -> tuple[bool, str]:
        if state.data_layer.fallback_used != "supabase":
            return True, f"data_layer_fallback={state.data_layer.fallback_used}"
        segment_bias = _per_segment_bias(state, segment)
        if segment_bias is None:
            return True, f"no_per_segment_bias_threshold={threshold_pct}pct"
        if segment_bias in {"neutral", "mixed"}:
            return False, f"segment_bias_quiet={segment_bias}"
        return True, f"segment_bias={segment_bias}_threshold={threshold_pct}pct"

    return _eval


def _bias_shifted_evaluator(state: AtlasResearchState, segment: str) -> tuple[bool, str]:
    """Low/standard-tier evaluator. Regens on per-segment bias shift."""
    segment_bias = _per_segment_bias(state, segment)
    if segment_bias is None:
        return True, "no_per_segment_bias"
    if segment_bias in {"bullish", "bearish", "strong_bullish", "strong_bearish"}:
        return True, f"segment_bias={segment_bias}"
    return False, f"segment_bias_quiet={segment_bias}"


# ─── Canonical rule table ────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _default_rules() -> tuple[TriageRule, ...]:
    """Build the rule set once — sector count is fixed and YAML is static.

    Returns a tuple for immutability + hashability (so callers can freely
    iterate without worrying about mutation).
    """
    rules: list[TriageRule] = [
        # Phase 1 alt-data — low tier; bias-shift driven.
        _rule_for_segment("alt-sentiment-news", "low", "bias"),
        _rule_for_segment("alt-cta-positioning", "low", "bias"),
        _rule_for_segment("alt-options-derivatives", "low", "bias"),
        _rule_for_segment("alt-politician-signals", "low", "bias"),
        # Phase 2 institutional — standard tier.
        _rule_for_segment("inst-institutional-flows", "standard", "bias"),
        _rule_for_segment("inst-hedge-fund-intel", "standard", "bias"),
        # Phase 3 macro — mandatory.
        _rule_for_segment("macro", "mandatory", "always"),
        # Phase 4 asset classes — mandatory (crypto) + high (others).
        _rule_for_segment("bonds", "high", "price_move"),
        _rule_for_segment("commodities", "high", "price_move"),
        _rule_for_segment("forex", "high", "price_move"),
        _rule_for_segment("crypto", "mandatory", "always"),
        _rule_for_segment("international", "standard", "bias"),
        # Phase 5 equities — mandatory top-down + low per-sector.
        _rule_for_segment("equity", "mandatory", "always"),
    ]
    # 11 sectors are low-tier by default.
    for sector in load_sectors():
        rules.append(_rule_for_segment(sector.slug, "low", "bias"))
    return tuple(rules)


# ─── Public API ──────────────────────────────────────────────────────────────


def evaluate(state: AtlasResearchState) -> DeltaTriageResult:
    """Return per-segment regenerate/carry decisions for a delta run.

    Safe to call on baseline / monthly states too — caller decides whether
    to use the result. On non-delta runs returns an empty decision list.
    """
    if state.run_type != "delta":
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
