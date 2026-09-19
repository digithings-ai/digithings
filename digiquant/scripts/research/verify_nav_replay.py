"""Verify recorded house NAV against an independent Nautilus schedule replay.

Rebuilds the house book from ``positions`` book weights + sealed R2 market
OHLCV (real volumes, #4053), runs the hardened schedule replay
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

``--write --mark-through YYYY-MM-DD`` extends the replay grid past the last
committed book using the held positions (no schedule entry, no fabricated
rebalance) so the engine still marks to market when the house run committed no
book that day (#3439). The scheduled workflow passes today UTC; it is a no-op
when a book exists for the target date. ``positions`` is never written by this
path, so a missing book remains detectable.

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
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any  # score:allow untyped any — duck-typed Supabase client

if TYPE_CHECKING:  # pragma: no cover - annotation-only import
    from digiquant.research.supabase_io import SupabaseClient

_MAX_ROWS = 1000  # PostgREST [api].max_rows (digiquant/supabase/config.toml); page cap.
_MAX_PAGES = 10_000  # runaway-fetch guard: ~10M rows, far beyond any book table.

FAIL_TOL_BP = 25.0  # breach: engine vs recorded daily return differs by >25bp.
# Rationale: the restatement replay matched to <1e-6, but this guard compares
# against *stored* rows that may carry integer-lot quantization noise at $100M
# scale (~0.05bp/lot) plus operator touch-ups. 25bp keeps the red band for
# real methodology breaks (e.g. stale-book scale errors), not dust.
WARN_TOL_BP = 1.0  # warning band: integer-lot quantization noise lives here
SCALED_NOTIONAL_USD = 100_000_000.0  # scaled cash so integer lots ≈ arithmetic chain
# Deploy at most this share of NAV per book date. Integer-lot sizing plus split
# fills can execute a few ticks past the sizing close; on a fully-invested book
# that drift overdraws cash and halts the whole replay (#4005). The reserve is
# ~$250k at the scaled notional and costs a fraction of a basis point per day.
FILL_DRIFT_CAP = Decimal("0.9975")


def _rows_from_inception(rows: list[dict], inception_date: str) -> list[dict]:
    """Drop rows dated before ``inception_date`` (pre-cutover books, #3695/#4005)."""
    return [r for r in rows if str(r.get("date") or "") >= inception_date]


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

    Returns the inner OR expression (no outer ``or(...)``) so it can be passed
    straight to ``.or_()`` alongside any other predicate.
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
    workspace_scoped: bool = True,
    tickers: list[str] | None = None,
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

    ``workspace_scoped=False`` is for market/reference tables that carry no
    ``workspace_id`` column: applying a workspace predicate there raises
    PostgREST 42703 and kills the fetch (#3990).

    ``tickers`` narrows a market-data scan to the book the replay will trade
    (#4002): the house book spans a few dozen tickers while the price table
    holds hundreds of thousands of rows, and fetching the whole table every
    night is both slow and pointless. The caller keeps history back to
    ``--inception-date`` (clipped in ``main``, #4005); within that window a
    ticker's latest pre-grid close can seed the forward-fill for a grid that
    starts on a non-trading day.
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
        if workspace_scoped:
            query = query.eq("workspace_id", house_id)
        if tickers:
            query = query.in_("ticker", list(tickers))
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


def _fetch_price_rows(
    sb: SupabaseClient, house_id: str, book_tickers: list[str], inception: date | str
) -> list[dict[str, Any]]:
    """OHLCV rows for the replay from the sealed R2 generations (#4053: R2 only).

    ``inception`` is the ``--inception-date`` value — ``main`` passes the parsed
    ISO string, callers may pass a ``date``; both clip through the same
    :func:`_rows_from_inception` guard (#4005).
    """
    # Imported per call (cached in sys.modules afterwards) so loading the module needs no
    # digiquant import at module scope, matching fill-entry-prices.py.
    from digiquant.research.data.queries import r2_ohlcv_rows

    inception_date = inception.isoformat() if isinstance(inception, date) else str(inception)
    # UTC, not local: the seal is a UTC date and `date.today()` tripped DTZ011.
    today = datetime.now(timezone.utc).date().isoformat()
    rows = r2_ohlcv_rows(tickers=book_tickers, since=inception_date, until=today)
    return _rows_from_inception(rows, inception_date)


def build_request(price_rows, position_rows, nav_rows, mark_through=None):
    """Build the schema-2.0 replay request from books, bars, and recorded NAV.

    ``mark_through`` (``YYYY-MM-DD`` or ``date``, optional) extends the replay
    grid through that date when it is later than the last committed book. The
    last book's positions are held (no schedule entry is added and no fill is
    fabricated), so the engine marks them to market at each intervening close —
    the daily MTM that would otherwise be missing when the house run commits no
    book (#3439). The ``positions`` table is never touched, so a missing book
    stays detectable.
    """
    from digiquant.dashboard.replay.models import (
        InstrumentBarSeries,
        OhlcvBar,
        PortfolioReplayRequest,
        ScheduledTargetWeights,
        TargetWeight,
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
        # Over-allocation (broken pre-cutover books) pro-rata normalizes (locked
        # decision); near-full deployment also keeps the fill-drift reserve so
        # integer-lot fills and split partial fills can never overdraw the
        # account and halt the replay (#4005).
        if gross > FILL_DRIFT_CAP:
            weights = {t: w * FILL_DRIFT_CAP / gross for t, w in weights.items()}
        schedule.append(
            ScheduledTargetWeights(
                effective_date=date.fromisoformat(d),
                weights=tuple(TargetWeight(ticker=t, weight=w) for t, w in sorted(weights.items())),
            )
        )

    book_dates = sorted(book_by_date)
    schedule_tickers = sorted({t for entry in book_by_date.values() for t in entry})
    if not book_dates or not schedule_tickers:
        raise ValueError("position rows carry no book tickers/dates; refusing an empty replay grid")
    # Bookless mark-to-market extension (#3439): when the house run commits no
    # book, the last book's weights still persist in the engine, but the grid
    # normally stops at that book date — so no NAV bar is produced for the
    # missing day and the published series reads flat. Extending the GRID (never
    # the schedule) lets the engine mark the unchanged positions at every close
    # through ``mark_through``. Bars for non-trading days are forward-filled
    # flat below, exactly as they already are for book-grid weekends/holidays.
    grid = list(book_dates)
    if mark_through is not None:
        mark_date = (
            mark_through.isoformat() if isinstance(mark_through, date) else str(mark_through)
        )
        if mark_date > book_dates[-1]:
            cursor = date.fromisoformat(book_dates[-1]) + timedelta(days=1)
            end = date.fromisoformat(mark_date)
            while cursor <= end:
                grid.append(cursor.isoformat())
                cursor += timedelta(days=1)

    closes: dict[tuple[str, str], Decimal] = {}
    volumes: dict[tuple[str, str], Decimal] = {}
    bars_by_ticker: dict[str, dict[str, OhlcvBar]] = {}
    repaired = 0
    for r in price_rows:
        ticker = r["ticker"]
        if ticker not in schedule_tickers:
            continue
        d = str(r["date"])
        open_ = Decimal(str(r["open"]))
        high = Decimal(str(r["high"]))
        low = Decimal(str(r["low"]))
        close = Decimal(str(r["close"]))
        # Fail loudly on non-finite bounds before any comparison: Postgres
        # ``numeric`` stores NaN/Infinity, and widening would otherwise
        # launder low=+Inf / high=-Inf into a finite, valid-looking bar.
        # Decimal NaN comparisons raise InvalidOperation, so is_finite()
        # must come first (#3994 review).
        if not (open_.is_finite() and high.is_finite() and low.is_finite() and close.is_finite()):
            raise ValueError(
                f"{ticker} {d}: non-finite OHLC value "
                f"(open={open_}, high={high}, low={low}, close={close}) "
                "— refusing to build a bar"
            )
        # Vendor bars can violate their own envelope: float-ULP close/low ties
        # and open>high cents. Widen the envelope instead of aborting the
        # nightly refresh; close is never rewritten (#3995). A stored
        # high<low is repaired the same way rather than rejected: the
        # observed prices are the evidence.
        repaired_high = max(high, open_, close)
        repaired_low = min(low, open_, close)
        if repaired_high != high or repaired_low != low:
            repaired += 1
        closes[(d, ticker)] = close
        volumes[(d, ticker)] = Decimal(str(r.get("volume") or 0))
        bars_by_ticker.setdefault(ticker, {})[d] = OhlcvBar(
            ts=datetime.fromisoformat(d).replace(tzinfo=timezone.utc),
            open=open_,
            high=repaired_high,
            low=repaired_low,
            close=close,
            volume=Decimal(str(r.get("volume") or 0)),
        )
    if repaired:
        print(f"WARN: widened OHLC bounds on {repaired} bar(s) (#3995)")

    # The strict contract needs one shared grid across instruments (#4002):
    # walk each schedule ticker over the book dates and forward-fill a missing
    # bar flat at the last close (volume 0) so a weekend/holiday book executes
    # on the last mark instead of aborting the refresh. A ticker's latest bar
    # *before* the grid seeds the first book date, so a grid that starts on a
    # non-trading day still fills from the Friday close.
    series_bars: dict[str, list[OhlcvBar]] = {}
    filled = 0
    for ticker in schedule_tickers:
        by_date = bars_by_ticker.get(ticker, {})
        earlier = [d for d in by_date if d < grid[0]]
        prior: OhlcvBar | None = by_date[max(earlier)] if earlier else None
        bars: list[OhlcvBar] = []
        for d in grid:
            bar = by_date.get(d)
            if bar is None:
                if prior is None:
                    raise ValueError(
                        f"{ticker}: no market bar at or before {d} "
                        "(cannot forward-fill a series before its first bar)"
                    )
                bar = OhlcvBar(
                    ts=datetime.fromisoformat(d).replace(tzinfo=timezone.utc),
                    open=prior.close,
                    high=prior.close,
                    low=prior.close,
                    close=prior.close,
                    volume=Decimal("0"),
                )
                filled += 1
            prior = bar
            bars.append(bar)
        series_bars[ticker] = bars
    if filled:
        print(f"WARN: forward-filled {filled} missing bar(s) on the book grid (#4002)")

    series = tuple(
        InstrumentBarSeries(ticker=t, bars=tuple(series_bars[t])) for t in schedule_tickers
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
        "--mark-through",
        default="",
        dest="mark_through",
        help="With --write, extend the replay grid through this date (YYYY-MM-DD) "
        "using the held last-book positions, so NAV is marked to market on days "
        "the house run committed no book (#3439). No-op when the book is current.",
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
    if args.mark_through:
        _ymd("--mark-through", args.mark_through)
        if not args.write:
            parser.error("--mark-through requires --write")
        if date.fromisoformat(args.mark_through) > datetime.now(timezone.utc).date():
            parser.error(
                f"--mark-through {args.mark_through} is in the future "
                f"(UTC today {datetime.now(timezone.utc).date().isoformat()})"
            )
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
        position_rows = _fetch_table(sb, "positions", house_id, "date,ticker,weight_pct")
        nav_rows = _fetch_table(sb, "nav_history", house_id, "date,nav")
        # Only the verified window enters the replay: pre-cutover books are
        # unreliable (#3695) and their broken gross weights trip the engine
        # (#4005).
        position_rows = _rows_from_inception(position_rows, args.inception_date)
        book_tickers = sorted(
            {str(r["ticker"]) for r in position_rows if r.get("ticker") != "CASH"}
        )
        # The replay only trades the book (#4002): scan just those tickers, not
        # every row of the market table.
        price_rows = (
            _fetch_price_rows(sb, house_id, book_tickers, args.inception_date)
            if book_tickers
            else []
        )
    except RuntimeError as exc:
        # Unstable/truncated pagination (#3803): never verify — and never
        # `--write` — against a partial series.
        print(f"FAIL: {exc}")
        return 2
    if not position_rows or not nav_rows:
        print("SKIP: no house positions/nav_history rows readable")
        return 1
    if not price_rows:
        print("SKIP: no sealed R2 rows for the book tickers")
        return 1

    request, _closes, recorded = build_request(
        price_rows, position_rows, nav_rows, mark_through=args.mark_through or None
    )
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
