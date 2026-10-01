"""One-shot backfill of Zammad tickets into a digisearch index (#4756).

Reads every visible ticket (GET-only, up to the 500-ticket list cap) plus
its articles, builds one Chunk per article with a body with full
non-anonymized metadata (demo mode, same contract as
the zammad MCP tools after #4944), and indexes into ``occ_tickets`` — a
separate index from the ``occ_help`` docs corpus — using the small
multilingual ONNX provider, so English queries match German/Spanish text.
The script pins ``DIGISEARCH_EMBEDDING_PROVIDER=multilingual`` (unless
already set) so the backend stamps and queries the collection with the
same model that produced the vectors.

Snapshot semantics: this is a point-in-time demo backfill (data as of
2026-10-01). There is no cron/daemon; re-run the script for a fresh
snapshot.

Usage:
    ZAMMAD_API_TOKEN=... CHROMA_PATH=/path/to/chroma \\
        python -m scripts.index_occ_tickets [--index occ_tickets] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from typing import Any

#: Demo snapshot date stamped on every chunk; the index is explicitly stale
#: after this date (no sync job — re-run for a fresh snapshot).
SNAPSHOT_DATE = "2026-10-01"

DEFAULT_INDEX = "occ_tickets"


def _int_or_none(value: Any) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None
    return number if number > 0 else None


def _clean_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only Chroma-safe metadata values (str/int/float/bool); drop Nones."""
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None:
            continue
        if isinstance(value, bool):
            cleaned[key] = value
        elif isinstance(value, (str, int, float)):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned


def build_ticket_chunks(
    ticket: dict[str, Any],
    articles: list[dict[str, Any]],
    customer_name: str | None = None,
    snapshot_date: str = SNAPSHOT_DATE,
) -> list[Any]:
    """Build one Chunk per article with a body (full metadata, no masking)."""
    from digisearch.core.models import Chunk

    from scripts.zammad_mcp.formatting import _field as _text
    from scripts.zammad_mcp.formatting import html_to_text

    ticket_id = _int_or_none(ticket.get("id"))
    customer_id = _int_or_none(ticket.get("customer_id"))
    number = _text(ticket.get("number"))
    title = _text(ticket.get("title")) or "(no title)"
    doc_id = f"zammad-ticket-{ticket_id if ticket_id is not None else number or '?'}"
    chunks: list[Any] = []
    for index, article in enumerate(articles, start=1):
        body = html_to_text(article.get("body"))
        if not body:
            continue
        sender = _text(article.get("sender")) or "unknown"
        kind = _text(article.get("type")) or "unknown"
        author = _text(article.get("from"))
        subject = _text(article.get("subject"))
        internal = bool(article.get("internal"))
        header = f"Ticket {number or ticket_id}: {title}\nArticle {index} ({sender}/{kind})"
        if internal:
            header += " [internal]"
        parts = [header]
        if author:
            parts.append(f"From: {author}")
        if subject:
            parts.append(f"Subject: {subject}")
        if body:
            parts.append(body)
        content = "\n".join(parts).strip()
        metadata = _clean_metadata(
            {
                "source": "zammad",
                "snapshot_date": snapshot_date,
                "ticket_id": ticket_id,
                "number": number,
                "title": title,
                "state": _text(ticket.get("state")),
                "group": _text(ticket.get("group")),
                "priority": _text(ticket.get("priority")),
                "customer": _text(ticket.get("customer")),
                "customer_id": customer_id,
                "customer_name": customer_name or "",
                "organization": _text(ticket.get("organization")),
                "owner": _text(ticket.get("owner")),
                "created_at": _text(ticket.get("created_at")),
                "updated_at": _text(ticket.get("updated_at")),
                "article_id": _int_or_none(article.get("id")),
                "article_index": index,
                "sender": sender,
                "article_type": kind,
                "internal": internal,
                "article_created_at": _text(article.get("created_at")),
            }
        )
        chunks.append(
            Chunk(
                id=f"zammad-{ticket_id if ticket_id is not None else 'n'}-{index}",
                content=content,
                doc_id=doc_id,
                metadata=metadata,
            )
        )
    return chunks


