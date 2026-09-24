"""Daily R2 refresh: vendor live overlap -> new immutable generations (#3780).

Cron entry point (``pipeline-market-data-refresh.yml``, 13:00 UTC): fetch the
latest bars (yfinance for prices, FRED/Yahoo-FX for macro), compare each
dataset's sealed overlap against its R2 generation via
:func:`overlap_hash`, and write a NEW generation only when data moved:

* sealed overlap differs (vendor restatement) -> ``full-repull``: re-fetch
  the full series and rewrite the generation;
* sealed overlap matches but new bars exist -> ``incremental`` merge via
  :func:`merge_history_live` (settled-close: the live ``as_of`` bar is
  dropped unless ``--sealed``);
* nothing new -> ``up-to-date`` (no write; the cron is idempotent).

Fail-soft serving, loud alerting (read-path decision recorded here): a
per-ticker fetch error-entry (``fetch_batch`` reports it in
``FetchResult.errors`` and raises nothing) keeps serving the previous
generation (``history-only``), marks ``manifest.stale=true``, and exits
non-zero so the workflow failure alerts. Unexpected exceptions become an
``error`` outcome the same way. One ticker's failure never aborts the rest
of the universe; outcomes are recorded per ticker and the manifest is still
written for the datasets that succeeded.

Registry conflicts (same key, different bytes) re-pull and recompute exactly
once. A recompute that lands on the same ``as_of`` with different bytes is a
same-day vendor restatement (#4621): it is sealed under a NEW immutable
content-hash key (``{as_of}--{sha12}.parquet``) and the ``latest`` pointer
flips to it, so the existing generation is never overwritten and the cron
stays green. Only a restatement put that itself conflicts is reported as an
``error``. R2 generations are immutable.

Dataset ids follow the Task 5 backfill exactly: normalized tickers for
prices (``SPY``), ``{source}__{series}`` lowercased-source for macro
(``fred__DGS10``). Writes go through the backfill's ``R2StoreAdapter`` so
the manifest entry shape stays identical. (The brief names the price fetcher
``download_ohlcv_batch``; the real adapter is ``fetch_batch`` in
``digiquant.data.prices.fetchers`` — used here.)

Exit codes: 0 fresh, 1 stale (gate refused or any ticker history-only/error),
SystemExit message on missing credentials/URIs (fail closed, like backfill).

Core macro mirror (#3780): the writers-stop paused the Supabase macro writers,
but ``macro_series_observations`` is a carve-out table still read directly by
twelve-x (Yahoo FX pair series). When core Supabase creds are present the
refresh mirrors the sealed Yahoo FX R2 generations back into that table
(:func:`mirror_macro_to_core`, fail-soft) so the carve-out keeps flowing.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable  # score:allow untyped any — R2 JSON + callbacks

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.data.prices.merge import (  # noqa: E402
    apply_settled_close,
    canonical_date,
    merge_history_live,
    overlap_hash,
)
from digiquant.data.prices.r2_history import (  # noqa: E402
    SOURCE_TABLE_MACRO,
    SOURCE_TABLE_PRICE,
    R2HistoryStore,
    build_manifest,
    generation_key,
    generation_restatement_key,
    latest_pointer_key,
    macro_key,
    macro_latest_pointer_key,
    macro_restatement_key,
    normalize_ticker,
)
from digiquant.data.prices.refresh_gate import staleness_gate  # noqa: E402
from digiquant.ops.checkpoint_archive import (  # noqa: E402
    R2_ACCESS_KEY_ENV,
    R2_ACCOUNT_ENV,
    R2_BUCKET_ENV,
    R2_SECRET_KEY_ENV,
    ArchiveVerifyError,
    R2Backend,
)

MODE_FULL_REPULL = "full-repull"
MODE_INCREMENTAL = "incremental"
MODE_UP_TO_DATE = "up-to-date"
MODE_HISTORY_ONLY = "history-only"
MODE_ERROR = "error"

_SOFT_FAIL_MODES = frozenset({MODE_HISTORY_ONLY, MODE_ERROR})

LIVE_WINDOW_DAYS = 45
# The live fetch window must span at least one publication period of the series
# (#4588). LIVE_WINDOW_DAYS assumes a series that publishes inside 45 days; for a
# monthly series the newest observation can legitimately sit ~90 days behind the
# run (release lag plus the pending release), so the 45-day window came back empty
# and the run was marked stale. Widening the window makes the fetch *non-empty*
# (it contains the seal row) so the existing up-to-date path covers it; an empty
# window is still a soft fail, since a dead feed looks the same as a slow one.
#
# Only ``monthly``/``quarterly`` actually widen: a weekly seal is at most ~7 days
# old, so the 45-day default already spans several publications, and widening it
# would only raise the age at which a dead weekly feed is noticed.
_CADENCE_WINDOW_DAYS: dict[str, int] = {
    "daily": LIVE_WINDOW_DAYS,
    "weekly": LIVE_WINDOW_DAYS,
    "monthly": 120,
    "quarterly": 240,
}
FULL_HISTORY_START = "1990-01-01"
PRICE_VALUE_COLS = ("open", "high", "low", "close", "volume")
MACRO_VALUE_COLS = ("obs_date", "value")
# Backfill macro generations carry exactly these columns (Task 5 writes the
# direct-PG SELECT of source,series_id,obs_date,value,unit — no meta).
MACRO_COLUMNS = ("source", "series_id", "obs_date", "value", "unit")
POSTGRES_URI_ENV = "CORE_POSTGRES_URI"
FRED_API_KEY_ENV = "FRED_API_KEY"
# Core Supabase REST creds for the macro mirror (same names the digiquant
# prices workflow already uses, with the legacy fallbacks).
CORE_SUPABASE_URL_ENV = "CORE_SUPABASE_URL"
CORE_SUPABASE_SERVICE_KEY_ENV = "CORE_SUPABASE_SERVICE_KEY"
SUPABASE_URL_FALLBACK_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_KEY_FALLBACK_ENV = "SUPABASE_SERVICE_ROLE_KEY"
# Sources whose sealed R2 generations must ALSO land in core
# ``macro_series_observations`` because a core-only reader still consumes them.
# The #3780 writers-stop paused every Supabase macro writer on the premise that
# no production reader remained; that premise missed twelve-x, whose
# ``fx_rates.py`` reads the Yahoo FX pair series (``FX/EUR`` … ``FX/CHF``,
# ``source="yahoo"``) straight from core ``macro_series_observations``. FRED is
# deliberately excluded: its core readers moved to R2, so re-writing it would
# resurrect a path that was retired on purpose.
CORE_MIRROR_MACRO_SOURCES = frozenset({"yahoo"})


def _sibling(name: str) -> Any:
    """Load a sibling script by file location (works run-as-script and in tests)."""
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    import importlib.util

    path = Path(__file__).resolve().with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load sibling script {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_backfill = _sibling("backfill_market_data_r2")


class FetchError(ValueError):
    """A per-dataset vendor failure that raised no exception (fail-soft).

    Wraps ``fetch_batch`` error-entries (``FetchResult.errors``) and empty
    live windows: the refresh keeps serving history for this dataset and
    records a ``history-only`` outcome instead of aborting the universe.
    """

    def __init__(self, target: str, detail: str) -> None:
        super().__init__(f"{target}: {detail}")
        self.target = target
        self.detail = detail


class _ConflictUnresolved(RuntimeError):
    """Re-pulled bytes still land on the conflicted key: do not re-put."""


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _shift_days(day: str, delta: int) -> str:
    base = datetime.fromisoformat(day[:10]).date()
    return (base + timedelta(days=delta)).isoformat()


def _outcome(
    name: str, mode: str, *, as_of: str = "", rows: int = 0, note: str = ""
) -> dict[str, Any]:
    return {"ticker": name, "mode": mode, "as_of": as_of, "rows": rows, "note": note}


def _max_date(frame: pl.DataFrame | None, col: str) -> str:
    if frame is None or frame.is_empty() or col not in frame.columns:
        return ""
    top = frame.select(pl.col(col).cast(pl.Date).max()).item()
    return str(top) if top is not None else ""


# -- frame normalization ----------------------------------------------------


def _normalize_live_frame(raw: pl.DataFrame, ticker: str) -> pl.DataFrame:
    """Project a ``fetch_batch`` frame onto the history schema (date-keyed).

    Renames ``timestamp``/``symbol`` to ``date``/``ticker``, coerces numerics
    (NaN -> null so vendor NaNs never false-positive a restatement), casts
    the date column, and sorts. Missing-date frames come back empty.
    """
    renames = {}
    if "timestamp" in raw.columns:
        renames["timestamp"] = "date"
    if "symbol" in raw.columns:
        renames["symbol"] = "ticker"
    frame = raw.rename(renames) if renames else raw
    if "date" not in frame.columns:
        raise FetchError(ticker, "live frame has no date column")
    if "ticker" not in frame.columns:
        frame = frame.with_columns(pl.lit(ticker).alias("ticker"))
    frame = frame.with_columns(pl.col("date").cast(pl.Date)).drop_nulls("date")
    for col in ("open", "high", "low", "close"):
        if col in frame.columns:
            frame = frame.with_columns(pl.col(col).fill_nan(None).cast(pl.Float64))
    if "volume" in frame.columns:
        frame = frame.with_columns(pl.col("volume").fill_nan(None).cast(pl.Int64))
    # Column alignment to history happens in _align_live; dtype parity is forced
    # above so vendor NaN/dtype drift cannot false-positive a restatement.
    return canonical_date(frame) if not frame.is_empty() else frame.clear()


def _align_live(hist: pl.DataFrame, live: pl.DataFrame) -> pl.DataFrame:
    """Select the history columns from *live* (missing -> null, extras dropped)."""
    out = live
    for col in hist.columns:
        if col not in out.columns and col != "date":
            out = out.with_columns(pl.lit(None).cast(hist.schema[col]).alias(col))
    return out.select(hist.columns).sort("date")


def _sealed_overlap(
    hist: pl.DataFrame, live: pl.DataFrame, seal: str, value_cols: tuple[str, ...]
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Sealed-date rows present on BOTH sides, projected to *value_cols*."""
    seal_d = pl.lit(seal).cast(pl.Date)
    dates = set(hist.filter(pl.col("date") <= seal_d)["date"].to_list()) & set(
        live.filter(pl.col("date") <= seal_d)["date"].to_list()
    )
    if not dates:
        empty = hist.clear().select(["date", *[c for c in value_cols if c != "date"]])
        return empty, empty.clone()
    cols = ["date", *[c for c in value_cols if c in hist.columns and c != "date"]]
    h = hist.filter(pl.col("date").is_in(sorted(dates))).select(cols).sort("date")
    live_overlap = live.filter(pl.col("date").is_in(sorted(dates))).select(cols).sort("date")
    return h, live_overlap


