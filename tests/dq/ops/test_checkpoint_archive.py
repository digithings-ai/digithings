"""Unit tests for digiquant.ops.checkpoint_archive (R2 blob offload, #3761)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

pytestmark = pytest.mark.unit

from digiquant.ops.checkpoint_archive import (  # noqa: E402
    LOW_WATERMARK_BYTES,
    ArchiveManifest,
    ArchiveNotFoundError,
    ArchiveVerifyError,
    R2Backend,
    _r2_backend_from_env,
    archive_thread,
    blob_key,
    bucket_usage,
    compress_payload,
    decompress_payload,
    evict_to_watermark,
    list_threads,
    main,
    parse_postgrest_bytea,
    previous_threads,
    reconcile_ledger,
    resolve_payload,
    restore_thread,
)


@dataclass
class _Resp:
    data: list[dict[str, Any]]


@dataclass
class _Query:
    table_name: str
    store: dict[str, list[dict[str, Any]]]
    _filters: list[tuple[str, Any]] = field(default_factory=list)
    _pending_update: dict[str, Any] | None = None
    _pending_delete: bool = False
    _order_cols: list[str] = field(default_factory=list)
    _range: tuple[int, int] | None = None
    fail: bool = False
    _selected: bool = False
    _select_cols: str = ""
    _action: str | None = None
    log: list[tuple[str, tuple[tuple[str, Any], ...], int]] = field(default_factory=list)

    def select(self, cols: str) -> "_Query":
        self._selected = True
        self._select_cols = cols
        return self

    def order(self, col: str) -> "_Query":
        self._order_cols.append(col)
        return self

    def range(self, start: int, end: int) -> "_Query":
        """Inclusive range, matching supabase-py/PostgREST semantics."""
        self._range = (start, end)
        return self

    def delete(self) -> "_Query":
        self._pending_delete = True
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, val))
        return self

    def insert(self, row: dict[str, Any]) -> "_Query":
        if self.fail:
            raise RuntimeError(f"injected failure on {self.table_name}")
        self.store.setdefault(self.table_name, []).append(dict(row))
        return _Query(table_name=self.table_name, store=self.store, _action="insert", log=self.log)

    def update(self, payload: dict[str, Any]) -> "_Query":
        self._pending_update = dict(payload)
        return self

    def execute(self) -> _Resp:
        table = self.store.setdefault(self.table_name, [])

        def _matches(row: dict[str, Any]) -> bool:
            for col, val in self._filters:
                if col.startswith("source_key->>"):
                    sub = col.split("->>", 1)[1]
                    if not isinstance(row.get("source_key"), dict):
                        return False
                    if row["source_key"].get(sub) != val:
                        return False
                elif row.get(col) != val:
                    return False
            return True

        rows = [r for r in table if _matches(r)]
        if self._order_cols:
            cols = self._order_cols
            rows.sort(key=lambda r: tuple(r.get(c) for c in cols))
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        if self._pending_delete:
            for row in rows:
                table.remove(row)
            return _Resp(data=[])
        if self._pending_update is not None:
            for row in rows:
                row.update(self._pending_update)
            return _Resp(data=[dict(r) for r in rows])
        if self._action is not None:
            return _Resp(data=[])
        if not self._selected:
            raise RuntimeError(f"select() required before execute() on {self.table_name}")
        if self._select_cols != "*":
            wanted = [c.strip() for c in self._select_cols.split(",")]
            rows = [{c: r.get(c) for c in wanted} for r in rows]
        else:
            rows = [dict(r) for r in rows]
        self.log.append((self._select_cols, tuple(self._filters), len(rows)))
        return _Resp(data=rows)


@dataclass
class FakeClient:
    store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    fail_tables: set[str] = field(default_factory=set)
    log: list[tuple[str, tuple[tuple[str, Any], ...], int]] = field(default_factory=list)

    def table(self, name: str) -> _Query:
        return _Query(
            table_name=name, store=self.store, fail=name in self.fail_tables, log=self.log
        )

    def fail_on_table(self, name: str) -> None:
        self.fail_tables.add(name)


class FakeStore:
    """In-memory StorageBackend double."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.original: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = bytes(data)
        # Archiver stores compressed bytes; remember the raw form for asserts.
        self.original[key] = decompress_payload(bytes(data))

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        del self.objects[key]
        self.original.pop(key, None)

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))


