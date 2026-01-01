"""Unit tests for digiquant.ops.checkpoint_archive: read-through and pointer resolution."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import pytest

pytestmark = pytest.mark.unit

from digiquant.ops.checkpoint_archive import (  # noqa: E402
    ArchiveNotFoundError,
    bucket_usage,
    compress_payload,
    list_threads,
    read_archived_document,
    read_archived_documents,
    reconcile_ledger,
    resolve_payload,
    resolve_payloads,
)

from tests.dq.ops.archive_fakes import (  # noqa: E402
    FakeArchiveClient,
    FakeStore,
)


class _BotoClientError(Exception):
    """boto3 ``ClientError``-shaped double (no botocore dependency in tests)."""

    def __init__(self, code: str, status: int = 404) -> None:
        super().__init__(code)
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }


class _MissingObjectStore(FakeStore):
    """Store whose ``get`` raises the boto3 missing-object shape."""

    def get(self, key: str) -> bytes:
        raise _BotoClientError("NoSuchKey")


def _document_pointer(**over: Any) -> dict[str, Any]:
    row = {
        "source_table": "documents",
        "source_key": {
            "workspace_id": "house",
            "document_key": "thesis",
            "date": "2026-09-07",
        },
        "r2_key": "documents/house/2026-09-07/thesis.zst",
        "sha256": "0" * 64,
        "size": 1,
        "owner": "house",
    }
    row.update(over)
    return row


class TestReadArchivedDocumentSoftFailures:
    """#3954: read-through must never raise into ``load_prior_context``."""

    def test_no_backend_warns_and_returns_none(self, monkeypatch: pytest.MonkeyPatch, caplog):
        for var in (
            "R2_ACCOUNT_ID",
            "R2_BUCKET",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        client = FakeArchiveClient(store={"archive_objects": [_document_pointer()]})
        with caplog.at_level(logging.WARNING, logger="digiquant.ops.checkpoint_archive"):
            got = read_archived_document(
                client,
                None,
                workspace_id="house",
                document_key="thesis",
                date_str="2026-09-07",
            )
        assert got is None
        assert "read-through disabled" in caplog.text
        assert "thesis" in caplog.text

    def test_missing_object_returns_none_not_raise(self, caplog):
        client = FakeArchiveClient(store={"archive_objects": [_document_pointer()]})
        with caplog.at_level(logging.WARNING, logger="digiquant.ops.checkpoint_archive"):
            got = read_archived_document(
                client,
                _MissingObjectStore(),
                workspace_id="house",
                document_key="thesis",
                date_str="2026-09-07",
            )
        assert got is None

    def test_registry_query_failure_returns_none_not_raise(self, caplog):
        class _RaisingClient:
            def table(self, name: str) -> Any:
                raise RuntimeError("registry unavailable")

        with caplog.at_level(logging.WARNING, logger="digiquant.ops.checkpoint_archive"):
            got = read_archived_document(
                _RaisingClient(),
                FakeStore(),
                workspace_id="house",
                document_key="thesis",
                date_str="2026-09-07",
            )
        assert got is None
        assert "read-through failed" in caplog.text

    def test_resolve_payload_normalizes_missing_object_to_not_found(self):
        client = FakeArchiveClient(store={"archive_objects": [_document_pointer()]})
        with pytest.raises(ArchiveNotFoundError):
            resolve_payload(
                client,
                _MissingObjectStore(),
                "documents",
                {"workspace_id": "house", "document_key": "thesis", "date": "2026-09-07"},
            )


class TestBatchedArchiveReads:
    """#4562: one ``archive_objects`` select per page, not one per version."""

    @staticmethod
    def _seed(store: FakeStore, client: FakeArchiveClient, *pairs: tuple[str, str]) -> None:
        for document_key, date_str in pairs:
            raw = json.dumps({"document_key": document_key, "date": date_str}).encode()
            blob = compress_payload(raw)
            r2_key = f"documents/house/{date_str}/{document_key}.zst"
            store.put(r2_key, blob)
            client.store.setdefault("archive_objects", []).append(
                _document_pointer(
                    source_key={
                        "workspace_id": "house",
                        "document_key": document_key,
                        "date": date_str,
                    },
                    r2_key=r2_key,
                    sha256=hashlib.sha256(blob).hexdigest(),
                )
            )

    def test_resolve_payloads_batches_one_query(self) -> None:
        client = FakeArchiveClient()
        store = FakeStore()
        pairs = [("thesis", "2026-09-07"), ("thesis", "2026-09-14"), ("macro", "2026-09-14")]
        self._seed(store, client, *pairs)
        client.log.clear()
        source_keys = [
            {"workspace_id": "house", "document_key": key, "date": date_str}
            for key, date_str in pairs
        ]
        resolved = resolve_payloads(client, store, "documents", source_keys)
        assert len(resolved) == 3
        assert sorted(json.loads(blob)["document_key"] for blob in resolved.values()) == [
            "macro",
            "thesis",
            "thesis",
        ]
        pointer_queries = [
            entry for entry in client.log if ("source_table", "documents") in entry[1]
        ]
        assert len(pointer_queries) == 1

    def test_resolve_payloads_skips_unresolvable(self) -> None:
        client = FakeArchiveClient()
        store = FakeStore()
        self._seed(store, client, ("thesis", "2026-09-07"))
        # A pointer whose recorded sha256 does not match the stored bytes.
        raw = json.dumps({"document_key": "corrupt", "date": "2026-09-07"}).encode()
        corrupt_key = "documents/house/2026-09-07/corrupt.zst"
        store.put(corrupt_key, compress_payload(raw))
        client.store["archive_objects"].append(
            _document_pointer(
                source_key={
                    "workspace_id": "house",
                    "document_key": "corrupt",
                    "date": "2026-09-07",
                },
                r2_key=corrupt_key,
                sha256="f" * 64,
            )
        )
        resolved = resolve_payloads(
            client,
            store,
            "documents",
            [
                {"workspace_id": "house", "document_key": "thesis", "date": "2026-09-07"},
                {"workspace_id": "house", "document_key": "corrupt", "date": "2026-09-07"},
                {"workspace_id": "house", "document_key": "absent", "date": "2026-09-07"},
            ],
        )
        assert len(resolved) == 1
        assert json.loads(next(iter(resolved.values())))["document_key"] == "thesis"

    def test_read_archived_documents_round_trip(self) -> None:
        client = FakeArchiveClient()
        store = FakeStore()
        self._seed(store, client, ("thesis", "2026-09-07"), ("macro", "2026-09-14"))
        out = read_archived_documents(
            client,
            store,
            workspace_id="house",
            keys=[("thesis", "2026-09-07"), ("macro", "2026-09-14"), ("absent", "2026-09-14")],
        )
        assert out == {
            ("thesis", "2026-09-07"): {"document_key": "thesis", "date": "2026-09-07"},
            ("macro", "2026-09-14"): {"document_key": "macro", "date": "2026-09-14"},
        }

    def test_read_archived_documents_no_backend_warns_and_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        for var in ("R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
            monkeypatch.delenv(var, raising=False)
        with caplog.at_level(logging.WARNING, logger="digiquant.ops.checkpoint_archive"):
            out = read_archived_documents(
                FakeArchiveClient(), None, workspace_id="house", keys=[("thesis", "2026-09-07")]
            )
        assert out == {}
        assert "read-through disabled" in caplog.text

    def test_read_archived_documents_skips_undecodable_bytes(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = FakeArchiveClient()
        store = FakeStore()
        self._seed(store, client, ("thesis", "2026-09-07"))
        # Valid zstd whose checksum matches, but the bytes are not JSON.
        blob = compress_payload(b"not json")
        r2_key = "documents/house/2026-09-07/broken.zst"
        store.put(r2_key, blob)
        client.store["archive_objects"].append(
            _document_pointer(
                source_key={
                    "workspace_id": "house",
                    "document_key": "broken",
                    "date": "2026-09-07",
                },
                r2_key=r2_key,
                sha256=hashlib.sha256(blob).hexdigest(),
            )
        )
        with caplog.at_level(logging.WARNING, logger="digiquant.ops.checkpoint_archive"):
            out = read_archived_documents(
                client,
                store,
                workspace_id="house",
                keys=[("thesis", "2026-09-07"), ("broken", "2026-09-07")],
            )
        assert set(out) == {("thesis", "2026-09-07")}
        assert "is not valid JSON" in caplog.text

    def test_read_archived_documents_registry_failure_degrades(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class _RaisingClient:
            def table(self, name: str) -> Any:
                raise RuntimeError("registry unavailable")

        with caplog.at_level(logging.WARNING, logger="digiquant.ops.checkpoint_archive"):
            out = read_archived_documents(
                _RaisingClient(),
                FakeStore(),
                workspace_id="house",
                keys=[("thesis", "2026-09-07")],
            )
        assert out == {}
        assert "batch read-through failed" in caplog.text


class TestStablePagination:
    """#3954: offset pages must carry a unique ORDER BY tiebreak."""

    def test_list_threads_stable_under_nonstable_source_order(self):
        expected = [f"t{i:04d}" for i in range(2500)]
        client = FakeArchiveClient(
            store={"checkpoints": [{"thread_id": t} for t in expected]},
            unstable_pagination=True,
        )
        assert list_threads(client) == expected

    def test_bucket_usage_stable_under_nonstable_source_order(self):
        client = FakeArchiveClient(unstable_pagination=True)
        for i in range(2500):
            client.table("archive_objects").insert(
                {
                    "source_table": "checkpoint_blobs",
                    "source_key": {"thread_id": f"t{i:04d}"},
                    "r2_key": f"r2/k{i:04d}",
                    "sha256": "0" * 64,
                    "size": i + 1,
                    "owner": "house",
                    "archived_at": f"2026-09-01T{i:04d}",
                }
            ).execute()
        assert bucket_usage(client) == sum(range(1, 2501))

    def test_reconcile_ledger_stable_under_nonstable_source_order(self):
        client = FakeArchiveClient(unstable_pagination=True)
        for i in range(2500):
            client.table("archive_objects").insert(
                {
                    "source_table": "checkpoint_blobs",
                    "source_key": {"thread_id": f"t{i:04d}"},
                    "r2_key": f"checkpoints/gone{i:04d}",
                    "sha256": "0" * 64,
                    "size": 1,
                    "owner": "house",
                    "archived_at": f"2026-09-01T{i:04d}",
                }
            ).execute()
        assert reconcile_ledger(client, FakeStore()) == []
        remaining = client.table("archive_objects").select("r2_key").range(0, 9999).execute().data
        assert remaining == []
