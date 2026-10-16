"""Gloomberb-backed macro panel writer (#4794, PR 2 wired).

Library only: frozen panel sets, per-cadence page limits, observation mapping,
and fetch entry points over an injected ``GloomberbClient``. No R2, no YAML
I/O, no Supabase.

Wired: ``scripts/refresh_market_data_r2.py`` and
``digiquant prices fetch-macro`` seal the kept panel ids from anonymous
``econ_series`` pages (``cache_ttl=0``). Dataset ids (``fred__{SERIES}``)
and the parquet ``source="fred"`` column are unchanged by the swap.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from digiquant.data.gloomberb.client import GloomberbClient
from digiquant.data.gloomberb.models import DigifetchError, EconSeriesInput
from digiquant.data.prices.macro_ingest import MacroManifest, MacroObservation

KEPT_SERIES_IDS: frozenset[str] = frozenset(
    {
        "DGS2",
        "DGS5",
        "DGS10",
        "DGS30",
        "DFF",
        "SOFR",
        "T10Y2Y",
        "T10Y3M",
        "T10YIE",
        "T5YIE",
        "DFII10",
        "T5YIFR",
        "BAMLH0A0HYM2",
        "BAMLC0A0CM",
        "VIXCLS",
        "VXVCLS",
        "DCOILWTICO",
        "M2SL",
        "UNRATE",
        "CPIAUCSL",
        "PCEPI",
        "WALCL",
        "ICSA",
    }
)
DROPPED_SERIES_IDS: frozenset[str] = frozenset(
    {
        "VXNCLS",
        "GVZCLS",
        "OVXCLS",
        "DTWEXBGS",
        "MANEMP",
        "NFCI",
        "STLFSI4",
        "MORTGAGE30US",
    }
)


class GloomberbMacroError(RuntimeError):
    """One series failed (disabled, rate_limited, upstream_error, empty page)."""


def window_limit(cadence: str | None) -> int:
    """Newest-page observation count for a manifest cadence."""
    key = (cadence or "daily").strip().lower()
    try:
        return {"daily": 60, "weekly": 16, "monthly": 8, "quarterly": 4}[key]
    except KeyError:
        raise ValueError(
            f"unknown cadence {cadence!r}; expected daily, weekly, monthly, quarterly"
        ) from None


def _obs_field(obs: Any, name: str) -> Any:
    """Attribute-or-mapping access so models and dict fixtures both work."""
    if hasattr(obs, name):
        return getattr(obs, name)
    if isinstance(obs, dict):
        return obs.get(name)
    return None


def gloomberb_observations_to_rows(
    series_id: str,
    unit: str | None,
    title: str | None,
    observations: list[Any],
) -> list[MacroObservation]:
    """Drop null values and blank dates. source='fred'. meta title only."""
    rows: list[MacroObservation] = []
    for obs in observations:
        date = _obs_field(obs, "date")
        value = _obs_field(obs, "value")
        if not date or value is None:
            continue
        try:
            coerced = float(value)
        except (TypeError, ValueError):
            continue
        row: MacroObservation = {
            "source": "fred",
            "series_id": series_id,
            "obs_date": str(date),
            "value": coerced,
            "unit": unit,
        }
        if title:
            row["meta"] = {"title": title}
        rows.append(row)
    return rows


def fetch_gloomberb_series(
    client: Any,
    series_id: str,
    *,
    unit: str | None,
    title: str | None,
    limit: int,
) -> list[MacroObservation]:
    """One econ_series call, sort_order desc. Raises GloomberbMacroError."""
    envelope = client.econ_series(
        EconSeriesInput(series_id=series_id, limit=limit, sort_order="desc")
    )
    data = _obs_field(envelope, "data")
    if isinstance(data, DigifetchError):
        raise GloomberbMacroError(f"{series_id}: econ_series failed {data.code}: {data.message}")
    if data is None:
        raise GloomberbMacroError(f"{series_id}: econ_series returned no data (code: empty)")
    observations = _obs_field(data, "observations") or []
    if len(observations) == 0:
        raise GloomberbMacroError(f"{series_id}: econ_series returned an empty page")
    return gloomberb_observations_to_rows(series_id, unit, title, observations)


def fetch_gloomberb(
    manifest: MacroManifest,
    client: Any,
    *,
    only_series: str | None = None,
    limit_for: Callable[[str | None], int] = window_limit,
) -> list[MacroObservation]:
    """Walk manifest.fred_series with per-series error isolation.

    A series that fails is skipped; the run fails only when every attempted
    series failed (upstream-down signal) — partial data beats none.
    """
    rows: list[MacroObservation] = []
    failed: list[tuple[str, str]] = []
    attempted: list[str] = []
    for item in manifest.fred_series:
        if not isinstance(item, dict):
            continue
        sid = item.get("id")
        if not sid or (only_series and sid != only_series):
            continue
        attempted.append(sid)
        limit = limit_for(item.get("cadence"))
        try:
            rows.extend(
                fetch_gloomberb_series(
                    client,
                    sid,
                    unit=item.get("unit"),
                    title=item.get("title"),
                    limit=limit,
                )
            )
        except Exception as exc:
            failed.append((sid, str(exc)[:200]))
            print(f"  [fetch_gloomberb] skipped {sid}: {exc}", file=sys.stderr)
            continue
    if attempted and len(failed) == len(attempted):
        detail = "; ".join(f"{sid}: {msg}" for sid, msg in failed[:5])
        raise RuntimeError(
            f"fetch_gloomberb: all {len(attempted)} series failed — upstream likely down. {detail}"
        )
    if failed:
        print(
            f"  [fetch_gloomberb] partial: {len(attempted) - len(failed)}/"
            f"{len(attempted)} series ok, {len(failed)} skipped",
            file=sys.stderr,
        )
    return rows


def build_ingest_client() -> GloomberbClient:
    """Ingest client: caching disabled so a seal never reads a stale envelope."""
    return GloomberbClient(cache_ttl=0)


__all__ = [
    "DROPPED_SERIES_IDS",
    "KEPT_SERIES_IDS",
    "GloomberbMacroError",
    "build_ingest_client",
    "fetch_gloomberb",
    "fetch_gloomberb_series",
    "gloomberb_observations_to_rows",
    "window_limit",
]