def _restated(
    hist: pl.DataFrame, live: pl.DataFrame, seal: str, value_cols: tuple[str, ...]
) -> bool:
    """True when the vendor rewrote sealed history (overlap hashes differ)."""
    if not seal:
        return False
    h, live_overlap = _sealed_overlap(hist, live, seal, value_cols)
    if h.is_empty():
        return False
    return overlap_hash(h) != overlap_hash(live_overlap)


def _settle(frame: pl.DataFrame, run: str, sealed: bool) -> pl.DataFrame:
    """The cron's own freshness computation: settled-close as-is (Task 3).

    Thin wrapper over :func:`apply_settled_close` — the live ``run``-dated
    bar is excluded unless the close has settled (``sealed``).
    """
    if sealed or frame.is_empty():
        return frame
    return apply_settled_close(frame, run, sealed)


# -- price refresh ----------------------------------------------------------


def _put_price(store: Any, ticker: str, frame: pl.DataFrame, as_of: str) -> str:
    """Write one price generation + swap the latest pointer; return the key."""
    norm = normalize_ticker(ticker)
    key = generation_key(ticker, as_of)
    payload = _backfill.to_parquet_bytes(frame.to_dicts(), date_col="date")
    store.put_generation(
        key,
        payload,
        SOURCE_TABLE_PRICE,
        {"ticker": norm, "as_of": as_of},
        rows=frame.height,
    )
    store.swap_latest_pointer(latest_pointer_key(ticker), key)
    return key


