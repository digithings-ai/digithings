"""Large ticket-result exports for the OCC help chat (DIG-2788).

A retrieval that returns more rows than ``EXPORT_ROW_LIMIT`` must not put those
rows in front of the model.  The full set becomes ONE artifact in the DigiChat
artifact store and only metadata travels back through the MCP response: count,
id list, date range, state/priority/group histograms and field coverage.

What changed from the first cut of this path, and why
----------------------------------------------------
The first version spooled the rows inside this container and served them from a
second stdlib HTTP server on :8771, behind the Worker's ``zammad-export`` edge
route, with a fixed 24h TTL.  Chris reversed that on DIG-2638:

* a fixed TTL keeps serving a link after the session that owns it is gone; the
  link is now bound to the chat session and dies with it;
* the artifact belongs in the store the rest of digichat already uses, not in a
  spool that only this process can read.

So this module no longer owns a directory, a port, a TTL or a download route.
It owns three things and nothing else:

1. the model-visible contract - :func:`summarize`, :func:`render_metadata_only`
   and :func:`_csv_bytes`, unchanged in behaviour;
2. :func:`build_artifact`, which turns a row set into the exact bytes and
   metadata ONE ``table`` artifact is made of, transport-agnostically;
3. the conversation-scoped ingest grant, which is what lets this container write
   into the store *without* gaining a storage credential.

Credential boundary
-------------------
This container holds no object-store credential and gains none.  What it is
given is a single-use **ingest grant** for one conversation, minted by digichat
for the turn and carrying no storage authority of its own: it names the
conversation the artifact must belong to, and the store rejects any write whose
conversation the caller does not own.  The grant is a capability scoped to one
write in one conversation, not a key to the object store, and it dies with the
session that issued it - the same lifetime as the link.

Expiry
------
There is deliberately no TTL constant in this file.  The artifact's lifetime is
the conversation's: the ``artifacts`` row is removed by ``ON DELETE CASCADE``
when the conversation goes, and the link stops validating when the session
stops.  Nothing here schedules, reads or writes a time-to-live.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from scripts.zammad_mcp.formatting import _counts_line, _field, _parse_timestamp

#: Rows above this count go to an artifact instead of the model.  25 mirrors
#: ``MAX_TICKETS`` in the Worker's market-data handler, so both surfaces cap the
#: model-visible set at the same size.
EXPORT_ROW_LIMIT = 25

#: Ids listed in the model-visible summary.  A 500-row retrieval would otherwise
#: push ~5 KB of bare numbers into the context, which is the thing this module
#: exists to prevent; the rest are in the artifact and the summary says so.
EXPORT_ID_LIST_LIMIT = 200

#: The columns the summary names first.  Everything else a row carries is kept,
#: sorted, after these.
SUMMARY_FIELDS = (
    "id",
    "number",
    "title",
    "state",
    "priority",
    "group",
    "customer",
    "owner",
    "created_at",
    "updated_at",
    "close_at",
)

#: Fields summarised as a histogram rather than a range or a count.
HISTOGRAM_FIELDS = ("state", "priority", "group")

#: ``kind`` on the artifact row.  ``artifacts/route.ts`` maps a .json name to the
#: same kind, so this and the store agree on what "a table" is.
ARTIFACT_KIND = "table"

#: The artifact's media type.  A .json artifact is served inline by the store's
#: ``INLINE_PREFIXES``, so the browser shows the rows rather than downloading a
#: file the user then has to open.
ARTIFACT_MEDIA_TYPE = "application/json"


class ExportError(Exception):
    """Any failure building an export.  Never carries row values."""


def ticket_ref(ticket: dict[str, Any]) -> str:
    """The id a human or ``get_ticket`` call uses, matching the list renderer."""
    return _field(ticket.get("id")) or _field(ticket.get("number")) or "?"


def _histogram(rows: list[dict[str, Any]], field: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = _field(row.get(field))
        if value:
            counter[value] += 1
    return counter


def _range_of(rows: list[dict[str, Any]], field: str) -> tuple[str, str] | None:
    """ISO bounds of a timestamp field, or None when no row carries one."""
    stamps = [(_parse_timestamp(row.get(field)), _field(row.get(field))) for row in rows]
    parsed = [(stamp, raw) for stamp, raw in stamps if stamp is not None and raw]
    if not parsed:
        return None
    earliest = min(parsed, key=lambda item: item[0])
    latest = max(parsed, key=lambda item: item[0])
    return earliest[1], latest[1]


def _coverage(rows: list[dict[str, Any]]) -> list[str]:
    """``field present in N of M rows`` lines, ordered by coverage then name."""
    total = len(rows)
    lines = []
    for field in SUMMARY_FIELDS:
        filled = sum(1 for row in rows if _field(row.get(field)))
        if filled:
            lines.append(f"  {field}: {filled}/{total}")
    return lines


def summarize(tickets: list[dict[str, Any]]) -> dict[str, Any]:
    """Everything the model is allowed to see about a large result set."""
    rows = list(tickets or [])
    refs = [ticket_ref(row) for row in rows]
    shown = refs[:EXPORT_ID_LIST_LIMIT]
    return {
        "count": len(rows),
        "ids": shown,
        "ids_shown": len(shown),
        "ids_omitted": max(0, len(refs) - len(shown)),
        "created_range": _range_of(rows, "created_at"),
        "updated_range": _range_of(rows, "updated_at"),
        "histograms": {field: dict(_histogram(rows, field)) for field in HISTOGRAM_FIELDS},
        "field_coverage": _coverage(rows),
    }


def _csv_bytes(tickets: list[dict[str, Any]]) -> bytes:
    """Union of every key across the rows, known columns first."""
    columns = [field for field in SUMMARY_FIELDS]
    extra = sorted({key for row in tickets for key in row} - set(SUMMARY_FIELDS))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns + extra, extrasaction="ignore", restval="")
    writer.writeheader()
    for row in tickets:
        flat = {}
        for key, value in row.items():
            flat[key] = (
                json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
            )
        writer.writerow(flat)
    return buffer.getvalue().encode("utf-8")


def artifact_name(tool: str) -> str:
    """The store's ``name`` for one oversized result set."""
    return f"zammad-tickets-{(tool or 'export').replace('_', '-')}.json"


