"""Phase 7E / H8 — deterministic risk-sizing enforcement (#726, Pillar 2).

H7 ``PMDirectionMemo`` supplies direction (long|flat) and conviction ranks only.
This phase maps those inputs plus H5/H6 analyst context into deterministic,
risk-managed weights via :func:`~digiquant.olympus.hermes.sizing.size_portfolio` —
the sole weight owner on the thesis-first path (ADR-0020).

**WP8.4 (#2734):** on the memo path, when ``h8_sizing_input_mode=calibrated`` (default)
and a validated ``AllocationInputBundle`` is present, raw weights come from calibrated
forecasts (reliability × max(0, μ) / σ_ε). Rank→conviction and fixed-premium Kelly are
not used on that path. Missing bundle falls back to the characterized incumbent path
(versioned; never an unversioned hybrid). Downstream controls are unchanged.

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
from digiquant.olympus.hermes.allocation_contracts import (
    AllocationInputBundle,
    AlteredTarget,
    AssetInputStatus,
    BindingConstraint,
    RejectedTarget,
)
from digiquant.olympus.hermes.allocation_hashes import weights_fingerprint
from digiquant.olympus.hermes.models.deliberation import is_unchallenged_carry
from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection
from digiquant.olympus.hermes.payloads import analyst_payloads, deliberation_summaries
from digiquant.olympus.hermes.pretrade_risk import (
    CostLiquidityScalars,
    ForecastQualityScalars,
    PreTradeRiskBuildRequest,
    build_pretrade_risk_report,
)
from digiquant.olympus.hermes.risk_controls import BreakerConfig, breaker_scale_from_nav_history
from digiquant.olympus.hermes.sector_map import asset_class, sector_bucket
from digiquant.olympus.hermes.sizing import (
    SizingCaps,
    TickerRisk,
    calibrated_raw_score,
    size_portfolio,
)
from digiquant.olympus.hermes.sizing_events import (
    LineageValidationError,
    SizingAdjustment,
    SizingAdjustmentType,
    validate_sizing_lineage,
)
from digiquant.olympus.hermes.turnover import (
    apply_rebalancing_cadence,
    clamp_no_trade_band,
    no_trade_band_pp,
)

logger = logging.getLogger(__name__)

# Calendar-day window to find the latest technicals row ≤ run_date. Wide enough to
# clear weekends + holidays + a stale prices cron (the Saturday-baseline lag, #726).
_VOL_LOOKBACK_DAYS = 40
_CONVICTION_FLOOR, _CONVICTION_CAP = -5.0, 5.0

H8_SIZING_INPUT_MODE_CALIBRATED = "calibrated"
H8_SIZING_INPUT_MODE_INCUMBENT = "incumbent"
_H8_SIZING_INPUT_MODES = frozenset(
    {H8_SIZING_INPUT_MODE_CALIBRATED, H8_SIZING_INPUT_MODE_INCUMBENT}
)
_SIZING_RATIONALE_FALLBACK = "Position weight set by deterministic risk sizing."
_MAX_ACTION_RATIONALE_LEN = 2000


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


def resolve_h8_sizing_input_mode(preferences: Mapping[str, Any]) -> str:
    """Versioned H8 raw-input mode. Unknown values fall back to calibrated (Gate 2)."""
    raw = preferences.get("h8_sizing_input_mode", H8_SIZING_INPUT_MODE_CALIBRATED)
    mode = str(raw).strip().lower() if raw is not None else H8_SIZING_INPUT_MODE_CALIBRATED
    if mode not in _H8_SIZING_INPUT_MODES:
        return H8_SIZING_INPUT_MODE_CALIBRATED
    return mode


def calibrated_scores_from_bundle(
    bundle: AllocationInputBundle,
    *,
    long_tickers: list[str],
) -> dict[str, float]:
    """Map H7-authorized longs to WP8.4 raw scores; degraded/negative → omitted.

    Missing or non-available calibrated slices receive no new risk (cash/safety).
    """
    by_ticker = {item.ticker: item for item in bundle.calibrated_returns}
    scores: dict[str, float] = {}
    for ticker in long_tickers:
        slice_ = by_ticker.get(ticker)
        if slice_ is None or slice_.status is not AssetInputStatus.AVAILABLE:
            continue
        if slice_.expected_gross_return is None or slice_.forecast_error_std is None:
            continue
        score = calibrated_raw_score(
            expected_gross_return=float(slice_.expected_gross_return),
            forecast_error_std=float(slice_.forecast_error_std),
            reliability_weight=float(slice_.reliability_weight),
        )
        if score > 0:
            scores[ticker] = score
    return scores


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


def _densify_memo_ranks(long_entries: list[TickerDirection]) -> dict[str, int]:
    """Map H7 long roster to dense ranks 1..N (best first).

    Gapful raw ranks (e.g. ``[2, 7, 11]``) and duplicate ranks tie-break by ticker
    so conviction mapping depends on ordering only, not rank gaps.
    """
    ordered = sorted(long_entries, key=lambda entry: (entry.conviction_rank, entry.ticker))
    return {entry.ticker: idx + 1 for idx, entry in enumerate(ordered)}


def _memo_effective_inputs(
    memo: PMDirectionMemo,
    _analysts: dict[str, dict[str, Any]],
    default_conviction: float,
) -> tuple[dict[str, float], dict[str, str]]:
    """Per H7-authorized long: conviction from dense rank; stance is not H5-gated."""
    long_entries = [entry for entry in memo.roster if entry.direction == "long"]
    n_long = len(long_entries)
    floor = max(default_conviction, 2.0)
    dense_ranks = _densify_memo_ranks(long_entries)
    convictions: dict[str, float] = {}
    stances: dict[str, str] = {}
    for entry in long_entries:
        convictions[entry.ticker] = _clamp_conviction(
            _rank_to_conviction(dense_ranks[entry.ticker], n_long, floor=floor)
        )
        # H7 owns eligibility on the memo path; H5 stance must not drop a long.
        stances[entry.ticker] = "buy"
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


def _verb(
    current: float | None,
    target: float,
    *,
    preferences: Mapping[str, Any] | None = None,
) -> str:
    """Rebalance verb from current → target weight. Unknown current ⇒ treat as 0."""
    cur = current or 0.0
    if cur <= 0 < target:
        return "new"
    if target <= 0 < cur:
        return "exit"
    if preferences is not None and cur > 0 and target > 0:
        if abs(target - cur) < no_trade_band_pp(cur, dict(preferences)):
            return "hold"
    elif abs(target - cur) <= 1e-9:
        return "hold"
    if target > cur:
        return "add"
    return "trim"


def _selection_rationale_by_ticker(
    state: AtlasResearchState,
    memo: PMDirectionMemo | None,
) -> dict[str, str]:
    """Per-ticker PM selection thesis for published rebalance actions (#2597).

    Priority: H7 roster narrative → H4 focus-roster rationale → H6 conclusion → H5 thesis.
    """
    out: dict[str, str] = {}

    if memo is not None:
        for row in memo.roster:
            narrative = str(row.narrative or "").strip()
            if not narrative:
                continue
            out[row.ticker.strip().upper()] = narrative[:_MAX_ACTION_RATIONALE_LEN]

    for entry in state.phase_hermes.focus_roster:
        ticker = entry.ticker.strip().upper()
        if ticker in out:
            continue
        rationale = str(entry.rationale or "").strip()
        if rationale:
            out[ticker] = rationale[:_MAX_ACTION_RATIONALE_LEN]

    for ticker, summary in deliberation_summaries(state).items():
        key = ticker.strip().upper()
        if key in out:
            continue
        conclusion = str(summary.get("conclusion") or "").strip()
        if conclusion:
            out[key] = conclusion[:_MAX_ACTION_RATIONALE_LEN]

    for ticker, payload in analyst_payloads(state).items():
        key = ticker.strip().upper()
        if key in out:
            continue
        thesis = str(payload.get("thesis") or "").strip()
        if thesis:
            out[key] = thesis[:_MAX_ACTION_RATIONALE_LEN]

    return out


def _published_action_rationale(
    ticker: str,
    selection_rationale_by_ticker: dict[str, str] | None,
) -> str:
    key = ticker.strip().upper()
    lookup = {
        k.strip().upper(): v.strip()
        for k, v in (selection_rationale_by_ticker or {}).items()
        if isinstance(k, str) and isinstance(v, str) and v.strip()
    }
    return lookup.get(key) or _SIZING_RATIONALE_FALLBACK


def _rebuild_actions(
    original_actions: list[Any],
    pm_targets: dict[str, float],
    sized: dict[str, float],
    current_weights: dict[str, float] | None = None,
    selection_rationale_by_ticker: dict[str, str] | None = None,
    preferences: Mapping[str, Any] | None = None,
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
    live = current_weights or {}
    pref = dict(preferences or {})
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
            if current is None:
                current = _opt_float(live.get(ticker))
            if current is not None:
                row["current_pct"] = round(current, 4)
                row["action"] = _verb(current, new_target, preferences=pref or None)
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
    for ticker, target in sized.items():
        if ticker not in seen:
            current = _opt_float(live.get(ticker))
            verb = _verb(current, target, preferences=pref or None)
            row: dict[str, Any] = {
                "ticker": ticker,
                "action": verb,
                "target_pct": round(target, 4),
                "rationale": _published_action_rationale(
                    ticker,
                    selection_rationale_by_ticker,
                ),
            }
            if current is not None:
                row["current_pct"] = round(current, 4)
            out.append(row)
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
    current_weights = preferences.get("current_weights") or {}
    widest_current = max(
        (_opt_float(v) or 0.0 for v in current_weights.values()),
        default=0.0,
    )
    return no_trade_band_pp(widest_current, dict(preferences)) if widest_current > 0 else threshold


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
) -> tuple[RebalancePayload | None, Any | None, Any | None]:
    """Run deterministic sizing; return None on no-op / fail-soft.

    Third element is the WP8.3 shadow ``AllocationInputBundle`` (or ``None``).
    """
    from digiquant.olympus.hermes.h8_risk_snapshots import resolve_h8_risk_artifacts

    caps = SizingCaps.from_preferences(state.config.preferences)
    memo = state.phase_hermes.pm_direction_memo
    memo_obj: PMDirectionMemo | None = None
    if memo is not None:
        memo_obj = (
            memo if isinstance(memo, PMDirectionMemo) else PMDirectionMemo.model_validate(memo)
        )
    selection_rationale_by_ticker = _selection_rationale_by_ticker(state, memo_obj)

    try:
        breaker = breaker_scale_from_nav_history(
            deps.client,
            state.run_date,
            config=BreakerConfig.from_preferences(state.config.preferences),
            workspace_id=getattr(state.config, "workspace_id", None),
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
    # #2803: resolver always returns typed artifacts (unavailable on failure).
    risk_artifacts = resolve_h8_risk_artifacts(
        state=state,
        pm_tickers=pm_tickers,
        corr=corr_frame,
    )
    # WP8.3 (#2730) / WP8.4 (#2734): assemble canonical AllocationInputBundle at H8 entry.
    # Covariance for the bundle must match the full H7 roster (long+flat), which may
    # differ from the longs-only ``pm_tickers`` snapshot used for incumbent sizing audit.
    allocation_bundle = None
    if memo is not None and risk_artifacts is not None:
        try:
            from digiquant.olympus.hermes.allocation_inputs import (
                assemble_allocation_input_bundle_from_state,
            )

            memo_obj = (
                memo_obj
                if memo_obj is not None
                else (
                    memo
                    if isinstance(memo, PMDirectionMemo)
                    else PMDirectionMemo.model_validate(memo)
                )
            )
            bundle_tickers = sorted(
                entry.ticker for entry in memo_obj.roster if not _is_cash(entry.ticker)
            )
            if bundle_tickers == sorted(pm_tickers):
                bundle_covariance = risk_artifacts.covariance_snapshot
            else:
                bundle_covariance = resolve_h8_risk_artifacts(
                    state=state,
                    pm_tickers=bundle_tickers,
                    corr=corr_frame,
                ).covariance_snapshot

            # Derive the common horizon from H6 deliberation (DEFAULT fills gaps only).
            # Hardcoding expected=21 rejected coherent non-21 books into silent
            # incumbent_fallback (#2814 / WP8 review finding).
            allocation_bundle = assemble_allocation_input_bundle_from_state(
                state,
                risk_policy=risk_artifacts.policy,
                covariance=bundle_covariance,
            )
        except Exception as exc:
            logger.warning("phase7e: allocation input bundle failed (%s); continuing", exc)
            allocation_bundle = None

    input_mode = resolve_h8_sizing_input_mode(state.config.preferences)
    calibrated_scores: dict[str, float] | None = None
    sizing_mode_label = H8_SIZING_INPUT_MODE_INCUMBENT
    if (
        memo is not None
        and input_mode == H8_SIZING_INPUT_MODE_CALIBRATED
        and allocation_bundle is not None
    ):
        candidate_scores = calibrated_scores_from_bundle(allocation_bundle, long_tickers=pm_tickers)
        if candidate_scores:
            calibrated_scores = candidate_scores
            sizing_mode_label = H8_SIZING_INPUT_MODE_CALIBRATED
        else:
            # Owner-approved degraded fallback: no AVAILABLE positive-alpha slice →
            # characterized incumbent path (never an unversioned hybrid / silent all-cash).
            sizing_mode_label = "incumbent_fallback"
            logger.warning(
                "phase7e: calibrated sizing requested but no usable calibrated scores; "
                "falling back to characterized incumbent rank→conviction path"
            )
    elif memo is not None and input_mode == H8_SIZING_INPUT_MODE_CALIBRATED:
        sizing_mode_label = "incumbent_fallback"
        logger.warning(
            "phase7e: calibrated sizing requested but AllocationInputBundle unavailable; "
            "falling back to characterized incumbent rank→conviction path"
        )

    unchallenged: list[str] = []
    events: list[SizingAdjustment] = []
    try:
        analysts = analyst_payloads(state)
        debates = deliberation_summaries(state)
        if calibrated_scores is not None:
            # H7 owns eligibility; H5 stance must not drop a long. Magnitude from bundle.
            stances = {ticker: "buy" for ticker in pm_tickers}
            # Corr-dedup priority uses calibrated scores; unused tickers stay at 0.
            convictions = {
                ticker: float(calibrated_scores.get(ticker, 0.0)) for ticker in pm_tickers
            }
            unchallenged = []
        elif memo is not None:
            convictions, stances = _memo_effective_inputs(memo, analysts, caps.min_conviction)
            convictions, unchallenged = _cap_unchallenged_convictions(
                convictions, debates, bar=caps.min_conviction, events=events
            )
        else:
            convictions, stances = _effective_inputs(
                pm_tickers,
                analysts,
                debates,
                default_conviction=caps.min_conviction,
            )
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
            calibrated_scores=calibrated_scores,
        )
    except Exception as exc:  # sizing must never crash the run
        logger.warning("phase7e: risk sizing failed (%s); keeping prior book", exc)
        return None, risk_artifacts, allocation_bundle

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
    drifted_current = {
        str(k): float(v) for k, v in current_weights.items() if _opt_float(v) is not None
    }
    sized = clamp_no_trade_band(
        sized,
        current_weights=drifted_current,
        preferences=dict(state.config.preferences),
    )
    mode_note = f" sizing_input_mode={sizing_mode_label}."
    bundle_note = ""
    bundle_hash: str | None = None
    if allocation_bundle is not None:
        bundle_hash = allocation_bundle.bundle_content_hash
        bundle_note = f" allocation_input_bundle_hash={bundle_hash}."
    updated: RebalancePayload = {
        "recommended_portfolio": [
            {"ticker": ticker, "target_pct": round(weight, 4)} for ticker, weight in sized.items()
        ],
        "actions": _rebuild_actions(
            original_actions,
            pm_targets,
            sized,
            current_weights,
            selection_rationale_by_ticker=selection_rationale_by_ticker,
            preferences=dict(state.config.preferences),
        ),
        "notes": (f"{prior_notes}\n\n" if prior_notes else "")
        + f"Risk-sizing (H8): {result.explanation}{breaker_note}"
        f"{_unchallenged_note(unchallenged)}{mode_note}{bundle_note}",
        # #2417 / #2768: reason-coded H8 adjustments — persisted by H9 as
        # TargetAdjustment rows when unit is ``pct``. ``requested_pct`` is the
        # pre-cap map so ledger requested_weight can differ from approved.
        "adjustments": [event.model_dump() for event in events],
        "requested_pct": dict(result.requested_pct),
        "h8_sizing_input_mode": sizing_mode_label,
    }
    if bundle_hash is not None:
        updated["allocation_input_bundle_hash"] = bundle_hash

    logger.info(
        "phase7e: sized %d→%d holdings, %.1f%% invested / %.1f%% cash, ex-ante vol ~%s%% (%s)",
        len(pm_tickers),
        len(sized),
        result.gross_pct,
        result.cash_pct,
        result.realized_portfolio_vol,
        sizing_mode_label,
    )
    return updated, risk_artifacts, allocation_bundle


_BINDING_CONSTRAINT_TYPES = frozenset(
    {
        SizingAdjustmentType.SINGLE_NAME_CAP,
        SizingAdjustmentType.SECTOR_CAP,
        SizingAdjustmentType.CORRELATION_DEDUP,
        SizingAdjustmentType.DRAWDOWN_BREAKER,
        SizingAdjustmentType.GRID_ROUNDING,
        SizingAdjustmentType.FINAL_GROSS_SCALE,
    }
)


def _final_book_weights(sized_book: RebalancePayload) -> tuple[dict[str, float], float]:
    """Extract final risky weights + cash from the post-control sized book.

    Uses the same extractor as H9 (`weights_from_sized_book`) so the report
    fingerprint equals the book H9 will validate and commit (#2824 / WP9 review).
    """
    # Lazy import: commit_io pulls atlas/hermes writers; avoid module-cycle at import.
    from digiquant.olympus.hermes.writers.commit_io import weights_from_sized_book

    risky = weights_from_sized_book(sized_book)
    invested = sum(risky.values())
    cash = max(0.0, 100.0 - invested)
    return risky, cash


def _prior_book_weights_for_report(
    state: AtlasResearchState,
    allocation_bundle: AllocationInputBundle | None,
) -> tuple[dict[str, float], float]:
    """Prior risky/cash for the report — prefer the exact bundle snapshot."""
    if allocation_bundle is not None:
        prior = allocation_bundle.prior_book
        return prior.risky_weights(), float(prior.cash_weight_pct)
    prefs = dict(state.config.preferences or {})
    current = dict(prefs.get("current_weights") or {})
    risky: dict[str, float] = {}
    cash = 0.0
    for key, value in current.items():
        weight = _opt_float(value)
        if weight is None:
            continue
        if _is_cash(str(key)):
            cash += weight
            continue
        if weight > 0:
            risky[str(key)] = weight
    if cash <= 0:
        cash = max(0.0, 100.0 - sum(risky.values()))
    return risky, cash


def _controls_from_adjustments(
    sized_book: RebalancePayload,
) -> tuple[tuple[BindingConstraint, ...], tuple[AlteredTarget, ...], tuple[RejectedTarget, ...]]:
    """Map H8 explanation events onto WP9.1 control blocks (observational only).

    Multiple adjustments can land on one ticker (carry then final-cap, etc.). The
    contract requires unique tickers in altered/rejected lists, so we collapse to
    first-requested → last-adjusted per ticker while keeping every binding event.
    """
    binding: list[BindingConstraint] = []
    altered_by_ticker: dict[str, AlteredTarget] = {}
    rejected_by_ticker: dict[str, RejectedTarget] = {}
    for raw in sized_book.get("adjustments") or []:
        try:
            event = (
                raw if isinstance(raw, SizingAdjustment) else SizingAdjustment.model_validate(raw)
            )
        except Exception:
            continue
        kind = event.adjustment_type
        if kind in _BINDING_CONSTRAINT_TYPES and event.unit == "pct":
            binding.append(
                BindingConstraint(
                    constraint_id=f"{kind.value}:{event.ticker}",
                    constraint_kind=kind.value,
                    ticker=event.ticker,
                    bound_value=float(event.adjusted_pct),
                    observed_value=float(event.original_pct),
                    reason=event.reason,
                )
            )
        if event.unit != "pct":
            continue
        if kind is SizingAdjustmentType.FLAT_EXIT and float(event.adjusted_pct) <= 0.0:
            rejected_by_ticker[event.ticker] = RejectedTarget(
                ticker=event.ticker,
                requested_weight_pct=float(event.original_pct),
                reason=event.reason,
            )
            altered_by_ticker.pop(event.ticker, None)
            continue
        if abs(float(event.original_pct) - float(event.adjusted_pct)) <= 1e-12:
            continue
        prior = altered_by_ticker.get(event.ticker)
        requested = (
            float(prior.requested_weight_pct) if prior is not None else float(event.original_pct)
        )
        altered_by_ticker[event.ticker] = AlteredTarget(
            ticker=event.ticker,
            requested_weight_pct=requested,
            final_weight_pct=float(event.adjusted_pct),
            adjustment_type=kind.value,
            reason=event.reason,
        )
    return (
        tuple(binding),
        tuple(altered_by_ticker[t] for t in sorted(altered_by_ticker)),
        tuple(rejected_by_ticker[t] for t in sorted(rejected_by_ticker)),
    )


def _forecast_quality_from_bundle(
    allocation_bundle: AllocationInputBundle | None,
) -> ForecastQualityScalars | None:
    if allocation_bundle is None:
        return None
    degraded = 0
    uncertainty_vals: list[float] = []
    for slice_ in allocation_bundle.calibrated_returns:
        if slice_.status is not AssetInputStatus.AVAILABLE:
            degraded += 1
            continue
        if slice_.forecast_error_std is not None:
            uncertainty_vals.append(float(slice_.forecast_error_std))
    uncertainty = sum(uncertainty_vals) / len(uncertainty_vals) if uncertainty_vals else None
    return ForecastQualityScalars(
        staleness_sessions=0.0,
        forecast_uncertainty=uncertainty,
        degraded_input_count=float(degraded),
    )


def _cost_scalars_from_state(state: AtlasResearchState) -> CostLiquidityScalars | None:
    """Observational WP7 estimates already on state (typically empty until H9)."""
    estimates = state.phase_hermes.action_cost_estimates or {}
    if not estimates:
        return None
    expected_costs: list[float] = []
    adv_vals: list[float] = []
    days_vals: list[float] = []
    for payload in estimates.values():
        if not isinstance(payload, dict):
            continue
        cost = _opt_float(payload.get("expected_cost_bps"))
        if cost is None:
            cost = _opt_float(payload.get("expected_cost"))
        if cost is not None:
            expected_costs.append(cost)
        adv = _opt_float(payload.get("adv_participation_pct"))
        if adv is not None:
            adv_vals.append(adv)
        days = _opt_float(payload.get("days_to_liquidate"))
        if days is not None:
            days_vals.append(days)
    if not expected_costs and not adv_vals and not days_vals:
        return CostLiquidityScalars(unavailable_reason="cost/liquidity estimates incomplete")
    return CostLiquidityScalars(
        expected_cost=sum(expected_costs) / len(expected_costs) if expected_costs else None,
        adv_participation_pct=max(adv_vals) if adv_vals else None,
        days_to_liquidate=max(days_vals) if days_vals else None,
    )


def _annualized_vols_for_book(
    *,
    client: SupabaseClient,
    tickers: list[str],
    run_date: date,
) -> dict[str, float] | None:
    if not tickers:
        return {}
    risk = _load_ticker_risk(client, tickers, run_date)
    vols = {
        ticker: float(info.hist_vol_21)
        for ticker, info in risk.items()
        if info.hist_vol_21 is not None and float(info.hist_vol_21) >= 0.0
    }
    return vols or None


def _sector_map_for_book(tickers: list[str]) -> dict[str, str]:
    return {ticker: sector_bucket(ticker) for ticker in tickers}


def build_pretrade_risk_report_for_final_book(
    *,
    state: AtlasResearchState,
    sized_book: RebalancePayload,
    allocation_bundle: AllocationInputBundle | None,
    risk_artifacts: Any | None,
    deps: RiskSizingDeps,
) -> dict[str, Any] | None:
    """Build ``PreTradeRiskReport`` from the post-control final book only.

    Read-only observation — never mutates ``sized_book`` weights. Returns ``None``
    when required identity inputs are missing or the builder fails (typed report
    failure blocks only report promotion before H9 enforcement).
    """
    if allocation_bundle is None and not sized_book.get("allocation_input_bundle_hash"):
        return None
    policy_hash: str | None = None
    covariance = None
    if risk_artifacts is not None:
        policy_hash = getattr(getattr(risk_artifacts, "policy", None), "content_hash", None)
        covariance = getattr(risk_artifacts, "covariance_snapshot", None)
    if policy_hash is None and allocation_bundle is not None:
        policy_hash = allocation_bundle.control_settings.risk_policy_content_hash
    if not policy_hash:
        return None

    bundle_hash = (
        allocation_bundle.bundle_content_hash
        if allocation_bundle is not None
        else str(sized_book.get("allocation_input_bundle_hash"))
    )
    if not bundle_hash:
        return None

    final_risky, final_cash = _final_book_weights(sized_book)
    prior_risky, prior_cash = _prior_book_weights_for_report(state, allocation_bundle)
    binding, altered, rejected = _controls_from_adjustments(sized_book)
    tickers = sorted(final_risky)
    try:
        report = build_pretrade_risk_report(
            PreTradeRiskBuildRequest(
                run_id=str(state.run_id),
                session_date=state.run_date,
                allocation_input_bundle_hash=bundle_hash,
                risk_policy_hash=str(policy_hash),
                prior_risky_weights_pct=prior_risky,
                prior_cash_weight_pct=prior_cash,
                final_risky_weights_pct=final_risky,
                final_cash_weight_pct=final_cash,
                covariance_snapshot=covariance,
                annualized_vol_pct=_annualized_vols_for_book(
                    client=deps.client, tickers=tickers, run_date=state.run_date
                ),
                sector_by_ticker=_sector_map_for_book(tickers) if tickers else None,
                cost_liquidity=_cost_scalars_from_state(state),
                forecast_quality=_forecast_quality_from_bundle(allocation_bundle),
                binding_constraints=binding,
                altered_targets=altered,
                rejected_targets=rejected,
            )
        )
    except Exception as exc:
        logger.warning("phase7e: pre-trade risk report build failed (%s); omitting report", exc)
        return None

    expected_fp = weights_fingerprint(final_risky)
    if report.final_book_weights_fingerprint != expected_fp:
        logger.warning(
            "phase7e: pre-trade risk report fingerprint mismatch "
            "(report=%s book=%s); omitting report",
            report.final_book_weights_fingerprint,
            expected_fp,
        )
        return None
    return report.model_dump(mode="json")


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

        sized_book, risk_artifacts, allocation_bundle = _build_sized_book(
            pm_tickers=pm_tickers,
            pm_targets=pm_targets,
            original_actions=original_actions,
            prior_notes=prior_notes,
            state=state,
            deps=deps,
        )

        def _hermes_shadow(**kwargs: Any) -> PhaseHermesState:
            payload = dict(kwargs)
            if risk_artifacts is not None:
                payload["risk_policy"] = risk_artifacts.policy.model_dump(mode="json")
                payload["covariance_snapshot"] = risk_artifacts.covariance_snapshot.model_dump(
                    mode="json"
                )
            if allocation_bundle is not None:
                payload["allocation_input_bundle"] = allocation_bundle.model_dump(mode="json")
            return PhaseHermesState(**payload)

        if sized_book is None:
            if risk_artifacts is not None or allocation_bundle is not None:
                return {"phase_hermes": _hermes_shadow()}
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

        # WP9.3: attach PreTradeRiskReport only after the final control shell.
        # Fail-soft: report omission does not change the already-final sized book.
        report_payload: dict[str, Any] | None = None
        try:
            report_payload = build_pretrade_risk_report_for_final_book(
                state=state,
                sized_book=sized_book,
                allocation_bundle=allocation_bundle,
                risk_artifacts=risk_artifacts,
                deps=deps,
            )
        except Exception as exc:
            logger.warning(
                "phase7e: pre-trade risk report attach failed (%s); omitting report",
                exc,
            )
            report_payload = None
        if report_payload is not None:
            sized_book = {
                **sized_book,
                "pre_trade_risk_report_hash": report_payload.get("report_content_hash"),
            }

        hermes_kwargs: dict[str, Any] = {"sized_book": sized_book}
        if report_payload is not None:
            hermes_kwargs["pre_trade_risk_report"] = report_payload
        hermes_update = _hermes_shadow(**hermes_kwargs)

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


__all__ = [
    "H8_SIZING_INPUT_MODE_CALIBRATED",
    "H8_SIZING_INPUT_MODE_INCUMBENT",
    "RiskSizingDeps",
    "build_pretrade_risk_report_for_final_book",
    "build_risk_sizing_node",
    "build_risk_sizing_phase",
    "calibrated_scores_from_bundle",
    "resolve_h8_sizing_input_mode",
]