def _blob_row(**over: Any) -> dict[str, Any]:
    row = {
        "thread_id": "run1::portfolio",
        "checkpoint_ns": "",
        "channel": "phase_portfolio",
        "version": "v1",
        "type": "json",
        "blob": "\\x0102ff",
    }
    row.update(over)
    return row


def _write_row(**over: Any) -> dict[str, Any]:
    row = {
        "thread_id": "run1::portfolio",
        "checkpoint_ns": "",
        "checkpoint_id": "c1",
        "task_id": "t1",
        "idx": 0,
        "channel": "writes",
        "type": "json",
        "blob": "\\x00aa",
    }
    row.update(over)
    return row


class TestParsePostgrestBytea:
    def test_hex_string_decodes(self) -> None:
        assert parse_postgrest_bytea("\\x0102ff") == bytes([1, 2, 255])

    def test_bytes_pass_through(self) -> None:
        assert parse_postgrest_bytea(b"\x00\x01") == b"\x00\x01"

    def test_none_stays_none(self) -> None:
        assert parse_postgrest_bytea(None) is None


class TestBlobKey:
    def test_layout(self) -> None:
        assert (
            blob_key("run1::portfolio", "checkpoint_blobs", "phase_portfolio", "v1")
            == "checkpoints/run1::portfolio/checkpoint_blobs/phase_portfolio/v1.bin"
        )


class TestListThreads:
    def test_distinct_thread_ids(self) -> None:
        client = FakeClient(
            store={"checkpoints": [{"thread_id": "a"}, {"thread_id": "b"}, {"thread_id": "a"}]}
        )
        assert sorted(list_threads(client)) == ["a", "b"]


class TestArchiveThread:
    def test_archive_uploads_verifies_and_nulls(self) -> None:
        client = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row()],
                "checkpoint_writes": [_write_row()],
            }
        )
        store = FakeStore()
        manifest = archive_thread(client, store, "run1::portfolio")
        assert isinstance(manifest, ArchiveManifest)
        assert len(manifest.entries) == 2
        for entry in manifest.entries:
            assert decompress_payload(store.objects[entry.key]) == parse_postgrest_bytea(
                "\\x0102ff" if entry.key.endswith("/v1.bin") else "\\x00aa"
            )
            assert len(entry.sha256) == 64
        assert client.store["checkpoint_blobs"][0]["blob"] is None
        assert client.store["checkpoint_writes"][0]["blob"] is None

    def test_already_archived_rows_are_skipped(self) -> None:
        client = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row(blob=None)],
                "checkpoint_writes": [],
            }
        )
        manifest = archive_thread(client, FakeStore(), "run1::portfolio")
        assert manifest.entries == ()

    def test_verify_mismatch_never_nulls(self) -> None:
        class CorruptingStore(FakeStore):
            def get(self, key: str) -> bytes:
                return b"tampered"

        client = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row()],
                "checkpoint_writes": [],
            }
        )
        with pytest.raises(ArchiveVerifyError):
            archive_thread(client, CorruptingStore(), "run1::portfolio")
        assert client.store["checkpoint_blobs"][0]["blob"] == "\\x0102ff"

    def test_other_threads_untouched(self) -> None:
        client = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [
                    _blob_row(),
                    _blob_row(thread_id="run2::portfolio", blob="\\x99"),
                ],
                "checkpoint_writes": [],
            }
        )
        archive_thread(client, FakeStore(), "run1::portfolio")
        kept = [r for r in client.store["checkpoint_blobs"] if r["thread_id"] == "run2::portfolio"]
        assert kept[0]["blob"] == "\\x99"

    def test_archive_writes_registry_rows(self) -> None:
        client = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row()],
                "checkpoint_writes": [_write_row()],
            }
        )
        store = FakeStore()
        manifest = archive_thread(client, store, "run1::portfolio")
        rows = client.table("archive_objects").select("*").execute().data
        assert len(rows) == len(manifest.entries) == 2
        assert all(r["sha256"] for r in rows)
        assert all(r["owner"] == "house" for r in rows)

    def test_registry_failure_keeps_supabase_row(self) -> None:
        client = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row()],
                "checkpoint_writes": [],
            }
        )
        client.fail_on_table("archive_objects")
        with pytest.raises(Exception):
            archive_thread(client, FakeStore(), "run1::portfolio")
        blobs = client.table("checkpoint_blobs").select("*").execute().data
        assert any(b["blob"] is not None for b in blobs)

    def test_rerun_after_partial_archive_writes_no_duplicate_pointer(self) -> None:
        # A previous run uploaded + recorded the pointer but died before NULL-ing:
        # the blob is still non-null AND the registry row already exists.
        probe = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row()],
                "checkpoint_writes": [],
            }
        )
        first = archive_thread(probe, FakeStore(), "run1::portfolio")
        key = first.entries[0].key
        client = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row()],
                "checkpoint_writes": [],
                "archive_objects": [
                    {
                        "source_table": "checkpoint_blobs",
                        "source_key": {"thread_id": "run1::portfolio"},
                        "r2_key": key,
                        "sha256": first.entries[0].sha256,
                        "size": first.entries[0].size,
                        "owner": "house",
                    }
                ],
            }
        )
        manifest = archive_thread(client, FakeStore(), "run1::portfolio")
        rows = client.table("archive_objects").select("*").execute().data
        assert [r["r2_key"] for r in rows].count(key) == 1
        assert len(manifest.entries) == 1

    def test_rerun_with_conflicting_pointer_sha_raises(self) -> None:
        # Same r2_key but different bytes = real conflict, never silently keep.
        probe = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row()],
                "checkpoint_writes": [],
            }
        )
        first = archive_thread(probe, FakeStore(), "run1::portfolio")
        key = first.entries[0].key
        client = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row()],
                "checkpoint_writes": [],
                "archive_objects": [
                    {
                        "source_table": "checkpoint_blobs",
                        "source_key": {"thread_id": "run1::portfolio"},
                        "r2_key": key,
                        "sha256": "0" * 64,
                        "size": first.entries[0].size,
                        "owner": "house",
                    }
                ],
            }
        )
        with pytest.raises(ArchiveVerifyError):
            archive_thread(client, FakeStore(), "run1::portfolio")


