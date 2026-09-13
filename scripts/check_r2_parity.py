"""Parity gate: per-ticker row counts Supabase-vs-R2 with tolerance 0 (#3780).

Compares the row counts recorded at backfill time (``--supabase-counts`` JSON:
``{ticker: rows}``) against the R2 manifest's dataset entries and writes a CI
artifact JSON. Exit 0 on exact match, 1 otherwise. Consumed by the Task 7 gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any  # score:allow untyped any — R2 JSON payloads


def load_counts_from_manifest(manifest: dict[str, Any]) -> dict[str, int]:
    """Per-dataset R2 row counts from manifest ``datasets`` entries."""
    out: dict[str, int] = {}
    for dataset_id, entry in (manifest.get("datasets") or {}).items():
        if isinstance(entry, dict) and isinstance(entry.get("rows"), int):
            out[str(dataset_id)] = int(entry["rows"])
    return out


def compare_counts(supabase: dict[str, int], r2: dict[str, int]) -> dict[str, Any]:
    """Exact (tolerance 0) per-dataset row-count comparison.

    Stray R2 datasets fail the gate: extras are NOT tolerated, since a stray
    dataset means the backfill wrote under an unexpected id (Task 7 gate).
    Missing datasets are reported only in ``missing_in_r2``, never duplicated
    into ``mismatches`` (which is reserved for present-but-unequal counts).
    """
    missing = sorted(set(supabase) - set(r2))
    extra = sorted(set(r2) - set(supabase))
    mismatches = [
        {"dataset": name, "supabase": supabase[name], "r2": r2[name]}
        for name in sorted(supabase)
        if name in r2 and r2[name] != supabase[name]
    ]
    return {
        "ok": not mismatches and not missing and not extra,
        "tolerance": 0,
        "datasets": len(supabase),
        "mismatches": mismatches,
        "missing_in_r2": missing,
        "extra_in_r2": extra,
    }


def write_artifact(report: dict[str, Any], path: str) -> str:
    Path(path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="R2 manifest JSON file.")
    parser.add_argument("--supabase-counts", required=True, help="Ticker->rows JSON.")
    parser.add_argument("--out", default="/tmp/r2-parity.json", help="CI artifact path.")
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text())
    expected = {k: int(v) for k, v in json.loads(Path(args.supabase_counts).read_text()).items()}
    report = compare_counts(expected, load_counts_from_manifest(manifest))
    write_artifact(report, args.out)
    if report["ok"]:
        print(f"parity ok: {report['datasets']} datasets exact -> {args.out}")
        return 0
    print(f"parity FAILED: {len(report['mismatches'])} mismatch(es) -> {args.out}")
    for m in report["mismatches"]:
        print(f"  {m['dataset']}: supabase={m['supabase']} r2={m['r2']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
