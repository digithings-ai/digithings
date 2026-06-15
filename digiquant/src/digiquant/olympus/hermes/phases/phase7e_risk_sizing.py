"""Phase 7E — deterministic risk-sizing enforcement (#726, Pillar 2).

The PM (Phase 7D) proposes a candidate book: *which* tickers to hold (direction) with a
per-ticker conviction + narrative. This terminal-side phase replaces the PM's eyeballed
target weights with deterministic, risk-managed weights via
:func:`~digiquant.olympus.hermes.sizing.size_portfolio` — the code half of the FinPos
direction/sizing split. Sizing, position/sector caps, correlation de-dup, vol-targeting,
and the drawdown-breaker scale become CODE, so the book's risk profile is reproducible
and auditable.

**Runs before publish + materialize** (not between them): ``publish_phase`` writes the
``pm-rebalance`` document from ``state.phase7d_rebalance`` and ``portfolio_materialize``
books ``recommended_portfolio`` — so to keep the *published* digest and the *booked*
positions consistent, the sized book must be in state before either runs.

Per ticker the PM recommended: effective conviction = analyst ``conviction_score`` +
debate ``conviction_delta`` (clamped −5..+5); stance from the analyst (a carried holding
with no fresh analyst payload defaults to the conviction floor + "hold" so it survives
the select gate at minimal tilt rather than being dropped to cash for lack of new work).
Per-ticker vol comes from the latest ``price_technicals`` row at-or-before ``run_date``
(``hist_vol_21`` → ATR% → default); the concentration bucket from
:func:`~digiquant.olympus.hermes.sector_map.sector_bucket`.

Fail-soft: any data-layer or sizing error degrades to the PM's original book (the run
never crashes and the book is never silently emptied). No-op when the PM produced no
rebalance (``None``) — distinct from a deliberate 100%-cash stance (empty
``recommended_portfolio``), which the sizer simply returns as empty.

Correlation + the drawdown breaker are not wired yet (``corr=None`` → the sizer's
conservative full-correlation default; ``breaker_scale=1.0``); both arrive in follow-up
Pillar 2 PRs without changing this node's contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint: duck-typed Supabase client + rows

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import AtlasResearchState, RebalancePayload
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.sector_map import sector_bucket
from digiquant.olympus.hermes.sizing import SizingCaps, TickerRisk, size_portfolio

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


def _pm_direction(recommended: list[Any]) -> dict[str, float]:
    """The PM's chosen names → its proposed weight (deduped, positive, non-CASH).

    These are the *direction* the sizer re-sizes; the PM's actual weights are discarded
    in favour of conviction-based sizing but kept here to rebuild the action list.
    """
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


def build_risk_sizing_node(deps: RiskSizingDeps):
    """Return the Phase 7E enforcement node bound to ``deps``."""

    def risk_sizing(state: AtlasResearchState) -> dict[str, Any]:
        rebalance = state.phase7d_rebalance
        if rebalance is None:
            return {}  # PM never ran (partial graph / dry-run) — don't fabricate a book.

        pm_targets = _pm_direction(rebalance.get("recommended_portfolio") or [])
        pm_tickers = list(pm_targets)
        caps = SizingCaps.from_preferences(state.config.preferences)

        try:
            convictions, stances = _effective_inputs(
                pm_tickers,
                dict(state.phase7c_analysts),
                dict(state.phase7cd_debates),
                default_conviction=caps.min_conviction,
            )
            risk = _load_ticker_risk(deps.client, pm_tickers, state.run_date)
            result = size_portfolio(
                convictions=convictions,
                stances=stances,
                risk=risk,
                corr=None,
                caps=caps,
                breaker_scale=1.0,
            )
        except Exception as exc:  # noqa: BLE001 — sizing must never crash the run; keep PM book
            logger.warning("phase7e: risk sizing failed (%s); keeping PM book", exc)
            return {}

        sized = {p.ticker: p.target_pct for p in result.positions}
        updated: RebalancePayload = dict(rebalance)  # type: ignore[assignment]
        updated["recommended_portfolio"] = [
            {"ticker": ticker, "target_pct": round(weight, 4)} for ticker, weight in sized.items()
        ]
        updated["actions"] = _rebuild_actions(rebalance.get("actions") or [], pm_targets, sized)
        prior_notes = str(rebalance.get("notes") or "").strip()
        updated["notes"] = (
            f"{prior_notes}\n\n" if prior_notes else ""
        ) + f"Risk-sizing (Phase 7E): {result.explanation}"

        logger.info(
            "phase7e: sized %d→%d holdings, %.1f%% invested / %.1f%% cash, ex-ante vol ~%s%% (%s)",
            len(pm_tickers),
            len(sized),
            result.gross_pct,
            result.cash_pct,
            result.realized_portfolio_vol,
            caps.sizing_mode,
        )
        return {"phase7d_rebalance": updated}

    return risk_sizing


def build_risk_sizing_phase(deps: RiskSizingDeps) -> PipelinePhase:
    """Wrap the enforcement node into a single-node ``PipelinePhase``."""
    return PipelinePhase(
        name="risk-sizing",
        nodes=[NodeSpec(name="phase7e-risk-sizing", run=build_risk_sizing_node(deps))],
    )


__all__ = ["RiskSizingDeps", "build_risk_sizing_node", "build_risk_sizing_phase"]
