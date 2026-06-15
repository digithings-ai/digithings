"""Read structured price/technical + macro values from Supabase for the research agent.

These return compact, token-budgeted JSON (latest snapshot + a short recent window),
not full history. Selected technical columns only — the model gets signal, not noise.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint suppression: duck-typed Supabase client + rows

import polars as pl

from digiquant.data.prices.breadth import compute_breadth
from digiquant.data.prices.relative_strength import compute_relative_strength

logger = logging.getLogger(__name__)

# Indicator columns surfaced to the agent (trend / momentum / regime). Not all 30+.
TECHNICAL_COLUMNS: tuple[str, ...] = (
    "date",
    "sma_50",
    "sma_200",
    "pct_vs_sma50",
    "pct_vs_sma200",
    "rsi_14",
    "macd_hist",
    "roc_21",
    "adx_14",
    "atr_pct",
    "bb_pct_b",
    "zscore_200",
)


def get_price_technicals(*, client: Any, ticker: str, lookback: int = 20) -> dict[str, Any]:
    """Return {ticker, latest, window[]} of selected technicals for one ticker.

    ``window`` is newest-first, length <= lookback. ``latest`` is window[0] or {}.
    """
    resp = (
        client.table("price_technicals")
        .select(",".join(TECHNICAL_COLUMNS))
        .eq("ticker", ticker)
        .order("date", desc=True)
        .limit(lookback)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    return {"ticker": ticker, "latest": rows[0] if rows else {}, "window": rows}


def get_macro_series(
    *, client: Any, series_ids: list[str], lookback: int = 6, as_of: date | None = None
) -> dict[str, Any]:
    """Return {series_id: {latest, window[]}} for each requested FRED series id.

    ``as_of`` bounds observations to ``obs_date <= as_of`` (look-ahead-safe for
    historical/backfill reads); omit it for "latest available".
    """
    out: dict[str, Any] = {}
    for sid in series_ids:
        query = (
            client.table("macro_series_observations")
            .select("series_id,obs_date,value,unit")
            .eq("series_id", sid)
        )
        if as_of is not None:
            query = query.lte("obs_date", as_of.isoformat())
        resp = query.order("obs_date", desc=True).limit(lookback).execute()
        rows = getattr(resp, "data", None) or []
        out[sid] = {"latest": rows[0] if rows else {}, "window": rows}
    return out


def get_market_context(
    *,
    client: Any,
    tickers: list[str] | tuple[str, ...],
    series_ids: list[str] | tuple[str, ...],
    run_date: date,
    price_window_days: int = 7,
) -> dict[str, Any]:
    """Compact latest-values block for the run-wide shared context (#694).

    Returns ``{"as_of", "price_technicals": {ticker: {…latest row…}},
    "macro_series": {series_id: {date, value, prev_value, unit}}}``.

    - Technicals: one bulk query over ``tickers`` for the trailing
      ``price_window_days``; the newest row per ticker wins. Tickers absent
      from ``price_technicals`` are simply omitted.
    - Macro: re-uses :func:`get_macro_series` (per-series latest two
      observations — series cadences are mixed, so a bulk newest-first query
      would starve monthly series behind daily ones).
    """
    out: dict[str, Any] = {
        "as_of": run_date.isoformat(),
        "price_technicals": {},
        "macro_series": {},
    }
    if tickers:
        since = (run_date - timedelta(days=price_window_days)).isoformat()
        resp = (
            client.table("price_technicals")
            .select(",".join(("ticker", *TECHNICAL_COLUMNS)))
            .in_("ticker", list(tickers))
            .gte("date", since)
            .order("date", desc=True)
            .limit(len(tickers) * price_window_days)
            .execute()
        )
        for row in getattr(resp, "data", None) or []:
            ticker = row.get("ticker")
            if ticker and ticker not in out["price_technicals"]:
                out["price_technicals"][ticker] = {k: row.get(k) for k in TECHNICAL_COLUMNS}
    if series_ids:
        macro = get_macro_series(client=client, series_ids=list(series_ids), lookback=2)
        for sid, payload in macro.items():
            window = payload.get("window") or []
            if not window:
                continue
            latest = window[0]
            prev = window[1] if len(window) > 1 else {}
            out["macro_series"][sid] = {
                "date": latest.get("obs_date"),
                "value": latest.get("value"),
                "prev_value": prev.get("value"),
                "unit": latest.get("unit"),
            }
    return out


# ── Raw prices + derived market signals as agent tools (Pillar 1D) ───────────
#
# The research agents and the PM ground their claims by CALLING these (via the
# DATA_TOOLS surface in tools.py) — no pre-injected blobs. Each is derived from
# data already stored (price_history, price_technicals, ingested FRED); no paid
# feed. Reads are bounded; compute is Polars.

_VIX_SPOT_SERIES = "VIXCLS"
_VIX_3M_SERIES = "VXVCLS"


def get_price_history(*, client: Any, ticker: str, lookback: int = 60) -> dict[str, Any]:
    """Raw OHLCV daily bars for one ticker — ``{ticker, latest, window[]}`` newest-first."""
    resp = (
        client.table("price_history")
        .select("date,open,high,low,close,volume")
        .eq("ticker", ticker)
        .order("date", desc=True)
        .limit(lookback)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    return {"ticker": ticker, "latest": rows[0] if rows else {}, "window": rows}


def default_sector_etfs() -> list[str]:
    """Headline ETF per configured sector (relative-strength universe)."""
    try:
        from digiquant.olympus.atlas.sectors_config import load_sectors

        etfs: list[str] = []
        for sector in load_sectors():
            members = getattr(sector, "etfs", None) or []
            if members and members[0] not in etfs:
                etfs.append(members[0])
        return etfs
    except Exception as exc:  # noqa: BLE001 — missing/bad sectors.yaml → empty universe, never crash
        logger.warning("default_sector_etfs unavailable (%s)", exc)
        return []


def get_market_breadth(
    *, client: Any, run_date: date, window_days: int = 7, page_size: int = 1000
) -> dict[str, Any]:
    """Market breadth (% above 50/200-DMA + trend) over all tracked tickers.

    Reads the trailing ``window_days`` of ``price_technicals`` for every ticker and
    delegates the math to :func:`compute_breadth`. Paginates so the result genuinely
    covers all tracked tickers rather than a silently-truncated subset.
    """
    since = (run_date - timedelta(days=window_days)).isoformat()
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        resp = (
            client.table("price_technicals")
            .select("ticker,date,pct_vs_sma50,pct_vs_sma200")
            .gte("date", since)
            .lte("date", run_date.isoformat())
            .order("date", desc=True)
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = getattr(resp, "data", None) or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    if not rows:
        return {}
    return compute_breadth(pl.DataFrame(rows), as_of=run_date)


def get_sector_relative_strength(
    *,
    client: Any,
    run_date: date,
    etfs: list[str] | tuple[str, ...] | None = None,
    benchmark: str = "SPY",
    lookback_days: int = 220,
    page_size: int = 1000,
) -> dict[str, Any]:
    """Sector relative-strength vs ``benchmark`` from ``price_history`` closes.

    Defaults to the configured sector ETFs. Paginates the close history (a
    ~13-ticker × ~150-trading-day pull can exceed the single-response row cap)
    and delegates the math to :func:`compute_relative_strength`.
    """
    sector_etfs = list(etfs) if etfs else default_sector_etfs()
    tickers = list(dict.fromkeys([*sector_etfs, benchmark]))
    if len(tickers) <= 1:
        return {}
    since = (run_date - timedelta(days=lookback_days)).isoformat()
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        resp = (
            client.table("price_history")
            .select("date,ticker,close")
            .in_("ticker", tickers)
            .gte("date", since)
            .lte("date", run_date.isoformat())
            .order("date", desc=False)
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = getattr(resp, "data", None) or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    if not rows:
        return {}
    return compute_relative_strength(pl.DataFrame(rows), benchmark=benchmark, as_of=run_date)


def get_vix_term_structure(*, client: Any, run_date: date) -> dict[str, Any]:
    """VIX term structure from ingested FRED (spot ``VIXCLS`` vs 3-month ``VXVCLS``).

    ``backwardation`` (spot > 3M) flags acute stress; ``contango`` is the calm
    default. Returns ``{}`` when either series is missing.
    """
    macro = get_macro_series(
        client=client, series_ids=[_VIX_SPOT_SERIES, _VIX_3M_SERIES], lookback=1, as_of=run_date
    )
    spot = (macro.get(_VIX_SPOT_SERIES, {}).get("latest") or {}).get("value")
    three_m = (macro.get(_VIX_3M_SERIES, {}).get("latest") or {}).get("value")
    if spot is None or three_m is None:
        return {}
    spot_f = float(spot)
    three_m_f = float(three_m)
    return {
        "as_of": run_date.isoformat(),
        "vix": spot_f,
        "vix3m": three_m_f,
        "ratio": round(spot_f / three_m_f, 3) if three_m_f else None,
        "state": "backwardation" if spot_f > three_m_f else "contango",
    }


# ── Generic scoped data reader (Pillar 1D) ───────────────────────────────────
#
# One read-only, table-whitelisted reader the agents + PM call via the ``query_data``
# tool — backed by the shared ``digibase`` Supabase connector, so we don't hand-roll
# a bespoke tool per table or hand the model raw SQL. Scoped to the market-data +
# paper-book tables; operator-internal telemetry (decision_log, atlas_run_diagnostics)
# is deliberately NOT readable.
ALLOWED_READ_TABLES: frozenset[str] = frozenset(
    {
        "price_history",
        "price_technicals",
        "macro_series_observations",
        "positions",
        "nav_history",
        "theses",
        "thesis_vehicles",
        "position_events",
        "portfolio_metrics",
        "trading_calendar",
    }
)

_MAX_QUERY_ROWS = 500


def query_data(
    *,
    client: Any,
    table: str,
    columns: str = "*",
    eq: dict[str, Any] | None = None,
    gte: dict[str, Any] | None = None,
    lte: dict[str, Any] | None = None,
    in_: dict[str, list[Any] | tuple[Any, ...]] | None = None,
    order: str | None = None,
    desc: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """Read rows from a whitelisted market-data table via the digibase connector.

    Read-only and table-scoped: a table outside :data:`ALLOWED_READ_TABLES` is
    refused (the error is returned to the model, not raised). ``limit`` is capped
    at :data:`_MAX_QUERY_ROWS` so one tool call can't pull unbounded rows.
    """
    if table not in ALLOWED_READ_TABLES:
        return {
            "error": f"table {table!r} is not readable; choose one of {sorted(ALLOWED_READ_TABLES)}"
        }
    from digibase.connectors.supabase import SupabaseConnector

    capped = max(1, min(int(limit), _MAX_QUERY_ROWS))
    result = SupabaseConnector(client).select(
        table,
        columns or "*",
        eq=eq or None,
        gte=gte or None,
        lte=lte or None,
        in_=in_ or None,
        order=order,
        desc=desc,
        limit=capped,
    )
    if not result.success:
        return {"error": result.error}
    return {"table": table, "row_count": len(result.rows), "rows": result.rows}
