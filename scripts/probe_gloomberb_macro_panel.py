"""Probe the gloomberb macro panel baseline (#4794, PR 1).

For each id in the kept + dropped panel, calls anonymous ``econ_series`` with
``limit=1000``, ``sort_order=desc`` and prints ``id status n oldest newest``.

Exit 0 when every kept id is ``ok`` and every dropped id is ``empty``;
exit 2 on drift (kept id empty or error, or dropped id ``ok``).
Sends no headers, cookies, or keys beyond the client's anonymous defaults.
Do not check in this script's stdout.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from digiquant.data.gloomberb.models import DigifetchError, EconSeriesInput
from digiquant.data.prices.gloomberb_macro import (
    DROPPED_SERIES_IDS,
    KEPT_SERIES_IDS,
    build_ingest_client,
)


@dataclass
class SeriesProbe:
    series_id: str
    status: str  # "ok" | "empty" | "error"
    n: int
    oldest: str | None = None
    newest: str | None = None
    detail: str | None = None


@dataclass
class ProbeResult:
    series: list[SeriesProbe] = field(default_factory=list)
    exit_code: int = 0


def _obs_field(obs: Any, name: str) -> Any:
    if hasattr(obs, name):
        return getattr(obs, name)
    if isinstance(obs, dict):
        return obs.get(name)
    return None


def _probe_one(client: Any, series_id: str) -> SeriesProbe:
    try:
        envelope = client.econ_series(
            EconSeriesInput(series_id=series_id, limit=1000, sort_order="desc")
        )
    except Exception as exc:
        return SeriesProbe(series_id, "error", 0, detail=str(exc)[:200])
    data = _obs_field(envelope, "data")
    if isinstance(data, DigifetchError):
        return SeriesProbe(series_id, "error", 0, detail=f"{data.code}: {data.message}")
    if data is None:
        return SeriesProbe(series_id, "error", 0, detail="no data (code: empty)")
    observations = _obs_field(data, "observations") or []
    dates = sorted(str(_obs_field(obs, "date")) for obs in observations if _obs_field(obs, "date"))
    if not observations:
        return SeriesProbe(series_id, "empty", 0)
    return SeriesProbe(
        series_id,
        "ok",
        len(observations),
        oldest=dates[0] if dates else None,
        newest=dates[-1] if dates else None,
    )


def classify(client: Any) -> ProbeResult:
    """Pure probe over an injected client; ``main`` adds I/O and the exit."""
    rows = [_probe_one(client, sid) for sid in sorted(KEPT_SERIES_IDS | DROPPED_SERIES_IDS)]
    by_id = {row.series_id: row for row in rows}
    drift = any(by_id[sid].status != "ok" for sid in KEPT_SERIES_IDS) or any(
        by_id[sid].status != "empty" for sid in DROPPED_SERIES_IDS
    )
    return ProbeResult(series=rows, exit_code=2 if drift else 0)


def main() -> int:
    client = build_ingest_client()
    try:
        result = classify(client)
    finally:
        client.close()
    for row in result.series:
        print(f"{row.series_id} {row.status} n={row.n} {row.oldest} {row.newest}")
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
