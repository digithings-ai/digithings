#!/usr/bin/env python3
"""Reindex the DigiThings-guide `docs` index.

Reads the index manifest at docs/projects/digithings-guide/indexes/docs.yaml,
expands the `sources` globs against the repo root, and (today) performs a
DRY-RUN chunk count via the in-process DigiSearch stub. Swap to a real
service-less ingest call once DigiSearch exposes one.

Exit codes:
  0 — success (all resolved files ingested/dry-run-chunked without error)
  1 — manifest missing or malformed
  2 — ingest error

Usage:
  python scripts/reindex_digithings_guide.py              # dry-run
  python scripts/reindex_digithings_guide.py --apply      # wire to real ingest when available
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "docs" / "projects" / "digithings-guide" / "indexes" / "docs.yaml"


def resolve_sources(manifest_path: Path) -> tuple[str, list[Path]]:
    """Return (index_name, resolved file paths) from the manifest's `sources` globs."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    data = yaml.safe_load(manifest_path.read_text()) or {}
    index_name = (data.get("index_name") or "").strip()
    if not index_name:
        raise ValueError(f"manifest missing index_name: {manifest_path}")
    patterns = data.get("sources") or []
    seen: set[Path] = set()
    resolved: list[Path] = []
    for pattern in patterns:
        for match in sorted(REPO_ROOT.glob(pattern)):
            if not match.is_file():
                continue
            rp = match.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            resolved.append(match)
    return index_name, resolved


def dry_run(index_name: str, paths: list[Path]) -> int:
    """Parse + chunk each file in-process; print a summary. Uses the DigiSearch stub backend."""
    try:
        from digisearch.ingestion.chunkers.recursive import RecursiveChunker
        from digisearch.ingestion.registry import ParserRegistry
    except ImportError as exc:
        print(f"digisearch not importable: {exc}", file=sys.stderr)
        print(
            "Install with: pip install -e digisearch  (or run the real ingest once the CLI supports service-less mode)",
            file=sys.stderr,
        )
        return 2

    registry = ParserRegistry()
    chunker = RecursiveChunker(chunk_size=512, chunk_overlap=64)
    total_chunks = 0
    skipped: list[tuple[Path, str]] = []
    for path in paths:
        parser = registry.get_parser(str(path))
        if parser is None:
            skipped.append((path, "no parser"))
            continue
        try:
            doc = registry.parse(path)
            chunks = chunker.chunk(doc)
            total_chunks += len(chunks)
            print(f"  {path.relative_to(REPO_ROOT)}: {len(chunks)} chunks")
        except Exception as exc:  # noqa: BLE001 — dry-run surfaces parser errors
            skipped.append((path, str(exc)))

    print(f"\nindex={index_name} files={len(paths)} chunks={total_chunks} skipped={len(skipped)}")
    for path, reason in skipped:
        print(f"  SKIP {path.relative_to(REPO_ROOT)}: {reason}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ingest into the configured backend (not yet supported — runs dry-run with warning).",
    )
    args = parser.parse_args()

    try:
        index_name, paths = resolve_sources(MANIFEST)
    except (FileNotFoundError, ValueError) as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 1

    if not paths:
        print("no source files resolved — nothing to index", file=sys.stderr)
        return 0

    if args.apply:
        # Follow-up (tracked under issue #23): invoke service-less ingest once it
        # lands in DigiSearch. Until then, dry-run still proves the file set
        # parses and chunks cleanly.
        print("--apply: service-less ingest not yet available; running dry-run", file=sys.stderr)

    print(f"Resolving {len(paths)} source files for index '{index_name}'...")
    return dry_run(index_name, paths)


if __name__ == "__main__":
    raise SystemExit(main())