def _put_price_restatement(store: Any, ticker: str, frame: pl.DataFrame, as_of: str) -> str:
    """Seal a same-``as_of`` price revision under a NEW key + flip the pointer (#4621).

    The base generation key is immutable, so the revised bytes go under a
    content-hash key (:func:`generation_restatement_key`); the old generation
    stays readable under its own registry row. Raises
    :class:`ArchiveVerifyError` when the derived key itself conflicts — the
    caller must report that as an ``error``, never as success.
    """
    norm = normalize_ticker(ticker)
    payload = _backfill.to_parquet_bytes(frame.to_dicts(), date_col="date")
    key = generation_restatement_key(ticker, as_of, hashlib.sha256(payload).hexdigest())
    store.put_generation(
        key,
        payload,
        SOURCE_TABLE_PRICE,
        {"ticker": norm, "as_of": as_of},
        rows=frame.height,
    )
    store.swap_latest_pointer(latest_pointer_key(ticker), key)
    return key


def _full_repull(
    ticker: str, store: Any, run: str, sealed: bool, prior: pl.DataFrame | None
) -> dict[str, Any]:
    """Re-fetch the full series and rewrite the generation (restatement path)."""
    norm = normalize_ticker(ticker)
    prior_as_of = _max_date(prior, "date")
    end = _shift_days(run, 1)
    try:
        full = _settle(
            _normalize_live_frame(store.fetch_live_full(ticker, end), ticker),
            run,
            sealed,
        )
    except FetchError as exc:
        rows = prior.height if prior is not None else 0
        return _outcome(
            norm,
            MODE_HISTORY_ONLY,
            as_of=prior_as_of,
            rows=rows,
            note=f"full re-pull failed, serving history: {exc.detail}",
        )
    except Exception as exc:
        rows = prior.height if prior is not None else 0
        return _outcome(
            norm,
            MODE_ERROR,
            as_of=prior_as_of,
            rows=rows,
            note=f"full re-pull raised: {type(exc).__name__}: {exc}",
        )
    if full.is_empty():
        if prior is None:
            return _outcome(norm, MODE_ERROR, note="bootstrap: empty live window")
        return _outcome(
            norm,
            MODE_HISTORY_ONLY,
            as_of=prior_as_of,
            rows=prior.height,
            note="full re-pull empty, serving history",
        )
    full = full.unique(subset=["date"], keep="last").sort("date")
    top = _max_date(full, "date")

    def _rebuild() -> tuple[str, pl.DataFrame]:
        fresh = (
            _settle(
                _normalize_live_frame(store.fetch_live_full(ticker, end), ticker),
                run,
                sealed,
            )
            .unique(subset=["date"], keep="last")
            .sort("date")
        )
        return _max_date(fresh, "date"), fresh

    try:
        _put_price(store, ticker, full, top)
    except ArchiveVerifyError:
        try:
            top2, fresh = _rebuild()
        except Exception as exc:
            return _outcome(
                norm,
                MODE_ERROR,
                as_of=prior_as_of,
                rows=prior.height if prior is not None else 0,
                note=f"registry conflict, re-pull failed: {exc}",
            )
        if top2 == top:
            # Same-day restatement (#4621): same as_of, different bytes. The
            # base key is immutable, so seal the revision under a NEW
            # content-hash key and flip the pointer instead of erroring.
            try:
                new_key = _put_price_restatement(store, ticker, fresh, top2)
            except ArchiveVerifyError as exc:
                return _outcome(
                    norm,
                    MODE_ERROR,
                    as_of=prior_as_of,
                    rows=prior.height if prior is not None else 0,
                    note=f"registry conflict persists: {exc}",
                )
            return _outcome(
                norm,
                MODE_FULL_REPULL,
                as_of=top2,
                rows=fresh.height,
                note=f"sealed overlap restated (same-day revision {new_key})",
            )
        try:
            _put_price(store, ticker, fresh, top2)
        except ArchiveVerifyError:
            try:
                new_key = _put_price_restatement(store, ticker, fresh, top2)
            except ArchiveVerifyError as exc:
                return _outcome(
                    norm,
                    MODE_ERROR,
                    as_of=prior_as_of,
                    rows=prior.height if prior is not None else 0,
                    note=f"registry conflict persists: {exc}",
                )
            return _outcome(
                norm,
                MODE_FULL_REPULL,
                as_of=top2,
                rows=fresh.height,
                note=f"sealed overlap restated (same-day revision {new_key})",
            )
        top, full = top2, fresh
    return _outcome(
        norm,
        MODE_FULL_REPULL,
        as_of=top,
        rows=full.height,
        note="sealed overlap restated" if prior is not None else "bootstrap",
    )


