"""Delta triage — deterministic rules that decide which segments regenerate
on a weekday delta run vs. carry forward from the baseline.

Mirrors the priority table in ``digiquant/src/digiquant/olympus/atlas/docs/agentic/ARCHITECTURE.md``
§Mon–Sat — Daily Delta. Table-driven so the rules are readable and the
Phase 9 post-mortem can see exactly why a segment ran or didn't.

Tier vocabulary (from the ARCHITECTURE.md §Mon-Sat Daily Delta table):
- **mandatory** — always regenerate (macro, US equities, crypto).
- **high** — regenerate when a material price / yield / policy trigger fires
  (bonds / commodities / forex, threshold >0.5% OR new CB signal).
- **standard** — regenerate on major regional event or flow shift
  (international, institutional).
- **low** — regenerate on tracked-name move >1.5% or data-layer fallback;
  carry on stable directional bias when the tape is quiet (#951)
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

import os
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Any, Callable, Literal  # noqa: F401 — heterogeneous rule signatures

from digiquant.olympus.atlas.sectors_config import load_sectors
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    Carried,
    DeltaTriageDecision,
    DeltaTriageResult,
)
from digiquant.olympus.atlas.triage_signals import max_abs_move_for_segment
from digiquant.olympus.edit_mode.models import TriageSignal


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
    rule_kind: Literal[
        "always", "price_move", "bias", "bias_or_price", "onchain_unchanged", "env_gated"
    ],
    *,
    env_var: str | None = None,
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
    - ``onchain_unchanged`` -- low-tier; carry when the deterministic Hyperdash
      injection is unchanged vs. the prior run; see
      :func:`_onchain_unchanged_evaluator`.
    - ``env_gated`` -- low-tier; carry on delta by default, regen only when
      ``env_var`` is truthy; see :func:`_env_gated_evaluator`.
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
    if rule_kind == "onchain_unchanged":
        return TriageRule(
            segment=segment,
            tier=tier,
            evaluator=_bind_segment(_onchain_unchanged_evaluator, segment),
        )
    if rule_kind == "env_gated":
        if not env_var:
            raise ValueError("env_gated rule requires env_var")
        return TriageRule(
            segment=segment,
            tier=tier,
            evaluator=_bind_segment(_env_gated_evaluator(env_var), segment),
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
    """Low-tier evaluator (sectors / alt-data) -- regen on a fresh trigger
    (price move > ``threshold`` or data-layer fallback); carry when the
    tape is quiet.

    Changed by #951: a directional prior bias (bullish/bearish/strong_*)
    is **no longer** a standalone regenerate trigger. A segment that is
    persistently bullish with a quiet tape was re-paying the LLM every
    day under the old rule; now it carries with a
    ``stable_bias_quiet_tape=<bias>`` reason.

    Regeneration triggers (any one fires → regenerate):
    1. Data layer in fallback mode (untrusted feed).
    2. Tracked-name price move > ``threshold`` (default 1.5%).

    Carry when:
    - Price feed is healthy AND
    - All tracked tickers moved ≤ ``threshold`` AND
    - At least one signal is present (price data OR a recorded bias).
    - A directional bias on a quiet tape carries as ``stable_bias_quiet_tape``.

    Conservative default: no price data AND no bias → regenerate
    (insufficient evidence).
    """

    def _check(state: AtlasResearchState, segment: str) -> tuple[bool, str]:
        # Gate 1: untrusted data layer → regen regardless of bias/price.
        if state.data_layer.fallback_used != "supabase":
            return True, f"data_layer_fallback={state.data_layer.fallback_used}"

        segment_bias = _per_segment_bias(state, segment)
        max_move = max_abs_move_for_segment(segment, state.price_deltas)

        # Gate 2: price move above threshold → regen (news-driven day).
        if max_move is not None and max_move > threshold:
            return True, (
                f"tracked_name_move={_format_pct(max_move)}>threshold={_format_pct(threshold)}"
            )

        # No regen trigger fired. Decide between carry (we have evidence
        # the segment is quiet) and regen (no evidence at all).
        is_directional = segment_bias in {
            "bullish",
            "bearish",
            "strong_bullish",
            "strong_bearish",
        }
        have_quiet_bias = segment_bias in {"neutral", "mixed"}
        have_price_signal = max_move is not None

        # #951: directional bias + quiet tape + price data present → carry.
        if is_directional and have_price_signal:
            return False, (
                f"stable_bias_quiet_tape={segment_bias}"
                f"_price={_format_pct(max_move)}"
                f"<=threshold={_format_pct(threshold)}"
            )

        # #951: directional bias but NO price data → conservative regen
        # (we can't confirm the tape is quiet without price evidence).
        if is_directional and not have_price_signal:
            return True, (f"directional_bias={segment_bias}_no_price_data")

        if have_quiet_bias and have_price_signal:
            return False, (
                f"segment_bias_quiet={segment_bias}"
                f"_price_quiet={_format_pct(max_move)}"
                f"<=threshold={_format_pct(threshold)}"
            )
        if have_quiet_bias:
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


def _current_onchain_injection(state: AtlasResearchState) -> dict | None:
    """Return this run's compact Hyperdash injection, or None on a Hyperdash outage.

    Preflight writes the ``compact_summary()`` dict into
    ``data_layer.market_context['onchain_positioning']`` (#801); the
    alt-onchain-positioning segment interprets it. An absent/empty/non-dict
    value means no signal this run.
    """
    val = state.data_layer.market_context.get("onchain_positioning")
    return val if isinstance(val, dict) and val else None


def _prior_onchain_injection(state: AtlasResearchState) -> dict | None:
    """Return the prior run's persisted onchain injection, or None if unavailable.

    phase6_consolidate persists the same compact dict into the daily snapshot's
    ``onchain_positioning`` slot; preflight reloads the latest snapshot into
    ``prior_context.last_snapshots[0]['snapshot']``. None when there is no prior
    snapshot, no slot, or the slot is empty/non-dict.
    """
    if not state.prior_context.last_snapshots:
        return None
    snap = state.prior_context.last_snapshots[0].get("snapshot") or {}
    if not isinstance(snap, dict):
        return None
    val = snap.get("onchain_positioning")
    return val if isinstance(val, dict) and val else None


def _onchain_unchanged_evaluator(state: AtlasResearchState, _segment: str) -> tuple[bool, str]:
    """Low-tier evaluator for ``alt-onchain-positioning``.

    The segment is deterministically grounded — it just interprets the compact
    Hyperdash divergence preflight injects. So the only thing that can change its
    output is the injection itself. Carry (skip the LLM) when this run's injection
    is byte-for-byte equal to the prior run's persisted injection — a
    near-duplicate of already-interpreted data. Regenerate otherwise:
    - injection changed → re-interpret,
    - no prior injection → no baseline to compare → conservative regen,
    - no current injection (Hyperdash outage) → can't claim unchanged → regen so
      the segment records the absence.
    """
    current = _current_onchain_injection(state)
    if current is None:
        return True, "onchain_injection_absent_this_run"
    prior = _prior_onchain_injection(state)
    if prior is None:
        return True, "onchain_injection_no_prior_baseline"
    if current == prior:
        return False, "onchain_injection_unchanged"
    return True, "onchain_injection_changed"


def _env_gated_evaluator(env_var: str):
    """Build a low-tier evaluator that carries by default and regens only when
    ``env_var`` is truthy.

    Used for segments whose delta-run value is marginal enough to skip by
    default (saving an LLM call) but that an operator may want to force on via
    an env flag. Truthy = set to anything other than ``0`` / ``false`` / empty
    (matches the ``ATLAS_DATA_TOOLS`` kill-switch convention).
    """

    def _check(_state: AtlasResearchState, _segment: str) -> tuple[bool, str]:
        raw = os.environ.get(env_var, "").strip().lower()
        if raw not in ("", "0", "false"):
            return True, f"{env_var}={raw}"
        return False, f"{env_var}_unset_carry_on_delta"

    return _check


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
        # alt-onchain-positioning is deterministically grounded on the Hyperdash
        # injection (#801); carry when that injection is unchanged vs. yesterday.
        _rule_for_segment("alt-onchain-positioning", "low", "onchain_unchanged"),
        # alt-ai-portfolios is a marginal cross-model proxy (#658); carry on delta
        # by default, regen only when an operator forces it via AI_PORTFOLIOS_DELTA.
        _rule_for_segment("alt-ai-portfolios", "low", "env_gated", env_var="AI_PORTFOLIOS_DELTA"),
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


def triage_decision_to_signal(decision: DeltaTriageDecision) -> TriageSignal:
    """Map legacy triage vocabulary to :class:`TriageSignal` for ``resolve_edit_mode``.

    ``carry`` → ``quiet`` (skip when prior exists); ``regenerate`` → ``stale`` (edit).
    """
    if decision.decision == "carry":
        return TriageSignal(mode="quiet")
    return TriageSignal(mode="stale")


def _resolve_baseline_date(state: AtlasResearchState) -> date:
    """Prior artifact date used for carry provenance and triage metadata."""
    if state.baseline_date is not None:
        return state.baseline_date
    if state.prior_context.last_snapshots:
        snap = state.prior_context.last_snapshots[0]
        snap_date = snap.get("date")
        if isinstance(snap_date, str):
            return date.fromisoformat(snap_date)
    return state.run_date - timedelta(days=1)


def evaluate(state: AtlasResearchState) -> DeltaTriageResult:
    """Return per-segment regenerate/carry decisions for the daily run.

    Always evaluates the rule table (no ``run_type`` gate). Downstream
    ``resolve_edit_mode`` maps ``carry``/``regenerate`` to ``skip``/``edit``/``full``.
    """
    if state.cadence != "daily" and state.run_type == "delta" and state.baseline_date is None:
        raise ValueError("triage.evaluate: delta run requires baseline_date on state")

    baseline_date = _resolve_baseline_date(state)
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
        baseline_date=baseline_date,
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
    "triage_decision_to_signal",
]
