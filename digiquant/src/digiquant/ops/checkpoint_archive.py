"""Checkpoint payload archive: Supabase stays metadata-light, blobs live in R2 (#3761).

LangGraph's PostgresSaver snapshots full channel state per step, so two daily
runs hold ~200MB of ``bytea`` in ``checkpoint_blobs`` / ``checkpoint_writes``.
The offline archiver copies each payload to external object storage (verified
by SHA-256 read-back), then NULLs the ``bytea`` column. Metadata rows stay —
the tables become the lightweight index they were meant to be — and
:func:`restore_thread` reinserts payloads when forensics need the full trace.

The live checkpointer path is untouched; resume semantics are byte-identical
because archived-then-restored rows equal the originals.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

from digiquant.dashboard.tenancy import house_workspace_id

logger = logging.getLogger(__name__)

BLOB_TABLES = ("checkpoint_blobs", "checkpoint_writes")

# R2 key prefixes owned by this archiver. Market-data generations
# (``market-data/...``) share the bucket but are indexed by the
# R2HistoryStore manifest — eviction and reconciliation must never touch
# them (#3780).
MANAGED_PREFIXES = ("checkpoints/", "documents/")

# Key columns identifying one payload row per table (tables carry no PK).
BLOB_KEY_COLUMNS: dict[str, tuple[str, ...]] = {
    "checkpoint_blobs": ("thread_id", "checkpoint_ns", "channel", "version"),
    "checkpoint_writes": ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"),
}
DOCUMENT_KEY_COLUMNS = ("workspace_id", "document_key", "date")
# PostgREST caps one response page at 1000 rows: key scans must page explicitly.
DOC_SCAN_PAGE_SIZE = 1000
# Every table the archiver may read by key (DirectPostgresReader validates here).
KEY_COLUMNS_BY_TABLE: dict[str, tuple[str, ...]] = {
    **BLOB_KEY_COLUMNS,
    "documents": DOCUMENT_KEY_COLUMNS,
}


class ArchiveVerifyError(RuntimeError):
    """Read-back hash mismatch — the Supabase row is left untouched."""


class ArchiveNotFoundError(RuntimeError):
    """No pointer row — caller should read Supabase directly."""


DICT_VERSION = 1


def compress_payload(data: bytes) -> bytes:
    import zstandard as zstd

    return bytes([DICT_VERSION]) + zstd.compress(data, level=3)


def decompress_payload(blob: bytes) -> bytes:
    import zstandard as zstd

    if not blob or blob[0] != DICT_VERSION:
        raise ArchiveVerifyError(f"unsupported archive dict version: {blob[:1]!r}")
    return zstd.decompress(blob[1:])


def resolve_payload(
    client: Any, store: StorageBackend, source_table: str, source_key: dict[str, Any]
) -> bytes:
    """Read-through: pointer → R2 GET → sha256 verify → decompress.

    Raises :class:`ArchiveNotFoundError` when no pointer row exists — the
    caller is expected to have already checked Supabase directly.
    """
    query = client.table("archive_objects").select("*").eq("source_table", source_table)
    for col, val in source_key.items():
        query = query.eq(f"source_key->>{col}", val)
    rows = query.execute().data or []
    if not rows:
        raise ArchiveNotFoundError(f"no archive pointer for {source_table} {source_key}")
    row = rows[0]
    blob = store.get(row["r2_key"])
    if hashlib.sha256(blob).hexdigest() != row["sha256"]:
        raise ArchiveVerifyError(f"stored object corrupted: {row['r2_key']}")
    return decompress_payload(blob)


class StorageBackend(Protocol):
    """Object-store surface the archiver needs (R2, or a fake in tests)."""

    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def list_keys(self, prefix: str) -> list[str]: ...


HIGH_WATERMARK_BYTES = 8_500_000_000
LOW_WATERMARK_BYTES = 7_000_000_000


def bucket_usage(client: Any) -> int:
    """Sum of archived bytes per the ``archive_objects`` ledger."""
    rows = client.table("archive_objects").select("size").execute().data or []
    return sum(int(r.get("size") or 0) for r in rows)


def evict_to_watermark(
    client: Any, store: StorageBackend, latest_keys: set[str] | None = None
) -> list[str]:
    """Delete oldest-first until usage <= low watermark; never evict *latest_keys*."""
    protected = latest_keys or set()
    if bucket_usage(client) <= HIGH_WATERMARK_BYTES:
        return []
    rows = client.table("archive_objects").select("*").order("archived_at").execute().data or []
    evicted: list[str] = []
    for row in rows:
        if bucket_usage(client) <= LOW_WATERMARK_BYTES:
            break
        if row["r2_key"] in protected:
            continue
        if not row["r2_key"].startswith(MANAGED_PREFIXES):
            continue  # market-data generations are namespaced apart; never evict
        store.delete(row["r2_key"])
        client.table("archive_objects").delete().eq("r2_key", row["r2_key"]).execute()
        evicted.append(row["r2_key"])
        logger.info("evicted %s (%s bytes)", row["r2_key"], row["size"])
    return evicted


def reconcile_ledger(client: Any, store: StorageBackend) -> list[str]:
    """Drop dead managed ledger rows; report orphans + dead market-data pointers.

    Orphan R2 objects (present in the bucket, absent from the ledger) are
    reported for operator review — never auto-deleted. Only the archiver's
    own ``checkpoints/`` + ``documents/`` prefixes are in scope; market-data
    generations are indexed by the R2HistoryStore manifest instead (#3780).

    Dead market-data ledger rows (no backing object) are never auto-deleted
    either — their lifecycle belongs to the market-data tasks — but they are
    reported as orphans (same ``list[str]`` shape) so they stay visible.
    """
    ledger_keys = {
        r["r2_key"]
        for r in (client.table("archive_objects").select("r2_key").execute().data or [])
        if r.get("r2_key")
    }
    managed_keys = {k for k in ledger_keys if k.startswith(MANAGED_PREFIXES)}
    stored_keys = set(store.list_keys("checkpoints/")) | set(store.list_keys("documents/"))
    for dead in sorted(managed_keys - stored_keys):
        client.table("archive_objects").delete().eq("r2_key", dead).execute()
        logger.info("reconciled dead ledger row %s", dead)
    orphans = sorted(stored_keys - managed_keys)
    market_rows = sorted(k for k in ledger_keys - managed_keys if k.startswith("market-data/"))
    dead_market: list[str] = []
    if market_rows:
        stored_market = set(store.list_keys("market-data/"))
        dead_market = sorted(k for k in market_rows if k not in stored_market)
    return sorted(orphans + dead_market)


def parse_postgrest_bytea(value: Any) -> bytes | None:
    """Decode a PostgREST ``bytea`` cell: hex ``\\x…`` string or raw bytes."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    text = str(value)
    if text.startswith("\\x"):
        return bytes.fromhex(text[2:])
    return text.encode("utf-8")


def blob_key(thread_id: str, table: str, channel: str, version: str) -> str:
    """R2 object key layout: ``checkpoints/<thread>/<table>/<channel>/<version>.bin``."""
    return f"checkpoints/{thread_id}/{table}/{channel}/{version}.bin"


@dataclass(frozen=True)
class ArchiveEntry:
    key: str
    sha256: str
    size: int
    filters: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class ArchiveManifest:
    thread_id: str
    entries: tuple[ArchiveEntry, ...] = ()
    archived_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "archived_at": self.archived_at,
            "entries": [
                {
                    "key": e.key,
                    "sha256": e.sha256,
                    "size": e.size,
                    "filters": [[c, v] for c, v in e.filters],
                }
                for e in self.entries
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArchiveManifest":
        return cls(
            thread_id=str(payload["thread_id"]),
            archived_at=str(payload.get("archived_at") or ""),
            entries=tuple(
                ArchiveEntry(
                    key=e["key"],
                    sha256=e["sha256"],
                    size=int(e["size"]),
                    filters=tuple((c, v) for c, v in (e.get("filters") or [])),
                )
                for e in payload.get("entries") or []
            ),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _thread_max_ts(checkpoint: Any) -> datetime | None:
    """Parse a checkpoints-row ``checkpoint`` jsonb payload's ``ts`` field."""
    ts = checkpoint.get("ts") if isinstance(checkpoint, dict) else None
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(str(ts))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def threads_older_than(client: Any, retain_days: int) -> list[str]:
    """Threads whose newest checkpoint is older than *retain_days* (archive candidates)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retain_days)
    rows = client.table("checkpoints").select("thread_id,checkpoint").execute().data or []
    newest: dict[str, datetime] = {}
    for row in rows:
        thread_id = row.get("thread_id")
        if not thread_id:
            continue
        ts = _thread_max_ts(row.get("checkpoint"))
        if ts is not None and (thread_id not in newest or ts > newest[thread_id]):
            newest[thread_id] = ts
    return sorted(t for t, ts in newest.items() if ts < cutoff)


def list_threads(client: Any) -> list[str]:
    """Distinct checkpoint thread ids (one per graph run)."""
    rows = client.table("checkpoints").select("thread_id").execute().data or []
    return sorted({str(row["thread_id"]) for row in rows if row.get("thread_id")})


def previous_threads(client: Any, owner: str = "house") -> list[str]:
    """All threads except the newest — Supabase keeps the latest run per owner."""
    _ = owner  # owner scoping lands with multi-user threads; single house owner today
    rows = client.table("checkpoints").select("thread_id,checkpoint").execute().data or []
    newest: dict[str, datetime] = {}
    for row in rows:
        thread_id = row.get("thread_id")
        if not thread_id:
            continue
        ts = _thread_max_ts(row.get("checkpoint")) or datetime.min.replace(tzinfo=timezone.utc)
        if thread_id not in newest or ts > newest[thread_id]:
            newest[thread_id] = ts
    if not newest:
        return []
    latest = max(newest, key=lambda t: newest[t])
    return sorted(t for t in newest if t != latest)


def _row_version(table: str, row: dict[str, Any]) -> str:
    if table == "checkpoint_blobs":
        return f"{row.get('channel')}/{row.get('version')}"
    return f"{row.get('checkpoint_id')}/{row.get('task_id')}/{row.get('idx')}"


def _row_filters(table: str, row: dict[str, Any]) -> list[tuple[str, Any]]:
    return [(col, row.get(col)) for col in BLOB_KEY_COLUMNS[table]]


def _jsonable(value: Any) -> Any:
    """Coerce direct-Postgres native types to the JSON strings PostgREST returns.

    psycopg yields ``datetime.date``/``datetime`` and ``uuid.UUID`` objects
    where the PostgREST path yields ISO strings; the registry insert body is
    JSON-encoded, so normalize at this choke point for both callers.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _insert_pointer(
    client: Any,
    source_table: str,
    source_key: dict[str, Any],
    r2_key: str,
    sha256: str,
    size: int,
    owner: str,
) -> None:
    """Idempotent ``archive_objects`` insert; raises before any Supabase mutate.

    Re-recording identical bytes is a no-op so a retried run converges; the
    same key with different bytes raises so the Supabase row is kept.
    """
    existing = (
        client.table("archive_objects").select("r2_key,sha256").eq("r2_key", r2_key).execute().data
        or []
    )
    for pointer in existing:
        if pointer.get("sha256") == sha256:
            return
        raise ArchiveVerifyError(f"archive pointer conflict for {r2_key}: Supabase row kept")
    client.table("archive_objects").insert(
        {
            "source_table": source_table,
            "source_key": {key: _jsonable(val) for key, val in source_key.items()},
            "r2_key": r2_key,
            "sha256": sha256,
            "size": size,
            "owner": owner,
        }
    ).execute()


def record_pointer(client: Any, entry: ArchiveEntry, owner: str = "house") -> None:
    """Insert one ``archive_objects`` pointer row; raises before any NULL-ing.

    ``source_table`` is the stable key segment (``checkpoints/<thread>/<table>/...``),
    ``source_key`` the row filters as a JSON object. A failed insert propagates to
    the caller so the Supabase row is kept. Re-recording identical bytes is a
    no-op so a retried run converges; the same key with different bytes raises.
    """
    _insert_pointer(
        client,
        entry.key.split("/")[2],
        dict(entry.filters),
        entry.key,
        entry.sha256,
        entry.size,
        owner,
    )


try:  # Optional: only needed for the live direct-Postgres read path.
    from psycopg.rows import dict_row as _dict_row
except ImportError:  # Test doubles and PostgREST-only installs land here.
    _dict_row = None


def _psycopg_connect(uri: str) -> Any:
    """Open a direct Postgres connection; deferred import keeps the base install lean."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "psycopg is required for direct Postgres reads "
            "(install the digiquant research extra: pip install 'digiquant[research]')"
        ) from exc
    return psycopg.connect(uri)


class DirectPostgresReader:
    """Fetch payload rows over a direct Postgres connection.

    Every PostgREST statement runs under the authenticator role's 8s
    ``statement_timeout`` — large checkpoint blobs can never transfer that
    way. This reader runs the same single-row SELECTs over a direct
    connection (the path LangGraph's PostgresSaver writes through), where
    the database-level timeout applies.
    """

    def __init__(self, uri: str, connect: Any = None) -> None:
        self._uri = uri
        self._connect = connect or _psycopg_connect
        self._conn: Any = None

    def fetch_row(self, table: str, key: dict[str, Any]) -> dict[str, Any]:
        """Fetch exactly one row by full key; raises on any other count."""
        if table not in KEY_COLUMNS_BY_TABLE:
            raise ArchiveVerifyError(f"refusing direct read of unexpected table {table!r}")
        key_cols = KEY_COLUMNS_BY_TABLE[table]
        predicate = " AND ".join(f'"{col}" IS NOT DISTINCT FROM %s' for col in key_cols)
        sql = f'SELECT * FROM "{table}" WHERE {predicate}'
        params = tuple(key.get(col) for col in key_cols)
        if self._conn is None:
            self._conn = self._connect(self._uri)
        kwargs = {"row_factory": _dict_row} if _dict_row is not None else {}
        cur = self._conn.cursor(**kwargs)
        cur.execute(sql, params)
        rows = cur.fetchall()
        if len(rows) != 1:
            raise ArchiveVerifyError(
                f"expected 1 row for {table} {key}, found {len(rows)}; Supabase row kept"
            )
        return dict(rows[0])

    def close(self) -> None:
        """Close the underlying connection; safe to call more than once."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# Portfolio blob rows reach ~16MB each, so even small multi-row pages can exceed
# the Supabase statement timeout (prod 57014). Fetch in two phases: one key-only
# scan (tiny rows), then one single-row statement per payload row — each
# statement carries at most one row, the minimum PostgREST can transfer.
# Payload rows that large still exceed PostgREST's 8s authenticator timeout, so
# callers pass a DirectPostgresReader to fetch phase-2 rows directly instead.
def _fetch_thread_rows(
    client: Any, table: str, thread_id: str, payload_reader: Any = None
) -> list[dict[str, Any]]:
    """Fetch one thread's rows: key-only scan, then one single-row fetch per key.

    When ``payload_reader`` is given, payload rows come from it (direct
    Postgres); otherwise each payload row is a PostgREST single-row fetch.
    """
    key_cols = BLOB_KEY_COLUMNS[table]
    keys = (
        client.table(table).select(",".join(key_cols)).eq("thread_id", thread_id).execute().data
        or []
    )
    rows: list[dict[str, Any]] = []
    for key in keys:
        if payload_reader is not None:
            rows.append(payload_reader.fetch_row(table, key))
            continue
        query = client.table(table).select("*")
        for col in key_cols:
            query = query.eq(col, key.get(col))
        matches = query.execute().data or []
        if len(matches) != 1:
            raise ArchiveVerifyError(
                f"expected 1 row for {table} {key}, found {len(matches)}; Supabase row kept"
            )
        rows.append(matches[0])
    return rows


def archive_thread(
    client: Any,
    store: StorageBackend,
    thread_id: str,
    owner: str = "house",
    payload_reader: Any = None,
) -> ArchiveManifest:
    """Offload one thread's payloads: compress → put → verify → registry → NULL the ``bytea`` cell.

    Rows already NULL are skipped. Any verification failure raises
    :class:`ArchiveVerifyError` before touching Supabase, so a corrupt upload
    can never orphan a trace. A registry-insert failure raises before the NULL
    update, so the Supabase row is kept.
    """
    entries: list[ArchiveEntry] = []
    for table in BLOB_TABLES:
        rows = _fetch_thread_rows(client, table, thread_id, payload_reader=payload_reader)
        for row in rows:
            payload = parse_postgrest_bytea(row.get("blob"))
            if payload is None:
                continue
            key = blob_key(thread_id, table, str(row.get("channel")), _row_version(table, row))
            stored = compress_payload(payload)
            digest = hashlib.sha256(stored).hexdigest()
            store.put(key, stored)
            if hashlib.sha256(store.get(key)).hexdigest() != digest:
                raise ArchiveVerifyError(f"read-back mismatch for {key}; Supabase row kept")
            entry = ArchiveEntry(
                key=key, sha256=digest, size=len(stored), filters=tuple(_row_filters(table, row))
            )
            record_pointer(client, entry, owner)
            query = client.table(table).update({"blob": None})
            filters = _row_filters(table, row)
            for col, val in filters:
                query = query.eq(col, val)
            query.execute()
            entries.append(entry)
            logger.info("archived %s (%d bytes)", key, len(stored))
    return ArchiveManifest(thread_id=thread_id, entries=tuple(entries), archived_at=_now_iso())


def _payload_bytes(payload: Any) -> bytes:
    """Canonical bytes for a document payload (JSONB arrives as dict/list)."""
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def document_key(workspace: str, date: str, key: str) -> str:
    """R2 object key layout: ``documents/<workspace>/<date>/<key>.zst``."""
    return f"documents/{workspace}/{date}/{key}.zst"


def archive_documents(
    client: Any,
    store: StorageBackend,
    workspace: str,
    owner: str = "house",
    payload_reader: Any = None,
) -> int:
    """Offload older document versions: compress → put → verify → registry → NULL the payload cell.

    Groups ``documents`` rows by ``document_key`` within *workspace*, keeps the
    newest ``date`` live, and archives every older version. The 58MB table is
    never pulled whole: one key-only scan first, then one single-row fetch per
    older version (via ``payload_reader`` when given, else PostgREST). Rows
    already NULL (prior pointers) are skipped. Any verification failure raises
    :class:`ArchiveVerifyError` before touching Supabase, and a
    registry-insert failure raises before the NULL update, so a failed
    archive always keeps the Supabase row.
    """
    key_cols = DOCUMENT_KEY_COLUMNS
    # Page explicitly: PostgREST silently caps one response at 1000 rows.
    key_rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = (
            client.table("documents")
            .select(",".join(key_cols))
            .eq("workspace_id", workspace)
            .range(offset, offset + DOC_SCAN_PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        key_rows.extend(page)
        if len(page) < DOC_SCAN_PAGE_SIZE:
            break
        offset += DOC_SCAN_PAGE_SIZE
    groups: dict[str, list[dict[str, Any]]] = {}
    for key_row in key_rows:
        groups.setdefault(key_row.get("document_key"), []).append(key_row)
    archived = 0
    for key, versions in groups.items():
        versions.sort(key=lambda r: str(r.get("date")))
        for key_row in versions[:-1]:
            row_key = {col: key_row.get(col) for col in key_cols}
            if payload_reader is not None:
                row = payload_reader.fetch_row("documents", row_key)
            else:
                query = client.table("documents").select("*")
                for col, val in row_key.items():
                    query = query.eq(col, val)
                matches = query.execute().data or []
                if len(matches) != 1:
                    raise ArchiveVerifyError(
                        f"expected 1 row for documents {row_key}, found {len(matches)}; "
                        "Supabase row kept"
                    )
                row = matches[0]
            if row.get("payload") is None:
                continue
            r2_key = document_key(workspace, str(row.get("date")), str(key))
            stored = compress_payload(_payload_bytes(row["payload"]))
            digest = hashlib.sha256(stored).hexdigest()
            store.put(r2_key, stored)
            if hashlib.sha256(store.get(r2_key)).hexdigest() != digest:
                raise ArchiveVerifyError(f"read-back mismatch for {r2_key}; Supabase row kept")
            _insert_pointer(
                client,
                "documents",
                {
                    "workspace_id": workspace,
                    "document_key": key,
                    "date": row.get("date"),
                },
                r2_key,
                digest,
                len(stored),
                owner,
            )
            query = client.table("documents").update({"payload": None})
            for col, val in (
                ("workspace_id", workspace),
                ("document_key", key),
                ("date", row.get("date")),
            ):
                query = query.eq(col, val)
            query.execute()
            archived += 1
            logger.info("archived %s (%d bytes)", r2_key, len(stored))
    return archived


def restore_thread(client: Any, store: StorageBackend, manifest: ArchiveManifest) -> None:
    """Reinsert archived payloads from *manifest* (forensics path)."""
    for entry in manifest.entries:
        parts = entry.key.split("/")
        # checkpoints/<thread>/<table>/... — table is the stable segment.
        table = parts[2]
        stored = store.get(entry.key)
        if hashlib.sha256(stored).hexdigest() != entry.sha256:
            raise ArchiveVerifyError(f"stored object corrupted: {entry.key}")
        payload = decompress_payload(stored)
        query = client.table(table).update({"blob": payload})
        for col, val in entry.filters:
            query = query.eq(col, val)
        query.execute()
        logger.info("restored %s (%d bytes)", entry.key, len(payload))


@dataclass
class R2Backend:
    """S3-compatible object store (Cloudflare R2); boto3 imported on first use."""

    endpoint_url: str
    bucket: str
    access_key: str
    secret_key: str
    _client: Any = field(default=None, repr=False)

    def _s3(self) -> Any:
        if self._client is None:
            import boto3  # deferred — archiver-only dependency

            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
        return self._client

    def put(self, key: str, data: bytes) -> None:
        import io

        self._s3().upload_fileobj(io.BytesIO(data), self.bucket, key)

    def get(self, key: str) -> bytes:
        import io

        buf = io.BytesIO()
        self._s3().download_fileobj(self.bucket, key, buf)
        return buf.getvalue()

    def delete(self, key: str) -> None:
        self._s3().delete_object(Bucket=self.bucket, Key=key)

    def list_keys(self, prefix: str) -> list[str]:
        paginator = self._s3().get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", ()):
                keys.append(obj["Key"])
        return sorted(keys)


__all__ = [
    "DICT_VERSION",
    "ArchiveEntry",
    "ArchiveManifest",
    "ArchiveNotFoundError",
    "ArchiveVerifyError",
    "BLOB_KEY_COLUMNS",
    "BLOB_TABLES",
    "DOCUMENT_KEY_COLUMNS",
    "DOC_SCAN_PAGE_SIZE",
    "DirectPostgresReader",
    "HIGH_WATERMARK_BYTES",
    "KEY_COLUMNS_BY_TABLE",
    "LOW_WATERMARK_BYTES",
    "MANAGED_PREFIXES",
    "PG_URI_ENV",
    "R2Backend",
    "StorageBackend",
    "archive_thread",
    "archive_documents",
    "blob_key",
    "bucket_usage",
    "compress_payload",
    "decompress_payload",
    "document_key",
    "evict_to_watermark",
    "list_threads",
    "main",
    "parse_postgrest_bytea",
    "previous_threads",
    "reconcile_ledger",
    "record_pointer",
    "resolve_payload",
    "restore_thread",
    "threads_older_than",
]


R2_ACCOUNT_ENV = "R2_ACCOUNT_ID"
R2_BUCKET_ENV = "R2_BUCKET"
R2_ACCESS_KEY_ENV = "R2_ACCESS_KEY_ID"
R2_SECRET_KEY_ENV = "R2_SECRET_ACCESS_KEY"
PG_URI_ENV = "DIGI_CHECKPOINTER_POSTGRES_URI"


def _r2_backend_from_env() -> R2Backend | None:
    """Build the R2 backend from env; ``None`` when any var is missing."""
    import os

    account = (os.environ.get(R2_ACCOUNT_ENV) or "").strip()
    bucket = (os.environ.get(R2_BUCKET_ENV) or "").strip()
    access = (os.environ.get(R2_ACCESS_KEY_ENV) or "").strip()
    secret = (os.environ.get(R2_SECRET_KEY_ENV) or "").strip()
    if not (account and bucket and access and secret):
        return None
    endpoint = f"https://{account}.r2.cloudflarestorage.com"
    return R2Backend(endpoint_url=endpoint, bucket=bucket, access_key=access, secret_key=secret)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``--dry-run`` lists threads; otherwise archives all but ``--keep``.

    Returns 0 on success, 2 when credentials (Supabase, R2, or direct
    Postgres) are missing.
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list threads, change nothing")
    parser.add_argument(
        "--keep",
        action="append",
        default=[],
        help="thread id to keep (repeatable; archived threads are skipped)",
    )
    parser.add_argument("--manifest-out", default=None, help="write manifests JSON here")
    parser.add_argument(
        "--retain-days",
        type=int,
        default=None,
        help="archive only threads whose newest checkpoint is older than N days",
    )
    parser.add_argument("--owner", default="house", help="owner tag for registry rows")
    parser.add_argument(
        "--workspace",
        default=None,
        help="documents workspace id to archive (default: house workspace)",
    )
    args = parser.parse_args(argv)

    from digiquant.data.store.client import build_digiquant_client

    client = build_digiquant_client()
    if client is None:
        print("missing Supabase credentials; set CORE_SUPABASE_URL/CORE_SUPABASE_SERVICE_KEY")
        return 2
    # Archive set: previous runs only — the newest thread is never archived by a
    # run (it becomes "previous" on the next run). --keep/--retain-days further
    # restrict, never widen.
    threads = previous_threads(client, args.owner)
    keep = set(args.keep)
    if args.retain_days is not None:
        fresh = set(threads_older_than(client, args.retain_days))
        keep |= set(threads) - fresh
    if args.dry_run:
        for thread_id in threads:
            if thread_id in keep:
                continue
            print(thread_id)
        return 0
    store = _r2_backend_from_env()
    if store is None:
        print(
            "missing R2 credentials; set R2_ACCOUNT_ID/R2_BUCKET/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY"
        )
        return 2
    pg_uri = (os.environ.get(PG_URI_ENV) or "").strip()
    if not pg_uri:
        print(f"missing direct Postgres URI; set {PG_URI_ENV}")
        return 2
    manifests: list[dict[str, Any]] = []
    fresh_keys: set[str] = set()
    reader = DirectPostgresReader(pg_uri)
    try:
        for thread_id in threads:
            if thread_id in keep:
                continue
            manifest = archive_thread(client, store, thread_id, args.owner, payload_reader=reader)
            manifests.append(manifest.to_dict())
            fresh_keys.update(entry.key for entry in manifest.entries)
            print(f"archived {thread_id}: {len(manifest.entries)} payloads")
        docs = archive_documents(
            client,
            store,
            args.workspace or str(house_workspace_id()),
            args.owner,
            payload_reader=reader,
        )
        print(f"archived documents: {docs} payloads")
    finally:
        reader.close()
    evicted = evict_to_watermark(client, store, fresh_keys)
    for key in evicted:
        print(f"evicted {key}")
    if args.manifest_out:
        with open(args.manifest_out, "w", encoding="utf-8") as fh:
            json.dump(manifests, fh, indent=2)
    return 0
