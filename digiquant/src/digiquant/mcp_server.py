"""digiquant MCP server: backtest, optimize, export, strategy catalog.

Run::

    pip install -e "digiquant[mcp]"
    python -m digiquant.mcp_server

Uses the same ``service_*`` functions as the HTTP API.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Literal, overload

logger = logging.getLogger(__name__)

# ── Market-data backend: Supabase vs versioned R2 history (#3780, Task 4) ──
#
# ``DIGIQUANT_MARKET_DATA_BACKEND=r2`` routes the price/macro tools through the
# R2HistoryStore generations + manifest sealed at ``manifest["as_of"]``, merged
# with a live overlap and settled-close semantics. Default ``supabase`` keeps
# the current bodies byte-for-byte (extracted as ``_supabase_*`` below).

_TTL_SECONDS = 900
_ttl: dict[tuple, tuple[float, str]] = {}

# Calendar days of live overlap fetched ahead of the R2 manifest seal.
_R2_LIVE_OVERLAP_DAYS = 30


def _ttl_get(key: tuple) -> str | None:
    hit = _ttl.get(key)
    if hit and time.time() - hit[0] < _TTL_SECONDS:
        return hit[1]
    return None


def _supabase_technicals(ticker: str, lookback: int) -> str:
    """Current Supabase body, extracted unchanged (non-R2 path)."""
    from digiquant.research.data.queries import get_price_technicals
    from digiquant.research.supabase_io import SupabaseConfig, build_client

    try:
        client = build_client(SupabaseConfig.from_env())
        result = get_price_technicals(client=client, ticker=ticker, lookback=lookback)
    except Exception as exc:  # surface as JSON to the caller, never crash
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    return json.dumps(result, default=str)


def _supabase_macro(series_ids: list[str], lookback: int) -> str:
    """Current Supabase body, extracted unchanged (non-R2 path)."""
    from digiquant.research.data.queries import get_macro_series
    from digiquant.research.supabase_io import SupabaseConfig, build_client

    try:
        client = build_client(SupabaseConfig.from_env())
        result = get_macro_series(client=client, series_ids=series_ids, lookback=lookback)
    except Exception as exc:  # surface as JSON to the caller, never crash
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    return json.dumps(result, default=str)


def _get_r2_store() -> Any:
    """Build the read-path ``R2HistoryStore`` from env (patchable seam for tests)."""
    from digiquant.data.prices.r2_history import R2HistoryStore
    from digiquant.ops.checkpoint_archive import (
        R2_ACCESS_KEY_ENV,
        R2_ACCOUNT_ENV,
        R2_BUCKET_ENV,
        R2_SECRET_KEY_ENV,
        R2Backend,
    )

    account = (os.environ.get(R2_ACCOUNT_ENV) or "").strip()
    bucket = (os.environ.get(R2_BUCKET_ENV) or "").strip()
    access = (os.environ.get(R2_ACCESS_KEY_ENV) or "").strip()
    secret = (os.environ.get(R2_SECRET_KEY_ENV) or "").strip()
    if not (account and bucket and access and secret):
        raise RuntimeError(
            "missing R2 credentials; set R2_ACCOUNT_ID/R2_BUCKET/R2_ACCESS_KEY_ID/"
            "R2_SECRET_ACCESS_KEY"
        )
    backend = R2Backend(
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        bucket=bucket,
        access_key=access,
        secret_key=secret,
    )

    def _read_only_registry_insert(
        source_table: str, source_key: dict, r2_key: str, sha256: str, size: int
    ) -> None:
        raise RuntimeError("market-data MCP read path must not write registry rows")

    return R2HistoryStore(backend, _read_only_registry_insert)


def _read_manifest() -> dict:
    """Read the R2 market-data manifest (version-checked by the store)."""
    return _get_r2_store().read_manifest()  # type: ignore[no-any-return]


def _r2_is_stale(manifest_as_of: str, resolved_as_of: str) -> bool:
    """Task 6 staleness gate on the read path: seal >5 trading days behind as_of."""
    from digiquant.data.prices.refresh_gate import staleness_gate

    return not bool(staleness_gate(manifest_as_of, resolved_as_of)["ok"])


@overload
def _read_r2_window(ticker: str, as_of: str, manifest: dict | None = ...) -> list[dict]: ...


@overload
def _read_r2_window(
    ticker: str, as_of: str, manifest: dict | None = ..., *, return_stale: Literal[True]
) -> tuple[list[dict], bool]: ...


def _read_r2_window(
    ticker: str, as_of: str, manifest: dict | None = None, *, return_stale: bool = False
) -> list[dict] | tuple[list[dict], bool]:
    """Date-ascending indicator dicts for *ticker* sealed at *as_of*.

    R2 history (SHA-verified via the manifest) + live overlap fetched from
    ``(manifest_as_of, as_of]`` → :func:`merge_history_live` with
    ``sealed=False`` (settled close: the live ``as_of`` bar is excluded) →
    :func:`compute_indicators`. An ``as_of`` at or before the manifest seal
    skips the live fetch entirely, and the merged frame is additionally bounded
    to ``date <= as_of`` so historical reads (``as_of`` behind the seal — the
    cutover's backfill use case) cannot leak newer history (#3780 Task 7).
    A missing ``latest`` pointer (KeyError)
    maps to an unknown-ticker ``LookupError`` for the MCP error envelope.
    A live-fetch failure raises (surfaced as the ``{"error"}`` envelope by
    the caller) — it is never swallowed into a valid-looking window.
    A per-ticker fetch *error entry* (``FetchResult.errors`` with no raised
    exception, e.g. vendor ``no_data``) serves history-only rows but marks the
    read stale (fail-soft serving + loud flag — Task 7 decision, mirroring the
    Task 6 cron): pass ``return_stale=True`` to get ``(rows, live_stale)``.
    Indicator columns are attached to the merged frame via a date-ordered
    left join, with a row-count guard so a reordering/filtering change in
    :func:`compute_indicators` fails loud instead of misaligning.
    """
    import io
    from datetime import date as _date
    from datetime import timedelta as _td

    import polars as pl

    from digiquant.data.prices.merge import merge_history_live
    from digiquant.data.prices.r2_history import latest_pointer_key, normalize_ticker
    from digiquant.data.prices.technicals import compute_indicators

    manifest = manifest if manifest is not None else _read_manifest()
    as_of_d = _date.fromisoformat(as_of)
    manifest_d = _date.fromisoformat(str(manifest["as_of"]))
    manifest_seal = manifest_d.isoformat()
    resolved_as_of = as_of_d.isoformat()
    store = _get_r2_store()
    datasets = manifest.get("datasets") or {}
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

    hist = pl.read_parquet(io.BytesIO(payload))
    if "date" not in hist.columns and "timestamp" in hist.columns:
        hist = hist.rename({"timestamp": "date"})
    hist = hist.with_columns(pl.col("date").cast(pl.Date)).sort("date")

    if as_of_d <= manifest_d:
        live = hist.clear()
        live_stale = False
    else:
        live_stale = False
        try:
            from digiquant.data.prices.fetchers import fetch_batch

            live_start = max(manifest_d + _td(days=1), as_of_d - _td(days=_R2_LIVE_OVERLAP_DAYS))
            fetched = fetch_batch(
                [ticker],
                start=live_start.isoformat(),
                end=(as_of_d + _td(days=1)).isoformat(),
            )
            if ticker in fetched.errors:
                # Vendor error entry, no exception: serve history-only but flag
                # stale (Task 7 fail-soft decision) — never a fresh-looking seal.
                live_stale = True
                logger.warning(
                    "R2 read %s as_of=%s: live fetch error entry (%s); "
                    "serving history-only (stale)",
                    ticker,
                    resolved_as_of,
                    fetched.errors[ticker],
                )
            frame = fetched.frames.get(ticker)
            if frame is None or frame.is_empty():
                live = hist.clear()
            else:
                staged = frame.with_columns(pl.col("timestamp").cast(pl.Date).alias("date"))
                live = staged.select(
                    pl.col("date").cast(pl.Date),
                    *(
                        pl.col(c).cast(hist.schema[c])
                        if c in staged.columns
                        else pl.lit(None).cast(hist.schema[c]).alias(c)
                        for c in hist.columns
                        if c != "date"
                    ),
                )
        except Exception as exc:
            raise RuntimeError(f"live fetch failed for {ticker!r}: {exc}") from exc

    merged = merge_history_live(hist, live, manifest_seal, resolved_as_of, sealed=False)
    # Historical-read bound: the merge only caps history at the seal, so an
    # as_of behind the seal would leak newer history (look-ahead). No-op when
    # as_of >= seal (merge output is already <= as_of there).
    merged = merged.filter(pl.col("date") <= pl.lit(resolved_as_of).cast(pl.Date))
    if merged.is_empty():
        return ([], live_stale) if return_stale else []
    ohlcv = merged.rename({"date": "timestamp"}) if "timestamp" not in merged.columns else merged
    indicators = compute_indicators(ohlcv)
    if indicators.height != merged.height:
        raise RuntimeError(
            f"indicator/price row mismatch for {ticker!r}: "
            f"{indicators.height} indicator rows vs {merged.height} merged rows"
        )
    rows = (
        merged.select(pl.col("date"), pl.col("close"))
        .with_row_index("_mcp_pos")
        .join(indicators.with_row_index("_mcp_pos"), on="_mcp_pos", how="left")
        .drop("_mcp_pos")
        .sort("date")
        .to_dicts()
    )
    return (rows, live_stale) if return_stale else rows


def _read_r2_macro_window(
    series_ids: list[str], as_of: str, manifest: dict | None = None
) -> dict[str, dict]:
    """Per-series ``{latest, window}`` macro observations sealed at *as_of*.

    A series whose generation is missing from the manifest (unknown sha) or
    whose ``latest`` pointer is absent raises ``LookupError`` — surfaced as
    the ``{"error"}`` envelope by the caller — so backfill key mismatches
    fail loud instead of serving empty windows.
    """
    import io

    import polars as pl

    from digiquant.data.prices.r2_history import macro_latest_pointer_key

    manifest = manifest if manifest is not None else _read_manifest()
    datasets = manifest.get("datasets") or {}
    store = _get_r2_store()
    out: dict[str, dict] = {}
    for sid in series_ids:
        try:
            gen_key = store.read_latest(macro_latest_pointer_key("fred", sid))
            sha = None
            for cand in datasets.values():
                if isinstance(cand, dict) and cand.get("object") == gen_key:
                    sha = cand.get("sha256")
                    break
            if sha is None:
                raise LookupError(f"unknown macro series {sid!r}")
            frame = pl.read_parquet(io.BytesIO(store.get_generation(gen_key, str(sha))))
            date_col = "obs_date" if "obs_date" in frame.columns else "date"
            rows = (
                frame.with_columns(pl.col(date_col).cast(pl.Date))
                .filter(pl.col(date_col) <= pl.lit(as_of).cast(pl.Date))
                .sort(date_col)
                .to_dicts()
            )
            out[sid] = {"latest": rows[-1] if rows else {}, "window": rows}
        except KeyError:
            raise LookupError(f"unknown macro series {sid!r}") from None
    return out


def digiquant_get_price_technicals(
    ticker: str, lookback: int = 20, as_of: str | None = None
) -> str:
    """Technicals for *ticker*, Supabase-backed by default or R2-backed with the flag.

    The R2 envelope is ``{"as_of", "rows", "stale"}``: ``stale`` is true when
    the manifest seal is >5 trading days behind ``as_of`` (Task 6 gate) or the
    live overlap carried a per-ticker fetch error entry (history-only serve).

    Two independent ``stale`` signals share the name (#3780 Task 7 fix round
    M2): the manifest's writer-side ``stale`` (Task 6 refresh cron — the seal's
    age at generation time) vs this envelope's reader-side ``stale`` (evaluated
    per request from the seal and the live overlap). They can disagree (a fresh
    manifest served through a flaked live fetch reads stale here). Task 10 docs
    must carry the glossary entry.
    """
    try:
        lookback = min(int(lookback), 500)
        from digiquant.research.data.queries import r2_backend_enabled

        if not r2_backend_enabled():
            return _supabase_technicals(ticker, lookback)
        manifest = _read_manifest()
        if manifest["version"] != 1:
            return json.dumps({"error": f"unsupported manifest version {manifest['version']}"})
        resolved = as_of or manifest["as_of"]
        cache_key = ("technicals", ticker, resolved, manifest["version"])
        cached = _ttl_get(cache_key)
        if cached is not None:
            return cached
        rows, live_stale = _read_r2_window(ticker, resolved, manifest, return_stale=True)
        stale = live_stale or _r2_is_stale(str(manifest["as_of"]), resolved)
        if stale:
            logger.warning(
                "R2 technicals %s as_of=%s seal=%s live_stale=%s: serving stale window",
                ticker,
                resolved,
                manifest["as_of"],
                live_stale,
            )
        payload = json.dumps(
            {"as_of": resolved, "rows": rows[-lookback:], "stale": stale}, default=str
        )
        # Task 7 fix round (M1): never cache a stale-flagged payload — a stale
        # serve pinned for the full 900s TTL would keep reporting stale after
        # the vendor flake clears. Fresh payloads cache normally.
        if not stale:
            _ttl[cache_key] = (time.time(), payload)
        return payload
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


def digiquant_get_macro_series(
    series_ids: list[str], lookback: int = 6, as_of: str | None = None
) -> str:
    """Macro observations for *series_ids*, Supabase-backed by default or R2-backed.

    The R2 envelope is ``{"as_of", "series", "stale"}`` (per-series
    ``{latest, window}``). Unknown series fail loud (``{"error"}``); a stale
    manifest seal only flags ``stale`` — macro has no live overlap to repair it.

    Same two-``stale`` note as technicals (#3780 Task 7 fix round M2): the
    manifest's writer-side ``stale`` (Task 6 cron) vs this envelope's
    reader-side ``stale``. Task 10 docs must carry the glossary entry.
    """
    try:
        lookback = min(int(lookback), 500)
        from digiquant.research.data.queries import r2_backend_enabled

        if not r2_backend_enabled():
            return _supabase_macro(series_ids, lookback)
        manifest = _read_manifest()
        if manifest["version"] != 1:
            return json.dumps({"error": f"unsupported manifest version {manifest['version']}"})
        resolved = as_of or manifest["as_of"]
        cache_key = ("macro", tuple(series_ids), resolved, manifest["version"])
        cached = _ttl_get(cache_key)
        if cached is not None:
            return cached
        per_series = _read_r2_macro_window(series_ids, resolved, manifest)
        stale = _r2_is_stale(str(manifest["as_of"]), resolved)
        if stale:
            logger.warning(
                "R2 macro %s as_of=%s seal=%s: serving stale window",
                series_ids,
                resolved,
                manifest["as_of"],
            )
        series = {
            sid: {"latest": payload["latest"], "window": payload["window"][-lookback:]}
            for sid, payload in per_series.items()
        }
        payload = json.dumps({"as_of": resolved, "series": series, "stale": stale}, default=str)
        # Task 7 fix round (M1): same no-cache-on-stale rule as technicals.
        if not stale:
            _ttl[cache_key] = (time.time(), payload)
        return payload
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


try:
    from mcp.server.fastmcp import FastMCP

    _MCP_AVAILABLE = True
except ImportError:
    FastMCP = None  # type: ignore[assignment,misc]
    _MCP_AVAILABLE = False


def _require_mcp() -> type:
    if not _MCP_AVAILABLE:
        raise ImportError("Install mcp: pip install digiquant[mcp]")
    return FastMCP  # type: ignore[return-value]


def create_mcp_server() -> Any:
    _require_mcp()
    mcp = FastMCP("digiquant")

    @mcp.tool()
    def digiquant_list_strategies() -> str:
        """List registered strategies (name, aliases, description, default_params)."""
        from digiquant.service import service_list_strategies

        return json.dumps(service_list_strategies(), indent=2)

    @mcp.tool()
    def digiquant_run_backtest(
        strategy_name: str,
        symbols_json: str,
        data_dir: str | None = None,
        data_path: str | None = None,
        strategy_params_json: str | None = None,
    ) -> str:
        """Run a Nautilus backtest. symbols_json is a JSON array e.g. '["AAPL"]'."""
        symbols: list[str] = json.loads(symbols_json)
        params = json.loads(strategy_params_json) if strategy_params_json else None
        from digiquant.service import service_run_backtest

        result = service_run_backtest(
            strategy_name=strategy_name,
            symbols=symbols,
            data_path=data_path,
            data_dir=data_dir,
            strategy_params=params,
        )
        return result.model_dump_json(indent=2)

    @mcp.tool()
    def digiquant_run_optimize(
        strategy_name: str,
        symbols_json: str,
        data_dir: str | None = None,
        data_path: str | None = None,
        method: str = "grid",
        n_trials: int = 50,
        param_grid_json: str | None = None,
        strategy_params_json: str | None = None,
    ) -> str:
        """Run parameter optimization (grid, bayesian, or random).

        ``strategy_name='sdca'`` / ``'btc_sdca'`` is Stage B walk-forward
        (vs-flat-DCA). Freeze Stage A weights by passing them in
        ``strategy_params_json`` as ``*_weight`` keys. Stage A itself is
        ``digiquant_fit_sdca_weights``.
        """
        symbols: list[str] = json.loads(symbols_json)
        params = json.loads(strategy_params_json) if strategy_params_json else None
        grid = json.loads(param_grid_json) if param_grid_json else None
        from digiquant.service import service_run_optimize

        result = service_run_optimize(
            strategy_name=strategy_name,
            symbols=symbols,
            data_path=data_path,
            data_dir=data_dir,
            method=method,
            n_trials=n_trials,
            param_grid=grid,
            base_params=params,
        )
        return result.model_dump_json(indent=2)

    @mcp.tool()
    def digiquant_export(
        strategy_name: str,
        target: str,
        params_json: str | None = None,
    ) -> str:
        """Export strategy config (JSON or nautilus_bundle zip). targets: nautilus, nautilus_bundle, …"""
        params = json.loads(params_json) if params_json else {}
        from digiquant.service import service_run_export

        result = service_run_export(
            strategy_name=strategy_name,
            params=params,
            target=target,
        )
        return result.model_dump_json(indent=2)

    @mcp.tool()
    def digiquant_run_pipeline(
        strategy_name: str,
        symbols_json: str,
        data_dir: str | None = None,
        data_path: str | None = None,
        strategy_params_json: str | None = None,
        export_target: str = "nautilus",
        run_optimize: bool = True,
        run_export: bool = True,
        method: str = "grid",
        n_trials: int = 50,
        constraints_json: str | None = None,
    ) -> str:
        """Run validate → backtest → optional optimize → optional export via internal LangGraph.

        Returns JSON with ``trace``, and serialized ``backtest`` / ``optimize`` / ``export`` when run.
        """
        symbols: list[str] = json.loads(symbols_json)
        params = json.loads(strategy_params_json) if strategy_params_json else None
        constraints = json.loads(constraints_json) if constraints_json else None
        from digiquant.graph.pipeline import run_quant_workflow

        raw = run_quant_workflow(
            {
                "strategy_name": strategy_name,
                "symbols": symbols,
                "data_path": data_path,
                "data_dir": data_dir,
                "strategy_params": params,
                "export_target": export_target,
                "run_optimize": run_optimize,
                "run_export": run_export,
                "method": method,
                "n_trials": n_trials,
                "constraints": constraints,
            }
        )
        return json.dumps(raw, indent=2)

    @mcp.tool(name="digiquant_get_price_technicals")
    def digiquant_get_price_technicals_tool(
        ticker: str, lookback: int = 20, as_of: str | None = None
    ) -> str:
        """Latest technical indicators + recent daily window for a ticker (JSON).

        Reads the maintained ``price_technicals`` table in Supabase. Returns
        ``{"error": ...}`` if the data layer is unavailable.
        With ``DIGIQUANT_MARKET_DATA_BACKEND=r2``, reads the versioned R2
        history sealed at ``as_of`` (default: manifest seal) instead.
        """
        return digiquant_get_price_technicals(ticker, lookback=lookback, as_of=as_of)

    @mcp.tool(name="digiquant_get_macro_series")
    def digiquant_get_macro_series_tool(
        series_ids: list[str], lookback: int = 6, as_of: str | None = None
    ) -> str:
        """Latest values + recent window for FRED macro series ids (JSON).

        Reads the maintained ``macro_series_observations`` table in Supabase.
        Returns ``{"error": ...}`` if the data layer is unavailable.
        With ``DIGIQUANT_MARKET_DATA_BACKEND=r2``, reads the versioned R2
        history sealed at ``as_of`` (default: manifest seal) instead.
        """
        return digiquant_get_macro_series(series_ids, lookback=lookback, as_of=as_of)

    @mcp.tool()
    def digiquant_query_data(
        table: str,
        columns: str = "*",
        eq: dict[str, Any] | None = None,
        gte: dict[str, Any] | None = None,
        lte: dict[str, Any] | None = None,
        order: str | None = None,
        desc: bool = True,
        limit: int = 50,
    ) -> str:
        """Read rows from a whitelisted dashboard table (JSON).

        Exposes the same read-only, table-scoped reader the in-process portfolio
        agents use, so external agents (digichat / execution) can fetch the paper
        book and market data by key (#925). Allowed tables: ``positions``,
        ``nav_history``, ``theses``, ``thesis_vehicles``, ``position_events``,
        ``portfolio_metrics``, ``trading_calendar``. Market history
        (``price_history``, ``price_technicals``, ``macro_series_observations``)
        moved to the versioned R2 cache (#3780) and is no longer readable here —
        use ``digiquant_get_price_technicals`` / ``digiquant_get_macro_series``.
        Operator-internal telemetry (decision_log, diagnostics) is deliberately
        NOT readable.
        Group A books (``positions``, ``nav_history``, ``position_events``,
        ``portfolio_metrics``) default to the house ``workspace_id`` when
        ``eq`` omits it; pass ``eq.workspace_id`` to read another book.
        ``limit`` is capped server-side. Returns ``{"error": ...}`` on failure.
        """
        from digiquant.research.data.queries import query_data
        from digiquant.research.supabase_io import SupabaseConfig, build_client

        try:
            client = build_client(SupabaseConfig.from_env())
            result = query_data(
                client=client,
                table=table,
                columns=columns,
                eq=eq,
                gte=gte,
                lte=lte,
                order=order,
                desc=desc,
                limit=limit,
            )
        except Exception as exc:  # surface as JSON to the caller, never crash
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        return json.dumps(result, default=str)

    # ── Slapper tearsheet pipeline (price → Nautilus backtest → TradingView parity) ──
    # These wrap the repo's pipeline scripts so the whole flow is MCP-discoverable.
    # Paths are resolved relative to this package (editable/source checkout).
    def _scripts_dir() -> str:
        from pathlib import Path

        return str(Path(__file__).resolve().parents[2] / "scripts")

    def _validation_dir() -> str:
        from pathlib import Path

        return str(Path(__file__).resolve().parents[3] / "scripts" / "validation")

    @mcp.tool()
    def digiquant_fetch_coinbase_ohlcv(
        symbols_json: str = '["BTC/USD", "ETH/USD", "SOL/USD"]',
        start: str = "2015-07-20",
        cache_dir: str | None = None,
    ) -> str:
        """Fetch daily OHLCV from Coinbase (CCXT) into the price-history cache.

        ``symbols_json`` is a JSON array of CCXT symbols. ``start`` defaults
        to Coinbase BTC listing ``2015-07-20``; ETH/SOL begin at the first
        available Coinbase daily bar. Returns JSON mapping each ticker to
        ``{bars, first, last, path}`` (or ``{error}``).
        """
        import sys
        from pathlib import Path

        sd = _scripts_dir()
        if sd not in sys.path:
            sys.path.insert(0, sd)
        try:
            import ccxt
            from fetch_coinbase import DEFAULT_CACHE, SYMBOLS, bars_to_polars, fetch_all_daily
        except ImportError as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

        cache = Path(cache_dir) if cache_dir else DEFAULT_CACHE
        cache.mkdir(parents=True, exist_ok=True)
        exchange = ccxt.coinbase()
        out: dict[str, Any] = {}
        for sym in json.loads(symbols_json):
            ticker = SYMBOLS.get(sym, sym.replace("/", "-"))
            try:
                bars = fetch_all_daily(exchange, sym, start)
                if not bars:
                    out[ticker] = {"error": "no data"}
                    continue
                df = (
                    bars_to_polars(bars, ticker)
                    .unique(subset=["timestamp"], keep="last")
                    .sort("timestamp")
                )
                path = cache / f"{ticker}.csv"
                df.write_csv(path)
                out[ticker] = {
                    "bars": len(df),
                    "first": df["timestamp"][0],
                    "last": df["timestamp"][-1],
                    "path": str(path),
                }
            except Exception as exc:  # surface per-symbol, never crash
                out[ticker] = {"error": f"{type(exc).__name__}: {exc}"}
        return json.dumps(out, indent=2, default=str)

    @mcp.tool()
    def digiquant_fit_btc_power_law(
        ticker: str = "BTC-USD",
        cache_dir: str | None = None,
        refresh: bool = True,
        bulk_period: str = "max",
        output_path: str | None = None,
        notes: str = "",
    ) -> str:
        """Fit the BTC power-law (RAQQR) SDCA valuation rails from cached price history (#1082).

        Sources ``ticker`` daily closes via the canonical price-history cache
        (``digiquant.data.prices.history_cache``) rather than a bespoke fetch —
        ``refresh=True`` (default) incrementally updates the cache first via the
        same yfinance pipeline every other price-history consumer uses, bulk-fetching
        ``bulk_period`` of history for a ticker that isn't cached yet (default ``"max"``,
        since the fit requires at least 730 daily observations and a short bulk window
        would leave a cold cache short of that); ``refresh=False`` fits directly from
        whatever is already cached (useful when network access is unavailable). Persists
        the fit to ``output_path`` (default: ``sdca/btc_power_law_coefficients.json``,
        replacing the synthetic placeholder shipped with #1082 — pass an explicit
        ``output_path`` under a non-editable/read-only install where the package source
        tree isn't writable). Returns a JSON summary
        (``{fit_start, fit_end, fit_rows, path}``) or ``{"error": ...}``.
        """
        from pathlib import Path

        try:
            import polars as pl

            from digiquant.data.prices.history_cache import (
                DEFAULT_CACHE_DIR,
                incremental_update,
                load_cached,
            )
            from digiquant.strategies.sdca.btc_power_law import (
                fit_btc_power_law,
                save_coefficients,
            )
        except ImportError as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

        cdir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        try:
            if refresh:
                df = incremental_update([ticker], cdir, bulk_period=bulk_period).get(ticker)
            else:
                df = load_cached(ticker, cdir)
            if df is None or df.is_empty():
                return json.dumps({"error": f"no cached price history for {ticker!r}"})

            prices = (
                df.select(
                    pl.col("timestamp").cast(pl.Date).alias("date"),
                    pl.col("close"),
                )
                .unique(subset=["date"], keep="last")
                .sort("date")
            )
            coefficients = fit_btc_power_law(
                prices["date"],
                prices["close"],
                notes=notes
                or f"Fit from cached {ticker!r} history via digiquant_fit_btc_power_law.",
            )
            path = save_coefficients(coefficients, Path(output_path) if output_path else None)
        except Exception as exc:  # surface as JSON, never crash the server
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

        return json.dumps(
            {
                "fit_start": str(coefficients.fit_start),
                "fit_end": str(coefficients.fit_end),
                "fit_rows": coefficients.fit_rows,
                "path": str(path),
            },
            indent=2,
        )

    @mcp.tool()
    def digiquant_build_sdca_risk_index(
        ticker: str = "BTC-USD",
        cache_dir: str | None = None,
        refresh: bool = True,
        bulk_period: str = "max",
        risk_model: str = "btc_power_law",
        profile: str | None = None,
        profile_json: str | None = None,
        coefficients_path: str | None = None,
        output_path: str | None = None,
        indicator_weights: str = "{}",
        m2_path: str | None = None,
        dxy_path: str | None = None,
        eth_ticker: str = "ETH-USD",
        valuation_form: str = "log_quadratic",
        rolling_window: int = 90,
    ) -> str:
        """Build the SDCA ``date``/``risk`` parquet from a ``RiskModel`` + cached prices (#3168).

        Sources ``ticker`` daily closes via the canonical price-history cache.
        ``profile`` (``btc_v1`` / ``eth_research_v1``) or ``profile_json`` applies
        an ``SdcaAssetProfile`` (rails, oscillators, extra allowlist). Returns
        JSON or ``{"error": ...}`` (never raises).
        """
        from digiquant.sdca_mcp import run_build_sdca_risk_index

        return run_build_sdca_risk_index(
            ticker=ticker,
            cache_dir=cache_dir,
            refresh=refresh,
            bulk_period=bulk_period,
            risk_model=risk_model,
            profile=profile,
            profile_json=profile_json,
            coefficients_path=coefficients_path,
            output_path=output_path,
            indicator_weights=indicator_weights,
            m2_path=m2_path,
            dxy_path=dxy_path,
            eth_ticker=eth_ticker,
            valuation_form=valuation_form,
            rolling_window=rolling_window,
        )

    @mcp.tool()
    def digiquant_fetch_bitview_series(
        series_ids_json: str = '["mvrv", "asopr_24h", "puell_multiple", "rhodl_ratio"]',
        cache_dir: str | None = None,
        timeout: float = 30.0,
        start: int | None = None,
        end: int | None = None,
    ) -> str:
        """Fetch Bitview/BRK on-chain ``day1`` series into ``data/onchain/bitview/``.

        JSON API only (no HTML scrape). Default catalog is the #1086 v1 subset.
        ``nupl`` is refused (monotone of MVRV). Fail-soft + timeout. Coin Metrics
        community CC BY-NC series are not fetched. Network is the operator opt-in
        of invoking this tool.
        """
        from digiquant.sdca_mcp import run_fetch_bitview_series

        return run_fetch_bitview_series(
            series_ids_json=series_ids_json,
            cache_dir=cache_dir,
            timeout=timeout,
            start=start,
            end=end,
        )

    @mcp.tool()
    def digiquant_fit_sdca_weights(
        profile: str = "btc_v1",
        profile_json: str | None = None,
        cache_dir: str | None = None,
        coefficients_path: str | None = None,
        output_path: str | None = None,
        m2_path: str | None = None,
        dxy_path: str | None = None,
        eth_ticker: str = "ETH-USD",
        valuation_form: str = "log_quadratic",
        rolling_window: int = 90,
    ) -> str:
        """Stage A: fit composite weights so risk overlaps cycle windows.

        Not a second optimizer. Stage B is ``digiquant_run_optimize`` with
        ``strategy_name='sdca'``; pass ``regularized_weight_params`` as
        ``strategy_params_json``. No live-trading. Do not ``--push-supabase``.
        """
        from digiquant.sdca_mcp import run_fit_sdca_weights

        return run_fit_sdca_weights(
            profile=profile,
            profile_json=profile_json,
            cache_dir=cache_dir,
            coefficients_path=coefficients_path,
            output_path=output_path,
            m2_path=m2_path,
            dxy_path=dxy_path,
            eth_ticker=eth_ticker,
            valuation_form=valuation_form,
            rolling_window=rolling_window,
        )

    @mcp.tool()
    def digiquant_generate_slapper_tearsheet(
        strategy: str | None = None,
        cache_dir: str | None = None,
        signal_delay_days: int = 0,
        allow_example_calibrations: bool = False,
    ) -> str:
        """Run the NautilusTrader backtest for the Slapper family and write TV-style
        tearsheet JSON to the digiquant.io frontend. ``strategy=None`` runs all three.

        Structure comes from ``strategies/settings.json`` (public); calibrations
        resolve file -> Supabase (-> example only when ``allow_example_calibrations``).
        Each strategy runs in its own spawned process (#1389): NautilusTrader's Rust
        logging initializes once per process, so a second in-process engine would
        abort this server. ``signal_delay_days`` lags the public tearsheets by N
        calendar days (#1462). Returns ``{"entries": [...], "failures": {...}}``.
        """
        import sys
        from pathlib import Path

        sd = _scripts_dir()
        if sd not in sys.path:
            sys.path.insert(0, sd)
        try:
            import generate_tearsheets as gt
        except ImportError as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

        if signal_delay_days < 0:
            return json.dumps({"error": "signal_delay_days must be >= 0"})

        gt.load_repo_env()
        try:
            from digiquant.strategies.calibrations_loader import pick_calibration_source

            cal_source = pick_calibration_source(
                prefer_supabase=False,
                allow_example=allow_example_calibrations,
            )
        except Exception as exc:  # surface as JSON to the caller
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

        settings = gt.load_settings()
        if strategy is not None and strategy not in settings["strategies"]:
            return json.dumps(
                {
                    "error": f"Unknown strategy {strategy!r}; "
                    f"expected one of {sorted(settings['strategies'])}"
                }
            )
        cache = Path(cache_dir) if cache_dir else gt.DEFAULT_CACHE
        targets = (
            {strategy: settings["strategies"][strategy]} if strategy else settings["strategies"]
        )
        entries: list[dict[str, Any]] = []
        failures: dict[str, str] = {}
        for strat, cfg in targets.items():
            entry, error = gt.run_strategy_isolated(
                strat,
                cfg["symbol"],
                settings,
                cache,
                gt.FRONTEND_STRATEGIES,
                cal_source=cal_source,
                signal_delay_days=signal_delay_days,
            )
            if entry is not None:
                entries.append(entry)
            else:
                failures[strat] = error or "unknown error"
        return json.dumps({"entries": entries, "failures": failures}, indent=2, default=str)

    @mcp.tool()
    def digiquant_validate_slapper_vs_tradingview(
        strategy: str,
        ohlcv_csv: str,
        tv_export_csv: str,
        start_date: str = "2018-01-01",
    ) -> str:
        """Trade-level parity check of a Slapper strategy against a TradingView
        'List of Trades' CSV export (matches entry date + direction; breaks misses
        down by signal family). Returns match counts and the diff lists as JSON.
        """
        import sys

        vd = _validation_dir()
        if vd not in sys.path:
            sys.path.insert(0, vd)
        try:
            from compare_tv import compare
        except ImportError as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        try:
            return json.dumps(
                compare(strategy, ohlcv_csv, tv_export_csv, start_date), indent=2, default=str
            )
        except Exception as exc:  # surface as JSON to the caller
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    @mcp.tool()
    def dashboard_run_policy_replay(
        pair_content_hash: str,
        run_id: str | None = None,
    ) -> str:
        """Register a policy replay run against a stored pair (summary IDs only).

        Recommendation/read only — never activates or promotes production policy.
        """
        from digiquant.dashboard.replay.exposure import PolicyReplayExposureError
        from digiquant.service import service_run_policy_replay

        try:
            summary = service_run_policy_replay(
                pair_content_hash=pair_content_hash,
                run_id=run_id,
            )
        except (LookupError, PolicyReplayExposureError, ValueError) as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        return json.dumps({"ok": True, "data": summary.model_dump(mode="json")}, indent=2)

    @mcp.tool()
    def dashboard_get_policy_replay(run_id: str) -> str:
        """Fetch a policy replay run summary by id (fail closed if unknown)."""
        from digiquant.dashboard.replay.exposure import PolicyReplayExposureError
        from digiquant.service import service_get_policy_replay

        try:
            summary = service_get_policy_replay(run_id)
        except (LookupError, PolicyReplayExposureError, ValueError) as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        return json.dumps({"ok": True, "data": summary.model_dump(mode="json")}, indent=2)

    @mcp.tool()
    def dashboard_get_policy_comparison(comparison_id: str) -> str:
        """Fetch a policy comparison summary (artifact IDs / status only)."""
        from digiquant.dashboard.replay.exposure import PolicyReplayExposureError
        from digiquant.service import service_get_policy_comparison

        try:
            summary = service_get_policy_comparison(comparison_id)
        except (LookupError, PolicyReplayExposureError, ValueError) as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        return json.dumps({"ok": True, "data": summary.model_dump(mode="json")}, indent=2)

    @mcp.tool()
    def dashboard_evaluate_policy_gate(
        comparison_id: str,
        criteria_version_id: str,
    ) -> str:
        """Evaluate immutable gate criteria (eligibility only — never activates)."""
        from digiquant.dashboard.replay.exposure import PolicyReplayExposureError
        from digiquant.service import service_evaluate_policy_gate

        try:
            summary = service_evaluate_policy_gate(
                comparison_id=comparison_id,
                criteria_version_id=criteria_version_id,
            )
        except (LookupError, PolicyReplayExposureError, ValueError) as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        return json.dumps({"ok": True, "data": summary.model_dump(mode="json")}, indent=2)

    @mcp.tool()
    def dashboard_get_policy_gate_evaluation(evaluation_id: str) -> str:
        """Fetch a gate-evaluation summary by id (fail closed if unknown)."""
        from digiquant.dashboard.replay.exposure import PolicyReplayExposureError
        from digiquant.service import service_get_policy_gate_evaluation

        try:
            summary = service_get_policy_gate_evaluation(evaluation_id)
        except (LookupError, PolicyReplayExposureError, ValueError) as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        return json.dumps({"ok": True, "data": summary.model_dump(mode="json")}, indent=2)

    return mcp


def run_mcp(
    transport: str = "streamable-http",
    host: str = "127.0.0.1",
    port: int = 8767,
) -> None:
    mcp = create_mcp_server()
    logger.info("Starting digiquant MCP server on %s:%d (transport=%s)", host, port, transport)
    mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(description="digiquant MCP server")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport (Claude Desktop)")
    parser.add_argument("--host", default=os.environ.get("DIGIQUANT_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("DIGIQUANT_MCP_PORT", "8767"))
    )
    args = parser.parse_args()
    transport = "stdio" if args.stdio else "streamable-http"
    run_mcp(transport=transport, host=args.host, port=args.port)
