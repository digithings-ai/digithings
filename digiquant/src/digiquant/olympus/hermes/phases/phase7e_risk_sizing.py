"""Phase 7E / H8 — deterministic risk-sizing enforcement (#726, Pillar 2).

H7 ``PMDirectionMemo`` supplies direction (long|flat) and conviction ranks only.
This phase maps those inputs plus H5/H6 analyst context into deterministic,
risk-managed weights via :func:`~digiquant.olympus.hermes.sizing.size_portfolio` —
the sole weight owner on the thesis-first path (ADR-0020).

**H8 inside Hermes graph (PR 4c):** output lands in ``phase_hermes.sized_book``.
Legacy chain-terminal invocation may still write ``phase7d_rebalance`` when no memo
is present.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any  # score:allow untyped any — scored-lint: duck-typed Supabase client + rows

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.data.queries import get_return_correlations
from digiquant.olympus.atlas.state import AtlasResearchState, PhaseHermesState, RebalancePayload
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.models.deliberation import is_unchallenged_carry
from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo
from digiquant.olympus.hermes.payloads import analyst_payloads, deliberation_summaries
from digiquant.olympus.hermes.risk_controls import BreakerConfig, breaker_scale_from_nav_history
from digiquant.olympus.hermes.sector_map import asset_class, sector_bucket
from digiquant.olympus.hermes.sizing import SizingCaps, TickerRisk, size_portfolio
from digiquant.olympus.hermes.sizing_events import (
    LineageValidationError,
    SizingAdjustment,
    SizingAdjustmentType,
    validate_sizing_lineage,
)
from digiquant.olympus.hermes.turnover import apply_rebalancing_cadence

logger = logging.getLogger(__name__)

# Calendar-day window to find the latest technicals row ≤ run_date. Wide enough to
# clear weekends + holidays + a stale prices cron (the Saturday-baseline lag, #726).
_VOL_LOOKBACK_DAYS = 40
_CONVICTION_FLOOR, _CONVICTION_CAP = -5.0, 5.0


@dataclass(frozen=True)
class RiskSizingDeps:
    """Wiring deps for the Phase 7E enforcement node (injected Supabase client)."""

    client: SupabaseClient


def _opt_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _is_cash(ticker: Any) -> bool:
    return isinstance(ticker, str) and ticker.strip().upper() == "CASH"


def _clamp_conviction(value: float) -> float:
    return max(_CONVICTION_FLOOR, min(_CONVICTION_CAP, value))


def _pm_direction_legacy(recommended: list[Any]) -> dict[str, float]:
    """Legacy 7D chosen names → proposed weight (deduped, positive, non-CASH)."""
    targets: dict[str, float] = {}
    for row in recommended:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or not ticker or _is_cash(ticker):
            continue
        weight = _opt_float(row.get("target_pct")) or 0.0
        if weight <= 0:
            continue
        targets[ticker] = targets.get(ticker, 0.0) + weight
    return targets


def _memo_long_tickers(memo: PMDirectionMemo) -> list[str]:
    return [entry.ticker for entry in memo.roster if entry.direction == "long"]


def _rank_to_conviction(rank: int, n_long: int, *, floor: float) -> float:
    """Map H7 ordinal rank (1 = best) to a sizing conviction in [-5, 5]."""
    if n_long <= 0:
        return floor
    if n_long == 1:
        return 5.0
    span = max(5.0 - floor, 0.0)
    return 5.0 - (rank - 1) * span / (n_long - 1)


def _memo_effective_inputs(
    memo: PMDirectionMemo,
    analysts: dict[str, dict[str, Any]],
    default_conviction: float,
) -> tuple[dict[str, float], dict[str, str]]:
    """Per long ticker: conviction from H7 rank + stance from analyst payload."""
    long_entries = [entry for entry in memo.roster if entry.direction == "long"]
    n_long = len(long_entries)
    floor = max(default_conviction, 2.0)
    convictions: dict[str, float] = {}
    stances: dict[str, str] = {}
    for entry in long_entries:
        convictions[entry.ticker] = _clamp_conviction(
            _rank_to_conviction(entry.conviction_rank, n_long, floor=floor)
        )
        analyst = analysts.get(entry.ticker) or {}
        stance = str(analyst.get("stance") or "buy")
        stances[entry.ticker] = stance if stance in ("buy", "hold") else "hold"
    return convictions, stances


def _effective_inputs(
    tickers: list[str],
    analysts: dict[str, dict[str, Any]],
    debates: dict[str, dict[str, Any]],
    default_conviction: float,
) -> tuple[dict[str, float], dict[str, str]]:
    """Per ticker: effective conviction (analyst score + debate delta, clamped) + stance."""
    convictions: dict[str, float] = {}
    stances: dict[str, str] = {}
    for ticker in tickers:
        analyst = analysts.get(ticker) or {}
        debate = debates.get(ticker) or {}
        if analyst:
            base = _opt_float(analyst.get("conviction_score")) or 0.0
            stance = str(analyst.get("stance") or "hold")
        else:
            base = default_conviction
            stance = "hold"
        delta = _opt_float(debate.get("conviction_delta")) or 0.0
        convictions[ticker] = _clamp_conviction(base + delta)
        stances[ticker] = stance
    return convictions, stances


def _cap_unchallenged_convictions(
    convictions: Mapping[str, float],
    debates: Mapping[str, Mapping[str, Any]],
    *,
    bar: float,
    events: list[SizingAdjustment] | None = None,
) -> tuple[dict[str, float], list[str]]:
    """Hold every crash-carried name at the entry ``bar``; return the book and those names.

    H6 fails soft: when the deliberation LLM crashes it carries the analyst's own stance
    forward, so a position that received **no** PM challenge could still be sized at top
    conviction — 40% of the 2026-07-31 book, including all three new opens. Capping at
    ``SizingCaps.min_conviction`` means an unchallenged name stays in the book but can never
    outrank one that was actually debated.

    Capping *at* the bar rather than scaling below it is deliberate. A name pushed under the
    bar is dropped by the sizer's **selection** step and then re-added at its drifted weight
    by the #1649 held-carry backstop — which can end up **larger** than applying no haircut
    at all. Capping at the bar clears `_select`'s ``>=`` so selection never drops it.
    Correlation de-dup can still drop a capped leg in favour of a challenged one
    (``sizing._corr_dedup`` drops the lower-conviction side of a >0.80 pair); that is the
    intended outcome, not an escape hatch.

    ``events`` (#2417), when passed, gets one ``CONVICTION_FLOOR`` event per capped
    ticker, emitted right here as a pure side-channel: no counterfactual re-sizing run
    is performed (a second ``size_portfolio`` call could legitimately drop a *different*
    ticker via ``_corr_dedup``, which would be a more confusing explanation than none).
    The event is recorded in the conviction domain (``unit="conviction"``), reading
    ``conviction`` and ``bar`` — the exact values already used above — before
    ``convictions`` is reassigned by the caller, so it has zero effect on the real book.
    """
    out: dict[str, float] = {}
    capped: list[str] = []
    for ticker, conviction in convictions.items():
        if conviction > bar and is_unchallenged_carry(debates.get(ticker) or {}):
            if events is not None:
                events.append(
                    SizingAdjustment(
                        ticker=ticker,
                        adjustment_type=SizingAdjustmentType.CONVICTION_FLOOR,
                        original_pct=conviction,
                        adjusted_pct=bar,
                        unit="conviction",
                        reason=(
                            f"unchallenged-carry conviction capped {conviction:.2f} -> "
                            f"{bar:.2f} (bar)"
                        ),
                    )
                )
            out[ticker] = bar
            capped.append(ticker)
        else:
            out[ticker] = conviction
    return out, sorted(capped)


def _unchallenged_note(unchallenged: list[str]) -> str:
    """Book-note sentence naming the positions no PM challenge ever reached (#1742)."""
    if not unchallenged:
        return ""
    return (
        " Held at the conviction bar (H6 deliberation failed, no PM challenge): "
        f"{', '.join(unchallenged)}."
    )


def _load_ticker_risk(
    client: SupabaseClient, tickers: list[str], run_date: date
) -> dict[str, TickerRisk]:
    """Assemble ``{ticker: TickerRisk}`` — latest ``price_technicals`` row ≤ run_date for
    vol, :func:`sector_bucket` for concentration. Fail-soft: a read error (or a missing
    ticker) leaves vol unset so the sizer falls back to its default annualized vol."""
    latest: dict[str, dict[str, Any]] = {}
    if tickers:
        try:
            since = (run_date - timedelta(days=_VOL_LOOKBACK_DAYS)).isoformat()
            resp = (
                client.table("price_technicals")
                .select("ticker,date,hist_vol_21,atr_pct")
                .in_("ticker", list(tickers))
                .lte("date", run_date.isoformat())  # look-ahead guard (no future rows)
                .gte("date", since)
                .order("date", desc=True)
                .limit(len(tickers) * _VOL_LOOKBACK_DAYS)
                .execute()
            )
            for row in getattr(resp, "data", None) or []:
                ticker = row.get("ticker")
                if ticker and ticker not in latest:  # desc order → first seen is freshest
                    latest[ticker] = row
        except Exception as exc:  # vol read is best-effort; default vol used
            logger.warning("phase7e: price_technicals read failed (%s); using default vol", exc)
    return {
        ticker: TickerRisk(
            ticker=ticker,
            hist_vol_21=_opt_float((latest.get(ticker) or {}).get("hist_vol_21")),
            atr_pct=_opt_float((latest.get(ticker) or {}).get("atr_pct")),
            sector=sector_bucket(ticker),
            asset_class=asset_class(ticker),
        )
        for ticker in tickers
    }


def _verb(current: float | None, target: float) -> str:
    """Rebalance verb from current → target weight. Unknown current ⇒ treat as 0."""
    cur = current or 0.0
    if cur <= 0 < target:
        return "new"
    if target <= 0 < cur:
        return "exit"
    if target > cur + 1e-9:
        return "add"
    if target < cur - 1e-9:
        return "trim"
    return "hold"


def _rebuild_actions(
    original_actions: list[Any],
    pm_targets: dict[str, float],
    sized: dict[str, float],
    current_weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Rebuild the advisory action list to match the SIZED book.

    For a retained ticker, updates ``target_pct`` to the sized weight AND recomputes the
    verb from ``current_pct`` → sized target (so the published document doesn't say "add"
    when sizing actually trimmed the position to a cap). When ``current_pct`` is unknown
    the PM's verb is preserved (it can't be recomputed). A PM name that sizing dropped
    becomes an explicit exit-to-cash. ``materialize`` ignores ``actions`` (it books
    ``recommended_portfolio``); these drive the published document only.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for action in original_actions:
        if not isinstance(action, dict):
            continue
        ticker = action.get("ticker")
        if not isinstance(ticker, str) or not ticker:
            continue
        seen.add(ticker)
        row = dict(action)
        if ticker in sized:
            new_target = round(sized[ticker], 4)
            row["target_pct"] = new_target
            current = _opt_float(action.get("current_pct"))
            if current is not None:  # recompute verb only when we know the live weight
                row["action"] = _verb(current, new_target)
        elif ticker in pm_targets:
            base = str(action.get("rationale") or "").strip()
            row["action"] = "exit"
            row["target_pct"] = 0.0
            row["rationale"] = (
                f"{base} [removed by risk sizing — cap / correlation de-dup / conviction floor]"
            ).strip()
        out.append(row)
    # Sized tickers the PM had no explicit action row for — the NORM on the H7 memo
    # path (original_actions is empty there), so every booked day misreported held
    # rebalances as "new" (#1676). Classify against the live drifted weight instead:
    # add / trim / hold for existing positions, "new" only for genuinely new names.
    live = current_weights or {}
    for ticker, target in sized.items():
        if ticker not in seen:
            verb = _verb(_opt_float(live.get(ticker)), target)
            out.append(
                {
                    "ticker": ticker,
                    "action": verb,
                    "target_pct": round(target, 4),
                    "rationale": "Position weight set by deterministic risk sizing.",
                }
            )
    return out


def _held_carry_weights(state: AtlasResearchState) -> dict[str, float]:
    """Prior (drifted) weights for deliberately carried held names (#1030, #1555, #1649).

    Two classes of held name must be carried at their current drifted weight or H9
    fails closed with "held ticker missing from book and not flat" — the fail-closed
    that silently froze **every** delta-day commit from 2026-06-26 (#1555) and again
    on 2026-07-21/22 (#1649):

    - H4-gated: the staleness gate moved a quiet held name into
      ``focus_roster_excluded`` (no fresh analyst, absent from the H7 PM memo).
    - Memo-unaddressed (#1649): the H7 PM memo's roster omitted a held name
      entirely (neither ``long`` nor ``flat``) — memo coverage is LLM discipline,
      and an owned position with no explicit instruction defaults to "hold".

    Scoped to :func:`~digiquant.olympus.hermes.writers.commit_io.carried_held_tickers`
    — reusing the exact set H9's coherence check exempts so the carry set and the
    exemption set can never diverge into a new silent mismatch. A PM-exited name
    (addressed in the roster, marked ``flat``) is memo-addressed, so it is never
    resurrected here.

    Returns weights only — no ``SizingAdjustment`` event, because whether a carry
    actually lands depends on the caller's ``setdefault`` (a name already sized by
    the PM/sizer is left untouched). Emitting the event here, unconditionally,
    produced a ``CONTINUITY_CARRY`` record for carries that never happened (#2417
    CodeRabbit review on #2434) — the caller emits it only when the carry sticks.
    """
    # Lazy import: keeps the phase7e ↔ commit_io edge one-directional at import time.
    from digiquant.olympus.hermes.writers.commit_io import carried_held_tickers

    gated = carried_held_tickers(state)
    if not gated:
        return {}
    carry: dict[str, float] = {}
    for ticker in gated:
        weight = _drifted_weight(state, ticker)
        if weight is not None and weight > 0:
            carry[ticker] = weight
    return carry


def _drifted_weight(state: AtlasResearchState, ticker: str) -> float | None:
    """Current (mark-to-market) weight for *ticker*, falling back to the prior book."""
    current = _opt_float((state.config.preferences.get("current_weights") or {}).get(ticker))
    if current is not None and current > 0:
        return float(current)
    for row in state.prior_context.prior_book:
        if str(row.get("ticker")).strip().upper() == ticker:
            prior = _opt_float(row.get("weight_pct"))
            if prior is not None and prior > 0:
                return float(prior)
    return None


def _apply_held_continuity_backstop(
    sized: dict[str, float],
    state: AtlasResearchState,
    events: list[SizingAdjustment] | None = None,
) -> dict[str, float]:
    """FINAL-book held invariant (#1649): held ⇒ positive weight or explicit flat.

    The per-cause carries (#1030 gated, #1649 memo-unaddressed) cover known cracks,
    but the 2026-07-22 22:54 run proved unknown ones exist: NINE held names reached
    H9 with weight<=0 despite the memo-unaddressed carry being live (suspected:
    PM-longed names dropped by sizing caps — memo-addressed, so exempt from the
    carry). This backstop enforces the invariant on the FINAL sized dict regardless
    of cause: any held, non-flat ticker at weight<=0 is re-added at its drifted
    weight, with a WARNING naming the cause bucket (memo-addressed ⇒ sized-out;
    else carry-miss) so diagnostics show exactly which crack fired. A held name
    with NO recoverable weight stays out and H9 still fails closed — that case
    genuinely needs eyes.
    """
    from digiquant.olympus.hermes.writers.commit_io import (
        flat_tickers_from_memo,
        held_tickers,
        memo_addressed_tickers,
    )

    flats = flat_tickers_from_memo(state)
    addressed = memo_addressed_tickers(state)
    out = dict(sized)
    for ticker in sorted(held_tickers(state)):
        if out.get(ticker, 0.0) > 0:
            continue
        if ticker in flats:
            # H7 explicitly said "flat" for this held name — never resurrect it. Distinct
            # from the carry-miss/pm-addressed-sized-out branch below (#2417 FLAT_EXIT vs
            # CONTINUITY_CARRY): the two are structurally mutually exclusive because
            # ``memo_addressed_tickers`` already includes flat-tagged tickers, so a flat
            # ticker can never also reach the carry-miss branch.
            if events is not None:
                events.append(
                    SizingAdjustment(
                        ticker=ticker,
                        adjustment_type=SizingAdjustmentType.FLAT_EXIT,
                        original_pct=_drifted_weight(state, ticker) or 0.0,
                        adjusted_pct=0.0,
                        reason="H7-flat: held position honored as exit, never resurrected",
                    )
                )
            continue
        weight = _drifted_weight(state, ticker)
        cause = "pm-addressed but sized out (caps?)" if ticker in addressed else "carry miss"
        if weight is None:
            logger.warning(
                "held-continuity backstop: %s has weight<=0 (%s) and NO recoverable "
                "drifted weight — H9 will fail closed",
                ticker,
                cause,
            )
            continue
        logger.warning(
            "held-continuity backstop: re-adding %s at drifted %.4f (%s)",
            ticker,
            weight,
            cause,
        )
        if events is not None:
            events.append(
                SizingAdjustment(
                    ticker=ticker,
                    adjustment_type=SizingAdjustmentType.CONTINUITY_CARRY,
                    original_pct=out.get(ticker, 0.0),
                    adjusted_pct=weight,
                    reason=cause,
                )
            )
        out[ticker] = weight
    return out


def _cap_total_invested(
    sized: dict[str, float], events: list[SizingAdjustment] | None = None
) -> dict[str, float]:
    """FINAL-book allocation invariant (#1676): Σ positive weights ≤ 100%.

    Nothing upstream enforces the total, and the held-continuity backstop (#1649)
    legitimately ADDS drifted weights on top of an already-allocated book — the
    correct rescue can overshoot 100%. Proportionally scale all positive weights
    down when the total exceeds 100 (cash residual < 100 is always valid).
    """
    total = sum(w for w in sized.values() if w > 0)
    if total <= 100.0 + 1e-9:
        return sized
    scale = 100.0 / total
    logger.warning(
        "total-invested cap: sized book at %.2f%% > 100%%; scaling all positions by %.4f",
        total,
        scale,
    )
    if events is not None:
        for ticker, w in sized.items():
            if w > 0:
                events.append(
                    SizingAdjustment(
                        ticker=ticker,
                        adjustment_type=SizingAdjustmentType.FINAL_GROSS_SCALE,
                        original_pct=w,
                        adjusted_pct=w * scale,
                        reason=f"total invested {total:.2f}% > 100%; scaled by {scale:.4f}",
                    )
                )
    return {t: (w * scale if w > 0 else w) for t, w in sized.items()}


def _lineage_materiality_pct(preferences: Mapping[str, Any]) -> float:
    """Widest no-trade band in play (#2417 §6).

    Mirrors ``turnover.apply_turnover_to_sized_book``'s own
    ``max(threshold, rel_band * current_pct)`` so the lineage validator never flags a
    delta that clamp already decided was immaterial with an independently-tuned
    epsilon. ``validate_sizing_lineage`` takes one scalar, so this uses the widest
    (most permissive) per-ticker band actually in play this run.
    """
    threshold = float(preferences.get("rebalance_threshold_pct") or 3.0)
    rel_band = float(preferences.get("rebalance_rel_band_pct") or 20.0) / 100.0
    current_weights = preferences.get("current_weights") or {}
    widest_current = max(
        (_opt_float(v) or 0.0 for v in current_weights.values()),
        default=0.0,
    )
    return max(threshold, rel_band * widest_current)


def _validate_h8_lineage(
    pm_targets: dict[str, float],
    sized_book: RebalancePayload,
    preferences: Mapping[str, Any],
    *,
    targets_are_weights: bool = True,
) -> None:
    """Separate, louder layer on top of ``_build_sized_book``'s fail-soft guard (#2417 §6).

    Called only after ``_build_sized_book`` has already returned a payload — never
    replaces, masks, or is masked by that function's own try/except around
    ``size_portfolio``. Never raises past this point and never mutates ``sized_book``:
    a lineage failure is logged, not converted into a dropped rebalance.

    ``targets_are_weights`` must be ``False`` for the memo path (H7 direction-only —
    no PM weights, per the H7/H8 split), where ``pm_targets`` is a membership flag
    (every long-roster ticker = 1.0), not a real requested weight. Comparing that
    flag against a real approved percentage is meaningless — it flagged nearly every
    sized position as an "unexplained delta" and logged an ERROR with a stack trace
    on most production runs (#2417 CodeRabbit review on #2434), since the live
    production path *is* the memo path. This layer no-ops there until a follow-up
    gives the memo path a real pre-H8 target representation (see #2417 design spec
    §6 "Open items to confirm"). It is exact for the legacy ``phase7d_rebalance``
    path (default ``True``), where ``pm_targets`` already holds real target_pct
    weights (``_pm_direction_legacy``).
    """
    if not targets_are_weights:
        return
    approved = {
        str(row["ticker"]): _opt_float(row.get("target_pct")) or 0.0
        for row in sized_book.get("recommended_portfolio") or []
    }
    adjustments = [
        SizingAdjustment.model_validate(event) for event in sized_book.get("adjustments") or []
    ]
    try:
        validate_sizing_lineage(
            pm_targets,
            approved,
            adjustments,
            materiality_pct=_lineage_materiality_pct(preferences),
        )
    except LineageValidationError:
        logger.error("H8 lineage validation failed", exc_info=True)


def _build_sized_book(
    *,
    pm_tickers: list[str],
    pm_targets: dict[str, float],
    original_actions: list[Any],
    prior_notes: str,
    state: AtlasResearchState,
    deps: RiskSizingDeps,
) -> tuple[RebalancePayload | None, Any | None]:
    """Run deterministic sizing; return None on no-op / fail-soft."""
    from digiquant.olympus.hermes.h8_risk_snapshots import resolve_h8_risk_artifacts

    caps = SizingCaps.from_preferences(state.config.preferences)
    memo = state.phase_hermes.pm_direction_memo

    try:
        breaker = breaker_scale_from_nav_history(
            deps.client,
            state.run_date,
            config=BreakerConfig.from_preferences(state.config.preferences),
        )
        breaker_scale = breaker.scale
        breaker_note = f" Drawdown breaker: {breaker.reason}." if breaker.scale < 1.0 else ""
    except Exception as exc:  # breaker is best-effort; neutral on failure
        logger.warning("phase7e: drawdown breaker failed (%s); neutral scale", exc)
        breaker_scale, breaker_note = 1.0, ""

    try:
        corr_frame = get_return_correlations(
            client=deps.client,
            tickers=pm_tickers,
            run_date=state.run_date,
        )
    except Exception as exc:  # correlation is best-effort
        logger.warning("phase7e: correlation read failed (%s); using full-correlation default", exc)
        corr_frame = None

    # WP6.3 (#2698): resolve incumbent policy + covariance snapshot before sizing.
    # Audit-only in Phase 1 — incumbent ``size_portfolio`` inputs stay unchanged.
    try:
        risk_artifacts = resolve_h8_risk_artifacts(
            state=state,
            pm_tickers=pm_tickers,
            corr=corr_frame,
        )
    except Exception as exc:
        logger.warning("phase7e: risk snapshot resolution failed (%s); continuing sizing", exc)
        risk_artifacts = None

    unchallenged: list[str] = []
    events: list[SizingAdjustment] = []
    try:
        analysts = analyst_payloads(state)
        debates = deliberation_summaries(state)
        if memo is not None:
            convictions, stances = _memo_effective_inputs(memo, analysts, caps.min_conviction)
        else:
            convictions, stances = _effective_inputs(
                pm_tickers,
                analysts,
                debates,
                default_conviction=caps.min_conviction,
            )
        # Applied to BOTH branches on purpose. The memo branch is the live production path
        # (H7 writes a memo every run), so a haircut wired only into the no-memo branch
        # would be inert in production (#1742).
        convictions, unchallenged = _cap_unchallenged_convictions(
            convictions, debates, bar=caps.min_conviction, events=events
        )
        if unchallenged:
            logger.warning(
                "phase7e: %d position(s) held at the conviction bar — H6 deliberation "
                "crashed, so no PM challenge ran (%s)",
                len(unchallenged),
                ", ".join(unchallenged),
            )
        risk = _load_ticker_risk(deps.client, pm_tickers, state.run_date)
        result = size_portfolio(
            convictions=convictions,
            stances=stances,
            risk=risk,
            corr=corr_frame,
            caps=caps,
            breaker_scale=breaker_scale,
        )
    except Exception as exc:  # sizing must never crash the run
        logger.warning("phase7e: risk sizing failed (%s); keeping prior book", exc)
        return None, risk_artifacts

    sized = {p.ticker: p.target_pct for p in result.positions}
    # #2417: bring in every event size_portfolio already emitted (caps, corr-dedup,
    # vol-scale, breaker, grid-rounding) alongside the conviction-floor event above.
    events.extend(result.adjustments)
    # Carry deliberately gated-out or memo-unaddressed held names at their current
    # drifted weight (#1030, #1555, #1649) BEFORE the cadence band, so they flow through as continuing positions
    # (held, not traded). Skip (and don't emit an event for) any ticker the PM/sizer
    # already sized — only a quiet held name that sizing would otherwise drop is
    # actually carried, and only an actual carry gets a CONTINUITY_CARRY event.
    for ticker, weight in _held_carry_weights(state).items():
        if ticker in sized:
            continue
        sized[ticker] = weight
        events.append(
            SizingAdjustment(
                ticker=ticker,
                adjustment_type=SizingAdjustmentType.CONTINUITY_CARRY,
                original_pct=0.0,
                adjusted_pct=weight,
                reason="held ticker gated/memo-unaddressed — carried at drifted weight",
            )
        )
    # current_weights is already mark-to-market drifted in preflight (#955). The cadence
    # dispatcher rebalances through the no-trade band on a permitted day, else holds the
    # drifted book (only PM direction changes trade).
    current_weights = dict(state.config.preferences.get("current_weights") or {})
    sized = apply_rebalancing_cadence(
        sized,
        current_weights={
            str(k): float(v) for k, v in current_weights.items() if _opt_float(v) is not None
        },
        prior_book=list(state.prior_context.prior_book),
        preferences=dict(state.config.preferences),
        run_date=state.run_date,
        events=events,
    )
    sized = _apply_held_continuity_backstop(sized, state, events=events)
    sized = _cap_total_invested(sized, events=events)
    updated: RebalancePayload = {
        "recommended_portfolio": [
            {"ticker": ticker, "target_pct": round(weight, 4)} for ticker, weight in sized.items()
        ],
        "actions": _rebuild_actions(original_actions, pm_targets, sized, current_weights),
        "notes": (f"{prior_notes}\n\n" if prior_notes else "")
        + f"Risk-sizing (H8): {result.explanation}{breaker_note}{_unchallenged_note(unchallenged)}",
        # #2417: reason-coded, in-memory explanation of every material adjustment this
        # H8 pass made — explanation-only, never persisted, never affects the weights
        # computed above.
        "adjustments": [event.model_dump() for event in events],
    }

    logger.info(
        "phase7e: sized %d→%d holdings, %.1f%% invested / %.1f%% cash, ex-ante vol ~%s%% (%s)",
        len(pm_tickers),
        len(sized),
        result.gross_pct,
        result.cash_pct,
        result.realized_portfolio_vol,
        caps.sizing_mode,
    )
    return updated, risk_artifacts


def build_risk_sizing_node(deps: RiskSizingDeps):
    """Return the Phase 7E / H8 enforcement node bound to ``deps``."""

    def risk_sizing(state: AtlasResearchState) -> dict[str, Any]:
        memo_raw = state.phase_hermes.pm_direction_memo
        rebalance = state.phase7d_rebalance
        if memo_raw is None and rebalance is None:
            return {}

        memo: PMDirectionMemo | None = None
        if memo_raw is not None:
            memo = (
                memo_raw
                if isinstance(memo_raw, PMDirectionMemo)
                else PMDirectionMemo.model_validate(memo_raw)
            )

        if memo is not None:
            pm_tickers = _memo_long_tickers(memo)
            pm_targets = {ticker: 1.0 for ticker in pm_tickers}
            prior_notes = str(memo.memo or "").strip()
            original_actions: list[Any] = []
        else:
            pm_targets = _pm_direction_legacy(rebalance.get("recommended_portfolio") or [])
            pm_tickers = list(pm_targets)
            prior_notes = str(rebalance.get("notes") or "").strip()
            original_actions = list(rebalance.get("actions") or [])

        sized_book, risk_artifacts = _build_sized_book(
            pm_tickers=pm_tickers,
            pm_targets=pm_targets,
            original_actions=original_actions,
            prior_notes=prior_notes,
            state=state,
            deps=deps,
        )
        if sized_book is None:
            if risk_artifacts is not None:
                return {
                    "phase_hermes": PhaseHermesState(
                        risk_policy=risk_artifacts.policy.model_dump(mode="json"),
                        covariance_snapshot=risk_artifacts.covariance_snapshot.model_dump(
                            mode="json"
                        ),
                    )
                }
            return {}

        # #2417 §6: unexplained-delta lineage check, layered on top of (not inside)
        # _build_sized_book's own fail-soft try/except — logs and continues, never
        # affects the already-computed sized_book. The memo path's pm_targets are
        # membership flags, not weights (see _validate_h8_lineage docstring), so the
        # comparison only runs for the legacy phase7d_rebalance path.
        _validate_h8_lineage(
            pm_targets,
            sized_book,
            state.config.preferences,
            targets_are_weights=memo is None,
        )

        hermes_update = PhaseHermesState(sized_book=sized_book)
        if risk_artifacts is not None:
            hermes_update = PhaseHermesState(
                sized_book=sized_book,
                risk_policy=risk_artifacts.policy.model_dump(mode="json"),
                covariance_snapshot=risk_artifacts.covariance_snapshot.model_dump(mode="json"),
            )

        if memo is not None:
            return {"phase_hermes": hermes_update}
        return {"phase7d_rebalance": sized_book, "phase_hermes": hermes_update}

    return risk_sizing


def build_risk_sizing_phase(deps: RiskSizingDeps) -> PipelinePhase:
    """Wrap the enforcement node into a single-node ``PipelinePhase`` (H8)."""
    return PipelinePhase(
        name="hermes_h8_risk_sizing",
        nodes=[NodeSpec(name="hermes/portfolio/risk-sizing", run=build_risk_sizing_node(deps))],
    )


__all__ = ["RiskSizingDeps", "build_risk_sizing_node", "build_risk_sizing_phase"]