class TestRestoreThread:
    def test_round_trip(self) -> None:
        client = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row()],
                "checkpoint_writes": [_write_row()],
            }
        )
        store = FakeStore()
        manifest = archive_thread(client, store, "run1::portfolio")
        assert client.store["checkpoint_blobs"][0]["blob"] is None
        restore_thread(client, store, manifest)
        # Restored as raw bytes (PostgREST re-encodes to hex on read).
        assert client.store["checkpoint_blobs"][0]["blob"] == b"\x01\x02\xff"
        assert client.store["checkpoint_writes"][0]["blob"] == b"\x00\xaa"

    def test_manifest_serializes(self) -> None:
        client = FakeClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [_blob_row()],
                "checkpoint_writes": [],
            }
        )
        manifest = archive_thread(client, FakeStore(), "run1::portfolio")
        revived = ArchiveManifest.from_dict(manifest.to_dict())
        assert revived == manifest


class TestPreviousThreads:
    def test_previous_threads_excludes_newest(self) -> None:
        client = FakeClient(
            store={
                "checkpoints": [
                    {"thread_id": "t-old", "checkpoint": {"ts": "2026-09-01T00:00:00+00:00"}},
                    {"thread_id": "t-new", "checkpoint": {"ts": "2026-09-08T00:00:00+00:00"}},
                ]
            }
        )
        assert previous_threads(client) == ["t-old"]


class TestR2Backend:
    def test_construction_holds_config(self) -> None:
        backend = R2Backend(
            endpoint_url="https://abc.r2.cloudflarestorage.com",
            bucket="digithings-checkpoint-archive",
            access_key="key",
            secret_key="secret",
        )
        assert backend.bucket == "digithings-checkpoint-archive"


