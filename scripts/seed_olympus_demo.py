#!/usr/bin/env python3
"""Seed Olympus with demo nav_history (>=2 pts) + a resolved decision_log batch.

Development / demo utility.  Does NOT run in CI or production.  Designed for
fresh installs that have run no Hermes cycles so the Performance tear sheet
renders an equity curve + decision track-record instead of empty-state.

Fixes #1045

Usage::

    SUPABASE_URL=https://...  SUPABASE_SERVICE_ROLE_KEY=service_...  \\
        python scripts/seed_olympus_demo.py

    # Preview without writing:
    python scripts/seed_olympus_demo.py --dry-run

    # Wipe all seeded rows first (uses the demo marker):
    python scripts/seed_olympus_demo.py --clear

Idempotency
-----------
- nav_history upserts on PK (date).
- decision_log upserts on UNIQUE (run_id, ticker); run_ids are derived from
  a fixed seed so re-running is a no-op.
- portfolio_metrics upserts on UNIQUE (date).
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import uuid
from datetime import date, timedelta
from typing import Any

# ── constants ────────────────────────────────────────────────────────────────

_SEED = 42
_NAV_BASE = 100.0
_NAV_START = date(2025, 1, 6)  # first Monday of January 2025
_NAV_WEEKS = 72  # ~17 months of weekly data

# Deterministic namespace so demo run_ids are stable across invocations.
_UUID_NS = uuid.UUID("d1671045-0000-0000-0000-000000000000")

# Resolved decisions: (run_date, ticker, stance, conviction, holding_days,
#                       actual_return_pct, alpha_pct, reflection_snippet)
# fmt: off
_DECISIONS: list[tuple[str, str, str, int, int, float, float, str]] = [
    ("2025-01-13", "SPY",  "long",  8, 5,  2.1,  0.0,  "Broad-market momentum held; entry timing was accurate. No adjustments needed."),
    ("2025-01-27", "NVDA", "long",  9, 5, 11.4,  9.3,  "Earnings beat catalysed the move. High-conviction thesis played out cleanly."),
    ("2025-02-10", "TLT",  "long",  6, 5, -3.8, -5.9,  "Rate cut thesis was premature; macro regime shifted. Weight smaller next time."),
    ("2025-02-24", "AAPL", "long",  7, 5,  4.2,  2.1,  "iPhone cycle tailwind held longer than expected. Conviction score undersized."),
    ("2025-03-10", "GLD",  "long",  7, 5,  5.7,  3.6,  "Safe-haven bid on geopolitical risk. Gold held through equity volatility."),
    ("2025-03-24", "MSFT", "long",  8, 5,  6.9,  4.8,  "Azure revenue print beat; cloud segment re-rated. Thesis confirmed."),
    ("2025-04-07", "META", "long",  9, 5,  9.3,  7.2,  "Ad-revenue recovery stronger than modelled. Early long was well-timed."),
    ("2025-04-21", "BITO", "long",  6, 5, 18.2, 16.1,  "BTC halving cycle demand absorbed faster than consensus. Overcrowded but profitable."),
    ("2025-05-05", "AMZN", "long",  7, 5,  3.5,  1.4,  "AWS re-acceleration in line with thesis. No surprise; steady conviction paid off."),
    ("2025-05-19", "TSM",  "long",  8, 5, -1.9, -4.0,  "Geopolitical premium spiked; correct thesis, wrong timing. Tighten entry triggers."),
    ("2025-06-02", "SPY",  "flat",  3, 5,  1.8,  0.0,  "Defensive posture during late-cycle uncertainty cost performance. Re-examine flat threshold."),
    ("2025-06-16", "NVDA", "long",  9, 5, 14.7, 12.6,  "AI capex upcycle confirmed again. Strong alpha; maintain conviction signal weighting."),
    ("2025-07-07", "TLT",  "flat",  5, 5, -2.3,  0.0,  "Flattened correctly ahead of hot CPI print. Saved drawdown vs prior long."),
    ("2025-07-21", "GLD",  "long",  7, 5,  3.1,  1.0,  "Dollar weakness supported gold. Thesis in-line; modest but consistent alpha."),
    ("2025-08-04", "AAPL", "long",  6, 5, -2.8, -4.9,  "Guidance miss post-earnings. Conviction was too high relative to event risk."),
    ("2025-08-18", "MSFT", "long",  8, 5,  8.4,  6.3,  "AI integration wins on enterprise side. Outperformed broad market cleanly."),
    ("2025-09-08", "META", "long",  9, 5,  7.6,  5.5,  "Reels monetisation ahead of plan. Social-ad thesis intact; strong alpha."),
    ("2025-09-22", "BITO", "flat",  4, 5, 22.4,  0.0,  "Missed large BTC move by going flat. Risk-off bias cost 22 pts of alpha."),
    ("2025-10-06", "AMZN", "long",  7, 5,  5.9,  3.8,  "Retail + AWS combined beat. Well-constructed thesis; execution in-line."),
    ("2025-11-03", "TSM",  "long",  8, 5,  9.2,  7.1,  "Geopolitical premium faded; semiconductor upcycle re-priced. Patience rewarded."),
]
# fmt: on


# ── nav generation ────────────────────────────────────────────────────────────


def generate_nav_rows() -> list[dict[str, Any]]:
    """Return deterministic weekly nav_history rows (base 100, GBM-like path)."""
    rng = random.Random(_SEED)
    rows: list[dict[str, Any]] = []
    nav = _NAV_BASE
    for week in range(_NAV_WEEKS):
        d = _NAV_START + timedelta(weeks=week)
        # Weekly GBM: ~13% annual drift, ~11% annual vol
        drift = 0.0025
        shock = rng.gauss(0, 0.015)
        nav = round(nav * math.exp(drift + shock), 6)
        invested = round(rng.uniform(0.70, 0.95), 4)
        rows.append(
            {
                "date": d.isoformat(),
                "nav": nav,
                "invested_pct": invested,
                "cash_pct": round(1.0 - invested, 4),
            }
        )
    return rows


# ── portfolio_metrics ─────────────────────────────────────────────────────────


def generate_metrics_row(nav_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary metrics from the generated NAV series."""
    navs = [r["nav"] for r in nav_rows]
    weekly_returns = [(navs[i] - navs[i - 1]) / navs[i - 1] for i in range(1, len(navs))]
    mean_r = sum(weekly_returns) / len(weekly_returns)
    variance = sum((r - mean_r) ** 2 for r in weekly_returns) / len(weekly_returns)
    weekly_vol = math.sqrt(variance)
    annual_vol = round(weekly_vol * math.sqrt(52) * 100, 2)
    annual_sharpe = round((mean_r * 52) / (weekly_vol * math.sqrt(52) + 1e-9), 3)

    # Max drawdown
    peak = navs[0]
    max_dd = 0.0
    for n in navs:
        peak = max(peak, n)
        dd = (n - peak) / peak
        if dd < max_dd:
            max_dd = dd
    max_dd_pct = round(max_dd * 100, 2)

    total_return = round((navs[-1] - navs[0]) / navs[0] * 100, 2)
    last_date = nav_rows[-1]["date"]
    return {
        "date": last_date,
        "pnl_pct": total_return,
        "sharpe": annual_sharpe,
        "volatility": annual_vol,
        "max_drawdown": max_dd_pct,
        "alpha": round(total_return - 14.2, 2),  # vs approximate SPY baseline
        "cash_pct": nav_rows[-1]["cash_pct"],
        "total_invested": nav_rows[-1]["invested_pct"],
        "computed_from": "demo-seed",
    }


