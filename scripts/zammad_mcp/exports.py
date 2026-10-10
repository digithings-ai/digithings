"""Large ticket-result exports for the OCC help chat (DIG-2638).

A retrieval that returns more rows than ``EXPORT_ROW_LIMIT`` must not put those
rows in front of the model.  The full set is written to a spool directory in
this container and only metadata travels back through the MCP response: count,
id list, date range, state/priority/group histograms and field coverage.  The
file itself is served by :mod:`scripts.zammad_mcp.export_server` on the
container's :8771, which the Cloudflare Worker proxies under the *same*
fail-closed ``x-digi-mcp-key`` edge gate as the tools themselves
(``zammad-export`` in the Worker's ``MCP_EDGE_SERVERS`` map).  A download link
therefore works for exactly the callers that can already reach ``search_tickets``.

The spool is deliberately container-local: this container holds no object-store
credential, and adding one would put a second secret inside the very thing the
OCC invite-key gate protects.  The export id is an unguessable token, not an
authorisation -- authorisation is the edge gate in front of the download route.

Both formats are written under one id (``<id>.json`` and ``<id>.csv``) plus a
small ``<id>.meta.json`` manifest that carries the expiry and the metadata the
model sees, so the download route can answer from the manifest alone.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scripts.zammad_mcp.formatting import _counts_line, _field, _parse_timestamp

#: Rows above this count go to an export instead of the model.  25 mirrors
#: ``MAX_TICKETS`` in the Worker's market-data handler, so both surfaces cap the
#: model-visible set at the same size.
EXPORT_ROW_LIMIT = 25

#: Default lifetime of a download, in seconds (24h).
EXPORT_TTL_SECONDS = 24 * 60 * 60

#: Ids listed in the model-visible summary.  A 500-row retrieval would otherwise
#: push ~5 KB of bare numbers into the context, which is the thing this module
#: exists to prevent; the rest are in the download and the summary says so.
EXPORT_ID_LIST_LIMIT = 200

#: Fields the coverage line reports, in this order.  Any other key a row carries
#: still reaches the JSON/CSV export -- this only bounds the summary.
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

HISTOGRAM_FIELDS = ("state", "priority", "group")

EXPORT_FORMATS = ("json", "csv")

EXPORT_ID_RE = re.compile(r"\A[0-9a-f]{32}\Z")

DEFAULT_SPOOL_DIR = "/var/tmp/zammad-exports"


class ExportError(Exception):
    """Base class for export failures."""


class ExportNotFound(ExportError):
    """No export exists under that id."""


class ExportExpired(ExportError):
    """The export existed but its TTL has passed."""


def spool_dir() -> Path:
    """Directory holding the exports.  ``ZAMMAD_EXPORT_DIR`` overrides it."""
    return Path(os.environ.get("ZAMMAD_EXPORT_DIR") or DEFAULT_SPOOL_DIR)


def ttl_seconds() -> int:
    """Export lifetime.  ``ZAMMAD_EXPORT_TTL_SECONDS`` overrides the 24h default."""
    raw = os.environ.get("ZAMMAD_EXPORT_TTL_SECONDS")
    if raw is None or not str(raw).strip():
        return EXPORT_TTL_SECONDS
    try:
        value = int(str(raw).strip())
    except ValueError:
        return EXPORT_TTL_SECONDS
    return value if value > 0 else EXPORT_TTL_SECONDS


def new_export_id() -> str:
    """Unguessable, filename-safe token.  This is a locator, not a credential."""
    return secrets.token_hex(16)


def is_valid_export_id(export_id: str) -> bool:
    """True for ids this module is willing to touch on disk.

    The hex-only alphabet is the path-traversal guard: ``..``, ``/`` and
    friends cannot pass, so a hostile id cannot escape the spool directory.
    """
    return bool(EXPORT_ID_RE.match(export_id or ""))


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


def _write_atomic(path: Path, payload: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def export_paths(export_id: str, directory: Path | None = None) -> dict[str, Path]:
    """Manifest and payload paths for one id.  Callers must validate the id."""
    base = directory or spool_dir()
    return {
        "meta": base / f"{export_id}.meta.json",
        "json": base / f"{export_id}.json",
        "csv": base / f"{export_id}.csv",
    }


def write_export(
    tickets: list[dict[str, Any]],
    *,
    tool: str,
    query: str = "",
    directory: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Write the full set to the spool and return its manifest.

    Returns the manifest dict; the caller renders *metadata only* from it.  The
    full rows never appear in the returned structure, so a caller that only
    renders the manifest cannot leak them by accident.
    """
    rows = list(tickets or [])
    if not rows:
        raise ExportError("refusing to write an empty export")

    export_id = new_export_id()
    base = directory or spool_dir()
    base.mkdir(parents=True, exist_ok=True)
    paths = export_paths(export_id, base)

    created = now or datetime.now(timezone.utc)
    expires = created + timedelta(seconds=ttl_seconds())

    manifest = {
        "export_id": export_id,
        "tool": tool,
        "query": query,
        "created_at": created.isoformat(),
        "expires_at": expires.isoformat(),
        "ttl_seconds": ttl_seconds(),
        "formats": list(EXPORT_FORMATS),
        "summary": summarize(rows),
    }

    _write_atomic(
        paths["json"], json.dumps(rows, indent=2, sort_keys=True, default=str).encode("utf-8")
    )
    _write_atomic(paths["csv"], _csv_bytes(rows))
    _write_atomic(paths["meta"], json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))
    return manifest


