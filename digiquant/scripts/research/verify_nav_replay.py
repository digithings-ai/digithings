"""Verify recorded house NAV against an independent Nautilus schedule replay.

Rebuilds the house book from ``positions`` book weights + ``price_history``
OHLCV (real volumes), runs the hardened schedule replay
(``digiquant.dashboard.replay``, schema 2.0, causal-fill convention), and
compares the engine NAV path against recorded ``nav_history``.

Single source of truth: with ``--write`` the engine NAV path (normalized to
the inception-100 scale) is persisted to ``nav_history`` — the engine is the
last writer under the documented workflow order (the booking path still writes
provisional rows at book time; the engine step runs after and overwrites them,
and a read-only verify runs after metrics so drift fails loudly).
``refresh_performance_metrics.refresh_nav_point`` only guards that the row
exists; tearsheets read the stored series. Default mode is read-only
verification.

Exit codes: 0 = within tolerance (or write succeeded), 1 = usage/config
error, 2 = NAV breach / engine failure.

Requires ``nautilus_trader`` (``digiquant[nautilus]``) and Supabase env —
``CORE_SUPABASE_URL`` / ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``
(see ``digiquant/src/digiquant/research/config/supabase.env``).

Read-only unless ``--write``: SELECTs Group A tables pinned to the house
workspace. ``--write`` upserts ``nav_history`` (house-pinned) only. All
fetches use cursor pagination over a deterministic ``(date, ticker)`` order
(#3803) and refuse to verify or write from a truncated/unstable page.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

_MAX_ROWS = 1000  # PostgREST [api].max_rows (digiquant/supabase/config.toml); page cap.
_MAX_PAGES = 10_000  # runaway-fetch guard: ~10M rows, far beyond any book table.

FAIL_TOL_BP = 25.0  # breach: engine vs recorded daily return differs by >25bp.
# Rationale: the restatement replay matched to <1e-6, but this guard compares
# against *stored* rows that may carry integer-lot quantization noise at $100M
# scale (~0.05bp/lot) plus operator touch-ups. 25bp keeps the red band for
# real methodology breaks (e.g. stale-book scale errors), not dust.
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
    key = os.environ.get(
        "CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    ).strip()
    if not url or not key:
        raise SystemExit(
            "CORE_SUPABASE_URL/SUPABASE_URL and "
            "CORE_SUPABASE_SERVICE_KEY/SUPABASE_SERVICE_ROLE_KEY required"
        )
    return create_client(url, key)


def _fetch_key(row: dict, has_ticker: bool) -> tuple[str, ...]:
    """Sort/fetch cursor for one row: ``(date, ticker)`` or ``(date,)``.

    A blank fallback for a missing key (the old ``str(row.get(...) or "")``)
    collides with a real key and turns corrupt input into a bogus duplicate-key
    pagination error — so a projection that requires a key refuses a row without
    one instead.
    """
    day = str(row.get("date") or "")
    if not day:
        raise RuntimeError("row is missing its date — cannot build a pagination cursor")
    if not has_ticker:
        return (day,)
    ticker = row.get("ticker")
    if ticker is None or not str(ticker).strip():
        raise RuntimeError(f"row for date {day} is missing its ticker — refusing the fetch")
    return (day, str(ticker))


def _keyset_term(has_ticker: bool, last_key: tuple[str, ...]) -> str:
    """PostgREST seek past ``last_key`` in ``(date[, ticker])`` order.

    Returns the inner OR expression (no outer ``or(...)``) so callers can nest
    it inside a workspace ``or`` without dropping either predicate.
    """
    day = last_key[0]
    if not has_ticker:
        return f"date.gt.{day}"
    return f"date.gt.{day},and(date.eq.{day},ticker.gt.{last_key[1]})"


def _fetch_table(
    sb,
    table: str,
    house_id: str,
    cols: str,
    or_null_workspace: bool = False,
    page_size: int = _MAX_ROWS,
    max_rows: int = _MAX_ROWS,
) -> list[dict]:
    """Fetch every row of ``table`` with keyset (seek) pagination (#3803, #3948).

    Ordering is deterministic — ``(date, ticker)`` when the projection carries
    ``ticker``, else ``(date,)`` — and each page seeks strictly past the last
    key it saw (``date > d OR (date = d AND ticker > t)``), never on an offset:
    a concurrent book upsert between pages can neither shift rows out of the
    series nor duplicate them into the weight schedule that ``--write`` persists
    as truth.

    The request size is bounded by the server's configured ``max_rows`` cap
    (PostgREST ``[api].max_rows``, mirrored by ``_MAX_ROWS``). A page that comes
    back the full requested size means "there may be more" and the cursor
    advances; only a short page ends the loop. Asking for more than the cap
    raises instead of accepting a server-clamped page — the #3948 bug, where a
    boundary-widened ``limit(page_size + boundary_seen)`` exceeded the cap,
    ``len(page) < page_size + boundary_seen`` looked like "done", and the loop
    broke *before* the stall guard, silently dropping 1001 rows.

    Fail-closed: a page out of order, duplicate keys within a page, a missing
    required key, a stalled cursor, or more than ``_MAX_PAGES`` pages raises
    ``RuntimeError`` instead of returning a truncated series. Callers must not
    write NAV from a partial fetch.
    """
    selected = {c.strip() for c in cols.split(",")}
    has_ticker = "ticker" in selected
    if page_size > max_rows:
        raise RuntimeError(
            f"{table}: page_size={page_size} exceeds max_rows={max_rows} — "
            "refusing a request the server would silently clamp"
        )
    rows: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    last_key: tuple[str, ...] | None = None
    pages = 0
    while True:
        pages += 1
        if pages > _MAX_PAGES:
            raise RuntimeError(f"{table}: exceeded {_MAX_PAGES} pages — refusing a runaway fetch")
        query = sb.table(table).select(cols).order("date")
        if has_ticker:
            query = query.order("ticker")
        if or_null_workspace:
            # Omitted workspace_id = house (HOUSE_BOOK_SCOPE.md): match both.
            # When seeking, the keyset predicate must be ANDed inside each
            # workspace branch so one ``or`` carries both conditions.
            if last_key is None:
                query = query.or_(f"workspace_id.eq.{house_id},workspace_id.is.null")
            else:
                seek = _keyset_term(has_ticker, last_key)
                query = query.or_(
                    f"and(workspace_id.eq.{house_id},or({seek})),"
                    f"and(workspace_id.is.null,or({seek}))"
                )
        else:
            query = query.eq("workspace_id", house_id)
            if last_key is not None:
                if has_ticker:
                    query = query.or_(_keyset_term(True, last_key))
                else:
                    query = query.gt("date", last_key[0])
        page = query.limit(page_size).execute().data or []

        keys = [_fetch_key(r, has_ticker) for r in page]
        if any(a > b for a, b in zip(keys, keys[1:])):
            raise RuntimeError(
                f"{table}: page arrived out of (date,ticker) order — "
                "pagination is unstable, refusing the fetch"
            )
        if len(page) and len(set(keys)) < len(keys):
            raise RuntimeError(
                f"{table}: duplicate (date,ticker) keys within one page — "
                "pagination is unstable, refusing the fetch"
            )
        fresh = [(r, k) for r, k in zip(page, keys) if k not in seen]
        for r, k in fresh:
            seen.add(k)
            rows.append(r)
        # Stall guard runs before any break: a page that yields no new key
        # means the cursor did not advance (e.g. a server ignoring the seek),
        # and breaking here would silently drop the rest of the table.
        if page and not fresh:
            raise RuntimeError(
                f"{table}: pagination stalled at {last_key} "
                f"(page_size={page_size}) — refusing a truncated fetch"
            )
        if len(page) < page_size:
            break
        last_key = keys[-1]
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


def _slice_write_path(
    engine_nav: dict[str, object],
    inception_date: str,
    date: str = "",
) -> tuple[dict[str, object], set[str] | None]:
    """Slice the engine path to writable dates (>= ``inception_date``).

    Returns ``(write_path, target)`` for :func:`_write_nav`. The inception-100
    base is then derived from the first bar >= inception, so a full-path
    write can never resurrect deleted pre-cutoff rows (#3695). Raises
    ``ValueError`` when ``date`` names no writable bar.
    """
    write_path = {d: v for d, v in engine_nav.items() if d >= inception_date}
    if date:
        if date < inception_date:
            raise ValueError(
                f"{date} predates inception {inception_date} "
                "(pre-cutoff history was deleted as unreliable; see #3695)"
            )
        if date not in write_path:
            raise ValueError(f"engine path has no bar for {date}")
        return write_path, {date}
    return write_path, None


def _write_nav(
    sb,
    house_id: str,
    full_engine_nav: dict[str, object],
    dates_to_write: set[str] | None = None,
) -> int:
    """Persist engine NAV rows to ``nav_history`` on the inception-100 scale.

    Normalization: ``nav[d] = 100 * engine[d] / base`` where ``base`` is
    ALWAYS the engine NAV on the FIRST bar of the passed path — the function
    derives it internally, so a single-date caller cannot self-normalize to
    100 by passing a one-row path. Callers MUST pass the inception-sliced
    path (see :func:`_slice_write_path`); the function itself only trusts
    ``arg[0]``. ``dates_to_write`` only slices which rows are upserted
    (None = full path). Returns the number of rows upserted.
    """
    from decimal import Decimal as _Decimal

    dates = sorted(full_engine_nav)
    if not dates:
        print("WRITE: empty engine NAV path — nothing persisted")
        return 0
    base = _Decimal(str(full_engine_nav[dates[0]]))
    if not base:
        print("WRITE: zero opening engine NAV — refusing to persist")
        return 0
    wanted = dates_to_write if dates_to_write is not None else set(dates)
    ts = datetime.now(tz=timezone.utc).isoformat()
    rows = [
        {
            "workspace_id": house_id,
            "date": d,
            "nav": round(float(_Decimal(str(full_engine_nav[d])) / base * 100), 6),
            "updated_at": ts,
        }
        for d in dates
        if d in wanted
    ]
    sb.table("nav_history").upsert(rows, on_conflict="workspace_id,date").execute()
    print(f"WRITE: {len(rows)} nav_history rows upserted from engine ({dates[0]} → {dates[-1]})")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fail-tol-bp", type=float, default=FAIL_TOL_BP)
    parser.add_argument("--warn-tol-bp", type=float, default=WARN_TOL_BP)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist the engine NAV path to nav_history (engine is the sole NAV writer).",
    )
    parser.add_argument(
        "--date",
        default="",
        help="With --write, persist only this date (YYYY-MM-DD); default persists all dates from --inception-date.",
    )
    parser.add_argument(
        "--inception-date",
        default="2026-07-17",
        help="Earliest date ever written to nav_history. Pre-cutoff dates can never "
        "be resurrected (2026-06-23..26 deleted as unreliable #3695); the write "
        "target is sliced to dates >= this and the inception-100 base is the "
        "first bar >= this.",
    )
    args = parser.parse_args()
    # I1: the floor comparisons are raw string compares, so a malformed date
    # silently disables the guard ("" matches everything). Fail closed here.
    from datetime import date as _date

    def _ymd(label: str, value: str) -> None:
        try:
            _date.fromisoformat(value)
        except ValueError:
            parser.error(f"{label} must be YYYY-MM-DD (got {value!r})")

    _ymd("--inception-date", args.inception_date)
    if args.date:
        _ymd("--date", args.date)
    if args.date and not args.write:
        parser.error("--date requires --write (verify mode compares the full path)")
    if args.write and args.date and args.date < args.inception_date:
        parser.error(
            f"--date {args.date} predates --inception-date {args.inception_date} "
            "(pre-cutoff history was deleted as unreliable; see #3695)"
        )

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

    try:
        price_rows = _fetch_table(
            sb,
            "price_history",
            house_id,
            "date,ticker,open,high,low,close,volume",
            or_null_workspace=True,
        )
        position_rows = _fetch_table(sb, "positions", house_id, "date,ticker,weight_pct")
        nav_rows = _fetch_table(sb, "nav_history", house_id, "date,nav")
    except RuntimeError as exc:
        # Unstable/truncated pagination (#3803): never verify — and never
        # `--write` — against a partial series.
        print(f"FAIL: {exc}")
        return 2
    if not position_rows or not nav_rows:
        print("SKIP: no house positions/nav_history rows readable")
        return 1

    request, _closes, recorded = build_request(price_rows, position_rows, nav_rows)
    result = run_shared_cash_portfolio_replay(request)
    if result.status != PortfolioReplayStatus.OK:
        print(f"FAIL: replay {result.status.value}: {result.message}")
        return 2

    engine_nav = {str(p.ts.date()): p.nav for p in result.nav_path}
    if args.write:
        try:
            write_path, target = _slice_write_path(engine_nav, args.inception_date, args.date)
        except ValueError as exc:
            print(f"WRITE FAIL: {exc}")
            return 2
        if not write_path:
            print(f"WRITE FAIL: no engine bars >= inception {args.inception_date}")
            return 2
        n = _write_nav(sb, house_id, write_path, target)
        if not n:
            return 2
        return 0

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
