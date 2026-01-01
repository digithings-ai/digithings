"""Unit tests for digiquant.ops.checkpoint_archive: ledger, direct Postgres, pagination."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.unit

from digiquant.ops.checkpoint_archive import (  # noqa: E402
    LOW_WATERMARK_BYTES,
    ArchiveVerifyError,
    bucket_usage,
    evict_to_watermark,
    list_threads,
    main,
    previous_threads,
    reconcile_ledger,
    threads_older_than,
)

from tests.dq.ops.archive_fakes import (  # noqa: E402
    FakeArchiveClient,
    FakeStore,
    blob_row,
)


def _seed_ledger(client: FakeArchiveClient, keys_sizes: list[tuple[str, int]]) -> None:
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
    client = FakeArchiveClient()
    _seed_ledger(
        client,
        [
            ("checkpoints/a", 4_000_000_000),
            ("checkpoints/b", 3_000_000_000),
            ("checkpoints/c", 2_000_000_000),
        ],
    )
    store = FakeStore()
    for key in ("checkpoints/a", "checkpoints/b", "checkpoints/c"):
        store.objects[key] = b"x"
    evicted = evict_to_watermark(client, store)
    assert evicted == ["checkpoints/a"]
    assert bucket_usage(client) <= LOW_WATERMARK_BYTES


def test_evict_never_touches_latest_run():
    client = FakeArchiveClient()
    _seed_ledger(client, [("checkpoints/latest-x", 9_000_000_000)])
    store = FakeStore()
    store.objects["checkpoints/latest-x"] = b"x"
    assert evict_to_watermark(client, store, {"checkpoints/latest-x"}) == []


def test_reconcile_removes_dead_ledger_rows():
    client = FakeArchiveClient()
    _seed_ledger(client, [("checkpoints/gone", 10)])
    assert reconcile_ledger(client, FakeStore()) == []
    rows = client.table("archive_objects").select("*").execute().data
    assert rows == []


def test_reconcile_reports_orphans_without_deleting():
    client = FakeArchiveClient()
    store = FakeStore()
    store.objects["checkpoints/orphan/x.bin"] = b"y"
    assert reconcile_ledger(client, store) == ["checkpoints/orphan/x.bin"]
    assert "checkpoints/orphan/x.bin" in store.objects


def test_reconcile_reports_dead_market_data_without_deleting():
    client = FakeArchiveClient()
    _seed_ledger(client, [("market-data/price/SPY/2026-09-08.parquet", 10)])
    store = FakeStore()  # no backing object: dead market-data pointer
    assert reconcile_ledger(client, store) == ["market-data/price/SPY/2026-09-08.parquet"]
    rows = client.table("archive_objects").select("*").execute().data
    assert [r["r2_key"] for r in rows] == ["market-data/price/SPY/2026-09-08.parquet"]


def test_fetch_thread_rows_two_phase_single_row_statements():
    from digiquant.ops.checkpoint_archive import _fetch_thread_rows

    client = FakeArchiveClient()
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

    client = FakeArchiveClient()
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
        self._rows = rows if rows is not None else [blob_row()]
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

        rows = [blob_row(channel="a"), blob_row(channel="b")]
        client = FakeArchiveClient(store={"checkpoint_blobs": [dict(r) for r in rows]})
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
            "digiquant.data.store.client.build_digiquant_client", lambda: FakeArchiveClient()
        )
        monkeypatch.setenv("R2_ACCOUNT_ID", "x")
        monkeypatch.setenv("R2_BUCKET", "bkt")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "k")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "s")
        monkeypatch.delenv("CORE_POSTGRES_URI", raising=False)
        assert main([]) == 2


def test_list_threads_scans_all_pages():
    """list_threads must paginate: 1100 threads span two PostgREST pages (#3789)."""
    client = FakeArchiveClient(
        store={"checkpoints": [{"thread_id": f"t{i:04d}"} for i in range(1100)]}
    )
    assert list_threads(client) == [f"t{i:04d}" for i in range(1100)]


def test_threads_older_than_scans_all_pages():
    """threads_older_than must see past the 1000-row cap (#3789)."""
    client = FakeArchiveClient(
        store={
            "checkpoints": [
                {"thread_id": f"t{i:04d}", "checkpoint": {"ts": "2026-01-01T00:00:00+00:00"}}
                for i in range(1050)
            ]
        }
    )
    assert threads_older_than(client, retain_days=30) == [f"t{i:04d}" for i in range(1050)]


def test_previous_threads_scans_all_pages():
    """previous_threads must see past the 1000-row cap, still excluding newest (#3789)."""
    rows = [
        {
            "thread_id": f"t{i:04d}",
            "checkpoint": {"ts": "2026-01-01T00:00:00+00:00"},
        }
        for i in range(1050)
    ]
    rows[-1]["checkpoint"] = {"ts": "2026-09-08T00:00:00+00:00"}
    client = FakeArchiveClient(store={"checkpoints": rows})
    got = previous_threads(client)
    assert len(got) == 1049
    assert "t1049" not in got
    assert got == sorted(got)


def test_fetch_thread_rows_key_scan_paginates():
    """A hot thread's key-only scan must page past the 1000-row cap (#3789)."""
    from digiquant.ops.checkpoint_archive import _fetch_thread_rows

    client = FakeArchiveClient()
    for i in range(1050):
        client.store.setdefault("checkpoint_blobs", []).append(
            {
                "thread_id": "t1",
                "checkpoint_ns": f"ns{i:04d}",
                "channel": "c",
                "version": "v",
                "blob": b"x",
            }
        )
    rows = _fetch_thread_rows(client, "checkpoint_blobs", "t1")
    assert [r["checkpoint_ns"] for r in rows] == [f"ns{i:04d}" for i in range(1050)]
    # Key-only scan paged twice (1000 + 50); payload fetches stay single-row.
    assert len([e for e in client.log if e[0] != "*"]) == 2
    assert all(count <= 1 for cols, _, count in client.log if cols == "*")


def test_bucket_usage_sums_all_pages():
    """bucket_usage must sum past the 1000-row cap, not silently undercount (#3790)."""
    client = FakeArchiveClient()
    _seed_ledger(client, [(f"r2/k{i:04d}", 10) for i in range(1100)])
    assert bucket_usage(client) == 11_000


def test_evict_to_watermark_paginates_and_uses_local_total():
    """Ledger past the cap: one paginated oldest-first scan, local total, no re-selects."""
    client = FakeArchiveClient()
    for i in range(1500):
        client.table("archive_objects").insert(
            {
                "source_table": "checkpoint_blobs",
                "source_key": {"thread_id": f"t{i:04d}"},
                "r2_key": f"checkpoints/k{i:04d}",
                "sha256": "0" * 64,
                "size": 10_000_000,
                "owner": "house",
                "archived_at": f"2026-09-01T{i:04d}",
            }
        ).execute()
    store = FakeStore()
    for i in range(1500):
        store.objects[f"checkpoints/k{i:04d}"] = b"x"
    evicted = evict_to_watermark(client, store)
    # 15GB total; evict oldest-first until <= 7GB low watermark → 800 rows (8GB).
    assert evicted == [f"checkpoints/k{i:04d}" for i in range(800)]
    # The ordered scan paged twice (1000 + 500); no per-row ledger re-selects.
    full_scans = [e for e in client.log if e[0] == "*"]
    assert len(full_scans) == 2
    assert [e for e in client.log if e[0] == "size"] == []
    assert bucket_usage(client) == 700 * 10_000_000


def test_reconcile_ledger_scans_all_pages():
    """Dead-ledger cleanup must see past the 1000-row cap (#3789)."""
    client = FakeArchiveClient()
    _seed_ledger(client, [(f"checkpoints/gone{i:04d}", 10) for i in range(1050)])
    assert reconcile_ledger(client, FakeStore()) == []
    remaining = client.table("archive_objects").select("r2_key").range(0, 9999).execute().data
    assert remaining == []


def test_reconcile_reports_documents_prefix_orphans():
    """reconcile_ledger must list documents/ orphans too, never auto-delete (#3791)."""
    client = FakeArchiveClient()
    store = FakeStore()
    store.objects["checkpoints/orphan/x.bin"] = b"y"
    store.objects["documents/house/2026-09-07/thesis.zst"] = b"z"
    assert reconcile_ledger(client, store) == [
        "checkpoints/orphan/x.bin",
        "documents/house/2026-09-07/thesis.zst",
    ]
    assert set(store.objects) == {
        "checkpoints/orphan/x.bin",
        "documents/house/2026-09-07/thesis.zst",
    }
