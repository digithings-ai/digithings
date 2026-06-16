"""Macro time-series ingestion — FRED, Yahoo FX, Frankfurter FX (legacy), crypto FNG (legacy).

Consolidates four Atlas scripts:

* ``ingest_fred.py`` → :func:`fetch_fred`
* ``ingest_fx_frankfurter.py`` → :func:`fetch_frankfurter` (legacy, opt-in)
* ``ingest_crypto_fng.py`` → :func:`fetch_crypto_fng` (legacy, opt-in)
* ``scripts/lib/macro_ingest.py`` helpers → private in this module

The default daily pipeline pulls FRED + Yahoo FX (:func:`fetch_fx_yahoo`).
:func:`fetch_frankfurter` and :func:`fetch_crypto_fng` remain importable for
explicit opt-in via ``--sources frankfurter,fng`` but are no longer scheduled.

Each fetcher returns a list of row dicts matching the
``macro_series_observations`` Supabase schema exactly:

    {"source": str, "series_id": str, "obs_date": "YYYY-MM-DD",
     "value": float, "unit": str | None, "meta": dict | None}

Callers (CLI / supabase_writer) are responsible for upserting. This separation
keeps the fetchers unit-testable without a Supabase client.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRANKFURTER_BASE = "https://api.frankfurter.app"
FNG_URL = "https://api.alternative.me/fng/"

FRED_OVERLAP_DAYS = 14
FRANKFURTER_OVERLAP_DAYS = 7


class FredSeriesEntry(TypedDict, total=False):
    """One FRED series entry from the macro manifest YAML (SIMP-014)."""

    id: str
    series_id: str
    unit: str | None
    title: str | None


class FredRawObservation(TypedDict, total=False):
    """Single observation dict from the FRED JSON API (SIMP-014)."""

    date: str
    value: str
    realtime_start: str


class MacroObservationMeta(TypedDict, total=False):
    """Optional ``macro_series_observations.meta`` JSON (SIMP-014)."""

    title: str
    realtime_start: str
    base: str
    quote: str
    yahoo_symbol: str
    quote_convention: str
    classification: str
    # Fed rate-probability provenance (#778, fed_probabilities.py).
    event_ticker: str
    strike: float
    strike_type: str
    yes_bid: float | None
    yes_ask: float | None
    question: str
    group_item_threshold: str


class MacroObservation(TypedDict, total=False):
    """One ``macro_series_observations`` row (SIMP-014)."""

    source: str
    series_id: str
    obs_date: str
    value: float
    unit: str | None
    meta: MacroObservationMeta | None


class FrankfurterRatesPayload(TypedDict, total=False):
    """Frankfurter ``/{start}..{end}`` JSON body (SIMP-014)."""

    rates: dict[str, dict[str, float | str]]


class FngApiEntry(TypedDict, total=False):
    """One entry from alternative.me fear/greed API (SIMP-014)."""

    timestamp: str | int
    value: str | float
    value_classification: str


@dataclass(frozen=True)
class MacroManifest:
    """Parsed macro series manifest (YAML-equivalent)."""

    fred_series: list[FredSeriesEntry]
    fred_backfill_start: str
    frankfurter_base: str
    frankfurter_symbols: list[str]
    frankfurter_backfill_start: str
    fng_series_id: str
    fng_backfill_limit: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MacroManifest":
        fred = payload.get("fred") or {}
        ff = payload.get("frankfurter") or {}
        fng = payload.get("crypto_fear_greed") or {}
        raw_series = fred.get("series") or []
        fred_series: list[FredSeriesEntry] = [s for s in raw_series if isinstance(s, dict)]  # type: ignore[misc]
        return cls(
            fred_series=fred_series,
            fred_backfill_start=str(fred.get("backfill_start") or "1990-01-01"),
            frankfurter_base=str(ff.get("base") or "USD"),
            frankfurter_symbols=list(ff.get("symbols") or ["EUR", "GBP", "JPY", "CAD"]),
            frankfurter_backfill_start=str(ff.get("backfill_start") or "1999-01-04"),
            fng_series_id=str(fng.get("series_value_id") or "FNG/value"),
            fng_backfill_limit=int(fng.get("backfill_limit") or 3650),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MacroManifest":
        import yaml  # type: ignore[import-not-found]

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Manifest {path} must be a mapping")
        return cls.from_dict(data)


# ─── HTTP session with retries (shared by all three upstreams) ──────────────


def _retrying_session(
    *,
    total: int = 3,
    backoff_factor: float = 1.5,
) -> Any:
    """``requests.Session`` with retry on 5xx / connection errors / read timeouts.

    Upstream data providers (FRED in particular) occasionally return transient
    5xx. Without retries, a single flake kills the whole daily job. Defaults
    (3 tries, 1.5s exponential backoff) cover a window of roughly 0s → 1.5s →
    4.5s → 10.5s before giving up.
    """
    import requests  # type: ignore[import-not-found]
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff_factor,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s = requests.Session()
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


# Public, stable alias so other ingest modules (e.g. fed_probabilities) don't depend on the
# underscored private name.
retrying_session = _retrying_session


# ─── FRED ───────────────────────────────────────────────────────────────────


def fetch_fred_series(
    api_key: str,
    series_id: str,
    observation_start: str,
    observation_end: str | None = None,
    *,
    timeout: float = 120.0,
    session: Any | None = None,
) -> list[FredRawObservation]:
    """Single-series FRED observations fetch. Returns raw observation dicts."""
    params: dict[str, Any] = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
    }
    if observation_end:
        params["observation_end"] = observation_end
    s = session if session is not None else _retrying_session()
    r = s.get(FRED_OBS_URL, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json().get("observations") or []


def fred_observations_to_rows(
    series_id: str,
    unit: str | None,
    title: str | None,
    observations: list[FredRawObservation],
) -> list[MacroObservation]:
    rows: list[MacroObservation] = []
    for obs in observations:
        d = obs.get("date")
        raw = obs.get("value")
        if not d or raw in (None, ".", ""):
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        meta: MacroObservationMeta = {}
        if title:
            meta["title"] = title
        if rs := obs.get("realtime_start"):
            meta["realtime_start"] = rs
        row: MacroObservation = {
            "source": "fred",
            "series_id": series_id,
            "obs_date": d,
            "value": val,
            "unit": unit,
        }
        if meta:
            row["meta"] = meta
        rows.append(row)
    return rows


def fetch_fred(
    manifest: MacroManifest,
    api_key: str,
    *,
    start: str | None = None,
    end: str | None = None,
    only_series: str | None = None,
) -> list[MacroObservation]:
    """Fetch all FRED series in ``manifest`` and return unified observation rows.

    Per-series error isolation: if one series fails after retries, the remaining
    series continue. Failures are logged to stderr. The run fails only if
    **every** series failed (upstream-down signal) — partial data beats none.
    """
    if not api_key:
        raise ValueError("fetch_fred requires api_key")
    import sys

    import requests  # type: ignore[import-not-found]

    rows: list[MacroObservation] = []
    failed: list[tuple[str, str]] = []
    attempted: list[str] = []
    end_s = end or date.today().isoformat()
    sess = _retrying_session()
    for item in manifest.fred_series:
        if not isinstance(item, dict):
            continue
        sid = item.get("id")
        if not sid or (only_series and sid != only_series):
            continue
        attempted.append(sid)
        start_s = start or manifest.fred_backfill_start
        try:
            observations = fetch_fred_series(api_key, sid, start_s, end_s, session=sess)
        except (requests.RequestException, ValueError) as exc:
            failed.append((sid, str(exc)[:200]))
            print(f"  [fetch_fred] skipped {sid}: {exc}", file=sys.stderr)
            continue
        rows.extend(
            fred_observations_to_rows(sid, item.get("unit"), item.get("title"), observations)
        )
    if attempted and len(failed) == len(attempted):
        detail = "; ".join(f"{sid}: {msg}" for sid, msg in failed[:5])
        raise RuntimeError(
            f"fetch_fred: all {len(attempted)} series failed — upstream likely down. {detail}"
        )
    if failed:
        print(
            f"  [fetch_fred] partial: {len(attempted) - len(failed)}/{len(attempted)} series ok, "
            f"{len(failed)} skipped",
            file=sys.stderr,
        )
    return rows


# ─── Frankfurter (ECB FX) ───────────────────────────────────────────────────


def _iter_year_chunks(start_d: date, end_d: date):
    y = start_d.year
    while True:
        chunk_start = max(start_d, date(y, 1, 1))
        chunk_end = min(end_d, date(y, 12, 31))
        if chunk_start <= chunk_end:
            yield chunk_start.isoformat(), chunk_end.isoformat()
        if chunk_end >= end_d:
            break
        y += 1


def fetch_frankfurter_range(
    start: str,
    end: str,
    base: str,
    symbols: list[str],
    *,
    timeout: float = 120.0,
    session: Any | None = None,
) -> FrankfurterRatesPayload:
    url = f"{FRANKFURTER_BASE}/{start}..{end}"
    s = session if session is not None else _retrying_session()
    r = s.get(url, params={"from": base, "to": ",".join(symbols)}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def frankfurter_payload_to_rows(
    payload: FrankfurterRatesPayload,
    base: str,
    symbols: list[str],
    date_min: str,
    date_max: str,
) -> list[MacroObservation]:
    rates = payload.get("rates") or {}
    rows: list[MacroObservation] = []
    for obs_date, day_rates in sorted(rates.items()):
        if obs_date < date_min or obs_date > date_max:
            continue
        if not isinstance(day_rates, dict):
            continue
        for sym in symbols:
            raw = day_rates.get(sym)
            if raw is None:
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            meta: MacroObservationMeta = {"base": base, "quote": sym}
            rows.append(
                {
                    "source": "frankfurter",
                    "series_id": f"FX/{sym}",
                    "obs_date": obs_date,
                    "value": val,
                    "unit": "fx",
                    "meta": meta,
                }
            )
    return rows


def fetch_frankfurter(
    manifest: MacroManifest,
    *,
    start: str | None = None,
    end: str | None = None,
) -> list[MacroObservation]:
    end_d = date.fromisoformat((end or date.today().isoformat())[:10])
    start_d = date.fromisoformat((start or manifest.frankfurter_backfill_start)[:10])
    if start_d > end_d:
        return []
    rows: list[MacroObservation] = []
    for s, e in _iter_year_chunks(start_d, end_d):
        payload = fetch_frankfurter_range(
            s, e, manifest.frankfurter_base, manifest.frankfurter_symbols
        )
        rows.extend(
            frankfurter_payload_to_rows(
                payload, manifest.frankfurter_base, manifest.frankfurter_symbols, s, e
            )
        )
    return rows


# ─── Yahoo FX (replaces Frankfurter for the default daily pipeline) ─────────

# Default Yahoo FX symbol map → series_id. Yahoo's quote conventions differ:
#   * ``EURUSD=X``  → USD per 1 EUR (e.g. 1.08)
#   * ``GBPUSD=X``  → USD per 1 GBP (e.g. 1.27)
#   * ``JPY=X``     → JPY per 1 USD (e.g. 150)
#   * ``CAD=X``     → CAD per 1 USD (e.g. 1.35)
# We persist Yahoo's native quote unchanged and stamp ``meta.quote_convention``
# so downstream consumers can disambiguate. Skill prompts already speak in the
# natural EUR/USD, GBP/USD, USD/JPY, USD/CAD direction — this matches them.
YAHOO_FX_DEFAULT: dict[str, dict[str, str]] = {
    "EURUSD=X": {"series_id": "FX/EUR", "quote_convention": "USD_per_EUR"},
    "GBPUSD=X": {"series_id": "FX/GBP", "quote_convention": "USD_per_GBP"},
    "JPY=X": {"series_id": "FX/JPY", "quote_convention": "JPY_per_USD"},
    "CAD=X": {"series_id": "FX/CAD", "quote_convention": "CAD_per_USD"},
}


def _yahoo_fx_download(
    yahoo_symbols: list[str],
    *,
    start: str | None,
    end: str | None,
):
    """Boundary helper: call yfinance and return a long-format Polars frame.

    Returns a ``pl.DataFrame`` with columns ``(obs_date, yahoo_symbol, close)``,
    NaN closes already filtered. Split out so tests can monkeypatch this one
    seam without leaking pandas anywhere into the test surface.

    We deliberately do not reuse :func:`_retrying_session` — yfinance manages
    its own HTTP session and retry semantics internally.
    """
    import polars as pl
    import yfinance as yf  # type: ignore[import-not-found]

    empty = pl.DataFrame(
        schema={"obs_date": pl.String, "yahoo_symbol": pl.String, "close": pl.Float64}
    )
    kwargs: dict[str, Any] = {"progress": False, "threads": True, "auto_adjust": False}
    if start:
        kwargs["start"] = start
    if end:
        kwargs["end"] = end
    raw = yf.download(yahoo_symbols, **kwargs)
    if raw is None or getattr(raw, "empty", True):
        return empty
    return _yahoo_fx_pandas_to_long(raw, yahoo_symbols)


def _yahoo_fx_pandas_to_long(raw, yahoo_symbols: list[str]):
    """Convert yfinance's pandas frame to a long-format Polars DataFrame.

    yfinance returns either a column-multiindexed frame (multi-symbol) or a
    flat OHLCV frame (single-symbol). We use the ``Close`` column only —
    FX series are stored as a single per-day reference value.
    """
    import polars as pl

    flat = raw.reset_index()
    cols = list(flat.columns)
    # Detect multi-symbol layout by tuple-typed column labels.
    is_multi = any(isinstance(c, tuple) for c in cols)
    records: list[dict[str, Any]] = []
    n_rows = len(flat)
    for i in range(n_rows):
        ts = flat.iloc[i, 0]
        obs_date = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
        for sym in yahoo_symbols:
            col = ("Close", sym) if is_multi else "Close"
            if col not in cols:
                continue
            raw_val = flat.iloc[i][col]
            try:
                fval = float(raw_val)
            except (TypeError, ValueError):
                continue
            # NaN check without importing pandas — NaN != NaN by definition.
            if fval != fval:
                continue
            records.append({"obs_date": obs_date, "yahoo_symbol": sym, "close": fval})
    if not records:
        return pl.DataFrame(
            schema={"obs_date": pl.String, "yahoo_symbol": pl.String, "close": pl.Float64}
        )
    return pl.DataFrame(records)


def yahoo_fx_payload_to_rows(
    payload,
    yahoo_to_series: dict[str, dict[str, str]],
) -> list[MacroObservation]:
    """Convert a long-format Polars FX frame into ``macro_series_observations`` rows.

    ``payload`` is the ``pl.DataFrame`` returned by :func:`_yahoo_fx_download`
    with columns ``(obs_date, yahoo_symbol, close)``.
    """
    if payload is None or payload.is_empty():
        return []
    rows: list[MacroObservation] = []
    for record in payload.iter_rows(named=True):
        sym = record["yahoo_symbol"]
        cfg = yahoo_to_series.get(sym)
        if cfg is None:
            continue
        meta: MacroObservationMeta = {
            "yahoo_symbol": sym,
            "quote_convention": cfg["quote_convention"],
        }
        rows.append(
            {
                "source": "yahoo",
                "series_id": cfg["series_id"],
                "obs_date": record["obs_date"],
                "value": float(record["close"]),
                "unit": "fx",
                "meta": meta,
            }
        )
    return rows


def fetch_fx_yahoo(
    *,
    start: str | None = None,
    end: str | None = None,
    symbols: dict[str, dict[str, str]] | None = None,
) -> list[MacroObservation]:
    """Fetch daily FX closes from Yahoo Finance.

    Returns ``macro_series_observations`` rows for each symbol in ``symbols``
    (defaults to :data:`YAHOO_FX_DEFAULT` — EUR/USD, GBP/USD, USD/JPY,
    USD/CAD). ``source="yahoo"`` distinguishes these from legacy Frankfurter
    rows so the upsert key ``(source, series_id, obs_date)`` does not collide
    on historical data.

    No FRED-style per-series isolation is needed — yfinance batches all four
    pairs in one HTTP call, so failure modes are all-or-nothing.
    """
    yahoo_to_series = symbols or YAHOO_FX_DEFAULT
    if not yahoo_to_series:
        return []
    payload = _yahoo_fx_download(list(yahoo_to_series.keys()), start=start, end=end)
    return yahoo_fx_payload_to_rows(payload, yahoo_to_series)


# ─── Crypto Fear & Greed ───────────────────────────────────────────────────


def fetch_fng_raw(
    limit: int, *, timeout: float = 60.0, session: Any | None = None
) -> list[FngApiEntry]:
    s = session if session is not None else _retrying_session()
    r = s.get(FNG_URL, params={"limit": limit}, timeout=timeout)
    r.raise_for_status()
    data = r.json().get("data")
    return data if isinstance(data, list) else []


def fng_entries_to_rows(entries: list[FngApiEntry], series_value_id: str) -> list[MacroObservation]:
    rows: list[MacroObservation] = []
    for item in entries:
        try:
            ts = int(item.get("timestamp", 0))
        except (TypeError, ValueError):
            continue
        if ts <= 0:
            continue
        obs_date = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        try:
            val = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        meta: MacroObservationMeta = {}
        if (cls := item.get("value_classification")) and isinstance(cls, str):
            meta["classification"] = cls
        row: MacroObservation = {
            "source": "crypto_fear_greed",
            "series_id": series_value_id,
            "obs_date": obs_date,
            "value": val,
            "unit": "index",
        }
        if meta:
            row["meta"] = meta
        rows.append(row)
    return rows


def fetch_crypto_fng(manifest: MacroManifest, *, backfill: bool = False) -> list[MacroObservation]:
    limit = manifest.fng_backfill_limit if backfill else 30
    entries = fetch_fng_raw(limit)
    return fng_entries_to_rows(entries, manifest.fng_series_id)


def dedupe_observation_rows(rows: list[MacroObservation]) -> list[MacroObservation]:
    """Last-wins per (source, series_id, obs_date) — matches the Atlas helper."""
    out: dict[tuple[str, str, str], MacroObservation] = {}
    for r in rows:
        key = (
            str(r.get("source", "")),
            str(r.get("series_id", "")),
            str(r.get("obs_date", ""))[:10],
        )
        out[key] = r
    return list(out.values())


__all__ = [
    "FNG_URL",
    "FRANKFURTER_BASE",
    "FRED_OBS_URL",
    "YAHOO_FX_DEFAULT",
    "FrankfurterRatesPayload",
    "FredRawObservation",
    "FredSeriesEntry",
    "FngApiEntry",
    "MacroManifest",
    "MacroObservation",
    "MacroObservationMeta",
    "dedupe_observation_rows",
    "fetch_crypto_fng",
    "fetch_fng_raw",
    "fetch_frankfurter",
    "fetch_frankfurter_range",
    "fetch_fred",
    "fetch_fred_series",
    "fetch_fx_yahoo",
    "fng_entries_to_rows",
    "frankfurter_payload_to_rows",
    "fred_observations_to_rows",
    "yahoo_fx_payload_to_rows",
]
