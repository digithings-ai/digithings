"""Unit tests for digiquant.data.prices.r2_history (#3780, Task 2).

Immutable versioned market-data generations in R2: put -> read-back SHA-256
verify -> registry insert -> pointer swap. Never overwrites in place.
Also pins the Task 2 scoping invariant: checkpoint evict/reconcile never
touch market-data/ rows.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

pytestmark = pytest.mark.unit

from digiquant.ops.checkpoint_archive import (  # noqa: E402
    ArchiveVerifyError,
    evict_to_watermark,
    reconcile_ledger,
)


class FakeR2:
    """In-memory StorageBackend double with corruption + put-count hooks."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts: list[str] = []
        self.corrupt_next_get = False

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = bytes(data)
        self.puts.append(key)

    def get(self, key: str) -> bytes:
        raw = bytes(self.objects[key])
        if self.corrupt_next_get:
            self.corrupt_next_get = False
            return b"corrupted-bytes"
        return raw

    def delete(self, key: str) -> None:
        del self.objects[key]

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))

    def latest_pointer(self, prefix: str) -> str | None:
        raw = self.objects.get(f"{prefix}/latest")
        return None if raw is None else raw.decode("utf-8")


class FakeRegistry:
    """archive_objects double mirroring _insert_pointer idempotency."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def __call__(
        self,
        source_table: str,
        source_key: dict[str, Any],
        r2_key: str,
        sha256: str,
        size: int,
    ) -> None:
        for row in self.rows:
            if row["r2_key"] == r2_key:
                if row["sha256"] == sha256:
                    return
                raise ArchiveVerifyError(
                    f"archive pointer conflict for {r2_key}: Supabase row kept"
                )
        self.rows.append(
            {
                "source_table": source_table,
                "source_key": dict(source_key),
                "r2_key": r2_key,
                "sha256": sha256,
                "size": size,
            }
        )


@pytest.fixture
def fakes() -> tuple[Any, FakeR2, FakeRegistry]:
    from digiquant.data.prices.r2_history import R2HistoryStore

    r2 = FakeR2()
    registry = FakeRegistry()
    return R2HistoryStore(r2, registry), r2, registry


def test_put_generation_verifies_before_pointer(fakes: Any) -> None:
    store, r2, registry = fakes
    r2.corrupt_next_get = True
    with pytest.raises(ArchiveVerifyError):
        store.put_generation("market-data/price/SPY/2026-09-08.parquet", b"data-bytes")
    assert r2.latest_pointer("market-data/price/SPY") is None
    assert registry.rows == []


def test_put_generation_registers_pointer_on_success(fakes: Any) -> None:
    import hashlib

    store, r2, registry = fakes
    gen = store.put_generation(
        "market-data/price/SPY/2026-09-08.parquet",
        b"data-bytes",
        "market-data/price",
        {"ticker": "SPY", "as_of": "2026-09-08"},
    )
    assert gen.key == "market-data/price/SPY/2026-09-08.parquet"
    assert gen.sha256 == hashlib.sha256(b"data-bytes").hexdigest()
    assert gen.as_of == "2026-09-08"
    assert len(registry.rows) == 1
    assert registry.rows[0]["source_table"] == "market-data/price"
    assert r2.objects[gen.key] == b"data-bytes"


def test_put_generation_conflict_raises_for_different_bytes(fakes: Any) -> None:
    store, _, _ = fakes
    key = "market-data/price/SPY/2026-09-08.parquet"
    store.put_generation(key, b"v1", "market-data/price", {"ticker": "SPY"})
    with pytest.raises(ArchiveVerifyError):
        store.put_generation(key, b"v2-different", "market-data/price", {"ticker": "SPY"})


def test_get_generation_rejects_corruption(fakes: Any) -> None:
    store, r2, _ = fakes
    gen = store.put_generation("market-data/price/SPY/2026-09-08.parquet", b"data-bytes")
    assert store.get_generation(gen.key, gen.sha256) == b"data-bytes"
    assert store.read_generation(gen.key, gen.sha256) == b"data-bytes"
    r2.objects[gen.key] = b"tampered"
    with pytest.raises(ArchiveVerifyError):
        store.get_generation(gen.key, gen.sha256)


def test_key_grammar() -> None:
    from digiquant.data.prices.r2_history import (
        generation_key,
        latest_pointer_key,
        macro_key,
        snapshot_key,
    )

    assert generation_key("SPY", "2026-09-08") == "market-data/price/SPY/2026-09-08.parquet"
    assert generation_key("brk/b", "2026-09-08") == "market-data/price/BRK-B/2026-09-08.parquet"
    assert latest_pointer_key("SPY") == "market-data/price/SPY/latest"
    assert (
        macro_key("FRED", "DGS10", "2026-09-08")
        == "market-data/macro/FRED__DGS10/2026-09-08.parquet"
    )
    assert snapshot_key("202608", "SPY") == "market-data/snapshots/202608/SPY.parquet"


def test_manifest_round_trip(fakes: Any) -> None:
    from digiquant.data.prices.r2_history import build_manifest

    store, _, _ = fakes
    manifest = build_manifest(
        "2026-09-08",
        {"SPY": {"object": "market-data/price/SPY/2026-09-08.parquet", "rows": 500}},
    )
    assert manifest["version"] == 1
    store.write_manifest(manifest)
    assert store.read_manifest() == manifest


def test_manifest_rejects_unknown_version(fakes: Any) -> None:
    store, r2, _ = fakes
    r2.objects["market-data/manifest.json"] = json.dumps(
        {"version": 999, "as_of": "2026-09-08"}
    ).encode("utf-8")
    with pytest.raises(ValueError, match="unsupported manifest version"):
        store.read_manifest()


def test_manifest_write_rejects_unknown_version(fakes: Any) -> None:
    store, _, _ = fakes
    with pytest.raises(ValueError, match="unsupported manifest version"):
        store.write_manifest({"version": 999, "as_of": "2026-09-08"})


def test_pointer_swap_is_single_put(fakes: Any) -> None:
    from digiquant.data.prices.r2_history import generation_key, latest_pointer_key

    store, r2, _ = fakes
    gen = store.put_generation(generation_key("SPY", "2026-09-08"), b"data-bytes")
    r2.puts.clear()
    store.swap_latest_pointer(latest_pointer_key("SPY"), gen.key)
    assert r2.puts == [latest_pointer_key("SPY")]
    assert store.read_latest(latest_pointer_key("SPY")) == gen.key


class _Resp:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _LedgerTable:
    """Minimal archive_objects double: select/order/eq/delete + execute."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._filters: list[tuple[str, Any]] = []
        self._delete = False
        self._order: str | None = None

    def select(self, _cols: str) -> "_LedgerTable":
        return self

    def order(self, col: str) -> "_LedgerTable":
        self._order = col
        return self

    def eq(self, col: str, val: Any) -> "_LedgerTable":
        self._filters.append((col, val))
        return self

    def delete(self) -> "_LedgerTable":
        self._delete = True
        return self

    def insert(self, row: dict[str, Any]) -> "_LedgerTable":
        self._rows.append(dict(row))
        return self

    def execute(self) -> _Resp:
        matched = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters)]
        if self._order is not None:
            matched.sort(key=lambda r: r.get(self._order))
        if self._delete:
            for row in matched:
                self._rows.remove(row)
            return _Resp([])
        return _Resp([dict(r) for r in matched])