def backfill(
    index_name: str = DEFAULT_INDEX,
    max_tickets: int | None = None,
    dry_run: bool = False,
    snapshot_date: str = SNAPSHOT_DATE,
) -> dict[str, Any]:
    """Fetch tickets + articles, build chunks, index them. Returns a summary.

    Pins ``DIGISEARCH_EMBEDDING_PROVIDER=multilingual`` (unless already set)
    so the backend stamps and queries the collection with the same model
    that produced the vectors.
    """
    from scripts.zammad_mcp.client import ZammadClient, ZammadError

    if not os.environ.get("ZAMMAD_API_TOKEN", "").strip():
        raise SystemExit("zammad error: ZAMMAD_API_TOKEN is not set")
    if max_tickets is not None and max_tickets < 1:
        raise SystemExit("zammad error: --max-tickets must be a positive integer")
    client = ZammadClient()
    try:
        tickets = client.list_tickets()
    except ZammadError as exc:
        raise SystemExit(f"zammad error: {exc}") from exc
    capped_at_500 = max_tickets is None and len(tickets) == 500
    if max_tickets is not None:
        tickets = tickets[:max_tickets]
    chunks: list[Any] = []
    resolved: dict[int, str] = {}
    failures = 0
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
        chunks.extend(
            build_ticket_chunks(ticket, articles, customer_name, snapshot_date=snapshot_date)
        )
    summary: dict[str, Any] = {
        "index": index_name,
        "tickets_scanned": len(tickets),
        "capped_at_500": capped_at_500,
        "ticket_failures": failures,
        "chunks": len(chunks),
        "snapshot_date": snapshot_date,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    if dry_run or not chunks:
        return summary
    from digisearch.embedding.factory import wrap_embedding_pipeline
    from digisearch.embedding.providers.multilingual import get_default_multilingual_embedder
    from digisearch.pipeline.ingest import index_chunks

    provider = wrap_embedding_pipeline(get_default_multilingual_embedder(), use_cache=False)
    # Pin the provider for the backend too: route_add_chunks re-resolves it
    # from env, and an unset default (minilm) would stamp the collection
    # with the wrong model id and embed queries in the wrong space.
    # Scoped + restored so the one-shot leaves no process-global side effects.
    previous_provider = os.environ.get("DIGISEARCH_EMBEDDING_PROVIDER")
    os.environ.setdefault("DIGISEARCH_EMBEDDING_PROVIDER", "multilingual")
    try:
        index_chunks(index_name, chunks, embedding_provider=provider)
    finally:
        if previous_provider is None:
            os.environ.pop("DIGISEARCH_EMBEDDING_PROVIDER", None)
        else:
            os.environ["DIGISEARCH_EMBEDDING_PROVIDER"] = previous_provider
    return summary


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: ``python -m scripts.index_occ_tickets [--dry-run]``."""
    parser = argparse.ArgumentParser(description="Backfill Zammad tickets into occ_tickets")
    parser.add_argument("--index", default=DEFAULT_INDEX, help="Target index name")
    parser.add_argument("--max-tickets", type=int, default=None, help="Cap ticket count")
    parser.add_argument("--dry-run", action="store_true", help="Build chunks, skip indexing")
    parser.add_argument("--snapshot-date", default=SNAPSHOT_DATE, help="Snapshot label")
    args = parser.parse_args(argv)
    summary = backfill(
        index_name=args.index,
        max_tickets=args.max_tickets,
        dry_run=args.dry_run,
        snapshot_date=args.snapshot_date,
    )
    print(
        f"occ_tickets backfill: {summary['chunks']} chunk(s) from "
        f"{summary['tickets_scanned']} ticket(s) "
        f"({summary['ticket_failures']} failures) -> {summary['index']} "
        f"[snapshot {summary['snapshot_date']}]" + (" (dry run)" if args.dry_run else "")
    )


if __name__ == "__main__":  # pragma: no cover
    main()
