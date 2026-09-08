"""Verify recorded house NAV against an independent Nautilus schedule replay.

Rebuilds the house book from ``positions`` book weights + ``price_history``
OHLCV (real volumes), runs the hardened schedule replay
(``digiquant.dashboard.replay``, schema 2.0, causal-fill convention), and
compares the engine NAV path against recorded ``nav_history``.

Exit codes: 0 = within tolerance, 1 = usage/config error, 2 = NAV breach.

Requires ``nautilus_trader`` (``digiquant[nautilus]``) and Supabase env —
``CORE_SUPABASE_URL`` / ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``
(see ``digiquant/src/digiquant/research/config/supabase.env``).

Read-only: SELECTs Group A tables pinned to the house workspace. Never writes.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

FAIL_TOL_BP = 25.0  # breach: engine vs recorded daily return differs by >25bp
WARN_TOL_BP = 1.0  # warning band: integer-lot quantization noise lives here
SCALED_NOTIONAL_USD = 100_000_000.0  # scaled cash so integer lots ≈ arithmetic chain


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    for _ in range(6):
        here = here.parent
        candidate = (
            here / "digiquant" / "src" / "digiquant" / "research" / "config" / "supabase.env"
        )
        if candidate.exists():
            load_dotenv(candidate)
            return


def _get_client():
    try:
        from supabase import create_client
    except ImportError as exc:
        raise SystemExit(f"pip install supabase ({exc})")
    url = os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL", "")).strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise SystemExit("CORE_SUPABASE_URL/SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
    return create_client(url, key)


def _fetch_table(
    sb, table: str, house_id: str, cols: str, or_null_workspace: bool = False
) -> list[dict]:
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        query = sb.table(table).select(cols).order("date")
        if or_null_workspace:
            # Omitted workspace_id = house (HOUSE_BOOK_SCOPE.md): match both.
            query = query.or_(f"workspace_id.eq.{house_id},workspace_id.is.null")
        else:
            query = query.eq("workspace_id", house_id)
        page = query.range(offset, offset + page_size - 1).execute().data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def build_request(price_rows, position_rows, nav_rows):
    from digiquant.dashboard.replay.models import (
        InstrumentBarSeries,
        OhlcvBar,
        PortfolioReplayRequest,
        ScheduledTargetWeights,
        TargetWeight,
    )

    closes: dict[tuple[str, str], Decimal] = {}
    volumes: dict[tuple[str, str], Decimal] = {}
    per_ticker: dict[str, list[OhlcvBar]] = {}
    for r in price_rows:
        d = str(r["date"])
        closes[(d, r["ticker"])] = Decimal(str(r["close"]))
        volumes[(d, r["ticker"])] = Decimal(str(r.get("volume") or 0))
        per_ticker.setdefault(r["ticker"], []).append(
            OhlcvBar(
                ts=datetime.fromisoformat(d).replace(tzinfo=timezone.utc),
                open=Decimal(str(r["open"])),
                high=Decimal(str(r["high"])),
                low=Decimal(str(r["low"])),
                close=Decimal(str(r["close"])),
                volume=Decimal(str(r.get("volume") or 0)),
            )
        )
    series = tuple(
        InstrumentBarSeries(ticker=t, bars=tuple(per_ticker[t])) for t in sorted(per_ticker)
    )

    book_by_date: dict[str, dict[str, Decimal]] = {}
    for r in position_rows:
        d = str(r["date"])
        if r.get("ticker") == "CASH":
            continue
        book_by_date.setdefault(d, {})[r["ticker"]] = Decimal(str(r["weight_pct"])) / 100

    schedule: list[ScheduledTargetWeights] = []
    for d in sorted(book_by_date):
        weights = book_by_date[d]
        gross = sum(weights.values())
        if gross > 1:  # day-one style over-allocation: pro-rata normalize (locked decision)
            weights = {t: w / gross for t, w in weights.items()}
        schedule.append(
            ScheduledTargetWeights(
                effective_date=date.fromisoformat(d),
                weights=tuple(TargetWeight(ticker=t, weight=w) for t, w in sorted(weights.items())),
            )
        )

    return (
        PortfolioReplayRequest(
            schema_version="2.0",
            request_id="verify-nav-replay",
            series=series,
            target_weights=(),
            weight_schedule=tuple(schedule),
            starting_cash=Decimal(str(SCALED_NOTIONAL_USD)),
            execution={"next_bar_execution": False},
        ),
        closes,
        {str(r["date"]): Decimal(str(r["nav"])) for r in nav_rows},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fail-tol-bp", type=float, default=FAIL_TOL_BP)
    parser.add_argument("--warn-tol-bp", type=float, default=WARN_TOL_BP)
    args = parser.parse_args()

    try:
        from digiquant.dashboard.replay.models import PortfolioReplayStatus
        from digiquant.dashboard.replay.nautilus_portfolio import (
            run_shared_cash_portfolio_replay,
        )
        from digiquant.dashboard.tenancy import house_workspace_id
    except ImportError as exc:
        print(f"SKIP: replay modules not importable ({exc})")
        return 1
    try:
        import nautilus_trader  # noqa: F401
    except ImportError:
        print("SKIP: nautilus_trader not installed (digiquant[nautilus])")
        return 1

    _load_env()
    sb = _get_client()
    house_id = str(house_workspace_id())

    price_rows = _fetch_table(
        sb,
        "price_history",
        house_id,
        "date,ticker,open,high,low,close,volume",
        or_null_workspace=True,
    )
    position_rows = _fetch_table(sb, "positions", house_id, "date,ticker,weight_pct")
    nav_rows = _fetch_table(sb, "nav_history", house_id, "date,nav")
    if not position_rows or not nav_rows:
        print("SKIP: no house positions/nav_history rows readable")
        return 1

    request, _closes, recorded = build_request(price_rows, position_rows, nav_rows)
    result = run_shared_cash_portfolio_replay(request)
    if result.status != PortfolioReplayStatus.OK:
        print(f"FAIL: replay {result.status.value}: {result.message}")
        return 2

    engine_nav = {str(p.ts.date()): p.nav for p in result.nav_path}
    dates = sorted(set(engine_nav) & set(recorded))
    worst_bp = 0.0
    worst_day = ""
    breaches: list[str] = []
    warnings: list[str] = []
    prev_eng = prev_rec = None
    for d in dates:
        if prev_eng is None:
            prev_eng, prev_rec = engine_nav[d], recorded[d]
            continue
        r_eng = float((engine_nav[d] - prev_eng) / prev_eng) if prev_eng else 0.0
        r_rec = float((recorded[d] - prev_rec) / prev_rec) if prev_rec else 0.0
        gap_bp = abs(r_eng - r_rec) * 10_000
        if gap_bp > worst_bp:
            worst_bp, worst_day = gap_bp, d
        if gap_bp > args.fail_tol_bp:
            breaches.append(f"{d}: engine {r_eng:+.4%} vs recorded {r_rec:+.4%} ({gap_bp:.1f}bp)")
        elif gap_bp > args.warn_tol_bp:
            warnings.append(f"{d}: {gap_bp:.2f}bp")
        prev_eng, prev_rec = engine_nav[d], recorded[d]

    print(f"compared {len(dates)} days; worst gap {worst_bp:.2f}bp on {worst_day}")
    for w in warnings:
        print(f"  warn: {w}")
    if breaches:
        print("BREACH:")
        for b in breaches:
            print(f"  {b}")
        return 2
    print("OK: recorded NAV matches independent Nautilus replay")
    return 0


if __name__ == "__main__":
    sys.exit(main())
