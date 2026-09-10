"""Record pre-cutover Supabase answers as parity goldens. One-time use.

Snapshots the live Supabase market tables (``price_technicals``,
``macro_series_observations``) for the three pinned golden dates and writes
one JSON fixture per date plus ``docs/perf/baseline.json`` (per-tool latency
Task 10's load harness asserts against). Goldens are recorded once and never
regenerated — later tasks diff against these files.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

DATES = ("2024-12-31", "2025-03-15", "2025-08-29")
TICKERS = ("SPY", "QQQ", "AAPL")
SERIES_IDS = ("DGS10", "VIXCLS")
TECHNICALS_LOOKBACK = 20
MACRO_LOOKBACK = 6

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "supabase-answers"
DEFAULT_BASELINE = REPO_ROOT / "docs" / "perf" / "baseline.json"


def record_one(
    ticker: str, as_of: str, fetch: Callable[[str, str], list[dict[str, Any]]]
) -> dict[str, Any]:
    """Wrap one ticker's fetched rows in the golden envelope."""
    return {"ticker": ticker, "as_of": as_of, "rows": fetch(ticker, as_of)}


def _summarize_latency(samples_ms: list[float]) -> dict[str, Any]:
    """p50/p99 summary. n is tiny by design (one sample per golden date)."""
    if not samples_ms:
        return {"n": 0, "p50_ms": None, "p99_ms": None}
    ordered = sorted(samples_ms)
    return {
        "n": len(ordered),
        "p50_ms": round(statistics.median(ordered), 1),
        "p99_ms": round(ordered[-1], 1),
    }


def main(
    dates: tuple[str, ...] = DATES,
    out_dir: Path = DEFAULT_OUT_DIR,
    baseline_path: Path = DEFAULT_BASELINE,
) -> int:
    from digiquant.data.store.client import build_digiquant_client
    from digiquant.research.data import queries as q

    client = build_digiquant_client()
    out_dir.mkdir(parents=True, exist_ok=True)
    tech_ms: list[float] = []
    macro_ms: list[float] = []
    for as_of in dates:
        run_date = date.fromisoformat(as_of)
        start = time.perf_counter()
        technicals = {
            t: q.get_price_technicals(client=client, ticker=t, lookback=TECHNICALS_LOOKBACK)
            for t in TICKERS
        }
        tech_ms.append((time.perf_counter() - start) * 1000.0)
        start = time.perf_counter()
        macro = q.get_macro_series(
            client=client,
            series_ids=list(SERIES_IDS),
            lookback=MACRO_LOOKBACK,
            as_of=run_date,
        )
        macro_ms.append((time.perf_counter() - start) * 1000.0)
        payload = {
            "as_of": as_of,
            "tickers": list(TICKERS),
            "series_ids": list(SERIES_IDS),
            "technicals": technicals,
            "macro": macro,
        }
        (out_dir / f"{as_of}.json").write_text(json.dumps(payload, default=str))
    baseline = {
        "backend": "supabase",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "dates": list(dates),
        "tools": {
            "get_price_technicals": _summarize_latency(tech_ms),
            "get_macro_series": _summarize_latency(macro_ms),
        },
    }
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
