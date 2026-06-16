#!/usr/bin/env python3
"""Backtest the agent's recorded decisions (Pillar 3C, #726).

Zero LLM cost. Reads ``decision_log`` (the agent's calls), computes each long-side
decision's realized return over its holding window + the benchmark's return over the same
window from ``price_history`` (look-ahead-safe via ``query_returns_window`` — only prices
inside the window are used), and runs the pure
:func:`digiquant.olympus.atlas.backtest.backtest_decisions` to print a decision-level tear
sheet: hit-rate, mean/median alpha, compounded return vs benchmark, max drawdown,
information / Sortino ratios, and **conviction-bucket calibration** (do higher-conviction
calls earn higher alpha?).

Read-only — no writes, no LLM, no schema change. Run weekly / on demand.

Usage::

    python digiquant/scripts/atlas/backtest_decisions.py [--start YYYY-MM-DD] [--benchmark SPY]

Env: ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``. Exit 0 = clean; 1 = hard failure;
2 = bad ``--start``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any  # noqa  # scored-lint: duck-typed Supabase client + rows

# repo root: .../digiquant/scripts/atlas/backtest_decisions.py → up 4 (atlas → scripts →
# digiquant → repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_DEFAULT_LOOKBACK_DAYS = 365
_LONG_STANCES = ("buy", "hold")


def _ensure_importable() -> None:
    for rel in ("digiquant/src", "digigraph/src", "digibase/src", "digismith/src"):
        path = str(_REPO_ROOT / rel)
        if path not in sys.path:
            sys.path.insert(0, path)


def _parse_date(value: str) -> date:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _opt_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _read_decisions(client: Any, since_iso: str) -> list[dict]:
    resp = (
        client.table("decision_log")
        .select("run_date,ticker,stance,conviction,holding_days,benchmark")
        .gte("run_date", since_iso)
        .order("run_date", desc=False)
        .execute()
    )
    return list(getattr(resp, "data", None) or [])


def build_trades(*, client: Any, decisions: list[dict], default_benchmark: str = "SPY") -> list:
    """Turn decision_log rows into realized :class:`Trade`s, skipping non-long stances and
    decisions whose price window isn't available yet (look-ahead-safe)."""
    from digiquant.olympus.atlas.backtest import Trade
    from digiquant.olympus.atlas.supabase_io import query_returns_window

    trades = []
    for row in decisions:
        stance = str(row.get("stance") or "").strip().lower()
        ticker = row.get("ticker")
        if stance not in _LONG_STANCES or not isinstance(ticker, str) or not ticker:
            continue
        try:
            decision_date = _parse_date(row["run_date"])
        except (KeyError, ValueError, TypeError):
            continue
        holding_days = int(row.get("holding_days") or 5)
        benchmark = row.get("benchmark") or default_benchmark
        ticker_win = query_returns_window(
            client=client, ticker=ticker, start_date=decision_date, holding_days=holding_days
        )
        bench_win = query_returns_window(
            client=client, ticker=benchmark, start_date=decision_date, holding_days=holding_days
        )
        if ticker_win is None or bench_win is None:
            continue  # insufficient price data → skip (the window hasn't fully landed)
        trades.append(
            Trade(
                date=decision_date,
                ticker=ticker,
                return_frac=ticker_win[0],
                benchmark_frac=bench_win[0],
                conviction=_opt_float(row.get("conviction")),
                stance=stance,
            )
        )
    return trades


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest recorded Atlas decisions (zero LLM).")
    parser.add_argument("--start", default=None, help="Earliest decision run_date YYYY-MM-DD.")
    parser.add_argument("--benchmark", default="SPY", help="Default benchmark ticker.")
    args = parser.parse_args(argv)

    since = (
        args.start
        or (datetime.now(timezone.utc).date() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)).isoformat()
    )
    try:
        _parse_date(since)
    except ValueError:
        print(f"error: bad --start {args.start!r} (expected YYYY-MM-DD)", file=sys.stderr)
        return 2

    _ensure_importable()
    from digiquant.olympus.atlas.backtest import backtest_decisions
    from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client

    try:
        client = build_client(SupabaseConfig.from_env())
    except Exception as exc:  # noqa: BLE001 — config/connectivity failure is a hard error
        print(f"error: Supabase client unavailable: {exc}", file=sys.stderr)
        return 1

    try:
        decisions = _read_decisions(client, since)
        trades = build_trades(client=client, decisions=decisions, default_benchmark=args.benchmark)
        result = backtest_decisions(trades)
    except Exception as exc:  # noqa: BLE001 — surface a hard failure as a non-zero exit
        print(f"error: backtest failed: {exc}", file=sys.stderr)
        return 1

    payload = asdict(result)
    payload["since"] = since
    payload["decisions_scanned"] = len(decisions)
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
