"""Build and ingest a static ``occ_tickets`` seed snapshot (#4987).

The Cloudflare ``digithings-stack`` container wipes ``/data`` on every cold
boot, so ``seed_chroma.sh`` re-ingests ``digithings_docs`` and ``occ_help``
from ``/seed`` on each restart. ``occ_tickets`` needs the same treatment or
the OCC tenant map fan-out (``occ_help,occ_tickets``) queries an index nobody
ever populated.

Two ways to fill it:

* run ``scripts/index_occ_tickets.py`` inside the container against live
  Zammad on every boot (no PII in git, but every boot pays ~185 ticket
  round-trips and the backfill script has to ship in the image), or
* commit a point-in-time snapshot and let the existing seed oneshot ingest
  it like the other two indexes.

This module implements the second form as a single JSONL file — one line
per ticket article::

    {"id": ..., "doc_id": ..., "content": ..., "metadata": {...}}

Bodies and metadata come from
:func:`scripts.index_occ_tickets.build_ticket_chunks`, so a snapshot is
byte-identical to what a live backfill would write, and ``--ingest`` feeds
the same :func:`digisearch.pipeline.ingest.index_chunks` path under the same
pinned embedding provider. One file instead of ~900 markdown/sidecar pairs
keeps the repository diff small and a refresh a single ``git rm`` + rebuild.

Demo mode: customer names and emails are stored in full and internal
articles are tagged ``[internal]``, matching the zammad MCP tools after
#4944. Do not run this outside a demo deployment.

Usage:
    # refresh the committed payload (needs live Zammad)
    ZAMMAD_API_TOKEN=... python -m scripts.build_occ_tickets_seed \\
        --out apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl

    # what seed_chroma.sh runs inside the container
    python -m scripts.build_occ_tickets_seed --ingest /seed/occ_tickets.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

#: Default payload destination — copied to /seed by the stack image.
DEFAULT_OUT = Path("apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl")


def _chunk_to_row(chunk: Any) -> dict[str, Any]:
    return {
        "id": str(chunk.id),
        "doc_id": str(chunk.doc_id),
        "content": str(chunk.content),
        "metadata": dict(chunk.metadata or {}),
    }


def write_snapshot(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def read_snapshot(in_path: Path) -> list[Any]:
    """Rebuild ``Chunk`` objects from a JSONL snapshot, preserving order."""
    from digisearch.core.models import Chunk

    chunks: list[Any] = []
    with in_path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"occ_tickets seed: {in_path}:{lineno}: invalid JSON ({exc})"
                ) from exc
            missing = {"id", "doc_id", "content"} - row.keys()
            if missing:
                raise SystemExit(f"occ_tickets seed: {in_path}:{lineno}: missing {sorted(missing)}")
            chunks.append(
                Chunk(
                    id=str(row["id"]),
                    content=str(row["content"]),
                    doc_id=str(row["doc_id"]),
                    metadata=row.get("metadata") or {},
                )
            )
    return chunks


def ingest_snapshot(in_path: Path, index_name: str) -> int:
    """Index a JSONL snapshot into ``index_name``. Returns the chunk count."""
    from scripts.index_occ_tickets import multilingual_index

    if not in_path.is_file():
        raise SystemExit(f"occ_tickets seed: no snapshot at {in_path}")
    chunks = read_snapshot(in_path)
    if not chunks:
        raise SystemExit(f"occ_tickets seed: {in_path} holds no articles")
    # Same helper the live backfill uses: pins the provider to the multilingual
    # model id, refuses a conflicting DIGISEARCH_EMBEDDING_PROVIDER, and
    # verifies Chroma's collection stamp against the vectors written.
    with multilingual_index(index_name, chunks):
        pass
    return len(chunks)


def build_snapshot(out_path: Path, max_tickets: int | None, snapshot_date: str) -> dict[str, Any]:
    """Fetch live Zammad tickets and write the JSONL snapshot."""
    from scripts.index_occ_tickets import _int_or_none, build_ticket_chunks
    from scripts.zammad_mcp.client import ZammadClient, ZammadError

    if not os.environ.get("ZAMMAD_API_TOKEN", "").strip():
        raise SystemExit("zammad error: ZAMMAD_API_TOKEN is not set")
    client = ZammadClient()
    try:
        tickets = client.list_tickets()
    except ZammadError as exc:
        raise SystemExit(f"zammad error: {exc}") from exc
    capped_at_500 = max_tickets is None and len(tickets) == 500
    if max_tickets is not None:
        tickets = tickets[:max_tickets]

    rows: list[dict[str, Any]] = []
    failures = 0
    resolved: dict[int, str] = {}
    for ticket in tickets:
        ticket_id = _int_or_none(ticket.get("id"))
        if ticket_id is None:
            failures += 1
            continue
        try:
            articles = client.get_articles(ticket_id)
        except ZammadError:
            failures += 1
            continue
        customer_name: str | None = None
        customer_id = _int_or_none(ticket.get("customer_id"))
        if customer_id is not None:
            if customer_id not in resolved:
                try:
                    resolved[customer_id] = client.resolve_user(customer_id)
                except ZammadError:
                    resolved[customer_id] = ""
            customer_name = resolved[customer_id] or None
        for chunk in build_ticket_chunks(
            ticket, articles, customer_name, snapshot_date=snapshot_date
        ):
            rows.append(_chunk_to_row(chunk))

    if not rows:
        raise SystemExit("occ_tickets seed: built 0 articles; refusing to write an empty payload")
    write_snapshot(rows, out_path)
    return {
        "out": str(out_path),
        "tickets_scanned": len(tickets),
        "capped_at_500": capped_at_500,
        "ticket_failures": failures,
        "articles": len(rows),
        "snapshot_date": snapshot_date,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build or ingest a static occ_tickets seed snapshot"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Snapshot JSONL path")
    parser.add_argument("--snapshot-date", default="2026-10-02", help="Snapshot label")
    parser.add_argument("--max-tickets", type=int, default=None, help="Cap ticket count")
    parser.add_argument(
        "--ingest",
        type=Path,
        default=None,
        help="Ingest an existing snapshot instead of fetching live Zammad",
    )
    parser.add_argument("--index", default="occ_tickets", help="Target index for --ingest")
    args = parser.parse_args(argv)

    if args.ingest is not None:
        count = ingest_snapshot(args.ingest, args.index)
        print(f"occ_tickets seed: ingested {count} article(s) into {args.index}")
        return

    if args.max_tickets is not None and args.max_tickets < 1:
        raise SystemExit("zammad error: --max-tickets must be a positive integer")
    summary = build_snapshot(args.out, args.max_tickets, args.snapshot_date)
    print(
        f"occ_tickets seed: {summary['articles']} article(s) from "
        f"{summary['tickets_scanned']} ticket(s) -> {summary['out']} "
        f"(snapshot {summary['snapshot_date']}, "
        f"{summary['ticket_failures']} ticket failure(s))"
    )


if __name__ == "__main__":
    main()