# ── decision log ─────────────────────────────────────────────────────────────


def generate_decision_rows() -> list[dict[str, Any]]:
    """Return resolved decision_log rows from the hardcoded _DECISIONS table."""
    rows: list[dict[str, Any]] = []
    for spec in _DECISIONS:
        run_date, ticker, stance, conviction, holding_days, actual_return, alpha, snippet = spec
        run_id = str(uuid.uuid5(_UUID_NS, f"{run_date}:{ticker}"))
        resolved_date = (
            date.fromisoformat(run_date) + timedelta(days=holding_days + 1)
        ).isoformat()
        reflection = (
            f"{snippet} "
            f"Actual return: {actual_return:+.1f}% over {holding_days}d. "
            f"Alpha vs SPY: {alpha:+.1f}%."
        )
        rows.append(
            {
                "run_id": run_id,
                "run_date": run_date,
                "ticker": ticker,
                "stance": stance,
                "conviction": conviction,
                "thesis": f"Demo thesis for {ticker} on {run_date}. {snippet[:80]}",
                "benchmark": "SPY",
                "holding_days": holding_days,
                "status": "resolved",
                "actual_return": actual_return,
                "alpha": alpha,
                "reflection": reflection,
                "resolved_at": f"{resolved_date}T16:00:00+00:00",
            }
        )
    return rows


