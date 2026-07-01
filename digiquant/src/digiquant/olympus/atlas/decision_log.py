"""Atlas Phase 9 closed-loop reflection — write/resolve helpers (#432).

Splits the two-phase reflection mechanic into testable units:

- :func:`persist_pending` — Phase A. End of every run. Writes one
  ``decision_log`` row per per-ticker analyst output that Phase 7C produced.
  Status starts as ``'pending'``.

- :func:`resolve_pending` — Phase B (run via :mod:`phases.preflight_reflect`).
  Start of every run. For every pending row whose holding window has elapsed,
  computes alpha vs. SPY from ``price_history``, calls the
  ``decision-reflector`` skill, and updates the row to ``status='resolved'``.

- :func:`fetch_recent_lessons` — preflight context loader. Returns the
  recent resolved rows the PM should see in PriorContext.

The Supabase wire calls live in :mod:`digiquant.olympus.atlas.supabase_io` so the LLM
and DB seams are independently testable.
"""

from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.hermes.payloads import analyst_payloads
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    query_pending_decisions,
    query_recent_lessons,
    query_returns_window,
    update_decision_resolution,
)

logger = logging.getLogger(__name__)

# Upper bound on the ``thesis`` column written to ``decision_log`` — Pydantic
# ``AnalystPayload.thesis`` allows up to 1200, so truncate explicitly rather
# than letting Postgres ``text`` store a longer value.
THESIS_MAX_CHARS = 800

# Trading-day window over which alpha is computed. Override per run via
# ``state.config.preferences['holding_days']``.
DEFAULT_HOLDING_DAYS = 5

# Benchmark ticker for alpha computation. Stored per-row already (migration
# 026), so multi-benchmark support is a future column-driven change.
DEFAULT_BENCHMARK = "SPY"


class ReflectorOutput(BaseModel):
    """LLM structured output for the ``decision-reflector`` skill."""

    reflection: str = Field(min_length=1)


def _truncate_thesis(thesis: str | None) -> str:
    """Trim ``thesis`` to ``THESIS_MAX_CHARS``; ``None`` becomes ``""`` so
    the DB write never stores ``NULL`` for missing analyst output."""
    if not thesis:
        return ""
    return thesis[:THESIS_MAX_CHARS]


def persist_pending(
    *,
    client: SupabaseClient,
    state: AtlasResearchState,
) -> int:
    """Phase A — write one ``pending`` row per ticker that Phase 7C produced.

    Returns the count of rows written. Skips silently when:
    - ``state.phase7c_analysts`` is empty (degenerate watchlist case).
    - The analyst payload is missing the required keys (defensive — phase 7C
      validates via Pydantic, but downstream replays might hand us partial
      data).

    Idempotency: relies on ``decision_log_rundate_ticker_unique`` (migration 044,
    re-keyed from the original ``(run_id, ticker)`` of migration 026). The grain
    is one decision per logical run DATE per ticker, so a same-day re-run — a CI
    outer-retry fires a fresh ``run_id`` each attempt — upserts the same row
    instead of duplicating it (the Jun-19 prod run double-wrote 20 rows for 10
    tickers under two run_ids; #947). The resolver's ``status='pending'`` guard
    still prevents overwriting an already-resolved reflection on replay.
    """
    analysts = analyst_payloads(state)
    if not analysts:
        return 0

    holding_days = _holding_days(state)

    rows_written = 0
    for ticker, payload in analysts.items():
        if not isinstance(payload, dict):
            continue
        stance = payload.get("stance")
        if not stance:
            # Phase 7C's Pydantic schema requires stance; missing here means
            # the payload was forged in a test or got corrupted upstream.
            # Skipping is conservative — never persist a half-decision.
            continue
        row = {
            "run_id": str(state.run_id),
            "run_date": state.run_date.isoformat(),
            "ticker": ticker,
            "stance": stance,
            "conviction": _coerce_int(payload.get("conviction_score")),
            "thesis": _truncate_thesis(payload.get("thesis")),
            "benchmark": DEFAULT_BENCHMARK,
            "holding_days": holding_days,
            "status": "pending",
        }
        client.table("decision_log").upsert(row, on_conflict="run_date,ticker").execute()
        rows_written += 1

    if rows_written:
        logger.info(
            "decision_log Phase A wrote %d pending rows (run_id=%s, run_date=%s)",
            rows_written,
            state.run_id,
            state.run_date.isoformat(),
        )
    return rows_written


