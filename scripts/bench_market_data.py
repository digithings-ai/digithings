"""Load harness for the R2 market-data cutover (#3780, Task 10).

Drives ``digiquant_get_price_technicals`` / ``digiquant_get_macro_series``
through the UNMOCKED MCP serving path (fake R2 store serves real parquet
bytes — no network, no creds) and compares p99 against the Task 1 Supabase
numbers in ``docs/perf/baseline.json``.

PASS = R2 p99 <= 2x the Supabase p99 AND R2 p99 <= 800ms, per tool.
Anything else fires the fallback-B trigger (follow-up migration, out of
this plan) and exits 2.

The TTL envelope cache is cleared before every timed call so each sample
measures the full serving cost (parquet decode + merge + indicators),
not a cache hit.

Supervised live runs (real R2 + vendors) stay operator-side: this harness
pins the serving-path budget; absolute wall-clock against production
backends is measured at promotion with the operator.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import sys
import time
from datetime import date as _date
from datetime import timedelta as _td
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "digiquant" / "src"))

DEFAULT_BASELINE = REPO_ROOT / "docs" / "perf" / "baseline.json"
P99_ABSOLUTE_BAR_MS = 800.0
RELATIVE_FACTOR = 2.0

_TECHNICALS = "get_price_technicals"
_MACRO = "get_macro_series"
_ALL_TOOLS = (_TECHNICALS, _MACRO)


def _percentile_ms(samples_ms: list[float], pct: float) -> float:
    """Nearest-rank percentile over the sample timings."""
    ordered = sorted(samples_ms)
    rank = math.ceil(pct * len(ordered))
    return ordered[min(len(ordered) - 1, max(0, rank - 1))]


def _price_payload(dates: list[str], closes: list[float]) -> tuple[bytes, str]:
    import polars as pl

    frame = pl.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": [c + 0.1 for c in closes],
            "low": [c - 0.1 for c in closes],
            "close": closes,
            "volume": [1_000_000.0] * len(dates),
        }
    )
    buf = io.BytesIO()
    frame.write_parquet(buf)
    payload = buf.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


def _macro_payload(rows: list[dict]) -> tuple[bytes, str]:
    import polars as pl

    buf = io.BytesIO()
    pl.DataFrame(rows).write_parquet(buf)
    payload = buf.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


class _FakeR2Store:
    """Generation bytes keyed on ``(key, sha256)`` like the production lookup."""

    def __init__(self, generations: dict[tuple[str, str], bytes]) -> None:
        self._generations = generations

    def get_generation(self, key: str, sha256: str) -> bytes:
        return self._generations[(key, sha256)]

    def read_latest(self, pointer_key: str) -> str:
        for gen_key, _sha in self._generations:
            if gen_key == pointer_key:
                return gen_key
        raise KeyError(pointer_key)


def _arm_fake_backend(as_of: str) -> None:
    """Patch the MCP R2 seam with synthetic generations sealed at *as_of*."""
    import digiquant.mcp_server as mcp
    from digiquant.data.prices.r2_history import macro_latest_pointer_key

    seal = _date.fromisoformat(as_of)
    dates = [(seal - _td(days=i)).isoformat() for i in range(599, -1, -1)]
    closes = [round(100.0 + i * 0.13, 2) for i in range(len(dates))]
    price_payload, price_sha = _price_payload(dates, closes)
    price_key = f"market-data/price/SPY/{as_of}.parquet"

    generations = {(price_key, price_sha): price_payload}
    datasets: dict[str, dict] = {
        "SPY": {"object": price_key, "sha256": price_sha, "rows": len(dates)}
    }
    for sid, base in (("DGS10", 4.2), ("VIXCLS", 18.5)):
        rows = [
            {"series_id": sid, "obs_date": d, "value": round(base + i * 0.01, 3)}
            for i, d in enumerate(dates[-30:])
        ]
        payload, sha = _macro_payload(rows)
        pointer = macro_latest_pointer_key("fred", sid)
        generations[(pointer, sha)] = payload
        datasets[f"fred__{sid}"] = {"object": pointer, "sha256": sha, "rows": len(rows)}
    manifest = {"version": 1, "as_of": as_of, "datasets": datasets}

    os.environ["DIGIQUANT_MARKET_DATA_BACKEND"] = "r2"
    mcp._read_manifest = lambda: manifest  # type: ignore[method-assign]
    mcp._get_r2_store = lambda: _FakeR2Store(generations)  # type: ignore[method-assign]
    mcp._ttl.clear()

    def _no_network(tickers: list[str], **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("bench harness must not touch the network")

    import digiquant.data.prices.fetchers as fetchers

    fetchers.fetch_batch = _no_network  # type: ignore[method-assign]


def _load_supabase_baselines(path: Path) -> dict[str, dict[str, float]]:
    raw = json.loads(path.read_text())
    # Post-Task-10 shape nests Task 1 under "supabase"; accept the original
    # flat Task 1 shape too so old checkouts keep working.
    node = raw.get("supabase", raw) if isinstance(raw, dict) else raw
    return {
        name: {
            "p50_ms": float(spec["p50_ms"]),
            "p99_ms": float(spec["p99_ms"]),
            "n": int(spec.get("n", 0)),
        }
        for name, spec in node["tools"].items()
    }


def _bench_tool(tool: str, n: int, as_of: str) -> dict[str, float]:
    import digiquant.mcp_server as mcp

    samples: list[float] = []
    for _ in range(n):
        mcp._ttl.clear()
        start = time.perf_counter()
        if tool == _TECHNICALS:
            out = mcp.digiquant_get_price_technicals("SPY", lookback=500, as_of=as_of)
        else:
            out = mcp.digiquant_get_macro_series(["DGS10", "VIXCLS"], lookback=6, as_of=as_of)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        payload = json.loads(out)
        if "error" in payload:
            raise RuntimeError(f"bench {tool} errored: {payload['error']}")
        samples.append(elapsed_ms)
    return {
        "n": float(n),
        "p50_ms": round(_percentile_ms(samples, 0.50), 1),
        "p99_ms": round(_percentile_ms(samples, 0.99), 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tools", default=",".join(_ALL_TOOLS), help="Comma-separated subset to bench."
    )
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--as-of", default="2025-08-29")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument(
        "--record",
        action="store_true",
        help="Write the R2 numbers beside the Task 1 Supabase numbers and exit 0.",
    )
    args = parser.parse_args(argv)

    tools = [t.strip() for t in args.tools.split(",") if t.strip()]
    unknown = [t for t in tools if t not in _ALL_TOOLS]
    if unknown:
        print(f"unknown tools: {unknown} (expected subset of {list(_ALL_TOOLS)})")
        return 1
    if args.n <= 0:
        print("--n must be positive")
        return 1

    baselines = _load_supabase_baselines(Path(args.baseline))
    _arm_fake_backend(args.as_of)

    results: dict[str, dict[str, float]] = {}
    failures: list[str] = []
    for tool in tools:
        stats = _bench_tool(tool, args.n, args.as_of)
        base_p99 = baselines[tool]["p99_ms"]
        stats["baseline_p99_ms"] = base_p99
        rel_ok = stats["p99_ms"] <= RELATIVE_FACTOR * base_p99
        abs_ok = stats["p99_ms"] <= P99_ABSOLUTE_BAR_MS
        stats["pass"] = float(rel_ok and abs_ok)
        results[tool] = stats
        status = "PASS" if rel_ok and abs_ok else "FAIL"
        print(
            f"{tool}: n={args.n} p50={stats['p50_ms']}ms p99={stats['p99_ms']}ms "
            f"(supabase p99={base_p99}ms; bar: <= {RELATIVE_FACTOR}x baseline "
            f"AND <= {P99_ABSOLUTE_BAR_MS}ms) -> {status}"
        )
        if not (rel_ok and abs_ok):
            failures.append(tool)

    if args.record:
        from datetime import UTC, datetime

        path = Path(args.baseline)
        raw = json.loads(path.read_text()) if path.exists() else {}
        supabase_node = raw.get("supabase", raw) if isinstance(raw, dict) else raw
        if "tools" not in supabase_node:
            print("baseline has no supabase tools to preserve; refusing to rewrite")
            return 1
        raw = {"supabase": supabase_node}
        raw["r2"] = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "as_of": args.as_of,
            "tools": {
                tool: {
                    "n": int(stats["n"]),
                    "p50_ms": stats["p50_ms"],
                    "p99_ms": stats["p99_ms"],
                }
                for tool, stats in results.items()
            },
        }
        path.write_text(json.dumps(raw, indent=2) + "\n")
        print(f"recorded R2 numbers to {path}")
        return 0

    if failures:
        print(
            f"fallback-B trigger fires for {failures}: R2 p99 breached the bar "
            "(follow-up migration, out of this plan)"
        )
        return 2
    print("bench PASS: R2 shows headroom against the Task 1 Supabase baselines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