# ── supabase helpers ──────────────────────────────────────────────────────────


def _build_client() -> Any:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    missing = [v for v, k in [("SUPABASE_URL", url), ("SUPABASE_SERVICE_ROLE_KEY", key)] if not k]
    if missing:
        sys.exit(f"ERROR: missing env var(s): {', '.join(missing)}")
    from supabase import create_client  # deferred optional dep

    return create_client(url, key)


def _upsert(client: Any, table: str, rows: list[dict[str, Any]], conflict: str) -> int:
    for row in rows:
        client.table(table).upsert(row, on_conflict=conflict).execute()
    return len(rows)


def _clear(client: Any) -> None:
    print("Clearing seeded rows…")
    client.table("nav_history").delete().gte("date", _NAV_START.isoformat()).execute()
    run_ids = [str(uuid.uuid5(_UUID_NS, f"{d}:{t}")) for d, t, *_ in _DECISIONS]
    for rid in run_ids:
        client.table("decision_log").delete().eq("run_id", rid).execute()
    nav_rows = generate_nav_rows()
    client.table("portfolio_metrics").delete().eq("date", nav_rows[-1]["date"]).execute()
    print("Done.")


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print rows without writing to Supabase."
    )
    parser.add_argument(
        "--clear", action="store_true", help="Delete previously seeded rows, then exit."
    )
    args = parser.parse_args()

    nav_rows = generate_nav_rows()
    decision_rows = generate_decision_rows()
    metrics_row = generate_metrics_row(nav_rows)

    if args.dry_run:
        print(f"[dry-run] nav_history rows:    {len(nav_rows)}")
        print(f"[dry-run] decision_log rows:   {len(decision_rows)}")
        print(f"[dry-run] portfolio_metrics:   1 row  (date={metrics_row['date']})")
        print(
            f"[dry-run] NAV range:           {nav_rows[0]['nav']:.2f} → {nav_rows[-1]['nav']:.2f}"
        )
        print(f"[dry-run] Total return:        {metrics_row['pnl_pct']:+.2f}%")
        print(f"[dry-run] Sharpe:              {metrics_row['sharpe']:.3f}")
        print(f"[dry-run] Max drawdown:        {metrics_row['max_drawdown']:.2f}%")
        return

    client = _build_client()

    if args.clear:
        _clear(client)
        return

    n = _upsert(client, "nav_history", nav_rows, "date")
    print(f"nav_history:       {n} rows upserted")

    d = _upsert(client, "decision_log", decision_rows, "run_id,ticker")
    print(f"decision_log:      {d} rows upserted")

    m = _upsert(client, "portfolio_metrics", [metrics_row], "date")
    print(f"portfolio_metrics: {m} row upserted")

    print(
        f"\nDone. Performance tear sheet should now render from "
        f"{nav_rows[0]['date']} to {nav_rows[-1]['date']}."
    )


if __name__ == "__main__":
    main()