def resolve_pending(
    *,
    client: SupabaseClient,
    run_date: date,
    reflector: Callable[[dict[str, Any]], ReflectorOutput] | None = None,
) -> int:
    """Phase B — resolve every pending row whose holding window has elapsed.

    Steps per due row:

    1. Fetch ticker returns over ``holding_days`` trading days.
    2. Fetch SPY returns over the same window.
    3. Compute ``alpha = ticker_return - benchmark_return``.
    4. Call the reflector skill (LLM) → 2-4 sentence lesson.
    5. Update the row to ``status='resolved'`` with alpha/lesson fields.

    Missing price data on either side → skip the row (it stays pending; the
    next run will retry once data arrives). AC #7 requires graceful handling.

    ``reflector`` is dependency-injected so tests can substitute a stub. The
    default implementation calls ``run_research_agent`` against the
    ``decision-reflector`` skill.

    Returns the number of rows actually resolved.
    """
    pending = query_pending_decisions(client=client, run_date=run_date)
    if not pending:
        return 0

    reflector_fn = reflector or _default_reflector

    resolved_count = 0
    skipped_no_data = 0
    for row in pending:
        try:
            decision_run_date = _parse_iso_date(row.get("run_date"))
        except ValueError:
            logger.warning("decision_log row has unparseable run_date: %s", row.get("run_date"))
            continue

        holding_days = _coerce_int(row.get("holding_days")) or DEFAULT_HOLDING_DAYS
        ticker = row.get("ticker") or ""
        benchmark = row.get("benchmark") or DEFAULT_BENCHMARK

        ticker_window = query_returns_window(
            client=client,
            ticker=ticker,
            start_date=decision_run_date,
            holding_days=holding_days,
        )
        bench_window = query_returns_window(
            client=client,
            ticker=benchmark,
            start_date=decision_run_date,
            holding_days=holding_days,
        )
        if ticker_window is None or bench_window is None:
            # Gracefully skip — row stays pending and the next due-window
            # check will retry once price_history catches up. AC #7.
            skipped_no_data += 1
            continue

        ticker_return, _t_start, _t_end = ticker_window
        bench_return, _b_start, _b_end = bench_window
        alpha = ticker_return - bench_return

        try:
            reflection = reflector_fn(
                {
                    "ticker": ticker,
                    "stance": row.get("stance"),
                    "conviction": row.get("conviction"),
                    "thesis": row.get("thesis") or "",
                    "run_date": row.get("run_date"),
                    "holding_days": holding_days,
                    "actual_return": ticker_return,
                    "benchmark": benchmark,
                    "benchmark_return": bench_return,
                    "alpha": alpha,
                }
            )
        except Exception as exc:  # noqa: BLE001 — reflector failure must not block sibling rows
            logger.warning(
                "decision_log reflector failed for %s (run_id=%s): %s",
                ticker,
                row.get("run_id"),
                exc,
            )
            continue

        update_decision_resolution(
            client=client,
            row_id=str(row.get("id") or ""),
            actual_return=ticker_return,
            alpha=alpha,
            reflection=reflection.reflection,
            resolved_at=_now_iso(),
        )
        resolved_count += 1

    if resolved_count or skipped_no_data:
        logger.info(
            "decision_log Phase B resolved=%d skipped_no_data=%d (run_date=%s)",
            resolved_count,
            skipped_no_data,
            run_date.isoformat(),
        )
    return resolved_count