def download_path(export_id: str) -> str:
    """Worker-relative download path, behind the same edge gate as the tools."""
    return f"/_stack/mcp/zammad-export/{export_id}"


def render_metadata_only(manifest: dict[str, Any], *, sample: list[str] | None = None) -> str:
    """The model-visible string: metadata plus the download path, never the rows."""
    summary = manifest.get("summary") or {}
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
        lines.append(f"  ... and {omitted} more id(s), all present in the download.")

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

    expires_at = manifest.get("expires_at") or "unknown"
    lines.extend(
        [
            "",
            f"Full set (JSON and CSV): {download_path(manifest.get('export_id'))}",
            "  The link needs the same OCC invite-key credential as these tools and "
            f"expires at {expires_at}.",
            "  Quote numbers from the metadata above, or fetch a single ticket with "
            "get_ticket; do not claim to have read the rows you were not given.",
        ]
    )
    return "\n".join(lines)


def load_export(
    export_id: str,
    fmt: str = "json",
    *,
    directory: Path | None = None,
    now: datetime | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Read one export, enforcing the TTL at read time.

    Raises ExportNotFound for an unknown id and ExportExpired once the TTL has
    passed -- the download route maps those to 404 and 410 respectively.
    """
    if not is_valid_export_id(export_id):
        raise ExportNotFound(f"malformed export id: {export_id!r}")
    if fmt not in EXPORT_FORMATS:
        raise ExportNotFound(f"unsupported export format: {fmt!r}")

    paths = export_paths(export_id, directory)
    try:
        manifest = json.loads(paths["meta"].read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExportNotFound(f"no export {export_id}") from exc

    reference = now or datetime.now(timezone.utc)
    expires_raw = str(manifest.get("expires_at") or "")
    try:
        expires = datetime.fromisoformat(expires_raw)
    except ValueError as exc:
        raise ExportNotFound(f"export {export_id} has no usable expiry") from exc
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if reference >= expires:
        raise ExportExpired(f"export {export_id} expired at {expires_raw}")

    payload = paths[fmt]
    try:
        return payload.read_bytes(), manifest
    except OSError as exc:
        raise ExportNotFound(f"export {export_id} has no {fmt} payload") from exc


def purge_expired(*, directory: Path | None = None, now: datetime | None = None) -> int:
    """Delete expired exports.  Returns how many were removed."""
    base = directory or spool_dir()
    if not base.is_dir():
        return 0
    reference = now or datetime.now(timezone.utc)
    removed = 0
    for manifest_path in base.glob("*.meta.json"):
        export_id = manifest_path.name[: -len(".meta.json")]
        if not is_valid_export_id(export_id):
            continue
        try:
            load_export(export_id, "json", directory=base, now=reference)
        except ExportExpired:
            for path in export_paths(export_id, base).values():
                try:
                    path.unlink()
                except OSError:
                    pass
            removed += 1
        except ExportError:
            continue
    return removed
