#!/usr/bin/env python3
"""Reindex the DigiThings-guide `docs` index.

Reads the index manifest at docs/projects/digithings-guide/indexes/docs.yaml,
expands the `sources` globs against the repo root, and either:
  - DRY-RUN (default): parses + chunks each file in-process via the DigiSearch
    stub backend and prints a chunk-count summary.
  - APPLY (--apply): posts each file to the DigiSearch ``POST /ingest`` HTTP
    endpoint and prints per-file progress.

Exit codes:
  0 — success (all resolved files ingested/dry-run-chunked without error)
  1 — manifest missing or malformed
  2 — ingest error (one or more files failed)

Usage:
  python scripts/reindex_digithings_guide.py              # dry-run (default)
  python scripts/reindex_digithings_guide.py --apply      # real ingest via DigiSearch HTTP API
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "docs" / "projects" / "digithings-guide" / "indexes" / "docs.yaml"
DEFAULT_DIGISEARCH_URL = "http://digisearch:8002"


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


def ingest_live(index_name: str, paths: list[Path], digisearch_url: str) -> int:
    """Post each file to the DigiSearch /ingest endpoint.

    Continues on per-file errors (connection failures, non-2xx responses).
    Returns 0 if all files succeeded, 2 if any file failed.
    """
    base_url = digisearch_url.rstrip("/")
    endpoint = f"{base_url}/ingest"
    failed = 0

    for path in paths:
        rel = path.relative_to(REPO_ROOT)
        payload = json.dumps(
            {"source": str(path.absolute()), "index_name": index_name}
        ).encode()
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
            chunks_created = body.get("chunks_created", "?")
            print(f"  {rel}: {chunks_created} chunks")
        except urllib.error.HTTPError as exc:
            # HTTPError is a subclass of URLError/OSError; catch first for richer message.
            print(f"  ERROR {rel}: HTTP {exc.code} {exc.reason}", file=sys.stderr)
            failed += 1
        except OSError as exc:
            # Covers URLError (connection refused, DNS) and TimeoutError.
            print(f"  ERROR {rel}: {exc}", file=sys.stderr)
            failed += 1

    if failed:
        print(
            f"\nindex={index_name} files={len(paths)} failed={failed}",
            file=sys.stderr,
        )
        return 2

    print(f"\nindex={index_name} files={len(paths)} all succeeded")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Post files to the DigiSearch /ingest HTTP endpoint (DIGISEARCH_URL env var).",
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
        digisearch_url = os.environ.get("DIGISEARCH_URL", DEFAULT_DIGISEARCH_URL)
        print(f"Ingesting {len(paths)} source files into index '{index_name}' via {digisearch_url}...")
        return ingest_live(index_name, paths, digisearch_url)

    print(f"Resolving {len(paths)} source files for index '{index_name}'...")
    return dry_run(index_name, paths)


if __name__ == "__main__":
    raise SystemExit(main())