def fetch_recent_lessons(
    *,
    client: SupabaseClient,
    run_date: date,
    watchlist: tuple[str, ...] = (),
    same_ticker_limit: int = 5,
    cross_ticker_limit: int = 3,
) -> list[dict[str, Any]]:
    """Convenience wrapper around :func:`supabase_io.query_recent_lessons`.

    Kept thin so the decision_log module is the single import surface for
    callers who want the full Phase 9 closed-loop API. Same arguments,
    same return shape.
    """
    return query_recent_lessons(
        client=client,
        run_date=run_date,
        tickers=watchlist,
        same_ticker_limit=same_ticker_limit,
        cross_ticker_limit=cross_ticker_limit,
    )


def _holding_days(state: AtlasResearchState) -> int:
    """Derive holding window from conviction or ``preferences['holding_days']``.

    If preferences['holding_days'] is set, honour the explicit override.
    Otherwise derive from the **median** conviction across the analyst
    payloads in this run: higher |conviction| → longer horizon (the agent
    should hold higher-conviction calls longer to realize their edge).

    Linear ramp ``days = round(3 + (median_conv - 1) * 2.75)`` (conviction 1 → 3
    days, conviction 5 → 14 days), so 1..5 → 3, 6, 8, 11, 14.

    Clamped to [3, 21] for safety.  Falls back to DEFAULT_HOLDING_DAYS (5)
    when no analyst payloads exist or the conviction data is missing.
    """
    # Explicit preference takes priority.
    raw = state.config.preferences.get("holding_days") if state.config.preferences else None
    if raw is not None:
        try:
            days = int(raw)
        except (TypeError, ValueError):
            pass
        else:
            if days >= 1:
                return days

    # Conviction-derived: collect all conviction scores from this run's analysts.
    analysts = analyst_payloads(state)
    convictions: list[float] = []
    for payload in (analysts or {}).values():
        if isinstance(payload, dict):
            raw_conv = payload.get("conviction_score")
            if raw_conv is not None:
                try:
                    convictions.append(float(raw_conv))
                except (TypeError, ValueError):
                    pass

    if not convictions:
        return DEFAULT_HOLDING_DAYS

    # Median conviction → holding days via the linear ramp documented above.
    days = int(round(3.0 + (statistics.median(convictions) - 1.0) * 2.75))
    return max(3, min(21, days))


def _coerce_int(val: Any) -> int | None:
    """Best-effort int coercion; ``None`` for missing or unparseable input."""
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _parse_iso_date(raw: Any) -> date:
    """Parse a date from str / date — used when reading rows back from Supabase."""
    if isinstance(raw, date):
        return raw
    if not raw:
        raise ValueError("missing date value")
    return date.fromisoformat(str(raw)[:10])


def _now_iso() -> str:
    """Current UTC timestamp as ISO 8601 — indirection for monkeypatching."""
    return datetime.now(timezone.utc).isoformat()


def _default_reflector(prompt_inputs: dict[str, Any]) -> ReflectorOutput:
    """Production reflector: invokes the ``decision-reflector`` skill via LiteLLM.

    Imports are lazy so unit tests that pass a stub ``reflector`` don't need
    ``digigraph`` / ``litellm`` installed.
    """
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.olympus.atlas.skills import load_skill

    skill_text = load_skill("decision-reflector")
    return run_research_agent(
        skill_text=skill_text,
        phase_inputs=prompt_inputs,
        shared_context={"phase": "decision-reflector"},
        output_model=ReflectorOutput,
        phase_slug="decision-reflector",
    )


__all__ = [
    "DEFAULT_BENCHMARK",
    "DEFAULT_HOLDING_DAYS",
    "ReflectorOutput",
    "THESIS_MAX_CHARS",
    "fetch_recent_lessons",
    "persist_pending",
    "resolve_pending",
]
