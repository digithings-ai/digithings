#!/usr/bin/env python3
"""Export the Atlas SnapshotEnvelope JSON Schema to disk.

The serialized JSON Schema is the artifact frontend / TypeScript consumers
read to generate types or runtime validators. Re-run after any field change
to ``digiquant.atlas.snapshot.SnapshotEnvelope``.

Usage::

    python3 scripts/export_atlas_snapshot_schema.py
    python3 scripts/export_atlas_snapshot_schema.py --output /tmp/snapshot.json

The default output path is
``digiquant/docs/schemas/atlas_snapshot.v{SCHEMA_VERSION}.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "digiquant" / "src"))

from digiquant.atlas.snapshot import SCHEMA_VERSION, SnapshotEnvelope  # noqa: E402


def _default_output_path() -> Path:
    return REPO_ROOT / "digiquant" / "docs" / "schemas" / f"atlas_snapshot.v{SCHEMA_VERSION}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_output_path(),
        help="Path to write the JSON Schema (default: digiquant/docs/schemas/...)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the on-disk schema differs from the freshly generated one.",
    )
    args = parser.parse_args(argv)

    schema = SnapshotEnvelope.model_json_schema()
    rendered = json.dumps(schema, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not args.output.exists():
            print(f"missing schema file: {args.output}", file=sys.stderr)
            return 1
        existing = args.output.read_text(encoding="utf-8")
        if existing != rendered:
            print(
                f"schema drift: {args.output} is stale; "
                "re-run scripts/export_atlas_snapshot_schema.py",
                file=sys.stderr,
            )
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output} (schema_version={SCHEMA_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
