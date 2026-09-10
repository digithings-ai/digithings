"""Read structured price/technical + macro values from Supabase for the research agent.

These return compact, token-budgeted JSON (latest snapshot + a short recent window),
not full history. Selected technical columns only — the model gets signal, not noise.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: duck-typed Supabase client + rows
)

import polars as pl

from digiquant.dashboard.tenancy import house_workspace_id
from digiquant.data.prices.breadth import compute_breadth
from digiquant.data.prices.correlation import pairwise_return_correlations
from digiquant.data.prices.etf_flows import compute_etf_flows_proxy
from digiquant.data.prices.fed_probabilities import fed_distribution_from_ladder
from digiquant.data.prices.relative_strength import compute_relative_strength
from digiquant.supabase_retry import run_with_supabase_retry

logger = logging.getLogger(__name__)


# ── R2 market-data backend (#3780, Task 7b) ───────────────────────────────
#
# ``DIGIQUANT_MARKET_DATA_BACKEND=r2`` routes every reader below through the
# versioned R2 generations sealed at ``as_of``; default ``supabase`` keeps the
# legacy table bodies byte-for-byte. The R2 read seams live in
# ``digiquant.mcp_server`` (``_read_r2_window`` / ``_read_r2_macro_window`` /
# ``_read_manifest`` / ``_get_r2_store`` — lazy-imported here so there is one
# patch point and one copy of the manifest-lookup semantics); the only imports
# from ``digiquant.data.prices`` here are the public key helpers
# (``prices/__init__.py`` re-exports neither ``merge`` nor ``r2_history`` —
# always the full path).


def _market_data_backend() -> str:
    """Live read of the ``DIGIQUANT_MARKET_DATA_BACKEND`` flag (default ``supabase``)."""
    import os

    return os.environ.get("DIGIQUANT_MARKET_DATA_BACKEND", "supabase").strip().lower()


def r2_backend_enabled() -> bool:
    """True when the R2 market-data cache is authoritative (#3780 cutover).

    Cross-module predicate for bespoke readers that keep a Supabase body for
    the default backend and an R2 seam for the cutover (supabase_io,
    portfolio writers, preflight). Readers that already flow through a
    migrated helper need no flag check — the helper owns the backend.
    """
    return _market_data_backend() == "r2"


def _r2_manifest() -> dict[str, Any]:
    """Read the R2 market-data manifest via the shared MCP seam."""
    from digiquant.mcp_server import _read_manifest

    return _read_manifest()  # type: ignore[no-any-return]


def _resolve_r2_as_of(as_of: date | None) -> str:
    """ISO ``as_of`` for an R2 read: explicit date, else the manifest watermark.

    The default is the seal — never wall-clock (settled-close semantics).
    """
    if as_of is not None:
        return as_of.isoformat()
    return str(_r2_manifest()["as_of"])


def _r2_generation_window(
    *,
    tickers: list[str] | tuple[str, ...],
    since: date | str,
    until: date | str,
    columns: tuple[str, ...],
    strict: bool = True,
) -> list[dict[str, Any]]:
    """Fetch + window + project sealed R2 generations (shared seam, #3780 fix round).

    ``since``/``until`` are inclusive ISO bounds. ``columns`` selects the
    projection: ``strict`` selects exactly (missing column raises, as before
    for closes); non-strict intersects with the generation's columns so
    readers needing volume omit absent columns per row. ``date`` values come
    back as ISO strings; all other columns pass through untouched (null
    closes included — callers coerce, mirroring the Supabase path).

    Transient R2 transport faults retry centrally here
    (:func:`run_with_supabase_retry` only retries marker-matched faults such
    as disconnects/timeouts — ``LookupError``/``ValueError`` fail loud on
    first attempt), so every ``r2_*_rows`` consumer shares one retry policy
    instead of each call site wrapping its own. Single-ticker live-overlap
    reads (:func:`_read_r2_window` and friends, MCP-owned) stay unwrapped at
    these call sites: on tool paths the dispatcher (``execute_tool``) already
    retries the whole dispatch, and direct-call readers are fail-soft by
    design (empty payload / skip / fallback on ``LookupError``).
    """
    import io

    import polars as pl

    from digiquant.data.prices.r2_history import latest_pointer_key, normalize_ticker
    from digiquant.mcp_server import _get_r2_store

    manifest = _r2_manifest()
    if manifest.get("version") != 1:
        raise ValueError(f"unsupported manifest version {manifest.get('version')}")
    since_s = since.isoformat() if isinstance(since, date) else str(since)
    until_s = until.isoformat() if isinstance(until, date) else str(until)
    store = _get_r2_store()
    datasets = manifest.get("datasets") or {}

    def _fetch() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for ticker in tickers:
            entry = datasets.get(ticker) or datasets.get(normalize_ticker(ticker))
            if entry is not None:
                payload = store.get_generation(str(entry["object"]), str(entry["sha256"]))
            else:
                try:
                    gen_key = store.read_latest(latest_pointer_key(ticker))
                except KeyError:
                    raise LookupError(f"unknown ticker {ticker!r}") from None
                sha: str | None = None
                for cand in datasets.values():
                    if isinstance(cand, dict) and cand.get("object") == gen_key:
                        sha = cand.get("sha256")
                        break
                if sha is None:
                    raise LookupError(f"unknown ticker {ticker!r}")
                payload = store.get_generation(gen_key, str(sha))
            frame = pl.read_parquet(io.BytesIO(payload))
            frame = frame.with_columns(pl.col("date").cast(pl.Date)).sort("date")
            if "ticker" not in frame.columns:
                frame = frame.with_columns(pl.lit(normalize_ticker(ticker)).alias("ticker"))
            window = frame.filter(
                (pl.col("date") >= pl.lit(since_s).cast(pl.Date))
                & (pl.col("date") <= pl.lit(until_s).cast(pl.Date))
            )
            keep = list(columns) if strict else [c for c in columns if c in window.columns]
            for row in window.select(keep).to_dicts():
                shaped = dict(row)
                shaped["date"] = str(shaped["date"])
                out.append(shaped)
        return out

    return run_with_supabase_retry(_fetch, operation="r2 generation window")


def r2_close_rows(
    *, tickers: list[str] | tuple[str, ...], since: date | str, until: date | str
) -> list[dict[str, Any]]:
    """``{date, ticker, close}`` rows from SEALED R2 generations (no live overlap).

    ``since``/``until`` are inclusive ISO bounds (``until`` is typically the run
    date — settled generations never hold an unformed bar, so no live fetch is
    needed for lookback math). Mirrors the ``_read_r2_window`` manifest lookup
    (verbatim ticker, then normalized; ``latest`` pointer fallback). Raises
    ``LookupError`` for an unknown ticker and ``ValueError`` for a non-v1
    manifest — both fail loud, never an empty window. Null closes are passed
    through (callers coerce, mirroring the Supabase ``numeric``-as-string path).
    """
    return _r2_generation_window(
        tickers=tickers, since=since, until=until, columns=("date", "ticker", "close")
    )


def r2_ohlcv_rows(
    *, tickers: list[str] | tuple[str, ...], since: date | str, until: date | str
) -> list[dict[str, Any]]:
    """``{date, ticker, open, high, low, close, volume}`` from sealed R2 generations.

    Same fetch as :func:`r2_close_rows` for readers needing volume (ETF-flow
    proxy). Columns absent from a generation are omitted per row.
    """
    return _r2_generation_window(
        tickers=tickers,
        since=since,
        until=until,
        columns=("date", "ticker", "open", "high", "low", "close", "volume"),
        strict=False,
    )


def r2_manifest_seal() -> tuple[date, int]:
    """``(seal_date, price_ticker_count)`` from the R2 manifest seal.

    The ticker count scopes to ``market-data/price/`` generations (macro
    ``{source}__{series}`` ids are excluded by object prefix, not by id
    heuristics). Freshness probes route here under the R2 backend.
    """
    from datetime import date as _date

    manifest = _r2_manifest()
    seal = _date.fromisoformat(str(manifest["as_of"]))
    datasets = manifest.get("datasets") or {}
    count = sum(
        1
        for entry in datasets.values()
        if isinstance(entry, dict) and str(entry.get("object", "")).startswith("market-data/price/")
    )
    return seal, count


class _SupabaseSelectError(Exception):
    """A failed connector select, carrying the raw error for retry classification."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


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


def get_price_technicals(
    *, client: Any, ticker: str, lookback: int = 20, as_of: date | None = None
) -> dict[str, Any]:
    """Return {ticker, latest, window[]} of selected technicals for one ticker.

    ``window`` is newest-first, length <= lookback. ``latest`` is window[0] or {}.
    ``as_of`` bounds rows to ``date <= as_of`` (look-ahead-safe for historical
    reads); omit it for "latest available" (Supabase) or the manifest watermark
    (R2 backend — never wall-clock).

    Under ``DIGIQUANT_MARKET_DATA_BACKEND=r2`` the rows are recomputed
    indicators over the sealed R2 generation (``_read_r2_window``), projected
    onto :data:`TECHNICAL_COLUMNS` with ISO date strings — the same envelope
    shape as the Supabase body. An unknown ticker returns the empty
    latest/window (Supabase parity — a missing ticker is not an outage).
    """
    if r2_backend_enabled():
        return _r2_price_technicals(ticker=ticker, lookback=lookback, as_of=as_of)
    query = (
        client.table("price_technicals").select(",".join(TECHNICAL_COLUMNS)).eq("ticker", ticker)
    )
    if as_of is not None:
        query = query.lte("date", as_of.isoformat())
    resp = query.order("date", desc=True).limit(lookback).execute()
    rows = getattr(resp, "data", None) or []
    return {"ticker": ticker, "latest": rows[0] if rows else {}, "window": rows}


def _r2_price_technicals(*, ticker: str, lookback: int, as_of: date | None) -> dict[str, Any]:
    """R2 branch of :func:`get_price_technicals` (see it for the contract)."""
    from digiquant.mcp_server import _read_r2_window

    try:
        rows = _read_r2_window(ticker, _resolve_r2_as_of(as_of))
    except LookupError:
        return {"ticker": ticker, "latest": {}, "window": []}
    shaped = [
        {
            col: (str(row["date"]) if col == "date" else row.get(col))
            for col in TECHNICAL_COLUMNS
            if col == "date" or col in row
        }
        for row in rows
    ]
    window = shaped[-lookback:][::-1] if lookback > 0 else []
    return {"ticker": ticker, "latest": window[0] if window else {}, "window": window}


def get_macro_series(
    *, client: Any, series_ids: list[str], lookback: int = 6, as_of: date | None = None
) -> dict[str, Any]:
    """Return {series_id: {latest, window[]}} for each requested FRED series id.

    ``as_of`` bounds observations to ``obs_date <= as_of`` (look-ahead-safe for
    historical/backfill reads); omit it for "latest available" (Supabase) or
    the manifest watermark (R2). ``window`` is newest-first, ``latest`` is
    window[0] or {} — identical on both backends. A series missing from R2
    returns the empty payload (Supabase parity per series).

    R2 coverage is FRED-sourced series only (the ``fred__{SERIES}`` manifest
    ids); prediction-market ``FEDPROB/*`` rows have no R2 generation — see
    :func:`get_fed_rate_probabilities`.
    """
    if r2_backend_enabled():
        return _r2_macro_series(series_ids=series_ids, lookback=lookback, as_of=as_of)
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


_MACRO_ENVELOPE_COLUMNS: tuple[str, ...] = ("series_id", "obs_date", "value", "unit")


def _r2_macro_series(*, series_ids: list[str], lookback: int, as_of: date | None) -> dict[str, Any]:
    """R2 branch of :func:`get_macro_series` (see it for the contract)."""
    from digiquant.mcp_server import _read_r2_macro_window

    manifest = _r2_manifest()
    resolved = as_of.isoformat() if as_of is not None else str(manifest["as_of"])
    out: dict[str, Any] = {}
    for sid in series_ids:
        try:
            payload = _read_r2_macro_window([sid], resolved, manifest)
        except LookupError:
            out[sid] = {"latest": {}, "window": []}
            continue
        rows = [
            {
                col: (str(row[col]) if col == "obs_date" else row.get(col))
                for col in _MACRO_ENVELOPE_COLUMNS
            }
            for row in payload[sid]["window"]
        ]
        window = rows[::-1][:lookback] if lookback > 0 else []
        out[sid] = {"latest": window[0] if window else {}, "window": window}
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
      from ``price_technicals`` are simply omitted. Under the R2 backend the
      same newest-row-per-ticker is read from the sealed generations via
      :func:`get_price_technicals` (one call per ticker — the helper owns the
      backend, so the envelope never changes).
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
        if r2_backend_enabled():
            # Trailing-window bound mirrors the Supabase bulk query: a ticker
            # whose newest sealed row predates the window is omitted (the
            # preflight basket-gap probe depends on the omission).
            since = (run_date - timedelta(days=price_window_days)).isoformat()
            for ticker in tickers:
                tech = get_price_technicals(
                    client=client,
                    ticker=ticker,
                    lookback=price_window_days,
                    as_of=run_date,
                )
                if tech["latest"] and str(tech["latest"].get("date") or "") >= since:
                    out["price_technicals"][ticker] = tech["latest"]
            # Newest-row-per-ticker already holds (lookback window, latest
            # first) — no bulk first-seen pass needed on this path.
        else:
            since = (run_date - timedelta(days=price_window_days)).isoformat()
            resp = (
                client.table("price_technicals")
                .select(",".join(("ticker", *TECHNICAL_COLUMNS)))
                .in_("ticker", list(tickers))
                .gte("date", since)
                .lte("date", run_date.isoformat())
                .order("date", desc=True)
                .limit(len(tickers) * price_window_days)
                .execute()
            )
            for row in getattr(resp, "data", None) or []:
                ticker = row.get("ticker")
                if ticker and ticker not in out["price_technicals"]:
                    out["price_technicals"][ticker] = {k: row.get(k) for k in TECHNICAL_COLUMNS}
    if series_ids:
        macro = get_macro_series(
            client=client, series_ids=list(series_ids), lookback=2, as_of=run_date
        )
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


def default_sector_etfs() -> list[str]:
    """Headline ETF per configured sector (relative-strength universe)."""
    try:
        from digiquant.research.sectors_config import load_sectors

        etfs: list[str] = []
        for sector in load_sectors():
            members = getattr(sector, "etfs", None) or []
            if members and members[0] not in etfs:
                etfs.append(members[0])
        return etfs
    except Exception as exc:  # missing/bad sectors.yaml → empty universe, never crash
        logger.warning("default_sector_etfs unavailable (%s)", exc)
        return []


def get_market_breadth(
    *, client: Any, run_date: date, window_days: int = 7, page_size: int = 1000
) -> dict[str, Any]:
    """Market breadth (% above 50/200-DMA + trend) over all tracked tickers.

    Reads the trailing ``window_days`` of ``price_technicals`` for every ticker and
    delegates the math to :func:`compute_breadth`. Paginates so the result genuinely
    covers all tracked tickers rather than a silently-truncated subset. Under the
    R2 backend the window comes from the sealed generations (same frame shape).
    """
    if r2_backend_enabled():
        return _r2_market_breadth(run_date=run_date, window_days=window_days)
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
    # compute_breadth returns the stamped-empty shape ({as_of, universe_size: 0}) for an
    # empty frame, so the no-rows path keeps the breadth contract (universe_size always
    # present) instead of a bare {} that KeyErrors downstream (#1011).
    return compute_breadth(pl.DataFrame(rows), as_of=run_date)


def _r2_market_breadth(*, run_date: date, window_days: int) -> dict[str, Any]:
    """R2 branch of :func:`get_market_breadth`: per-ticker sealed windows."""
    from digiquant.mcp_server import _read_r2_window

    manifest = _r2_manifest()
    # Price dataset ids are normalized tickers (Task 5 backfill); the object
    # prefix (not id heuristics) excludes macro ``{source}__{series}`` ids.
    tickers = sorted(
        dataset_id
        for dataset_id, entry in ((manifest.get("datasets") or {}).items())
        if isinstance(entry, dict) and str(entry.get("object", "")).startswith("market-data/price/")
    )
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            window = _read_r2_window(ticker, run_date.isoformat(), manifest)
        except LookupError:
            continue
        for row in window:
            if str(row.get("date") or "") >= (run_date - timedelta(days=window_days)).isoformat():
                rows.append(
                    {
                        "ticker": ticker,
                        "date": str(row.get("date")),
                        "pct_vs_sma50": row.get("pct_vs_sma50"),
                        "pct_vs_sma200": row.get("pct_vs_sma200"),
                    }
                )
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
    and delegates the math to :func:`compute_relative_strength`. Under the R2
    backend the closes come from the sealed generations (:func:`r2_close_rows`).
    """
    sector_etfs = list(etfs) if etfs else default_sector_etfs()
    tickers = list(dict.fromkeys([*sector_etfs, benchmark]))
    if len(tickers) <= 1:
        return {}
    since = (run_date - timedelta(days=lookback_days)).isoformat()
    if r2_backend_enabled():
        rows = r2_close_rows(tickers=tickers, since=since, until=run_date)
        if not rows:
            return {}
        return compute_relative_strength(pl.DataFrame(rows), benchmark=benchmark, as_of=run_date)
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


def get_etf_flows_proxy(
    *,
    client: Any,
    run_date: date,
    etfs: list[str] | tuple[str, ...] | None = None,
    lookback_days: int = 63,
    page_size: int = 1000,
) -> dict[str, Any]:
    """Volume-derived ETF flow PROXY (dollar-volume z-score + OBV trend) per sector ETF.

    True fund-flow data is paid; this derives a free turnover/accumulation proxy from
    ``price_history`` close+volume already stored, and delegates the math to
    :func:`compute_etf_flows_proxy`. Defaults to the configured sector ETFs; paginates the
    window. Always returns the stamped proxy shape (``as_of``/``note``/``universe_size``/
    ``flows``) — empty-but-stamped when the universe is empty or ``price_history`` has no rows —
    so callers see one consistent shape with the proxy caveat intact.
    """
    universe = list(etfs) if etfs else default_sector_etfs()
    if not universe:
        # Stamped empty shape (with the proxy note), not a bare {} — keeps the JSON shape and
        # the "NOT true flows" caveat consistent on the degraded path.
        return compute_etf_flows_proxy(pl.DataFrame(), as_of=run_date)
    since = (run_date - timedelta(days=lookback_days)).isoformat()
    if r2_backend_enabled():
        # Sealed generations carry OHLCV incl. volume (Task 5 PRICE_COLUMNS).
        return compute_etf_flows_proxy(
            pl.DataFrame(r2_ohlcv_rows(tickers=universe, since=since, until=run_date)),
            as_of=run_date,
        )
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        resp = (
            client.table("price_history")
            .select("date,ticker,close,volume")
            .in_("ticker", universe)
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
    # compute_etf_flows_proxy returns the stamped empty shape for an empty frame, so both the
    # no-rows and rows-exist paths share one consistent JSON shape (+ the proxy note).
    return compute_etf_flows_proxy(pl.DataFrame(rows), as_of=run_date)


def get_fed_rate_probabilities(
    *, client: Any, run_date: date, lookback_days: int = 7
) -> dict[str, Any]:
    """Forward FOMC rate-decision odds for the NEAREST upcoming meeting, from prediction markets.

    Reads the ``FEDPROB/*`` rows ingested into ``macro_series_observations`` (Kalshi survival
    ladder + Polymarket cross-check), takes the freshest snapshot ``<= run_date`` (look-ahead
    safe), picks the nearest meeting on/after ``run_date``, and derives the full 25bp upper-bound
    distribution from the Kalshi ladder. Returns ``{}`` when no Fed-probability data is present.

    Deliberately NOT routed to R2 (#3780 Task 7b): prediction-market snapshots
    have no R2 generation (the refresh cron + backfill cover FRED-sourced
    series only), so this stays on the Supabase table on both backends — and
    the ``fetch-macro --sources fedprob`` writer stays exempt from the
    writers-stop for the same reason.
    """
    since = (run_date - timedelta(days=lookback_days)).isoformat()
    resp = (
        client.table("macro_series_observations")
        .select("source,series_id,obs_date,value,meta")
        .in_("source", ["kalshi", "polymarket"])
        .gte("obs_date", since)
        .lte("obs_date", run_date.isoformat())
        .order("obs_date", desc=True)
        .limit(3000)
        .execute()
    )
    rows = [
        r
        for r in (getattr(resp, "data", None) or [])
        if str(r.get("series_id", "")).startswith("FEDPROB/")
    ]
    if not rows:
        return {}
    latest_obs = max(str(r.get("obs_date") or "") for r in rows)
    rows = [r for r in rows if str(r.get("obs_date") or "") == latest_obs]

    meetings: dict[str, dict[str, Any]] = {}
    for r in rows:
        parts = str(r.get("series_id", "")).split("/")
        if len(parts) < 3:
            continue
        bucket = meetings.setdefault(parts[1], {"ladder": {}, "polymarket": []})
        value = r.get("value")
        if value is None:
            continue
        if r.get("source") == "kalshi" and parts[2].startswith("upper_gt_"):
            try:
                bucket["ladder"][float(parts[2].removeprefix("upper_gt_"))] = float(value)
            except ValueError:
                continue
        elif r.get("source") == "polymarket":
            bucket["polymarket"].append(
                {
                    "outcome": "/".join(parts[2:]),
                    "prob": float(value),
                    "question": (r.get("meta") or {}).get("question"),
                }
            )
    if not meetings:
        return {}
    # Nearest meeting on/after the run date (else the latest available).
    future = sorted(mk for mk in meetings if mk >= run_date.isoformat())
    meeting = future[0] if future else max(meetings)
    data = meetings[meeting]
    ladder = data["ladder"]
    kalshi: dict[str, Any] = {}
    if ladder:
        kalshi = {"ladder": {f"{k:g}": v for k, v in sorted(ladder.items())}}
        kalshi.update(fed_distribution_from_ladder(ladder))
    sources = [
        s
        for s, present in (("kalshi", bool(ladder)), ("polymarket", bool(data["polymarket"])))
        if present
    ]
    if not sources:
        return {}
    return {
        "as_of": run_date.isoformat(),
        "meeting_date": meeting,
        "kalshi": kalshi,
        "polymarket": sorted(data["polymarket"], key=lambda d: -(d["prob"] or 0))[:12],
        "sources": sources,
    }


def get_return_correlations(
    *,
    client: Any,
    tickers: list[str],
    run_date: date,
    lookback_days: int = 63,
    page_size: int = 1000,
) -> pl.DataFrame | None:
    """Pairwise Pearson return correlations for ``tickers`` over a trailing window.

    Loads ``price_history`` closes for the requested tickers over the
    ``lookback_days`` trailing window with ``.lte("date", run_date)`` as a
    look-ahead guard (no future closes leak into the correlation estimate).
    Uses a single capped query (``tickers × lookback_days`` rows is small for a
    typical PM book; the ``page_size`` argument is kept for API symmetry with the
    other readers but is applied as a hard limit, not a paginated loop, since the
    correlation window is bounded by the PM's position count).

    Returns a long Polars frame ``{a, b, corr}`` ready for
    ``sizing.size_portfolio(corr=...)``, or ``None`` on any error or when there
    are fewer than two tickers with enough history (the caller keeps the
    conservative ρ=1.0 default). Fail-soft: no exception propagates to the caller.
    """
    if len(tickers) < 2:
        return None
    since = (run_date - timedelta(days=lookback_days)).isoformat()
    if r2_backend_enabled():
        try:
            rows = r2_close_rows(tickers=list(tickers), since=since, until=run_date)
        except LookupError as exc:
            logger.warning("get_return_correlations: failed (%s); skipping correlation", exc)
            return None
        if not rows:
            return None
        frame = pairwise_return_correlations(pl.DataFrame(rows))
        return frame if not frame.is_empty() else None
    try:
        resp = (
            client.table("price_history")
            .select("date,ticker,close")
            .in_("ticker", list(tickers))
            .gte("date", since)
            .lte("date", run_date.isoformat())  # look-ahead guard (no future closes)
            .order("date", desc=False)
            .limit(len(tickers) * page_size)
            .execute()
        )
        rows: list[dict[str, Any]] = getattr(resp, "data", None) or []
        if not rows:
            return None
        frame = pairwise_return_correlations(pl.DataFrame(rows))
        return frame if not frame.is_empty() else None
    except Exception as exc:  # correlation is best-effort; caller uses None
        logger.warning("get_return_correlations: failed (%s); skipping correlation", exc)
        return None


# ── Generic scoped data reader (Pillar 1D) ───────────────────────────────────
#
# One read-only, table-whitelisted reader the agents + PM call via the ``query_data``
# tool — backed by the shared ``digibase`` Supabase connector, so we don't hand-roll
# a bespoke tool per table or hand the model raw SQL. Scoped to the paper-book
# tables + the trading calendar; operator-internal telemetry (decision_log,
# atlas_run_diagnostics) is deliberately NOT readable.
#
# Market history (price_history, price_technicals, macro_series_observations)
# moved to the versioned R2 cache (#3780, Task 7 cutover): it is served via
# ``digiquant_get_price_technicals`` / ``digiquant_get_macro_series`` (MCP) and
# the ``get_*`` readers below (in-process), never via this generic reader.
MARKET_TABLES_REMOVED: tuple[str, ...] = (
    "price_history",
    "price_technicals",
    "macro_series_observations",
)
ALLOWED_READ_TABLES: frozenset[str] = frozenset(
    {
        "positions",
        "nav_history",
        "theses",
        "thesis_vehicles",
        "position_events",
        "portfolio_metrics",
        "trading_calendar",
    }
)

# Blinded-analyst scope for ``query_data``: with market tables removed from the
# generic reader, only the calendar remains here. (Blinded nodes still get
# market *values* via the injected ``market_context`` + dedicated readers.)
MARKET_DATA_TABLES: frozenset[str] = frozenset({"trading_calendar"})

# Group A private books: omitted workspace_id is the house, never an unfiltered
# date scan. Overlay same-date rows must not seed house research via query_data.
HOUSE_BOOK_READ_TABLES: frozenset[str] = frozenset(
    {"positions", "nav_history", "position_events", "portfolio_metrics"}
)

_MAX_QUERY_ROWS = 500

# columns must be "*" or a comma-separated list of bare column names. This blocks
# PostgREST relationship/embedding syntax (e.g. "*,decision_log(*)") that would
# otherwise read a NON-whitelisted table through an embedded select.
_SAFE_COLUMNS_RE = re.compile(r"^(\*|[A-Za-z_][A-Za-z0-9_]*(\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)$")


def _eq_for_query(table: str, eq: dict[str, Any] | None) -> dict[str, Any] | None:
    """Stamp house ``workspace_id`` on Group A books when the caller omitted it."""
    filters = dict(eq or {})
    if table in HOUSE_BOOK_READ_TABLES and "workspace_id" not in filters:
        filters["workspace_id"] = str(house_workspace_id())
    return filters or None


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
    allowed_tables: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Read rows from a whitelisted table via the digibase connector.

    Read-only and table-scoped: a table outside the active whitelist is refused
    (the error is returned to the model, not raised). Callers may pass a narrower
    ``allowed_tables`` (e.g. :data:`MARKET_DATA_TABLES` for blinded analyst nodes);
    it is intersected with :data:`ALLOWED_READ_TABLES`. ``limit`` is capped at
    :data:`_MAX_QUERY_ROWS` so one tool call can't pull unbounded rows.

    Group A books (``positions``, ``nav_history``, ``position_events``,
    ``portfolio_metrics``) default to the house ``workspace_id`` when ``eq``
    omits it, so overlay same-date rows cannot seed house research. Pass
    ``eq={"workspace_id": ...}`` to read another book.
    """
    tables = (allowed_tables & ALLOWED_READ_TABLES) if allowed_tables else ALLOWED_READ_TABLES
    if table not in tables:
        return {"error": f"table {table!r} is not readable; choose one of {sorted(tables)}"}
    safe_columns = (columns or "*").strip()
    if not _SAFE_COLUMNS_RE.fullmatch(safe_columns):
        # Block PostgREST relationship/embedding syntax that could reach other tables.
        return {"error": "columns must be '*' or a comma-separated list of plain column names"}
    from digibase.connectors.supabase import SupabaseConnector

    capped = max(1, min(int(limit), _MAX_QUERY_ROWS))

    def _select():  # type: ignore[no-untyped-def]
        select_result = SupabaseConnector(client).select(
            table,
            safe_columns,
            eq=_eq_for_query(table, eq),
            gte=gte or None,
            lte=lte or None,
            in_=in_ or None,
            order=order,
            desc=desc,
            limit=capped,
        )
        # The connector swallows transport faults into success=False — re-raise
        # retryable ones so transient disconnects / PGRST002 / 502s retry 3×
        # (#3299). Anything else still lands in the {"error": …} below.
        if not select_result.success:
            raise _SupabaseSelectError(select_result.error or "unknown select error")
        return select_result

    try:
        result = run_with_supabase_retry(_select, operation=f"query_data {table}")
    except _SupabaseSelectError as exc:
        return {"error": exc.detail}
    return {"table": table, "row_count": len(result.rows), "rows": result.rows}
