"""Unit tests for digiquant.ops.checkpoint_archive: write side, registry, CLI.

The ledger, pagination and read-through phases live in their own modules. The
PostgREST and R2 doubles live in ``tests/dq/ops/archive_fakes.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.unit

from digiquant.ops.checkpoint_archive import (  # noqa: E402
    ArchiveManifest,
    ArchiveNotFoundError,
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
    previous_threads,
    resolve_payload,
    restore_thread,
)

from tests.dq.ops.archive_fakes import (  # noqa: E402
    FakeArchiveClient,
    FakeStore,
    blob_row,
    write_row,
)


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
        client = FakeArchiveClient(
            store={"checkpoints": [{"thread_id": "a"}, {"thread_id": "b"}, {"thread_id": "a"}]}
        )
        assert sorted(list_threads(client)) == ["a", "b"]


class TestArchiveThread:
    def test_archive_uploads_verifies_and_nulls(self) -> None:
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row()],
                "checkpoint_writes": [write_row()],
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
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row(blob=None)],
                "checkpoint_writes": [],
            }
        )
        manifest = archive_thread(client, FakeStore(), "run1::portfolio")
        assert manifest.entries == ()

    def test_verify_mismatch_never_nulls(self) -> None:
        class CorruptingStore(FakeStore):
            def get(self, key: str) -> bytes:
                return b"tampered"

        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row()],
                "checkpoint_writes": [],
            }
        )
        with pytest.raises(ArchiveVerifyError):
            archive_thread(client, CorruptingStore(), "run1::portfolio")
        assert client.store["checkpoint_blobs"][0]["blob"] == "\\x0102ff"

    def test_other_threads_untouched(self) -> None:
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [
                    blob_row(),
                    blob_row(thread_id="run2::portfolio", blob="\\x99"),
                ],
                "checkpoint_writes": [],
            }
        )
        archive_thread(client, FakeStore(), "run1::portfolio")
        kept = [r for r in client.store["checkpoint_blobs"] if r["thread_id"] == "run2::portfolio"]
        assert kept[0]["blob"] == "\\x99"

    def test_archive_writes_registry_rows(self) -> None:
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row()],
                "checkpoint_writes": [write_row()],
            }
        )
        store = FakeStore()
        manifest = archive_thread(client, store, "run1::portfolio")
        rows = client.table("archive_objects").select("*").execute().data
        assert len(rows) == len(manifest.entries) == 2
        assert all(r["sha256"] for r in rows)
        assert all(r["owner"] == "house" for r in rows)

    def test_registry_failure_keeps_supabase_row(self) -> None:
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row()],
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
        probe = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row()],
                "checkpoint_writes": [],
            }
        )
        first = archive_thread(probe, FakeStore(), "run1::portfolio")
        key = first.entries[0].key
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row()],
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
        probe = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row()],
                "checkpoint_writes": [],
            }
        )
        first = archive_thread(probe, FakeStore(), "run1::portfolio")
        key = first.entries[0].key
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row()],
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
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row()],
                "checkpoint_writes": [write_row()],
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
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "run1::portfolio"}],
                "checkpoint_blobs": [blob_row()],
                "checkpoint_writes": [],
            }
        )
        manifest = archive_thread(client, FakeStore(), "run1::portfolio")
        revived = ArchiveManifest.from_dict(manifest.to_dict())
        assert revived == manifest


class TestPreviousThreads:
    def test_previous_threads_excludes_newest(self) -> None:
        client = FakeArchiveClient(
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
    """DirectPostgresReader-shaped double that delegates to the FakeArchiveClient.

    Used by live-path main() tests so they exercise the reader lifecycle
    without a real Postgres connection.
    """

    def __init__(self, client: FakeArchiveClient) -> None:
        self._client = client

    def fetch_row(self, table: str, key: dict[str, Any]) -> dict[str, Any]:
        from digiquant.ops.checkpoint_archive import KEY_COLUMNS_BY_TABLE

        query = self._client.table(table).select("*")
        for col in KEY_COLUMNS_BY_TABLE[table]:
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
        client = FakeArchiveClient(
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
        client = FakeArchiveClient(
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
        monkeypatch.setenv("CORE_POSTGRES_URI", "postgresql://fake/db")
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

    def test_main_wires_documents_phase(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from datetime import datetime, timezone

        from digiquant.dashboard.tenancy import house_workspace_id

        house = str(house_workspace_id())
        recent = datetime.now(timezone.utc).isoformat()
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "only-run", "checkpoint": {"ts": recent}}],
                "checkpoint_blobs": [],
                "checkpoint_writes": [],
                "documents": [
                    {
                        "workspace_id": house,
                        "document_key": "k",
                        "date": "2026-09-07",
                        "payload": {"a": 1},
                    },
                    {
                        "workspace_id": house,
                        "document_key": "k",
                        "date": "2026-09-08",
                        "payload": {"a": 2},
                    },
                ],
            }
        )
        monkeypatch.setattr("digiquant.data.store.client.build_digiquant_client", lambda: client)
        monkeypatch.setenv("R2_ACCOUNT_ID", "x")
        monkeypatch.setenv("R2_BUCKET", "bkt")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "k")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "s")
        monkeypatch.setenv("CORE_POSTGRES_URI", "postgresql://fake/db")
        monkeypatch.setattr("digiquant.ops.checkpoint_archive.R2Backend", lambda **kw: FakeStore())
        monkeypatch.setattr(
            "digiquant.ops.checkpoint_archive.DirectPostgresReader",
            lambda uri: _PostgrestPassthrough(client),
        )
        assert main([]) == 0
        out = capsys.readouterr().out
        assert "archived documents: 1 payloads" in out
        live = {r["date"]: r["payload"] for r in client.store["documents"]}
        assert live["2026-09-07"] is None  # archived
        assert live["2026-09-08"] == {"a": 2}  # retained
        pointers = client.store["archive_objects"]
        assert len(pointers) == 1 and pointers[0]["source_table"] == "documents"

    def test_main_workspace_default_resolves_house_uuid(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from datetime import datetime, timezone

        sentinel = "11111111-2222-4333-8444-555555555555"
        recent = datetime.now(timezone.utc).isoformat()
        client = FakeArchiveClient(
            store={
                "checkpoints": [{"thread_id": "only-run", "checkpoint": {"ts": recent}}],
                "checkpoint_blobs": [],
                "checkpoint_writes": [],
                "documents": [
                    {
                        "workspace_id": sentinel,
                        "document_key": "k",
                        "date": "2026-09-07",
                        "payload": {"a": 1},
                    },
                    {
                        "workspace_id": sentinel,
                        "document_key": "k",
                        "date": "2026-09-08",
                        "payload": {"a": 2},
                    },
                ],
            }
        )
        monkeypatch.setattr(
            "digiquant.ops.checkpoint_archive.house_workspace_id",
            lambda: sentinel,
        )
        monkeypatch.setattr("digiquant.data.store.client.build_digiquant_client", lambda: client)
        monkeypatch.setenv("R2_ACCOUNT_ID", "x")
        monkeypatch.setenv("R2_BUCKET", "bkt")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "k")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "s")
        monkeypatch.setenv("CORE_POSTGRES_URI", "postgresql://fake/db")
        monkeypatch.setattr("digiquant.ops.checkpoint_archive.R2Backend", lambda **kw: FakeStore())
        monkeypatch.setattr(
            "digiquant.ops.checkpoint_archive.DirectPostgresReader",
            lambda uri: _PostgrestPassthrough(client),
        )
        assert main([]) == 0
        out = capsys.readouterr().out
        assert "archived documents: 1 payloads" in out
        live = {r["date"]: r["payload"] for r in client.store["documents"]}
        assert live["2026-09-07"] is None  # archived
        assert live["2026-09-08"] == {"a": 2}  # retained


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
    client = FakeArchiveClient(
        store={
            "checkpoint_blobs": [blob_row()],
            "checkpoint_writes": [write_row()],
        }
    )
    store = FakeStore()
    archive_thread(client, store, "run1::portfolio")
    entry = client.table("archive_objects").select("*").execute().data[0]
    raw = resolve_payload(client, store, entry["source_table"], entry["source_key"])
    assert raw == store.original[entry["r2_key"]]


def test_resolve_missing_pointer_raises_not_found():
    with pytest.raises(ArchiveNotFoundError):
        resolve_payload(FakeArchiveClient(), FakeStore(), "checkpoint_blobs", {"thread_id": "nope"})