class _PostgrestPassthrough:
    """DirectPostgresReader-shaped double that delegates to the FakeClient.

    Used by live-path main() tests so they exercise the reader lifecycle
    without a real Postgres connection.
    """

    def __init__(self, client: FakeClient) -> None:
        self._client = client

    def fetch_row(self, table: str, key: dict[str, Any]) -> dict[str, Any]:
        from digiquant.ops.checkpoint_archive import BLOB_KEY_COLUMNS

        query = self._client.table(table).select("*")
        for col in BLOB_KEY_COLUMNS[table]:
            query = query.eq(col, key[col])
        rows = query.execute().data or []
        if len(rows) != 1:
            raise ArchiveVerifyError(f"expected 1 row for {key}, got {len(rows)}")
        return rows[0]

    def close(self) -> None:
        pass


class TestMain:
    def test_dry_run_lists_threads_without_uploading(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Dry-run lists the archive set (previous threads); the newest is excluded,
        # and --retain-days further restricts to stale threads only.
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        client = FakeClient(
            store={
                "checkpoints": [
                    {
                        "thread_id": "a",
                        "checkpoint": {"ts": (now - timedelta(days=5)).isoformat()},
                    },
                    {
                        "thread_id": "b",
                        "checkpoint": {"ts": (now - timedelta(days=1)).isoformat()},
                    },
                    {
                        "thread_id": "c",
                        "checkpoint": {"ts": (now - timedelta(hours=1)).isoformat()},
                    },
                ]
            }
        )
        monkeypatch.setattr("digiquant.data.store.client.build_digiquant_client", lambda: client)
        assert main(["--dry-run", "--retain-days", "2"]) == 0
        out = capsys.readouterr().out
        assert "a" in out and "b" not in out and "c" not in out

    def test_missing_credentials_fails_fast(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("digiquant.data.store.client.build_digiquant_client", lambda: None)
        assert main(["--dry-run"]) == 2

    def test_retain_days_archives_only_stale_threads(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        from datetime import datetime, timedelta, timezone

        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        client = FakeClient(
            store={
                "checkpoints": [
                    {"thread_id": "new-run", "checkpoint": {"ts": recent}},
                    {"thread_id": "old-run", "checkpoint": {"ts": old}},
                ],
                "checkpoint_blobs": [
                    {
                        "thread_id": "old-run",
                        "checkpoint_ns": "",
                        "channel": "c",
                        "version": "v",
                        "blob": "\\x01",
                    },
                    {
                        "thread_id": "new-run",
                        "checkpoint_ns": "",
                        "channel": "c",
                        "version": "v",
                        "blob": "\\x02",
                    },
                ],
                "checkpoint_writes": [],
            }
        )
        monkeypatch.setattr("digiquant.data.store.client.build_digiquant_client", lambda: client)
        monkeypatch.setenv("R2_ACCOUNT_ID", "x")
        monkeypatch.setenv("R2_BUCKET", "bkt")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "k")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "s")
        monkeypatch.setenv("DIGI_CHECKPOINTER_POSTGRES_URI", "postgresql://fake/db")
        monkeypatch.setattr("digiquant.ops.checkpoint_archive.R2Backend", lambda **kw: FakeStore())
        monkeypatch.setattr(
            "digiquant.ops.checkpoint_archive.DirectPostgresReader",
            lambda uri: _PostgrestPassthrough(client),
        )
        out = tmp_path / "manifests.json"
        assert main(["--retain-days", "2", "--manifest-out", str(out)]) == 0
        blobs = {r["thread_id"]: r["blob"] for r in client.store["checkpoint_blobs"]}
        assert blobs["old-run"] is None  # archived
        assert blobs["new-run"] == "\\x02"  # retained
        assert out.is_file()


def test_r2_backend_from_new_env_names(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID", "abc123")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_BUCKET", "digithings-archive")
    for old in (
        "CHECKPOINT_ARCHIVE_R2_ENDPOINT",
        "CHECKPOINT_ARCHIVE_R2_BUCKET",
        "CHECKPOINT_ARCHIVE_R2_ACCESS_KEY",
        "CHECKPOINT_ARCHIVE_R2_SECRET_KEY",
    ):
        monkeypatch.delenv(old, raising=False)
    backend = _r2_backend_from_env()
    assert backend is not None
    assert backend.endpoint_url == "https://abc123.r2.cloudflarestorage.com"
    assert backend.bucket == "digithings-archive"


def test_zstd_round_trip():
    data = b'{"channel":"messages","ts":"2026-09-09T00:00:00+00:00"}' * 100
    assert decompress_payload(compress_payload(data)) == data


def test_zstd_version_byte_rejects_unknown():
    blob = b"\x7f" + compress_payload(b"hello")[1:]
    with pytest.raises(ArchiveVerifyError):
        decompress_payload(blob)


def test_resolve_payload_round_trip():
    client = FakeClient(
        store={
            "checkpoint_blobs": [_blob_row()],
            "checkpoint_writes": [_write_row()],
        }
    )
    store = FakeStore()
    archive_thread(client, store, "run1::portfolio")
    entry = client.table("archive_objects").select("*").execute().data[0]
    raw = resolve_payload(client, store, entry["source_table"], entry["source_key"])
    assert raw == store.original[entry["r2_key"]]


def test_resolve_missing_pointer_raises_not_found():
    with pytest.raises(ArchiveNotFoundError):
        resolve_payload(FakeClient(), FakeStore(), "checkpoint_blobs", {"thread_id": "nope"})


def _seed_ledger(client: FakeClient, keys_sizes: list[tuple[str, int]]) -> None:
    for i, (key, size) in enumerate(keys_sizes):
        client.table("archive_objects").insert(
            {
                "source_table": "checkpoint_blobs",
                "source_key": {"thread_id": f"t{i}"},
                "r2_key": key,
                "sha256": "0" * 64,
                "size": size,
                "owner": "house",
                "archived_at": f"2026-09-0{i + 1}T00:00:00+00:00",
                "status": "archived",
            }
        ).execute()


def test_evict_oldest_first_to_low_watermark():
    client = FakeClient()
    _seed_ledger(
        client, [("r2/a", 4_000_000_000), ("r2/b", 3_000_000_000), ("r2/c", 2_000_000_000)]
    )
    store = FakeStore()
    for key in ("r2/a", "r2/b", "r2/c"):
        store.objects[key] = b"x"
    evicted = evict_to_watermark(client, store)
    assert evicted == ["r2/a"]
    assert bucket_usage(client) <= LOW_WATERMARK_BYTES


def test_evict_never_touches_latest_run():
    client = FakeClient()
    _seed_ledger(client, [("r2/latest-x", 9_000_000_000)])
    store = FakeStore()
    store.objects["r2/latest-x"] = b"x"
    assert evict_to_watermark(client, store, {"r2/latest-x"}) == []


def test_reconcile_removes_dead_ledger_rows():
    client = FakeClient()
    _seed_ledger(client, [("checkpoints/gone", 10)])
    assert reconcile_ledger(client, FakeStore()) == []
    rows = client.table("archive_objects").select("*").execute().data
    assert rows == []


def test_reconcile_reports_orphans_without_deleting():
    client = FakeClient()
    store = FakeStore()
    store.objects["checkpoints/orphan/x.bin"] = b"y"
    assert reconcile_ledger(client, store) == ["checkpoints/orphan/x.bin"]
    assert "checkpoints/orphan/x.bin" in store.objects


def test_fetch_thread_rows_two_phase_single_row_statements():
    from digiquant.ops.checkpoint_archive import _fetch_thread_rows

    client = FakeClient()
    for i in range(3):
        client.store.setdefault("checkpoint_blobs", []).append(
            {
                "thread_id": "t1",
                "checkpoint_ns": f"ns{i}",
                "channel": "c",
                "version": 1,
                "blob": b"x",
            }
        )
    rows = _fetch_thread_rows(client, "checkpoint_blobs", "t1")
    assert [r["checkpoint_ns"] for r in rows] == ["ns0", "ns1", "ns2"]
    assert all(r["blob"] == b"x" for r in rows)
    key_cols = {"thread_id", "checkpoint_ns", "channel", "version"}
    key_scans = [e for e in client.log if set(e[0].split(",")) == key_cols]
    assert len(key_scans) == 1
    full_fetches = [e for e in client.log if e[0] == "*"]
    assert len(full_fetches) == 3
    assert all(count <= 1 for _, _, count in full_fetches)
    assert all(("thread_id", "t1") in filters for _, filters, _ in full_fetches)


def test_fetch_thread_rows_duplicate_keys_raise():
    from digiquant.ops.checkpoint_archive import _fetch_thread_rows

    client = FakeClient()
    row = {
        "thread_id": "t1",
        "checkpoint_ns": "ns",
        "channel": "c",
        "version": 1,
        "blob": b"x",
    }
    client.store.setdefault("checkpoint_blobs", []).append(dict(row))
    client.store.setdefault("checkpoint_blobs", []).append(dict(row))
    with pytest.raises(ArchiveVerifyError):
        _fetch_thread_rows(client, "checkpoint_blobs", "t1")


class _FakePgConn:
    """Double for a psycopg connection: factory + cursor surface in one."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows if rows is not None else [_blob_row()]
        self.uri = ""
        self.sql = ""
        self.params: tuple[Any, ...] = ()
        self.closed = False

    def __call__(self, uri: str) -> "_FakePgConn":
        self.uri = uri
        return self

    def cursor(self, **kwargs: Any) -> "_FakePgConn":
        return self

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> "_FakePgConn":
        self.sql = sql
        self.params = params or ()
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._rows]

    def close(self) -> None:
        self.closed = True


class TestDirectPostgresReader:
    def test_fetch_thread_rows_uses_direct_reader_for_payloads(self) -> None:
        from digiquant.ops.checkpoint_archive import _fetch_thread_rows

        rows = [_blob_row(channel="a"), _blob_row(channel="b")]
        client = FakeClient(store={"checkpoint_blobs": [dict(r) for r in rows]})
        fetched: list[dict[str, Any]] = []

        class FakeDirectReader:
            def fetch_row(self, table: str, key: dict[str, Any]) -> dict[str, Any]:
                assert table == "checkpoint_blobs"
                fetched.append(dict(key))
                return next(r for r in rows if all(r[c] == key[c] for c in key))

        got = _fetch_thread_rows(
            client, "checkpoint_blobs", "run1::portfolio", payload_reader=FakeDirectReader()
        )
        assert got == rows
        assert len(fetched) == 2
        assert set(fetched[0]) == {"thread_id", "checkpoint_ns", "channel", "version"}
        # The phase-1 key scan was the only PostgREST statement.
        assert len(client.log) == 1

    def test_direct_reader_rejects_unknown_table(self) -> None:
        from digiquant.ops.checkpoint_archive import ArchiveVerifyError, DirectPostgresReader

        reader = DirectPostgresReader("postgresql://u:p@h/db", connect=_FakePgConn())
        with pytest.raises(ArchiveVerifyError):
            reader.fetch_row("pg_shadow", {"thread_id": "t"})

    def test_direct_reader_parameterizes_values(self) -> None:
        from digiquant.ops.checkpoint_archive import DirectPostgresReader

        conn = _FakePgConn()
        reader = DirectPostgresReader("postgresql://u:p@h/db", connect=conn)
        key = {
            "thread_id": "t",
            "checkpoint_ns": "",
            "channel": "c'; DROP TABLE checkpoint_blobs;--",
            "version": "v",
        }
        reader.fetch_row("checkpoint_blobs", key)
        assert "%s" in conn.sql
        assert "DROP" not in conn.sql
        assert conn.params == ("t", "", "c'; DROP TABLE checkpoint_blobs;--", "v")

    def test_direct_reader_wrong_row_count_raises(self) -> None:
        from digiquant.ops.checkpoint_archive import ArchiveVerifyError, DirectPostgresReader

        reader = DirectPostgresReader("postgresql://u:p@h/db", connect=_FakePgConn(rows=[]))
        with pytest.raises(ArchiveVerifyError):
            reader.fetch_row("checkpoint_blobs", {"thread_id": "t"})

    def test_main_requires_postgres_uri(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "digiquant.data.store.client.build_digiquant_client", lambda: FakeClient()
        )
        monkeypatch.setenv("R2_ACCOUNT_ID", "x")
        monkeypatch.setenv("R2_BUCKET", "bkt")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "k")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "s")
        monkeypatch.delenv("DIGI_CHECKPOINTER_POSTGRES_URI", raising=False)
        assert main([]) == 2
