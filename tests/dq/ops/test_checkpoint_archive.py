"""Unit tests for digiquant.ops.checkpoint_archive (R2 blob offload, #3761)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

pytestmark = pytest.mark.unit

from digiquant.ops.checkpoint_archive import (  # noqa: E402
    ArchiveManifest,
    ArchiveVerifyError,
    R2Backend,
    _r2_backend_from_env,
    archive_thread,
    blob_key,
    compress_payload,
    decompress_payload,
    list_threads,
    main,
    parse_postgrest_bytea,
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
    fail: bool = False

    def select(self, cols: str) -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, val))
        return self

    def insert(self, row: dict[str, Any]) -> "_Query":
        if self.fail:
            raise RuntimeError(f"injected failure on {self.table_name}")
        self.store.setdefault(self.table_name, []).append(dict(row))
        return _Query(table_name=self.table_name, store=self.store)

    def update(self, payload: dict[str, Any]) -> "_Query":
        self._pending_update = dict(payload)
        return self

    def execute(self) -> _Resp:
        table = self.store.setdefault(self.table_name, [])
        rows = [r for r in table if all(r.get(c) == v for c, v in self._filters)]
        if self._pending_update is not None:
            for row in rows:
                row.update(self._pending_update)
            return _Resp(data=[dict(r) for r in rows])
        return _Resp(data=[dict(r) for r in rows])


@dataclass
class FakeClient:
    store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    fail_tables: set[str] = field(default_factory=set)

    def table(self, name: str) -> _Query:
        return _Query(table_name=name, store=self.store, fail=name in self.fail_tables)

    def fail_on_table(self, name: str) -> None:
        self.fail_tables.add(name)


class FakeStore:
    """In-memory StorageBackend double."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = bytes(data)

    def get(self, key: str) -> bytes:
        return self.objects[key]


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


class TestR2Backend:
    def test_construction_holds_config(self) -> None:
        backend = R2Backend(
            endpoint_url="https://abc.r2.cloudflarestorage.com",
            bucket="digithings-checkpoint-archive",
            access_key="key",
            secret_key="secret",
        )
        assert backend.bucket == "digithings-checkpoint-archive"


class TestMain:
    def test_dry_run_lists_threads_without_uploading(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = FakeClient(store={"checkpoints": [{"thread_id": "a"}, {"thread_id": "b"}]})
        monkeypatch.setattr("digiquant.data.store.client.build_digiquant_client", lambda: client)
        assert main(["--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "a" in out and "b" in out

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
        monkeypatch.setattr("digiquant.ops.checkpoint_archive.R2Backend", lambda **kw: FakeStore())
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