class _LedgerClient:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows: list[dict[str, Any]] = rows if rows is not None else []

    def table(self, _name: str) -> _LedgerTable:
        return _LedgerTable(self.rows)


def _ledger_row(r2_key: str, size: int, archived_at: str) -> dict[str, Any]:
    return {
        "source_table": "checkpoint_blobs" if r2_key.startswith("checkpoints/") else r2_key,
        "source_key": {},
        "r2_key": r2_key,
        "sha256": "0" * 64,
        "size": size,
        "owner": "house",
        "archived_at": archived_at,
    }


def test_evict_ignores_market_data_rows() -> None:
    client = _LedgerClient(
        [
            _ledger_row("checkpoints/old/x.bin", 9_000_000_000, "2026-09-01T00:00:00+00:00"),
            _ledger_row(
                "market-data/price/SPY/2026-09-08.parquet",
                9_000_000_000,
                "2026-09-08T00:00:00+00:00",
            ),
        ]
    )
    store = FakeR2()
    store.objects["checkpoints/old/x.bin"] = b"x"
    store.objects["market-data/price/SPY/2026-09-08.parquet"] = b"y"
    evicted = evict_to_watermark(client, store)  # type: ignore[arg-type]
    assert evicted == ["checkpoints/old/x.bin"]
    assert "market-data/price/SPY/2026-09-08.parquet" in store.objects
    assert any(r["r2_key"] == "market-data/price/SPY/2026-09-08.parquet" for r in client.rows)


def test_reconcile_keeps_market_data_pointers() -> None:
    client = _LedgerClient(
        [
            _ledger_row(
                "market-data/price/SPY/2026-09-08.parquet", 10, "2026-09-08T00:00:00+00:00"
            ),
            _ledger_row("documents/house/2026-09-01/notes.zst", 10, "2026-09-01T00:00:00+00:00"),
        ]
    )
    store = FakeR2()
    store.objects["market-data/price/SPY/2026-09-08.parquet"] = b"y"
    store.objects["documents/house/2026-09-01/notes.zst"] = b"z"
    # Market-data orphans are out of scope: the manifest (not the ledger) indexes them.
    store.objects["market-data/price/SPY/stray.parquet"] = b"?"
    assert reconcile_ledger(client, store) == []  # type: ignore[arg-type]
    assert {r["r2_key"] for r in client.rows} == {
        "market-data/price/SPY/2026-09-08.parquet",
        "documents/house/2026-09-01/notes.zst",
    }