def build_artifact(
    tickets: list[dict[str, Any]],
    *,
    tool: str,
    query: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Turn a row set into the ONE artifact the store will hold.

    The returned dict is exactly what an ingest needs and nothing more: a
    ``token``, ``name``, ``mediaType``, ``kind``, ``bytes`` and the
    model-visible ``summary``.  The rows live in ``bytes`` and nowhere else, so
    a caller that renders only ``summary`` cannot leak them by accident.

    Both formats the export has always produced live inside the one artifact:
    ``csv`` carries the same rows rendered as CSV, and ``json`` carries them
    rendered as JSON, under a single envelope.  One artifact, one link, both
    formats - which is what the store's one-blob-per-row shape allows.
    """
    rows = list(tickets or [])
    if not rows:
        raise ExportError("refusing to build an empty artifact")

    created = now or datetime.now(timezone.utc)
    envelope = {
        "tool": tool,
        "query": query,
        "created_at": created.isoformat(),
        "summary": summarize(rows),
        "csv": _csv_bytes(rows).decode("utf-8"),
        "json": rows,
    }
    return {
        "token": new_artifact_token(),
        "name": artifact_name(tool),
        "mediaType": ARTIFACT_MEDIA_TYPE,
        "kind": ARTIFACT_KIND,
        "bytes": json.dumps(envelope, indent=2, sort_keys=True, default=str).encode("utf-8"),
        "summary": envelope["summary"],
    }


def new_artifact_token() -> str:
    """An opaque, filename-safe token for one artifact.

    This is a locator, not a credential: it names the artifact inside a
    conversation, and the store still refuses a read from a conversation the
    caller does not own.
    """
    import secrets

    return secrets.token_hex(16)


def render_metadata_only(
    artifact: dict[str, Any],
    *,
    link: str = "",
    sample: list[str] | None = None,
) -> str:
    """The model-visible string: metadata plus the link, never the rows.

    ``artifact`` is what :func:`build_artifact` returned.  Only ``summary`` is
    read out of it, so no row value can reach the model by way of this string
    unless it is already in the summary - and the summary carries none.
    """
    summary = artifact.get("summary") or {}
    count = int(summary.get("count") or 0)
    lines = [
        f"{count} ticket(s) matched; the full set was not returned inline.",
        f"Count: {count}",
    ]

    ids = list(summary.get("ids") or [])
    if ids:
        lines.append(f"Ticket ids ({len(ids)} shown): " + ", ".join(ids))
    omitted = int(summary.get("ids_omitted") or 0)
    if omitted:
        lines.append(f"  ... and {omitted} more id(s), all present in the artifact.")

    created_range = summary.get("created_range")
    if created_range:
        lines.append(f"Created between: {created_range[0]} and {created_range[1]}")
    updated_range = summary.get("updated_range")
    if updated_range:
        lines.append(f"Last updated between: {updated_range[0]} and {updated_range[1]}")

    for field, counter in (summary.get("histograms") or {}).items():
        if counter:
            lines.append(_counts_line(field.capitalize(), Counter(counter)))

    coverage = list(summary.get("field_coverage") or [])
    if coverage:
        lines.append("Field coverage:")
        lines.extend(coverage)

    if sample:
        lines.append("First rows only (preview, not the full set):")
        lines.extend(f"  {line}" for line in sample)

    if link:
        lines.extend(
            [
                "",
                f"Full set (CSV and JSON in one artifact): {link}",
                "  The link belongs to this chat session: it stops working when the "
                "session is reloaded or ended, and needs the same OCC invite-key "
                "credential as these tools.",
                "  Quote numbers from the metadata above, or fetch a single ticket "
                "with get_ticket; do not claim to have read the rows you were not given.",
            ]
        )
    return "\n".join(lines)
