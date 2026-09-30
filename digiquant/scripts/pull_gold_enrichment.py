#!/usr/bin/env python3
"""Gold enrichment pulls → snapshot store (research staging, #4804).

Each subcommand calls one free/anon digifetch tool through the in-process
dispatcher and persists the attribution-enveloped JSON via
``digiquant.data.enrichment.snapshots``. Enrichment-only: 15-minute delay,
§5.2 caps; never a pipeline input.

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/pull_gold_enrichment.py options-skew
    PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/pull_gold_enrichment.py options-skew --expiration 1798761600
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from digiquant.data.enrichment.snapshots import write_snapshot


def _dispatcher():
    from digiquant.data.gloomberb.agent_tools import build_digifetch_tool_dispatcher

    return build_digifetch_tool_dispatcher()


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_options_skew(
    symbol: str = "GLD", expiration: int | None = None, *, fetched_at: str | None = None
) -> tuple[str, dict]:
    """Snapshot the GLD chain and compute per-expiry put/call OI + volume ratios.

    Metrics use only OI/volume/strike/side/expiration (no greeks — the free
    tier does not return them; see Task 0 field table). Ratios > 1 mean
    put-heavy positioning for that expiry.
    """
    params: dict = {"symbol": symbol}
    if expiration is not None:
        params["expiration"] = expiration
    result = _dispatcher()("digifetch_options_chain", params)
    # Live dispatcher answers {"content": <JSON str>, "ok": bool}
    # (agent_tools.py); offline tests answer the JSON string directly.
    raw = result["content"] if isinstance(result, dict) else result
    chain = json.loads(raw)["data"]["chain"]  # shape per Task 0 table; KeyError surfaces drift
    legs = chain["calls"] + chain["puts"]
    by_expiry: dict[str, dict] = {}
    for leg in legs:
        bucket = by_expiry.setdefault(
            str(leg["expiration"]), {"call_oi": 0.0, "put_oi": 0.0, "call_vol": 0.0, "put_vol": 0.0}
        )
        side = "put" if leg["side"].lower().startswith("put") else "call"
        bucket[f"{side}_oi"] += float(leg.get("open_interest") or 0.0)
        bucket[f"{side}_vol"] += float(leg.get("volume") or 0.0)
    metrics = {
        exp: {
            "put_call_oi": (b["put_oi"] / b["call_oi"]) if b["call_oi"] else None,
            "put_call_volume": (b["put_vol"] / b["call_vol"]) if b["call_vol"] else None,
        }
        for exp, b in sorted(by_expiry.items())
    }
    path = write_snapshot(
        "digifetch_options_chain", params, raw, fetched_at=fetched_at or _now_utc()
    )
    (path.parent / f"{path.stem}.metrics.json").write_text(json.dumps(metrics, indent=2))
    return str(path), metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Gold enrichment pulls → snapshot store")
    sub = parser.add_subparsers(dest="command", required=True)
    p_skew = sub.add_parser("options-skew")
    p_skew.add_argument(
        "--expiration", type=int, default=None, help="Epoch seconds (default: all expiries)"
    )
    args = parser.parse_args()
    if args.command == "options-skew":
        path, metrics = snapshot_options_skew(expiration=args.expiration)
        print(f"snapshot: {path}")
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
