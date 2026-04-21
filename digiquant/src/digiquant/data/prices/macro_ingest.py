"""Macro time-series ingestion — FRED, Frankfurter FX, crypto Fear & Greed.

Consolidates four Atlas scripts:

* ``ingest_fred.py`` → :func:`fetch_fred`
* ``ingest_fx_frankfurter.py`` → :func:`fetch_frankfurter`
* ``ingest_crypto_fng.py`` → :func:`fetch_crypto_fng`
* ``scripts/lib/macro_ingest.py`` helpers → private in this module

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
from typing import Any

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRANKFURTER_BASE = "https://api.frankfurter.app"
FNG_URL = "https://api.alternative.me/fng/"

FRED_OVERLAP_DAYS = 14
FRANKFURTER_OVERLAP_DAYS = 7


@dataclass(frozen=True)
class MacroManifest:
    """Parsed macro series manifest (YAML-equivalent)."""

    fred_series: list[dict[str, Any]]
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
        return cls(
            fred_series=list(fred.get("series") or []),
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


# ─── FRED ───────────────────────────────────────────────────────────────────


def fetch_fred_series(
    api_key: str,
    series_id: str,
    observation_start: str,
    observation_end: str | None = None,
    *,
    timeout: float = 120.0,
) -> list[dict[str, Any]]:
    """Single-series FRED observations fetch. Returns raw observation dicts."""
    import requests  # type: ignore[import-not-found]

    params: dict[str, Any] = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
    }
    if observation_end:
        params["observation_end"] = observation_end
    r = requests.get(FRED_OBS_URL, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json().get("observations") or []


def fred_observations_to_rows(
    series_id: str,
    unit: str | None,
    title: str | None,
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for obs in observations:
        d = obs.get("date")
        raw = obs.get("value")
        if not d or raw in (None, ".", ""):
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        meta: dict[str, Any] = {}
        if title:
            meta["title"] = title
        if rs := obs.get("realtime_start"):
            meta["realtime_start"] = rs
        row: dict[str, Any] = {
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
) -> list[dict[str, Any]]:
    """Fetch all FRED series in ``manifest`` and return unified observation rows."""
    if not api_key:
        raise ValueError("fetch_fred requires api_key")
    rows: list[dict[str, Any]] = []
    end_s = end or date.today().isoformat()
    for item in manifest.fred_series:
        if not isinstance(item, dict):
            continue
        sid = item.get("id")
        if not sid or (only_series and sid != only_series):
            continue
        start_s = start or manifest.fred_backfill_start
        observations = fetch_fred_series(api_key, sid, start_s, end_s)
        rows.extend(
            fred_observations_to_rows(sid, item.get("unit"), item.get("title"), observations)
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
) -> dict[str, Any]:
    import requests  # type: ignore[import-not-found]

    url = f"{FRANKFURTER_BASE}/{start}..{end}"
    r = requests.get(url, params={"from": base, "to": ",".join(symbols)}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def frankfurter_payload_to_rows(
    payload: dict[str, Any],
    base: str,
    symbols: list[str],
    date_min: str,
    date_max: str,
) -> list[dict[str, Any]]:
    rates = payload.get("rates") or {}
    rows: list[dict[str, Any]] = []
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
            rows.append(
                {
                    "source": "frankfurter",
                    "series_id": f"FX/{sym}",
                    "obs_date": obs_date,
                    "value": val,
                    "unit": "fx",
                    "meta": {"base": base, "quote": sym},
                }
            )
    return rows


def fetch_frankfurter(
    manifest: MacroManifest,
    *,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    end_d = date.fromisoformat((end or date.today().isoformat())[:10])
    start_d = date.fromisoformat((start or manifest.frankfurter_backfill_start)[:10])
    if start_d > end_d:
        return []
    rows: list[dict[str, Any]] = []
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


# ─── Crypto Fear & Greed ───────────────────────────────────────────────────


def fetch_fng_raw(limit: int, *, timeout: float = 60.0) -> list[dict[str, Any]]:
    import requests  # type: ignore[import-not-found]

    r = requests.get(FNG_URL, params={"limit": limit}, timeout=timeout)
    r.raise_for_status()
    data = r.json().get("data")
    return data if isinstance(data, list) else []


def fng_entries_to_rows(
    entries: list[dict[str, Any]], series_value_id: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
        meta: dict[str, Any] = {}
        if (cls := item.get("value_classification")) and isinstance(cls, str):
            meta["classification"] = cls
        row: dict[str, Any] = {
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


def fetch_crypto_fng(manifest: MacroManifest, *, backfill: bool = False) -> list[dict[str, Any]]:
    limit = manifest.fng_backfill_limit if backfill else 30
    entries = fetch_fng_raw(limit)
    return fng_entries_to_rows(entries, manifest.fng_series_id)


def dedupe_observation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Last-wins per (source, series_id, obs_date) — matches the Atlas helper."""
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        key = (
            str(r.get("source", "")),
            str(r.get("series_id", "")),
            str(r.get("obs_date", ""))[:10],
        )
        out[key] = r
    return list(out.values())


__all__ = [
    "FRED_OBS_URL",
    "FRANKFURTER_BASE",
    "FNG_URL",
    "MacroManifest",
    "dedupe_observation_rows",
    "fetch_crypto_fng",
    "fetch_fng_raw",
    "fetch_frankfurter",
    "fetch_frankfurter_range",
    "fetch_fred",
    "fetch_fred_series",
    "fng_entries_to_rows",
    "frankfurter_payload_to_rows",
    "fred_observations_to_rows",
]