def refresh_ticker(
    ticker: str,
    store: Any,
    manifest: dict[str, Any] | None = None,
    *,
    as_of: str | None = None,
    sealed: bool = True,
) -> dict[str, Any]:
    """Refresh one ticker: restatement -> full-repull, new bars -> incremental.

    ``store`` provides ``read_history`` / ``fetch_live`` / ``fetch_live_full``
    plus the Task 2 seam (``put_generation`` / ``swap_latest_pointer`` /
    ``existing_generations``). Never raises for data problems: fetch
    error-entries become ``history-only``, unexpected exceptions ``error``.
    """
    norm = normalize_ticker(ticker)
    run = as_of or _today_iso()
    manifest = manifest if manifest is not None else {}
    try:
        hist = store.read_history(ticker)
    except LookupError:
        hist = None
    except Exception as exc:
        return _outcome(norm, MODE_ERROR, note=f"history read failed: {type(exc).__name__}: {exc}")
    if hist is None or hist.is_empty():
        return _full_repull(ticker, store, run, sealed, None)
    seal = _max_date(hist, "date") or str(manifest.get("as_of") or run)
    # The window must reach back over sealed history (restatement check), not
    # just the run date — otherwise a stale cache never overlaps its own seal.
    start, end = _shift_days(min(seal, run), -LIVE_WINDOW_DAYS), _shift_days(run, 1)
    try:
        live = _settle(
            _normalize_live_frame(store.fetch_live(ticker, start, end), ticker),
            run,
            sealed,
        )
    except FetchError as exc:
        return _outcome(
            norm,
            MODE_HISTORY_ONLY,
            as_of=seal,
            rows=hist.height,
            note=f"fetch failed, serving history: {exc.detail}",
        )
    except Exception as exc:
        return _outcome(
            norm,
            MODE_ERROR,
            as_of=seal,
            rows=hist.height,
            note=f"live fetch raised: {type(exc).__name__}: {exc}",
        )
    live = _align_live(hist, live)
    if _restated(hist, live, seal, PRICE_VALUE_COLS):
        return _full_repull(ticker, store, run, sealed, hist)
    merged = merge_history_live(hist, live, seal, run, sealed)
    top = _max_date(merged, "date")
    if not top or top <= seal:
        return _outcome(norm, MODE_UP_TO_DATE, as_of=seal, rows=hist.height, note="no new bars")
    try:
        _put_price(store, ticker, merged, top)
    except ArchiveVerifyError:
        try:
            fresh = _settle(
                _normalize_live_frame(store.fetch_live(ticker, start, end), ticker),
                run,
                sealed,
            )
            merged2 = merge_history_live(hist, _align_live(hist, fresh), seal, run, sealed)
            top2 = _max_date(merged2, "date")
        except Exception as exc:
            return _outcome(
                norm,
                MODE_ERROR,
                as_of=seal,
                rows=hist.height,
                note=f"registry conflict, re-pull failed: {exc}",
            )
        if not top2:
            return _outcome(
                norm,
                MODE_ERROR,
                as_of=seal,
                rows=hist.height,
                note=f"registry conflict for {generation_key(ticker, top)};"
                " kept existing generation",
            )
        if top2 == top:
            # Same-day restatement on the incremental path (#4621): seal the
            # revised bytes under a NEW content-hash key, flip the pointer.
            try:
                new_key = _put_price_restatement(store, ticker, merged2, top2)
            except ArchiveVerifyError as exc:
                return _outcome(
                    norm,
                    MODE_ERROR,
                    as_of=seal,
                    rows=hist.height,
                    note=f"registry conflict persists: {exc}",
                )
            return _outcome(
                norm,
                MODE_INCREMENTAL,
                as_of=top2,
                rows=merged2.height,
                note=f"seal {seal} -> {top2} (same-day revision {new_key})",
            )
        try:
            _put_price(store, ticker, merged2, top2)
        except ArchiveVerifyError:
            try:
                new_key = _put_price_restatement(store, ticker, merged2, top2)
            except ArchiveVerifyError as exc:
                return _outcome(
                    norm,
                    MODE_ERROR,
                    as_of=seal,
                    rows=hist.height,
                    note=f"registry conflict persists: {exc}",
                )
            return _outcome(
                norm,
                MODE_INCREMENTAL,
                as_of=top2,
                rows=merged2.height,
                note=f"seal {seal} -> {top2} (same-day revision {new_key})",
            )
        top, merged = top2, merged2
    return _outcome(
        norm, MODE_INCREMENTAL, as_of=top, rows=merged.height, note=f"seal {seal} -> {top}"
    )


