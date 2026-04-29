#!/usr/bin/env python3
"""
retrofit_delta_requests.py

Scan `data/agent-cache/daily/` for DIGEST-DELTA.md and write
delta-request.json in the current schema (templates/delta-request-schema.json).

Skips days that already have delta-request.json unless --force.
Baseline date is parsed from the delta markdown header when possible.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

ROOT = Path(__file__).resolve().parent.parent


def _load_legacy_module():
    path = Path(__file__).resolve().parent / "legacy_delta_to_ops.py"
    spec = importlib.util.spec_from_file_location("legacy_delta_to_ops_mod", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load legacy_delta_to_ops.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _discover_delta_md_dirs() -> Iterator[Tuple[str, Path]]:
    """Yield (YYYY-MM-DD, path_to_DIGEST-DELTA.md)."""
    bases = [ROOT / "data" / "agent-cache" / "daily"]
    seen_dates: set[str] = set()
    for base in bases:
        if not base.is_dir():
            continue
        for day_dir in sorted(base.iterdir()):
            if not day_dir.is_dir():
                continue
            name = day_dir.name
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", name):
                continue
            md = day_dir / "DIGEST-DELTA.md"
            if not md.is_file():
                continue
            if name in seen_dates:
                continue
            seen_dates.add(name)
            yield name, md


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="Overwrite existing delta-request.json")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    args = ap.parse_args()

    ldo = _load_legacy_module()
    written = 0
    skipped = 0

    for date_str, md_path in _discover_delta_md_dirs():
        md = md_path.read_text(encoding="utf-8")
        baseline = ldo.parse_baseline_date_from_delta_md(md)
        if not baseline:
            print(f"⚠️  skip {date_str}: could not parse baseline date from {md_path}")
            skipped += 1
            continue

        primary = md_path.parent / "delta-request.json"
        if primary.exists() and not args.force:
            print(f"⏭️  skip {date_str}: {primary} exists (use --force)")
            skipped += 1
            continue

        payload: Dict[str, Any] = ldo.build_delta_request_payload(date_str, baseline, md)
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

        targets: list[Path] = [primary]

        if args.dry_run:
            print(f"Would write {date_str} ({len(payload['ops'])} ops) → {[str(t) for t in targets]}")
            written += 1
            continue

        for t in targets:
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text(text, encoding="utf-8")
            print(f"✅ {t} ({len(payload['ops'])} ops)")
        written += 1

    print(f"Done. Written/queued: {written}, skipped: {skipped}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
