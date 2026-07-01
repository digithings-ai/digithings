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
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint: duck-typed Supabase client + rows

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.data.queries import get_return_correlations
from digiquant.olympus.atlas.state import AtlasResearchState, PhaseHermesState, RebalancePayload
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo
from digiquant.olympus.hermes.payloads import analyst_payloads, deliberation_summaries
from digiquant.olympus.hermes.risk_controls import BreakerConfig, breaker_scale_from_nav_history
from digiquant.olympus.hermes.sector_map import asset_class, sector_bucket
from digiquant.olympus.hermes.sizing import SizingCaps, TickerRisk, size_portfolio
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
        except Exception as exc:  # noqa: BLE001 — vol read is best-effort; default vol used
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
    original_actions: list[Any], pm_targets: dict[str, float], sized: dict[str, float]
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
    # Sized tickers the PM had no explicit action row for (rare) → minimal new rows.
    for ticker, target in sized.items():
        if ticker not in seen:
            out.append(
                {
                    "ticker": ticker,
                    "action": "new",
                    "target_pct": round(target, 4),
                    "rationale": "Position weight set by deterministic risk sizing.",
                }
            )
    return out


def _build_sized_book(
    *,
    pm_tickers: list[str],
    pm_targets: dict[str, float],
    original_actions: list[Any],
    prior_notes: str,
    state: AtlasResearchState,
    deps: RiskSizingDeps,
) -> RebalancePayload | None:
    """Run deterministic sizing; return None on no-op / fail-soft."""
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
    except Exception as exc:  # noqa: BLE001 — breaker is best-effort; neutral on failure
        logger.warning("phase7e: drawdown breaker failed (%s); neutral scale", exc)
        breaker_scale, breaker_note = 1.0, ""

    try:
        corr_frame = get_return_correlations(
            client=deps.client,
            tickers=pm_tickers,
            run_date=state.run_date,
        )
    except Exception as exc:  # noqa: BLE001 — correlation is best-effort
        logger.warning("phase7e: correlation read failed (%s); using full-correlation default", exc)
        corr_frame = None

    try:
        analysts = analyst_payloads(state)
        if memo is not None:
            convictions, stances = _memo_effective_inputs(memo, analysts, caps.min_conviction)
        else:
            convictions, stances = _effective_inputs(
                pm_tickers,
                analysts,
                deliberation_summaries(state),
                default_conviction=caps.min_conviction,
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
    except Exception as exc:  # noqa: BLE001 — sizing must never crash the run
        logger.warning("phase7e: risk sizing failed (%s); keeping prior book", exc)
        return None

    sized = {p.ticker: p.target_pct for p in result.positions}
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
    )
    updated: RebalancePayload = {
        "recommended_portfolio": [
            {"ticker": ticker, "target_pct": round(weight, 4)} for ticker, weight in sized.items()
        ],
        "actions": _rebuild_actions(original_actions, pm_targets, sized),
        "notes": (f"{prior_notes}\n\n" if prior_notes else "")
        + f"Risk-sizing (H8): {result.explanation}{breaker_note}",
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
    return updated


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

        sized_book = _build_sized_book(
            pm_tickers=pm_tickers,
            pm_targets=pm_targets,
            original_actions=original_actions,
            prior_notes=prior_notes,
            state=state,
            deps=deps,
        )
        if sized_book is None:
            return {}

        if memo is not None:
            return {"phase_hermes": PhaseHermesState(sized_book=sized_book)}
        return {"phase7d_rebalance": sized_book}

    return risk_sizing


def build_risk_sizing_phase(deps: RiskSizingDeps) -> PipelinePhase:
    """Wrap the enforcement node into a single-node ``PipelinePhase`` (H8)."""
    return PipelinePhase(
        name="hermes_h8_risk_sizing",
        nodes=[NodeSpec(name="hermes/portfolio/risk-sizing", run=build_risk_sizing_node(deps))],
    )


__all__ = ["RiskSizingDeps", "build_risk_sizing_node", "build_risk_sizing_phase"]