def refresh_universe(
    tickers: list[str],
    store: Any,
    manifest: dict[str, Any] | None = None,
    *,
    as_of: str | None = None,
    sealed: bool = True,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Refresh every ticker; one ticker's failure never aborts the rest."""
    outcomes: list[dict[str, Any]] = []
    for ticker in tickers:
        try:
            outcome = refresh_ticker(ticker, store, manifest, as_of=as_of, sealed=sealed)
        except Exception as exc:  # isolation net: record, continue
            outcome = _outcome(
                normalize_ticker(ticker),
                MODE_ERROR,
                note=f"refresh raised: {type(exc).__name__}: {exc}",
            )
        outcomes.append(outcome)
        if progress is not None:
            progress(f"{outcome['ticker']}: {outcome['mode']} ({outcome['note']})")
    return outcomes


# -- macro refresh ----------------------------------------------------------


def _normalize_macro_rows(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Macro observation dicts -> ``obs_date``-sorted frame (dedupe last-wins).

    Projects onto the backfill macro schema (:data:`MACRO_COLUMNS`): vendor
    rows carry ``meta`` dicts (FRED titles, Yahoo quote conventions) that the
    backfill never wrote, so keeping them would widen refresh generations and
    break the incremental ``pl.concat`` against backfill-shaped history.
    """
    if not rows:
        return pl.DataFrame(
            schema={
                "source": pl.String,
                "series_id": pl.String,
                "obs_date": pl.Date,
                "value": pl.Float64,
            }
        )
    frame = pl.DataFrame(rows)
    if "obs_date" not in frame.columns:
        raise FetchError(str(rows[0].get("series_id", "?")), "no obs_date column")
    frame = (
        frame.with_columns(
            pl.col("obs_date").cast(pl.Date),
            pl.col("value").fill_nan(None).cast(pl.Float64),
        )
        .drop_nulls("obs_date")
        .sort("obs_date")
    )
    key = [c for c in ("obs_date",) if c in frame.columns]
    frame = frame.unique(subset=key, keep="last").sort("obs_date")
    return frame.select([c for c in MACRO_COLUMNS if c in frame.columns])


def _put_macro(store: Any, source: str, series: str, frame: pl.DataFrame, as_of: str) -> str:
    key = macro_key(source, series, as_of)
    payload = _backfill.to_parquet_bytes(frame.to_dicts(), date_col="obs_date")
    store.put_generation(
        key,
        payload,
        SOURCE_TABLE_MACRO,
        {"source": source, "series": series, "as_of": as_of},
        rows=frame.height,
    )
    store.swap_latest_pointer(macro_latest_pointer_key(source, series), key)
    return key


def _put_macro_restatement(
    store: Any, source: str, series: str, frame: pl.DataFrame, as_of: str
) -> str:
    """Seal a same-``as_of`` macro revision under a NEW key + flip the pointer (#4621).

    Macro mirror of :func:`_put_price_restatement`: the base generation key is
    immutable, so revised bytes go under :func:`macro_restatement_key` and the
    old generation stays readable. A conflicting derived key still raises
    :class:`ArchiveVerifyError` for the caller to report as an ``error``.
    """
    payload = _backfill.to_parquet_bytes(frame.to_dicts(), date_col="obs_date")
    key = macro_restatement_key(source, series, as_of, hashlib.sha256(payload).hexdigest())
    store.put_generation(
        key,
        payload,
        SOURCE_TABLE_MACRO,
        {"source": source, "series": series, "as_of": as_of},
        rows=frame.height,
    )
    store.swap_latest_pointer(macro_latest_pointer_key(source, series), key)
    return key


def _yahoo_series_meta() -> dict[str, dict[str, str]]:
    """``series_id`` -> ``{yahoo_symbol, quote_convention}`` for mirror metadata."""
    from digiquant.data.prices.macro_ingest import YAHOO_FX_DEFAULT

    return {
        cfg["series_id"]: {
            "yahoo_symbol": sym,
            "quote_convention": cfg["quote_convention"],
        }
        for sym, cfg in YAHOO_FX_DEFAULT.items()
    }


def core_macro_rows(
    source: str,
    series: str,
    frame: pl.DataFrame,
    *,
    run: str,
    lookback_days: int = LIVE_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Sealed R2 macro frame -> core ``macro_series_observations`` rows (#3780).

    Windowed to ``[run - lookback_days, run]`` so the daily mirror re-writes a
    trailing overlap instead of the whole series — idempotent on the core PK
    ``(source, series_id, obs_date)``. ``lookback_days`` must exceed any gap a
    paused writer can leave, or the mirror cannot heal it; the default is the
    same 45-day horizon the R2 live fetch already uses.
    """
    if frame is None or frame.is_empty() or "obs_date" not in frame.columns:
        return []
    cutoff = (datetime.fromisoformat(run).date() - timedelta(days=lookback_days)).isoformat()
    meta = _yahoo_series_meta().get(series)
    out: list[dict[str, Any]] = []
    for record in frame.iter_rows(named=True):
        obs_date = record.get("obs_date")
        obs_iso = obs_date.isoformat() if hasattr(obs_date, "isoformat") else str(obs_date)[:10]
        if not obs_iso or obs_iso > run or obs_iso < cutoff:
            continue
        raw = record.get("value")
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        row: dict[str, Any] = {
            "source": source,
            "series_id": series,
            "obs_date": obs_iso,
            "value": value,
            "unit": record.get("unit") or "fx",
        }
        if meta is not None:
            row["meta"] = dict(meta)
        out.append(row)
    return out


def build_core_supabase_client() -> Any | None:
    """Core Supabase client from env, or ``None`` when creds are absent."""
    url = (
        os.environ.get(CORE_SUPABASE_URL_ENV, "").strip()
        or os.environ.get(SUPABASE_URL_FALLBACK_ENV, "").strip()
    )
    key = (
        os.environ.get(CORE_SUPABASE_SERVICE_KEY_ENV, "").strip()
        or os.environ.get(SUPABASE_SERVICE_KEY_FALLBACK_ENV, "").strip()
    )
    if not url or not key:
        return None
    from digiquant.data.prices.supabase_writer import build_supabase_client

    return build_supabase_client(url, key)


def mirror_macro_to_core(
    store: Any,
    specs: list[tuple[str, str, str | None]],
    *,
    run: str,
    client: Any | None,
    lookback_days: int = LIVE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Mirror sealed R2 macro generations into core ``macro_series_observations``.

    The #3780 writers-stop paused the Supabase macro writers for every source;
    the carve-out kept ``macro_series_observations`` alive for fedprob/bitview,
    but the Yahoo FX series that twelve-x reads from that same table stopped
    landing. The R2 generation is the source of truth, so mirroring a trailing
    window back into core restores the consumer without touching R2.

    Fail-soft by design: a missing client, an unreadable generation, or an
    upsert error is recorded and never fails the R2 refresh.
    """
    summary: dict[str, Any] = {"rows": 0, "series": 0, "skipped": []}
    targets = [
        (s.lower(), sid) for s, sid, _cadence in specs if s.lower() in CORE_MIRROR_MACRO_SOURCES
    ]
    if client is None or not targets:
        summary["skipped"] = [f"{s}__{sid}: no core client" for s, sid in targets]
        return summary
    from digiquant.data.prices.supabase_writer import upsert_macro_observations

    rows: list[dict[str, Any]] = []
    for source, series in targets:
        try:
            frame = store.read_macro(source, series)
        except Exception as exc:
            summary["skipped"].append(f"{source}__{series}: {type(exc).__name__}")
            continue
        series_rows = core_macro_rows(source, series, frame, run=run, lookback_days=lookback_days)
        if not series_rows:
            summary["skipped"].append(f"{source}__{series}: empty window")
            continue
        rows.extend(series_rows)
        summary["series"] += 1
    if rows:
        result = upsert_macro_observations(client, rows)
        summary["rows"] = result.rows
    return summary


#: Cadences whose empty-window ``history-only`` is benign (#4621). A slow FRED
#: series legitimately publishes nothing for weeks, so an empty fetch window
#: means "nothing to do", not feed death. Daily price tickers — and any
#: ``error`` outcome at any cadence — still fail loud.
SLOW_CADENCES = frozenset({"monthly", "quarterly"})


def _slow_macro_exempt_ids(macro_specs: list[tuple[str, str, str | None]]) -> set[str]:
    """Dataset ids whose ``history-only`` must not mark the run stale (#4621)."""
    return {
        f"{source}__{series}"
        for source, series, cadence in macro_specs
        if str(cadence or "").strip().lower() in SLOW_CADENCES
    }


def _live_window_days(cadence: str | None) -> int:
    """Live fetch window for a series' declared cadence (default: daily, 45d)."""
    if not cadence:
        return LIVE_WINDOW_DAYS
    key = cadence.strip().lower()
    try:
        return _CADENCE_WINDOW_DAYS[key]
    except KeyError:
        raise ValueError(
            f"unknown cadence {cadence!r}; expected one of {sorted(_CADENCE_WINDOW_DAYS)}"
        ) from None


def refresh_macro_series(
    source: str,
    series: str,
    store: Any,
    manifest: dict[str, Any] | None = None,
    *,
    as_of: str | None = None,
    cadence: str | None = None,
) -> dict[str, Any]:
    """Refresh one macro series (FRED revisions use the same restatement rule)."""
    source = source.lower()
    name = f"{source}__{series}"
    run = as_of or _today_iso()
    manifest = manifest if manifest is not None else {}
    try:
        hist = store.read_macro(source, series)
        if "obs_date" in hist.columns:
            hist = hist.with_columns(pl.col("obs_date").cast(pl.Date)).sort("obs_date")
    except LookupError:
        hist = None
    except Exception as exc:
        return _outcome(name, MODE_ERROR, note=f"history read failed: {type(exc).__name__}: {exc}")
    seal = _max_date(hist, "obs_date") or str(manifest.get("as_of") or run)
    start, end = _shift_days(run, -_live_window_days(cadence)), _shift_days(run, 1)

    def _fetch_full() -> pl.DataFrame:
        rows = store.fetch_macro_full(source, series, end)
        if not rows:
            raise FetchError(name, "empty full-window observations")
        # Macro settled-close: never carry an observation dated after the run.
        return _normalize_macro_rows(rows).filter(pl.col("obs_date") <= pl.lit(run).cast(pl.Date))

    if hist is None or hist.is_empty():
        try:
            full = _fetch_full()
        except FetchError as exc:
            return _outcome(name, MODE_HISTORY_ONLY, note=str(exc))
        except Exception as exc:
            return _outcome(
                name, MODE_ERROR, note=f"full re-pull raised: {type(exc).__name__}: {exc}"
            )
        top = _max_date(full, "obs_date")
        _put_macro(store, source, series, full, top)
        return _outcome(name, MODE_FULL_REPULL, as_of=top, rows=full.height, note="bootstrap")
    try:
        rows = store.fetch_macro(source, series, start, end)
    except FetchError as exc:
        return _outcome(
            name,
            MODE_HISTORY_ONLY,
            as_of=seal,
            rows=hist.height,
            note=f"fetch failed, serving history: {exc.detail}",
        )
    except Exception as exc:
        return _outcome(
            name,
            MODE_ERROR,
            as_of=seal,
            rows=hist.height,
            note=f"live fetch raised: {type(exc).__name__}: {exc}",
        )
    if not rows:
        return _outcome(
            name,
            MODE_HISTORY_ONLY,
            as_of=seal,
            rows=hist.height,
            note="empty live window, serving history",
        )
    live = _normalize_macro_rows(rows).filter(pl.col("obs_date") <= pl.lit(run).cast(pl.Date))
    if _restated(
        hist.rename({"obs_date": "date"}) if "date" not in hist.columns else hist,
        live.rename({"obs_date": "date"}),
        seal,
        ("value",),
    ):
        try:
            full = _fetch_full()
        except FetchError as exc:
            return _outcome(
                name,
                MODE_HISTORY_ONLY,
                as_of=seal,
                rows=hist.height,
                note=f"restated but re-pull failed: {exc.detail}",
            )
        except Exception as exc:
            return _outcome(
                name,
                MODE_ERROR,
                as_of=seal,
                rows=hist.height,
                note=f"restated but re-pull raised: {exc}",
            )
        top = _max_date(full, "obs_date")
        try:
            _put_macro(store, source, series, full, top)
        except ArchiveVerifyError:
            try:
                fresh = _fetch_full()
            except Exception as exc:
                return _outcome(
                    name,
                    MODE_ERROR,
                    as_of=seal,
                    rows=hist.height,
                    note=f"registry conflict, re-pull failed: {exc}",
                )
            top2 = _max_date(fresh, "obs_date")
            if not top2:
                return _outcome(
                    name,
                    MODE_ERROR,
                    as_of=seal,
                    rows=hist.height,
                    note=f"registry conflict for {macro_key(source, series, top)};"
                    " kept existing generation",
                )
            if top2 == top:
                # Same-day macro restatement (#4621): seal under a NEW
                # content-hash key and flip the pointer instead of erroring.
                try:
                    new_key = _put_macro_restatement(store, source, series, fresh, top2)
                except ArchiveVerifyError as exc:
                    return _outcome(
                        name,
                        MODE_ERROR,
                        as_of=seal,
                        rows=hist.height,
                        note=f"registry conflict persists: {exc}",
                    )
                return _outcome(
                    name,
                    MODE_FULL_REPULL,
                    as_of=top2,
                    rows=fresh.height,
                    note=f"sealed overlap restated (same-day revision {new_key})",
                )
            try:
                _put_macro(store, source, series, fresh, top2)
            except ArchiveVerifyError:
                try:
                    new_key = _put_macro_restatement(store, source, series, fresh, top2)
                except ArchiveVerifyError as exc:
                    return _outcome(
                        name,
                        MODE_ERROR,
                        as_of=seal,
                        rows=hist.height,
                        note=f"registry conflict persists: {exc}",
                    )
                return _outcome(
                    name,
                    MODE_FULL_REPULL,
                    as_of=top2,
                    rows=fresh.height,
                    note=f"sealed overlap restated (same-day revision {new_key})",
                )
            top, full = top2, fresh
        return _outcome(
            name, MODE_FULL_REPULL, as_of=top, rows=full.height, note="sealed overlap restated"
        )
    seal_d = pl.lit(seal).cast(pl.Date)
    new_rows = live.filter(pl.col("obs_date") > seal_d)
    if new_rows.is_empty():
        return _outcome(
            name, MODE_UP_TO_DATE, as_of=seal, rows=hist.height, note="no new observations"
        )
    merged = pl.concat([hist, new_rows]).unique(subset=["obs_date"], keep="last").sort("obs_date")
    top = _max_date(merged, "obs_date")
    try:
        _put_macro(store, source, series, merged, top)
    except ArchiveVerifyError:
        # Same-day macro restatement on the incremental path (#4621): seal the
        # revised bytes under a NEW content-hash key, flip the pointer. A
        # conflicting derived key stays a loud error, never silent success.
        try:
            new_key = _put_macro_restatement(store, source, series, merged, top)
        except ArchiveVerifyError as exc:
            return _outcome(
                name,
                MODE_ERROR,
                as_of=seal,
                rows=hist.height,
                note=f"registry conflict, kept existing: {exc}",
            )
        return _outcome(
            name,
            MODE_INCREMENTAL,
            as_of=top,
            rows=merged.height,
            note=f"seal {seal} -> {top} (same-day revision {new_key})",
        )
    return _outcome(
        name, MODE_INCREMENTAL, as_of=top, rows=merged.height, note=f"seal {seal} -> {top}"
    )


# -- production store (R2 + vendor fetch seams) ------------------------------


class RefreshStore(_backfill.R2StoreAdapter):
    """Backfill adapter + read/fetch seams for the refresh cron.

    Write side (``put_generation`` dataset registration, ``existing_``
    ``generations``, pointer swaps) is inherited unchanged so manifest
    entries keep the Task 5 shape.
    """

    @property
    def manifest(self) -> dict[str, Any]:
        return self._manifest

    def write_manifest(self, manifest: dict[str, Any]) -> str:
        return self._store.write_manifest(manifest)

    def _parquet_frame(self, payload: bytes, date_col: str) -> pl.DataFrame:
        frame = pl.read_parquet(io.BytesIO(payload))
        if date_col not in frame.columns:
            alt = "timestamp" if date_col == "date" else "date"
            if alt in frame.columns:
                frame = frame.rename({alt: date_col})
        return frame.with_columns(pl.col(date_col).cast(pl.Date)).sort(date_col)

    def read_history(self, ticker: str) -> pl.DataFrame:
        datasets = self._manifest.get("datasets") or {}
        entry = datasets.get(ticker) or datasets.get(normalize_ticker(ticker))
        if entry is not None:
            return self._parquet_frame(
                self._store.get_generation(str(entry["object"]), str(entry["sha256"])),
                "date",
            )
        try:
            gen_key = self._store.read_latest(latest_pointer_key(ticker))
        except Exception:
            raise LookupError(f"unknown ticker {ticker!r}") from None
        sha = next(
            (
                c.get("sha256")
                for c in datasets.values()
                if isinstance(c, dict) and c.get("object") == gen_key
            ),
            None,
        )
        if sha is None:
            raise LookupError(f"unknown ticker {ticker!r}")
        return self._parquet_frame(self._store.get_generation(gen_key, str(sha)), "date")

    def read_macro(self, source: str, series: str) -> pl.DataFrame:
        source = source.lower()
        datasets = self._manifest.get("datasets") or {}
        entry = datasets.get(f"{source}__{series}")
        if entry is not None:
            return self._parquet_frame(
                self._store.get_generation(str(entry["object"]), str(entry["sha256"])),
                "obs_date",
            )
        try:
            gen_key = self._store.read_latest(macro_latest_pointer_key(source, series))
        except Exception:
            raise LookupError(f"unknown macro {source}/{series}") from None
        sha = next(
            (
                c.get("sha256")
                for c in datasets.values()
                if isinstance(c, dict) and c.get("object") == gen_key
            ),
            None,
        )
        if sha is None:
            raise LookupError(f"unknown macro {source}/{series}")
        return self._parquet_frame(self._store.get_generation(gen_key, str(sha)), "obs_date")

    def fetch_live(self, ticker: str, start: str, end: str) -> pl.DataFrame:
        from digiquant.data.prices.fetchers import fetch_batch

        res = fetch_batch([ticker], start=start, end=end)
        if ticker in res.errors and ticker not in res.frames:
            raise FetchError(ticker, res.errors[ticker])
        frame = res.frames.get(ticker)
        if frame is None or frame.is_empty():
            raise FetchError(ticker, "empty live window")
        return frame

    def fetch_live_full(self, ticker: str, end: str) -> pl.DataFrame:
        from digiquant.data.prices.fetchers import fetch_batch

        res = fetch_batch([ticker], start=FULL_HISTORY_START, end=end)
        if ticker in res.errors and ticker not in res.frames:
            raise FetchError(ticker, res.errors[ticker])
        frame = res.frames.get(ticker)
        if frame is None or frame.is_empty():
            raise FetchError(ticker, "empty full-window fetch")
        return frame

    def fetch_macro(self, source: str, series: str, start: str, end: str) -> list[dict[str, Any]]:
        return self._fetch_macro(source, series, start, end)

    def fetch_macro_full(self, source: str, series: str, end: str) -> list[dict[str, Any]]:
        return self._fetch_macro(source, series, FULL_HISTORY_START, end)

    def _fetch_macro(self, source: str, series: str, start: str, end: str) -> list[dict[str, Any]]:
        if source == "fred":
            api_key = os.environ.get(FRED_API_KEY_ENV, "").strip()
            if not api_key:
                raise FetchError(f"{source}__{series}", f"missing {FRED_API_KEY_ENV}")
            from digiquant.data.prices.macro_ingest import MacroManifest, fetch_fred

            manifest = MacroManifest(fred_series=[{"id": series}], fred_backfill_start=start)
            rows = fetch_fred(manifest, api_key, start=start, end=end, only_series=series)
        elif source == "yahoo":
            from digiquant.data.prices.macro_ingest import (
                YAHOO_FX_DEFAULT,
                fetch_fx_yahoo,
            )

            by_series = {cfg["series_id"]: sym for sym, cfg in YAHOO_FX_DEFAULT.items()}
            symbol = by_series.get(series)
            if symbol is None:
                raise FetchError(f"{source}__{series}", "unknown yahoo series")
            rows = [
                r
                for r in fetch_fx_yahoo(
                    start=start, end=end, symbols={symbol: YAHOO_FX_DEFAULT[symbol]}
                )
                if r.get("series_id") == series
            ]
        else:
            raise FetchError(f"{source}__{series}", f"unknown macro source {source!r}")
        if not rows:
            raise FetchError(f"{source}__{series}", "empty live window")
        return rows


def build_store(postgres_uri: str) -> tuple[RefreshStore, dict[str, Any]]:
    """Production store: R2 backend + direct-PG registry + manifest load."""
    account = os.environ.get(R2_ACCOUNT_ENV, "").strip()
    bucket = os.environ.get(R2_BUCKET_ENV, "").strip()
    access = os.environ.get(R2_ACCESS_KEY_ENV, "").strip()
    secret = os.environ.get(R2_SECRET_KEY_ENV, "").strip()
    if not (account and bucket and access and secret):
        raise RuntimeError("missing R2 credentials (R2_ACCOUNT_ID/R2_BUCKET/...)")
    backend = R2Backend(
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        bucket=bucket,
        access_key=access,
        secret_key=secret,
    )
    store = R2HistoryStore(
        backend,
        _backfill._pg_registry_insert(postgres_uri),
        _backfill._pg_registry_lookup(postgres_uri),
    )
    try:
        manifest = store.read_manifest()
    except Exception as exc:
        if not _backfill._is_missing_manifest_error(exc):
            raise
        manifest = build_manifest("1970-01-01", {})
    adapter = RefreshStore(store, manifest)
    return adapter, manifest


def _resolve_macro_specs(
    cli_specs: list[str], manifest_path: str
) -> list[tuple[str, str, str | None]]:
    """``--macro-series SOURCE:SERIES`` or the research manifest + Yahoo FX.

    The third element is the series' native cadence (``None`` means daily), which
    sets the live fetch window in :func:`refresh_macro_series`.
    """
    if cli_specs:
        out: list[tuple[str, str, str | None]] = []
        for spec in cli_specs:
            source, _, series = spec.partition(":")
            if not source or not series:
                raise SystemExit(f"--macro-series expects SOURCE:SERIES, got {spec!r}")
            out.append((source.lower(), series, None))
        return out
    try:
        from digiquant.data.prices.macro_ingest import YAHOO_FX_DEFAULT, MacroManifest

        macro_manifest = MacroManifest.from_yaml(manifest_path)
        fred = [
            ("fred", str(s.get("id")), s.get("cadence"))
            for s in macro_manifest.fred_series
            if s.get("id")
        ]
        yahoo = [("yahoo", cfg["series_id"], None) for cfg in YAHOO_FX_DEFAULT.values()]
        return fred + yahoo
    except Exception as exc:
        print(f"warn: macro manifest unreadable ({exc}); skipping macro refresh")
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--universe", default="digiquant/src/digiquant/research/config/watchlist.md"
    )
    parser.add_argument("--tickers", default="", help="Comma-separated override.")
    parser.add_argument("--macro-series", action="append", default=[])
    parser.add_argument(
        "--skip-macro", action="store_true", help="Price-only refresh (skip FRED/Yahoo-FX series)."
    )
    parser.add_argument(
        "--macro-manifest", default="digiquant/src/digiquant/research/config/macro_series.yaml"
    )
    parser.add_argument(
        "--core-macro-mirror",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Mirror sealed R2 macro generations for core-only readers (Yahoo FX "
            "-> macro_series_observations) when core Supabase creds are set. "
            "#3780. Use --no-core-macro-mirror to disable."
        ),
    )
    parser.add_argument("--postgres-uri", default=os.environ.get(POSTGRES_URI_ENV, ""))
    parser.add_argument("--manifest-out", default="/tmp/market-data-refresh.json")
    parser.add_argument("--as-of", default="", help="Run date YYYY-MM-DD (default today).")
    parser.add_argument(
        "--sealed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep the live as-of bar (daily cron runs after settle).",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from digiquant.data.prices.fetchers import parse_watchlist

    run = args.as_of.strip() or _today_iso()
    if args.tickers.strip():
        universe = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        universe = parse_watchlist(args.universe)
    macro_specs = (
        [] if args.skip_macro else _resolve_macro_specs(args.macro_series, args.macro_manifest)
    )
    print(
        f"universe: {len(universe)} tickers; {len(macro_specs)} macro series;"
        f" run={run} sealed={args.sealed}"
    )

    if args.dry_run:
        for ticker in universe:
            print(f"plan: refresh {normalize_ticker(ticker)}")
        for source, series, _cadence in macro_specs:
            print(f"plan: refresh {source}__{series}")
        return 0
    if not args.postgres_uri:
        raise SystemExit(f"set --postgres-uri or ${POSTGRES_URI_ENV} (direct-PG only)")

    store, manifest = build_store(args.postgres_uri)
    ticker_outcomes = refresh_universe(
        universe, store, manifest, as_of=run, sealed=args.sealed, progress=print
    )
    macro_outcomes = []
    for source, series, cadence in macro_specs:
        try:
            outcome = refresh_macro_series(
                source, series, store, manifest, as_of=run, cadence=cadence
            )
        except Exception as exc:
            outcome = _outcome(
                f"{source}__{series}",
                MODE_ERROR,
                note=f"refresh raised: {type(exc).__name__}: {exc}",
            )
        macro_outcomes.append(outcome)
        print(f"{outcome['ticker']}: {outcome['mode']} ({outcome['note']})")

    mirror: dict[str, Any] = {"rows": 0, "series": 0, "skipped": []}
    if args.core_macro_mirror and macro_specs:
        try:
            mirror = mirror_macro_to_core(
                store, macro_specs, run=run, client=build_core_supabase_client()
            )
        except Exception as exc:
            mirror = {
                "rows": 0,
                "series": 0,
                "skipped": [f"mirror raised: {type(exc).__name__}"],
            }
        note = f"; skipped {', '.join(map(str, mirror['skipped']))}" if mirror["skipped"] else ""
        print(f"core macro mirror: {mirror['rows']} rows / {mirror['series']} series{note}")

    outcomes = ticker_outcomes + macro_outcomes
    datasets = manifest.get("datasets") or {}
    new_as_of = max(
        [str(e.get("as_of", "")) for e in datasets.values() if isinstance(e, dict)]
        + [str(manifest.get("as_of") or run)],
    )
    gate = staleness_gate(new_as_of, run)
    # Cadence-aware stale gate (#4621): a slow series sitting out its release
    # cycle is expected quiet, not an outage. Real feed death — daily price
    # errors/history-only, or any macro error — still fails loud.
    exempt = _slow_macro_exempt_ids(macro_specs)
    failed = [
        o
        for o in outcomes
        if o["mode"] in _SOFT_FAIL_MODES
        and not (o["ticker"] in exempt and o["mode"] == MODE_HISTORY_ONLY)
    ]
    stale = (not gate["ok"]) or bool(failed)
    manifest.update(build_manifest(new_as_of, datasets, stale=stale))
    digest = store.write_manifest(manifest)
    artifact = {
        "as_of": new_as_of,
        "run": run,
        "stale": stale,
        "stale_days": gate["stale_days"],
        "gate": gate,
        "failed": [o["ticker"] for o in failed],
        "outcomes": outcomes,
        "core_macro_mirror": mirror,
        "manifest_sha": digest,
    }
    Path(args.manifest_out).write_text(json.dumps(artifact, indent=2, sort_keys=True))
    print(
        f"refresh done: {len(outcomes)} dataset(s), as_of={new_as_of},"
        f" stale={stale} sha={digest} -> {args.manifest_out}"
    )
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
