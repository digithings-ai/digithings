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
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)

BLOB_TABLES = ("checkpoint_blobs", "checkpoint_writes")

# Key columns identifying one payload row per table (tables carry no PK).
BLOB_KEY_COLUMNS: dict[str, tuple[str, ...]] = {
    "checkpoint_blobs": ("thread_id", "checkpoint_ns", "channel", "version"),
    "checkpoint_writes": ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"),
}


class ArchiveVerifyError(RuntimeError):
    """Read-back hash mismatch — the Supabase row is left untouched."""


class StorageBackend(Protocol):
    """Object-store surface the archiver needs (R2, or a fake in tests)."""

    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...


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


def _row_version(table: str, row: dict[str, Any]) -> str:
    if table == "checkpoint_blobs":
        return f"{row.get('channel')}/{row.get('version')}"
    return f"{row.get('checkpoint_id')}/{row.get('task_id')}/{row.get('idx')}"


def _row_filters(table: str, row: dict[str, Any]) -> list[tuple[str, Any]]:
    return [(col, row.get(col)) for col in BLOB_KEY_COLUMNS[table]]


def archive_thread(client: Any, store: StorageBackend, thread_id: str) -> ArchiveManifest:
    """Offload one thread's payloads: put → verify → NULL the ``bytea`` cell.

    Rows already NULL are skipped. Any verification failure raises
    :class:`ArchiveVerifyError` before touching Supabase, so a corrupt upload
    can never orphan a trace.
    """
    entries: list[ArchiveEntry] = []
    for table in BLOB_TABLES:
        rows = client.table(table).select("*").eq("thread_id", thread_id).execute().data or []
        for row in rows:
            payload = parse_postgrest_bytea(row.get("blob"))
            if payload is None:
                continue
            key = blob_key(thread_id, table, str(row.get("channel")), _row_version(table, row))
            digest = hashlib.sha256(payload).hexdigest()
            store.put(key, payload)
            if hashlib.sha256(store.get(key)).hexdigest() != digest:
                raise ArchiveVerifyError(f"read-back mismatch for {key}; Supabase row kept")
            query = client.table(table).update({"blob": None})
            filters = _row_filters(table, row)
            for col, val in filters:
                query = query.eq(col, val)
            query.execute()
            entries.append(
                ArchiveEntry(key=key, sha256=digest, size=len(payload), filters=tuple(filters))
            )
            logger.info("archived %s (%d bytes)", key, len(payload))
    return ArchiveManifest(thread_id=thread_id, entries=tuple(entries), archived_at=_now_iso())


def restore_thread(client: Any, store: StorageBackend, manifest: ArchiveManifest) -> None:
    """Reinsert archived payloads from *manifest* (forensics path)."""
    for entry in manifest.entries:
        parts = entry.key.split("/")
        # checkpoints/<thread>/<table>/... — table is the stable segment.
        table = parts[2]
        payload = store.get(entry.key)
        if hashlib.sha256(payload).hexdigest() != entry.sha256:
            raise ArchiveVerifyError(f"stored object corrupted: {entry.key}")
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


__all__ = [
    "ArchiveEntry",
    "ArchiveManifest",
    "ArchiveVerifyError",
    "BLOB_KEY_COLUMNS",
    "BLOB_TABLES",
    "R2Backend",
    "StorageBackend",
    "archive_thread",
    "blob_key",
    "list_threads",
    "main",
    "parse_postgrest_bytea",
    "restore_thread",
    "threads_older_than",
]


R2_ACCOUNT_ENV = "R2_ACCOUNT_ID"
R2_BUCKET_ENV = "R2_BUCKET"
R2_ACCESS_KEY_ENV = "R2_ACCESS_KEY_ID"
R2_SECRET_KEY_ENV = "R2_SECRET_ACCESS_KEY"


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

    Returns 0 on success, 2 when credentials (Supabase or R2) are missing.
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
    args = parser.parse_args(argv)

    from digiquant.data.store.client import build_digiquant_client

    client = build_digiquant_client()
    if client is None:
        print("missing Supabase credentials; set CORE_SUPABASE_URL/CORE_SUPABASE_SERVICE_KEY")
        return 2
    threads = list_threads(client)
    if args.dry_run:
        for thread_id in threads:
            print(thread_id)
        return 0
    store = _r2_backend_from_env()
    if store is None:
        print("missing R2 credentials; set R2_ACCOUNT_ID/R2_BUCKET/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY")
        return 2
    manifests: list[dict[str, Any]] = []
    keep = set(args.keep)
    if args.retain_days is not None:
        fresh = set(threads_older_than(client, args.retain_days))
        keep |= set(threads) - fresh
    for thread_id in threads:
        if thread_id in keep:
            continue
        manifest = archive_thread(client, store, thread_id)
        manifests.append(manifest.to_dict())
        print(f"archived {thread_id}: {len(manifest.entries)} payloads")
    if args.manifest_out:
        with open(args.manifest_out, "w", encoding="utf-8") as fh:
            json.dump(manifests, fh, indent=2)
    return 0
