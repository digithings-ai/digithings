#!/usr/bin/env python3
"""Download a small slice of EDGAR-CORPUS (Hugging Face) to markdown for DigiSearch.

Requires: pip install -e "./digisearch[edgar-corpus]"

Example:
  python scripts/export_edgar_corpus_dev.py --year 2020 --max-documents 25

Output: digisearch/devdata/edgar_sample/edgar_*.md + .yaml sidecars
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", type=int, default=2020, help="Fiscal year config year_YYYY")
    ap.add_argument("--max-documents", type=int, default=25, help="Cap rows (streaming)")
    ap.add_argument(
        "--split",
        default="train",
        help="Dataset split (train|validation|test)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=repo_root / "digisearch" / "devdata" / "edgar_sample",
    )
    ap.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing edgar_*.md/yaml under out-dir before export",
    )
    args = ap.parse_args()

    if args.max_documents < 1:
        raise SystemExit("--max-documents must be >= 1")

    sys.path.insert(0, str(repo_root / "digisearch" / "src"))

    from digisearch.dev.edgar_sample_export import (
        clean_edgar_exports,
        row_to_dict,
        row_to_markdown,
        row_to_sidecar_metadata,
        row_to_stem,
        write_export_pair,
    )

    try:
        from datasets import load_dataset
    except ImportError as e:
        raise SystemExit(
            "Missing dependency: pip install -e \"./digisearch[edgar-corpus]\""
        ) from e

    out_dir: Path = args.out_dir
    if args.clean:
        n = clean_edgar_exports(out_dir)
        if n:
            print(f"cleaned {n} previous export file(s) under {out_dir}")

    config = f"year_{args.year}"
    print(f"loading eloukas/edgar-corpus/{config} split={args.split} streaming=True …")
    ds = load_dataset(
        "eloukas/edgar-corpus",
        config,
        split=args.split,
        streaming=True,
        trust_remote_code=True,
    )
    stream = ds.take(args.max_documents)

    written = 0
    skipped = 0
    for i, row_any in enumerate(stream):
        row = row_to_dict(row_any)
        stem = row_to_stem(row, i)
        body = row_to_markdown(row)
        if not body.strip():
            skipped += 1
            continue
        meta = row_to_sidecar_metadata(row, stem)
        write_export_pair(out_dir, stem, body, meta)
        written += 1
        print(f"wrote {stem}.md + .yaml")

    print(f"done: {written} document(s), {skipped} empty skipped → {out_dir}")


if __name__ == "__main__":
    main()
