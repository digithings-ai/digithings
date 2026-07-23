"""Phase 9D — materialize the PM decision into the paper portfolio (#700).

The Hermes PM (Phase 7D) emits ``state.phase7d_rebalance`` — a target book of
``recommended_portfolio`` weights. Previously that died as a document; the
``positions`` / ``nav_history`` tables the dashboard reads never got a row.
This terminal step turns the decision into the actual paper book, daily.

Owner decisions (2026-06-13):
- **Pipeline owns the book** — every non-monthly run auto-materializes.
- **NAV is a base-100 normalized index** (no FX, no notional dollars). Matches
  the ``nav_history`` schema intent (migration 012: "Indexed portfolio value
  (base 100) from simulated path"). No broker, no real money — paper only.

NAV chaining: ``nav(D) = nav(prev) × (1 + Σ wᵢ(prev) · deltaᵢ)`` where ``deltaᵢ``
is the freshest completed single-trading-day return from
:func:`query_price_deltas` (trading-day-aware; CASH delta = 0). The first run
(no prior positions) seeds ``nav = 100``. Because the scheduled run fires
intraday — before today's close lands in ``price_history`` — the index advances
using the most recent *available* close pair, i.e. one trading-day phase lag.
That is the standard, defensible behavior for an EOD-priced paper index.

All writes are idempotent upserts (``positions`` on ``(date, ticker)``,
``nav_history`` on ``date``), so a re-run of the same date is a no-op-equivalent.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint suppression: duck-typed Supabase client + rows

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.atlas.supabase_io import SupabaseClient, load_prior_book, query_price_deltas
from digiquant.olympus.hermes.payloads import analyst_payloads, deliberation_summaries, sized_book
from digiquant.olympus.hermes.risk_envelope import risk_horizon_days
from digiquant.olympus.hermes.sector_map import sector_bucket
from digiquant.olympus.performance_returns import calculate_performance_returns

logger = logging.getLogger(__name__)

# Seed value for the normalized NAV index on the first ever run.
_SEED_NAV = 100.0

# Minimum NAV history rows for Sharpe / vol / max-drawdown / alpha to be meaningful.
# Matches the gate in refresh_performance_metrics.py. Below this threshold, risk
# metrics are written as NULL (not 0) so the dashboard shows "insufficient history".
_MIN_NAV_HISTORY_ROWS = 20

# Benchmark ticker for portfolio alpha computation.
_ALPHA_BENCHMARK = "SPY"

# Per-position advisory risk fields (Pillar 2E). Gated OFF by default: the new columns
# (migration 039) and entry_price/entry_date population only land when the flag is on AND
# the migration has been applied to prod — so merging this code never breaks the scheduled
# delta/baseline materialize (which would otherwise upsert columns that don't exist yet).
_RISK_FIELDS_ENV = "OLYMPUS_POSITION_RISK_FIELDS"
_ATR_STOP_MULT = 2.0  # advisory stop at ~2× daily ATR below entry
_ATR_TARGET_MULT = 3.0  # advisory target at ~3× daily ATR above entry (1.5 R:R)
_CONVICTION_FLOOR, _CONVICTION_CAP = -5.0, 5.0


def _position_risk_fields_enabled() -> bool:
    return os.environ.get(_RISK_FIELDS_ENV, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class MaterializeDeps:
    """Wiring deps for the Phase 9D materialization node (injected client)."""

    client: SupabaseClient


def _coerce_float(val: Any) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _is_cash(ticker: Any) -> bool:
    return isinstance(ticker, str) and ticker.strip().upper() == "CASH"


# Map the analyst stance onto a valid `theses.status` (migration 002 CHECK:
# ACTIVE | MONITORING | CHALLENGED | CLOSED | INVALIDATED | PAUSED | NEW).
_THESIS_STATUS_BY_STANCE = {
    "buy": "ACTIVE",
    "hold": "ACTIVE",
    "watch": "MONITORING",
    "sell": "CHALLENGED",
}
_DEFAULT_THESIS_STATUS = "ACTIVE"


def _stance_to_thesis_status(stance: Any) -> str:
    if isinstance(stance, str):
        return _THESIS_STATUS_BY_STANCE.get(stance.strip().lower(), _DEFAULT_THESIS_STATUS)
    return _DEFAULT_THESIS_STATUS


def _clip(text: Any, limit: int) -> str:
    return str(text or "").strip()[:limit]


def _default_invalidation(analyst: dict[str, Any]) -> str:
    """Generate a rule-based invalidation string when the analyst left it empty.

    Priority order:
    1. Explicit ``stop_loss_pct`` from the analyst → use as-is.
    2. ``atr_pct`` available and > 0 → volatility-scaled stop at ~2×ATR
       (``_ATR_STOP_MULT``). This is Pillar 2E: a T-bill ETF with 0.1% daily
       ATR gets a 0.2% stop, not a generic 8%.
    3. Fallback → generic 8% advisory stop (entry-price-relative or absolute).

    The result is always non-empty so ACTIVE theses satisfy the non-empty
    invalidation contract (#814).
    """
    stop = _opt_float(analyst.get("stop_loss_pct"))
    if stop is not None and stop < 0:
        # stop_loss_pct is stored as a negative percentage (e.g. -5.0 means −5%)
        return f"Close if price falls {abs(stop):.1f}% below entry"
    # Volatility-scaled stop from ATR (#953 — Pillar 2E).
    atr = _opt_float(analyst.get("atr_pct"))
    if atr is not None and atr > 0:
        vol_stop = round(_ATR_STOP_MULT * atr, 1)
        entry = _opt_float(analyst.get("entry_price"))
        if entry is not None and entry > 0:
            threshold = round(entry * (1.0 - vol_stop / 100.0), 2)
            return (
                f"Close if price < {threshold:.2f} "
                f"({vol_stop:.1f}% volatility-scaled advisory stop from entry {entry:.2f})"
            )
        return f"Close if price falls {vol_stop:.1f}% below entry (volatility-scaled advisory stop)"
    entry = _opt_float(analyst.get("entry_price"))
    if entry is not None and entry > 0:
        # Derive a simple -8% advisory stop from entry
        threshold = entry * (1.0 - 0.08)
        return f"Close if price < {threshold:.2f} (8% advisory stop from entry {entry:.2f})"
    return "Close if price breaks below entry by more than 8% (advisory stop)"


def _upsert_theses(
    *,
    client: SupabaseClient,
    date_str: str,
    weights: dict[str, float],
    analysts: dict[str, Any],
    debates: dict[str, Any],
) -> int:
    """Materialize one thesis row (+ vehicle) per booked holding (#713).

    The live Atlas→Hermes chain previously never wrote the ``theses`` table (only
    frozen legacy scripts did), so the dashboard's Theses surface stayed empty.
    This derives one thesis per held ticker — keyed ``(date, thesis_id=ticker.lower())``
    to match the ``theses`` unique key — from the per-ticker ``AnalystPayload``
    (thesis text → notes/name, stance → status, debate bear-case / key tension
    → invalidation). The vehicle is the holding's own ticker.

    ``thesis_vehicles`` FK-references ``(date, thesis_id)`` on ``theses``, so the
    parent rows are written first; vehicle writes are best-effort enrichment and
    never block the book.

    Invariants enforced on write (#814):
    - Every ACTIVE thesis has a non-empty invalidation string.
    - A rule-based default is generated when the analyst/debate left it blank.
    """
    if not weights:
        return 0
    thesis_rows: list[dict[str, Any]] = []
    vehicle_rows: list[dict[str, Any]] = []
    for ticker in weights:
        analyst = analysts.get(ticker) or {}
        debate = debates.get(ticker) or {}
        short = _clip(analyst.get("thesis"), 60)
        # Prefer explicit debate invalidation; fall back to analyst field; then generate a default.
        # An empty invalidation on an ACTIVE thesis makes the dashboard's risk surface useless (#814).
        raw_invalidation = _clip(
            debate.get("bear_case") or debate.get("key_tension") or analyst.get("invalidation"), 400
        )
        status = _stance_to_thesis_status(analyst.get("stance"))
        if not raw_invalidation and status in ("ACTIVE", "MONITORING", "CHALLENGED"):
            invalidation = _default_invalidation(analyst)
        else:
            invalidation = raw_invalidation
        thesis_rows.append(
            {
                "date": date_str,
                "thesis_id": ticker.lower(),
                "name": f"{ticker} — {short}" if short else ticker,
                "vehicle": ticker,
                "invalidation": invalidation,
                "status": status,
                "notes": _clip(analyst.get("thesis"), 500),
            }
        )
        vehicle_rows.append(
            {
                "date": date_str,
                "thesis_id": ticker.lower(),
                "ticker": ticker,
                "rationale": "primary vehicle from PM allocation",
                "candidate_rank": 1,
            }
        )
    for row in thesis_rows:
        client.table("theses").upsert(row, on_conflict="date,thesis_id").execute()
    for row in vehicle_rows:
        try:
            client.table("thesis_vehicles").upsert(
                row, on_conflict="date,thesis_id,ticker"
            ).execute()
        except Exception as exc:  # noqa: BLE001 — vehicles are enrichment; never block the book
            logger.warning("phase9d: thesis_vehicles upsert failed (%s); continuing", exc)
    return len(thesis_rows)


def _prior_nav(client: SupabaseClient, run_date: date) -> float:
    """Latest ``nav_history.nav`` strictly before ``run_date`` (seed if none)."""
    resp = (
        client.table("nav_history")
        .select("date, nav")
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return _SEED_NAV
    nav = _coerce_float(rows[0].get("nav"))
    return nav if nav > 0 else _SEED_NAV


def _compute_nav(client: SupabaseClient, run_date: date, prior_book: list[dict[str, Any]]) -> float:
    """Chain the prior book's realized return onto the prior NAV index value."""
    prior_nav = _prior_nav(client, run_date)
    held = {
        str(r.get("ticker")): _coerce_float(r.get("weight_pct"))
        for r in prior_book
        if r.get("ticker") and not _is_cash(r.get("ticker"))
    }
    if not held:
        # No held names (first run, prior book all-cash, or positions pruned
        # while nav_history persists) → carry the index forward flat. _prior_nav
        # already returns the 100.0 seed when nav_history is empty, so this also
        # covers the first-ever run without resetting an existing index.
        return round(prior_nav, 6)
    deltas = query_price_deltas(client=client, tickers=tuple(held), run_date=run_date)
    port_return = sum((w / 100.0) * deltas.get(t, 0.0) for t, w in held.items())
    return round(prior_nav * (1.0 + port_return), 6)


def _upsert_portfolio_metrics(
    *,
    client: SupabaseClient,
    run_date: date,
) -> None:
    """Compute and persist ``portfolio_metrics`` risk stats from ``nav_history``.

    Fills sharpe, volatility, max_drawdown, and alpha columns that were
    previously left NULL (#953). Mirrors the math in
    ``refresh_performance_metrics._risk_metrics_from_nav_history`` (annualized
    Sharpe = mean/std * sqrt(252), vol = std * sqrt(252) * 100, max-drawdown
    from the equity curve). Alpha = portfolio total return - SPY total return
    over the same window.

    When ``nav_history`` has fewer than ``_MIN_NAV_HISTORY_ROWS`` rows the risk
    metrics are NULL (not 0) — the dashboard shows "insufficient history".

    ``pnl_pct`` is the day-over-day NAV return (latest NAV pair).

    Idempotent: upserts on ``date``.
    """
    date_str = run_date.isoformat()

    # Fetch all nav_history up to run_date for risk metrics.
    resp = (
        client.table("nav_history").select("date,nav").lte("date", date_str).order("date").execute()
    )
    nav_rows = list(getattr(resp, "data", None) or [])
    nav_observations = [row for row in nav_rows if row.get("date") and row.get("nav") is not None]
    navs = [_coerce_float(row.get("nav")) for row in nav_observations]

    benchmark_closes: list[float] = []
    if len(nav_observations) >= 2:
        try:
            benchmark_resp = (
                client.table("price_history")
                .select("date,close")
                .eq("ticker", _ALPHA_BENCHMARK)
                .gte("date", str(nav_observations[0]["date"]))
                .lte("date", str(nav_observations[-1]["date"]))
                .order("date")
                .execute()
            )
            benchmark_closes = [
                _coerce_float(row.get("close"))
                for row in (getattr(benchmark_resp, "data", None) or [])
                if row.get("close") is not None
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "phase9d: benchmark return computation failed (%s); benchmark return will be NULL",
                exc,
            )
    performance_returns = calculate_performance_returns(
        nav_values=navs,
        benchmark_closes=benchmark_closes,
        benchmark_ticker=_ALPHA_BENCHMARK,
    )

    # pnl_pct: day-over-day return from the two most recent NAV points.
    pnl_pct: float | None = None
    if len(navs) >= 2 and navs[-2] > 0:
        pnl_pct = round((navs[-1] - navs[-2]) / navs[-2] * 100.0, 4)
    elif len(navs) == 1:
        # First day — return vs seed (100).
        pnl_pct = round((navs[0] - _SEED_NAV) / _SEED_NAV * 100.0, 4)

    sharpe: float | None = None
    volatility: float | None = None
    max_drawdown: float | None = None
    alpha: float | None = None

    if len(navs) >= _MIN_NAV_HISTORY_ROWS:
        # Daily simple returns.
        returns = [
            (navs[i] - navs[i - 1]) / navs[i - 1] for i in range(1, len(navs)) if navs[i - 1] > 0
        ]
        if len(returns) >= 2:
            mean_r = sum(returns) / len(returns)
            var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
            std_r = math.sqrt(var_r)
            sharpe = round((mean_r / std_r) * math.sqrt(252), 6) if std_r > 0 else 0.0
            volatility = round(std_r * math.sqrt(252) * 100.0, 6)

            # Max drawdown from the equity curve.
            peak = navs[0]
            worst_dd = 0.0
            for n in navs:
                if n > peak:
                    peak = n
                if peak > 0:
                    dd = (n - peak) / peak
                    if dd < worst_dd:
                        worst_dd = dd
            max_drawdown = round(worst_dd * 100.0, 6)

        alpha = performance_returns.relative_return_pct

    row: dict[str, Any] = {
        "date": date_str,
        "pnl_pct": pnl_pct,
        "sharpe": sharpe,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "alpha": alpha,
        "net_return_pct": performance_returns.net_return_pct,
        "benchmark_return_pct": performance_returns.benchmark_return_pct,
        "relative_return_pct": performance_returns.relative_return_pct,
        "benchmark_ticker": performance_returns.benchmark_ticker,
    }
    client.table("portfolio_metrics").upsert(row, on_conflict="date").execute()
    logger.debug(
        "phase9d: portfolio_metrics upserted for %s (sharpe=%s, vol=%s, dd=%s, alpha=%s)",
        date_str,
        sharpe,
        volatility,
        max_drawdown,
        alpha,
    )


def _opt_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clamp_conviction(value: float) -> float:
    return max(_CONVICTION_FLOOR, min(_CONVICTION_CAP, value))


def _effective_conviction(analyst: Any, debate: Any) -> float | None:
    """Analyst conviction_score + debate conviction_delta, clamped −5..+5; None when the
    ticker has no fresh analyst payload (don't fabricate a grade for a carried holding)."""
    base = _opt_float((analyst or {}).get("conviction_score"))
    if base is None:
        return None
    delta = _opt_float((debate or {}).get("conviction_delta")) or 0.0
    return round(_clamp_conviction(base + delta), 2)


def _latest_values(
    client: SupabaseClient,
    table: str,
    value_col: str,
    tickers: list[str],
    run_date: date,
    *,
    lookback_days: int = 14,
) -> dict[str, float]:
    """``{ticker: value_col}`` from the latest row ≤ run_date per ticker (look-ahead-guarded).

    We only need each ticker's *most recent* value, so the query is bounded to a short
    ``lookback_days`` window — enough to clear weekends/holidays and find the latest daily
    row (``price_history`` / ``price_technicals`` are daily: ≤1 row/ticker/day). The page
    limit is tied to that window (``N × (lookback_days + 1)``) so it can never truncate a
    ticker still inside the window — the "crowding" failure mode this guards against. Fail-
    soft: a read error or missing value yields no entry for that ticker (the caller leaves
    the field unset rather than crashing the book); a partial resolve is logged.
    """
    if not tickers:
        return {}
    since = (run_date - timedelta(days=lookback_days)).isoformat()
    try:
        resp = (
            client.table(table)
            .select(f"ticker,date,{value_col}")
            .in_("ticker", list(tickers))
            .lte("date", run_date.isoformat())
            .gte("date", since)
            .order("date", desc=True)
            .limit(len(tickers) * (lookback_days + 1))
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 — risk fields are advisory; never block the book
        logger.warning(
            "phase9d: %s.%s read failed (%s); risk fields degrade", table, value_col, exc
        )
        return {}
    out: dict[str, float] = {}
    for row in getattr(resp, "data", None) or []:
        ticker = row.get("ticker")
        if isinstance(ticker, str) and ticker not in out:
            value = _opt_float(row.get(value_col))
            if value is not None:
                out[ticker] = value
    if len(out) < len(tickers):
        logger.debug(
            "phase9d: %s.%s resolved %d/%d tickers (rest left unset)",
            table,
            value_col,
            len(out),
            len(tickers),
        )
    return out


def _enrich_positions(
    *,
    client: SupabaseClient,
    run_date: date,
    date_str: str,
    pos_rows: list[dict[str, Any]],
    prior_book: list[dict[str, Any]],
    analysts: dict[str, Any],
    debates: dict[str, Any],
    preferences: dict[str, Any],
) -> None:
    """Add advisory per-position risk fields to the non-CASH ``pos_rows`` IN PLACE (Pillar 2E).

    entry_price/entry_date carry forward from the prior book (or seed at today's close + date
    on a first open); conviction = analyst + debate delta; sector_bucket from sector_map;
    stop_loss_pct / target_pct_gain are ATR-derived (advisory, NOT orders); horizon_days uses
    the dedicated risk preference. All best-effort — a missing input just leaves that field unset.
    """
    tickers = [str(r["ticker"]) for r in pos_rows if not _is_cash(r.get("ticker"))]
    if not tickers:
        return
    prior = {str(r.get("ticker")): r for r in prior_book if r.get("ticker")}
    closes = _latest_values(client, "price_history", "close", tickers, run_date)
    atr_pct = _latest_values(client, "price_technicals", "atr_pct", tickers, run_date)
    horizon_days = risk_horizon_days(preferences)

    for row in pos_rows:
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or _is_cash(ticker):
            continue
        prev = prior.get(ticker) or {}
        prev_entry = _opt_float(prev.get("entry_price"))
        if prev_entry is not None and prev_entry > 0:  # held → carry the original entry
            row["entry_price"] = round(prev_entry, 6)
            row["entry_date"] = prev.get("entry_date") or date_str
        else:  # first open → seed at today's close
            close = closes.get(ticker)
            if close is not None and close > 0:
                row["entry_price"] = round(close, 6)
            row["entry_date"] = date_str

        conviction = _effective_conviction(analysts.get(ticker), debates.get(ticker))
        if conviction is not None:
            row["conviction"] = conviction
        row["sector_bucket"] = sector_bucket(ticker)
        row["horizon_days"] = horizon_days

        atr = atr_pct.get(ticker)
        if atr is not None and atr > 0:  # ATR% is daily; advisory stop/target as ATR multiples
            row["stop_loss_pct"] = round(-_ATR_STOP_MULT * atr, 4)
            row["target_pct_gain"] = round(_ATR_TARGET_MULT * atr, 4)


def build_materialize_node(deps: MaterializeDeps):
    """Return the Phase 9D node bound to ``deps``."""

    def materialize(state: AtlasResearchState) -> dict[str, Any]:
        # The PM never ran (partial graph / legacy / dry-run) → don't fabricate a
        # book. This is distinct from the PM running and choosing to hold cash.
        book = sized_book(state)
        if book is None:
            return {}
        recommended = book.get("recommended_portfolio") or []

        run_date = state.run_date
        date_str = run_date.isoformat()
        client = deps.client

        # Target book from the PM's recommended weights. Coalesce duplicate
        # tickers (sum their weights — never double-count or upsert the same
        # (date,ticker) twice) and drop non-positive / CASH lines (CASH is the
        # residual, not a recommended holding).
        #
        # An EMPTY result is the PM's deliberate **100% CASH** stance (no
        # conviction this run) — a first-class position, booked as a CASH row
        # below. We do NOT pad the book with a cash-proxy ETF (BIL/SHY): those
        # are real holdings the PM picks on conviction, not a substitute for cash.
        weights: dict[str, float] = {}
        for row in recommended:
            if not isinstance(row, dict):
                continue
            ticker = row.get("ticker")
            if not isinstance(ticker, str) or not ticker or _is_cash(ticker):
                continue
            weight = _coerce_float(row.get("target_pct"))
            if weight <= 0:
                continue
            weights[ticker] = weights.get(ticker, 0.0) + weight

        # A malformed book summing > 100% is scaled proportionally to fully
        # invested (cash 0) rather than silently clamping the residual to an
        # inconsistent state.
        gross = sum(weights.values())
        if gross > 100.0:
            scale = 100.0 / gross
            weights = {t: w * scale for t, w in weights.items()}
            gross = 100.0
        invested = round(gross, 4)
        cash_pct = max(0.0, round(100.0 - invested, 4))
        # thesis_id links each non-CASH position to its thesis row (#814).
        # The thesis_id is always ticker.lower() (matches _upsert_theses keying).
        pos_rows: list[dict[str, Any]] = [
            {"date": date_str, "ticker": t, "weight_pct": round(w, 4), "thesis_id": t.lower()}
            for t, w in weights.items()
        ]

        # NAV index: mark the prior book BEFORE overwriting with today's, then
        # record this run's NAV point and book. Reads come from prior dates, so
        # ordering between the nav and positions writes is immaterial.
        prior_book = load_prior_book(
            client, run_date, include_risk_fields=_position_risk_fields_enabled()
        )
        nav = _compute_nav(client, run_date, prior_book)

        # Advisory per-position risk fields (Pillar 2E) — flag-gated so the migration-039
        # columns are only written once applied to prod; off → exact prior book shape.
        # Fail-soft: enrichment is advisory, so a config/read error here must never block the
        # book — log and book the plain weights.
        if _position_risk_fields_enabled():
            try:
                _enrich_positions(
                    client=client,
                    run_date=run_date,
                    date_str=date_str,
                    pos_rows=pos_rows,
                    prior_book=prior_book,
                    analysts=analyst_payloads(state),
                    debates=deliberation_summaries(state),
                    preferences=dict(state.config.preferences),
                )
            except Exception as exc:  # noqa: BLE001 — advisory fields must never block the book
                logger.warning(
                    "phase9d: position risk-field enrichment failed (%s); booking plain weights",
                    exc,
                    exc_info=True,
                )
                # Strip any partial enrichment so the upsert stays schema-safe.
                # Preserve thesis_id — it is set before enrichment and must survive a failure (#814).
                pos_rows = [
                    {
                        "date": date_str,
                        "ticker": r["ticker"],
                        "weight_pct": r["weight_pct"],
                        **({"thesis_id": r["thesis_id"]} if r.get("thesis_id") else {}),
                    }
                    for r in pos_rows
                ]

        client.table("nav_history").upsert(
            {
                "date": date_str,
                "nav": nav,
                "cash_pct": cash_pct,
                "invested_pct": round(invested, 4),
            },
            on_conflict="date",
        ).execute()

        # Portfolio-level risk metrics (#953): compute sharpe/vol/drawdown/alpha
        # from the nav_history series and upsert into portfolio_metrics. Advisory —
        # a failure here must never block the book.
        try:
            _upsert_portfolio_metrics(client=client, run_date=run_date)
        except Exception as exc:  # noqa: BLE001 — metrics are advisory
            logger.warning(
                "phase9d: portfolio_metrics write failed (%s); continuing",
                exc,
            )

        if cash_pct > 0.01:
            # The cash sleeve's category must satisfy chk_positions_category (migration 002),
            # whose vocabulary has no bare "cash" — "fixed_income_cash" is the cash bucket. A
            # literal "cash" raises 23514 and (for an all-cash book) blocks the whole positions
            # write. Cash is otherwise identified by ticker == "CASH". CASH has no thesis_id.
            pos_rows.append(
                {
                    "date": date_str,
                    "ticker": "CASH",
                    "weight_pct": cash_pct,
                    "category": "fixed_income_cash",
                }
            )
        # Assertion (#814): every non-CASH row must carry a thesis_id before the upsert.
        # This guards against a partial-enrichment regression silently nulling the FK.
        _non_cash_missing_thesis = [
            r["ticker"]
            for r in pos_rows
            if not _is_cash(r.get("ticker")) and not r.get("thesis_id")
        ]
        if _non_cash_missing_thesis:
            # Log as error but do not crash the book — a missing thesis_id is a data-quality
            # issue, not a correctness blocker for the positions write itself.
            logger.error(
                "phase9d: non-CASH positions missing thesis_id (will write NULL): %s",
                _non_cash_missing_thesis,
            )
        for row in pos_rows:
            client.table("positions").upsert(row, on_conflict="date,ticker").execute()

        # Theses surface (#713): one thesis per held ticker, from the analyst
        # payloads + debate summaries already in state. Skips the CASH ledger row
        # (not in ``weights``); a held ticker with no analyst payload still gets a
        # thesis (status defaults to ACTIVE). Writes nothing for a pure-cash book.
        # Invariant: _upsert_theses fills blank invalidation with a rule-based default
        # before writing, so ACTIVE theses always have a non-empty invalidation (#814).
        n_theses = _upsert_theses(
            client=client,
            date_str=date_str,
            weights=weights,
            analysts=analyst_payloads(state),
            debates=deliberation_summaries(state),
        )

        logger.info(
            "phase9d: booked %d positions (cash %.2f%%), nav=%.4f, %d theses for %s",
            len(pos_rows),
            cash_pct,
            nav,
            n_theses,
            date_str,
        )
        return {}

    return materialize


def build_materialize_phase(deps: MaterializeDeps) -> PipelinePhase:
    """Wrap the materialization node into a single-node ``PipelinePhase``."""
    return PipelinePhase(
        name="materialize",
        nodes=[NodeSpec(name="materialize-portfolio", run=build_materialize_node(deps))],
    )


__all__ = [
    "MaterializeDeps",
    "build_materialize_node",
    "build_materialize_phase",
]
