"""Delta triage — deterministic rules that decide which segments regenerate
on a weekday delta run vs. carry forward from the baseline.

Mirrors the priority table in ``digiquant/src/digiquant/atlas/docs/agentic/ARCHITECTURE.md``
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

**Signals available** (post-#438):
- **price deltas** (``state.price_deltas``): pct_change of the two latest
  trading-day closes, keyed by ticker. Triage phase populates this from
  ``price_history`` before evaluating rules. A missing ticker means "no
  signal" (not "zero move") — high-tier rules conservatively regen.
- **per-segment bias**: from ``prior_context.last_snapshots[0].snapshot``
  (preferred path) or per-segment ``documents`` rows (fallback). A
  ``neutral`` / ``mixed`` bias paired with a quiet price-delta is what
  permits a high-tier carry; either signal pointing toward action regens.

The CB-signal feed (e.g. an FOMC-day flag) is still not plumbed; high-tier
rules treat its absence as silent (not a regen trigger). When that signal
lands, the high-tier evaluator can OR it against the price-delta condition
without changing the carry-vs-regen contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Literal  # noqa: F401 — heterogeneous rule signatures

from digiquant.atlas.sectors_config import load_sectors
from digiquant.atlas.state import (
    AtlasResearchState,
    Carried,
    DeltaTriageDecision,
    DeltaTriageResult,
)
from digiquant.atlas.triage_signals import max_abs_move_for_segment


# Default price-move thresholds (fractional, not percent — matches the
# ``state.price_deltas`` value scale). Sourced from the ARCHITECTURE.md
# Mon–Sat Daily Delta table; exported as constants so the test suite can
# pin them and downstream callers can override per-segment if needed.
HIGH_TIER_PCT_THRESHOLD: float = 0.005  # 0.5% — bonds, commodities, forex
LOW_TIER_PCT_THRESHOLD: float = 0.015  # 1.5% — sectors, alt-data


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
    segment: str,
    tier: Tier,
    rule_kind: Literal["always", "price_move", "bias", "bias_or_price"],
) -> TriageRule:
    """Construct a TriageRule specialized to ``segment``.

    Each rule kind is a function of (state, segment) -> (bool, reason); we
    partial-apply the segment here so the evaluator matches the type alias.

    Rule kinds:
    - ``always`` -- mandatory tier; always regenerate.
    - ``price_move`` -- high-tier; regen on price-delta > 0.5% (or fallback /
      no data); see :func:`_price_move_evaluator`.
    - ``bias_or_price`` -- low-tier; regen on bias shift OR tracked-name
      move > 1.5%; see :func:`_low_tier_evaluator`.
    - ``bias`` -- standard-tier; regen on bias shift only.
    """
    if rule_kind == "always":
        return TriageRule(segment=segment, tier=tier, evaluator=_always)
    if rule_kind == "price_move":
        return TriageRule(
            segment=segment,
            tier=tier,
            evaluator=_bind_segment(
                _price_move_evaluator(threshold=HIGH_TIER_PCT_THRESHOLD), segment
            ),
        )
    if rule_kind == "bias_or_price":
        return TriageRule(
            segment=segment,
            tier=tier,
            evaluator=_bind_segment(_low_tier_evaluator(threshold=LOW_TIER_PCT_THRESHOLD), segment),
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


def _format_pct(value: float) -> str:
    """Format a fractional pct as a percent string (``0.0123`` -> ``1.23%``)."""
    return f"{value * 100:.2f}%"


def _price_move_evaluator(threshold: float):
    """Segment-aware high-tier evaluator.

    Regenerate when **any** of the following holds:
    1. Data layer is in fallback mode (we don't trust the price feed).
    2. The largest absolute pct_change among the segment's tracked tickers
       exceeds ``threshold`` -- this is the rubric's "yield/price move >0.5%"
       trigger.
    3. The prior-baseline per-segment bias is *not* neutral/mixed -- a
       directional view from yesterday is treated as live.

    Carry only when we have positive evidence the segment is quiet:
    - Price feed is healthy AND
    - All tracked tickers moved less than ``threshold`` AND
    - Prior bias is neutral/mixed (or absent -- a missing bias on a quiet
      price tape is OK to carry; the price-delta is the load-bearing signal
      for high-tier).

    Defaults to regenerate on any insufficient-evidence path. ``threshold``
    is fractional (``0.005`` = 0.5%) to match ``state.price_deltas``.
    """

    def _check(state: AtlasResearchState, segment: str) -> tuple[bool, str]:
        if state.data_layer.fallback_used != "supabase":
            return True, f"data_layer_fallback={state.data_layer.fallback_used}"

        max_move = max_abs_move_for_segment(segment, state.price_deltas)
        if max_move is None:
            # No price-delta data for this segment's tickers -> conservative
            # regen. Matches the docstring's "extra LLM cost is the cheaper
            # error mode" rubric.
            return True, f"no_price_delta_threshold={_format_pct(threshold)}"
        if max_move > threshold:
            return True, f"price_move={_format_pct(max_move)}>threshold={_format_pct(threshold)}"

        segment_bias = _per_segment_bias(state, segment)
        if segment_bias and segment_bias not in {"neutral", "mixed"}:
            return True, (
                f"segment_bias={segment_bias}_price_move={_format_pct(max_move)}"
                f"<=threshold={_format_pct(threshold)}"
            )
        # Quiet tape AND quiet/absent bias -> carry.
        bias_label = segment_bias or "absent"
        return False, (
            f"price_quiet_{_format_pct(max_move)}<=threshold={_format_pct(threshold)}"
            f"_bias={bias_label}"
        )

    return _check


def _low_tier_evaluator(threshold: float):
    """Low-tier evaluator (sectors / alt-data) -- regen on bias shift OR a
    tracked-name move > ``threshold``.

    Two-channel signal:
    - **Bias channel:** any bullish/bearish reading from yesterday's per-
      segment bias regenerates (the analyst already had a view).
    - **Price channel:** any tracked ticker for the segment moving more
      than ``threshold`` (default 1.5%) regenerates -- even on a neutral
      bias day, a sharp single-name / single-ETF move is news.

    Carry requires both channels to be quiet AND the segment to have at
    least one signal observed (price-delta data present OR a recorded
    neutral/mixed bias). A segment with neither data source falls through
    to regenerate -- same conservative default as before.
    """

    def _check(state: AtlasResearchState, segment: str) -> tuple[bool, str]:
        segment_bias = _per_segment_bias(state, segment)
        max_move = max_abs_move_for_segment(segment, state.price_deltas)

        if segment_bias and segment_bias in {
            "bullish",
            "bearish",
            "strong_bullish",
            "strong_bearish",
        }:
            return True, f"segment_bias={segment_bias}"

        if max_move is not None and max_move > threshold:
            return True, (
                f"tracked_name_move={_format_pct(max_move)}>threshold={_format_pct(threshold)}"
            )

        # No regen trigger fired. Decide between carry (we have evidence
        # the segment is quiet) and regen (no evidence at all).
        have_bias_signal = segment_bias in {"neutral", "mixed"}
        have_price_signal = max_move is not None

        if have_bias_signal and have_price_signal:
            return False, (
                f"segment_bias_quiet={segment_bias}"
                f"_price_quiet={_format_pct(max_move)}<=threshold={_format_pct(threshold)}"
            )
        if have_bias_signal:
            return False, f"segment_bias_quiet={segment_bias}_no_price_data"
        if have_price_signal:
            return False, (
                f"price_quiet={_format_pct(max_move)}<=threshold={_format_pct(threshold)}_no_bias"
            )
        return True, "no_per_segment_bias_no_price_data"

    return _check


def _bias_shifted_evaluator(state: AtlasResearchState, segment: str) -> tuple[bool, str]:
    """Standard-tier evaluator. Regens on per-segment bias shift only --
    no price-delta input (see module docstring's signal table)."""
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
        # Phase 1 alt-data -- low tier; bias-shift driven (no segment-tracked
        # tickers, so the price channel is no-op for these segments).
        _rule_for_segment("alt-sentiment-news", "low", "bias"),
        _rule_for_segment("alt-cta-positioning", "low", "bias"),
        _rule_for_segment("alt-options-derivatives", "low", "bias"),
        _rule_for_segment("alt-politician-signals", "low", "bias"),
        # Phase 2 institutional -- standard tier.
        _rule_for_segment("inst-institutional-flows", "standard", "bias"),
        _rule_for_segment("inst-hedge-fund-intel", "standard", "bias"),
        # Phase 3 macro -- mandatory.
        _rule_for_segment("macro", "mandatory", "always"),
        # Phase 4 asset classes -- mandatory (crypto) + high (others).
        _rule_for_segment("bonds", "high", "price_move"),
        _rule_for_segment("commodities", "high", "price_move"),
        _rule_for_segment("forex", "high", "price_move"),
        _rule_for_segment("crypto", "mandatory", "always"),
        _rule_for_segment("international", "standard", "bias"),
        # Phase 5 equities -- mandatory top-down + low per-sector.
        _rule_for_segment("equity", "mandatory", "always"),
    ]
    # 11 sectors are low-tier with the combined bias-or-price evaluator;
    # each sector slug maps to its ETF basket via triage_signals.segment_tickers().
    for sector in load_sectors():
        rules.append(_rule_for_segment(sector.slug, "low", "bias_or_price"))
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
