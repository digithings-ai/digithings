"""Same-day restatement keys for r2_history (#4621).

The evening cron re-fetches the same ``as_of`` with different bytes. The base
generation key is immutable (``put_generation`` still raises on a same-key /
different-bytes conflict), so the revision goes under a NEW content-hash key
(``{as_of}--{sha12}.parquet``) via :meth:`R2HistoryStore.put_restatement` and
the ``latest`` pointer flips to it. The old generation stays readable.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

pytestmark = pytest.mark.unit

from digiquant.data.prices.r2_history import (  # noqa: E402
    RESTATEMENT_SHORT_LEN,
    R2HistoryStore,
    generation_restatement_key,
    macro_restatement_key,
    restatement_key_for_base,
)
from digiquant.ops.checkpoint_archive import ArchiveVerifyError  # noqa: E402


class FakeR2:
    """In-memory StorageBackend double."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts: list[str] = []

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = bytes(data)
        self.puts.append(key)

    def get(self, key: str) -> bytes:
        return bytes(self.objects[key])

    def delete(self, key: str) -> None:
        del self.objects[key]

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))


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
                    f"archive pointer conflict for {r2_key}: registry row kept"
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

    def lookup(self, r2_key: str) -> str | None:
        for row in self.rows:
            if row["r2_key"] == r2_key:
                return str(row["sha256"])
        return None


@pytest.fixture
def fakes() -> tuple[Any, FakeR2, FakeRegistry]:
    r2 = FakeR2()
    registry = FakeRegistry()
    return R2HistoryStore(r2, registry, registry.lookup), r2, registry


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_restatement_key_grammar() -> None:
    digest = "ab" * 32
    short = digest[:RESTATEMENT_SHORT_LEN]
    assert generation_restatement_key("SPY", "2026-09-08", digest) == (
        f"market-data/price/SPY/2026-09-08--{short}.parquet"
    )
    assert generation_restatement_key("brk/b", "2026-09-08", digest) == (
        f"market-data/price/BRK-B/2026-09-08--{short}.parquet"
    )
    assert macro_restatement_key("fred", "DGS10", "2026-09-08", digest) == (
        f"market-data/macro/fred__DGS10/2026-09-08--{short}.parquet"
    )
    # Generic form inserts before a trailing .parquet, appends otherwise.
    assert restatement_key_for_base("a/b.parquet", digest) == f"a/b--{short}.parquet"
    assert restatement_key_for_base("a/latest", digest) == f"a/latest--{short}"


def test_put_restatement_writes_new_key_and_keeps_old(fakes: Any) -> None:
    from digiquant.data.prices.r2_history import generation_key, latest_pointer_key

    store, r2, registry = fakes
    base = generation_key("SPY", "2026-09-08")
    morning = store.put_generation(
        base, b"morning-bytes", "market-data/price", {"ticker": "SPY", "as_of": "2026-09-08"}
    )
    store.swap_latest_pointer(latest_pointer_key("SPY"), morning.key)

    evening = store.put_restatement(
        base,
        b"evening-revision",
        "market-data/price",
        {"ticker": "SPY", "as_of": "2026-09-08"},
    )
    assert evening.key != base
    assert evening.key == generation_restatement_key("SPY", "2026-09-08", evening.sha256)
    # Old generation untouched and still SHA-verified readable.
    assert r2.objects[base] == b"morning-bytes"
    assert store.get_generation(base, morning.sha256) == b"morning-bytes"
    assert store.get_generation(evening.key, evening.sha256) == b"evening-revision"
    assert len(registry.rows) == 2
    # Pointer flips to the revision.
    store.swap_latest_pointer(latest_pointer_key("SPY"), evening.key)
    assert store.read_latest(latest_pointer_key("SPY")) == evening.key


def test_put_restatement_same_bytes_reuses_base_key(fakes: Any) -> None:
    """Idempotent re-runs converge on the base key — no duplicate revision."""
    store, _, registry = fakes
    base = "market-data/price/SPY/2026-09-08.parquet"
    first = store.put_generation(base, b"same-bytes")
    second = store.put_restatement(base, b"same-bytes")
    assert second.key == base == first.key
    assert len(registry.rows) == 1


def test_put_restatement_unregistered_base_uses_base_key(fakes: Any) -> None:
    store, _, registry = fakes
    gen = store.put_restatement("market-data/price/NEW/2026-09-08.parquet", b"v1")
    assert gen.key == "market-data/price/NEW/2026-09-08.parquet"
    assert len(registry.rows) == 1


def test_put_generation_conflict_guard_unchanged(fakes: Any) -> None:
    """The base-key immutability guard still raises; restatement is opt-in."""
    store, r2, _ = fakes
    key = "market-data/price/SPY/2026-09-08.parquet"
    store.put_generation(key, b"v1")
    with pytest.raises(ArchiveVerifyError):
        store.put_generation(key, b"v2-different")
    assert r2.objects[key] == b"v1"


def test_restatement_key_is_immutable(fakes: Any) -> None:
    """A derived key with different bytes still raises — never silent overwrite."""
    store, _, _ = fakes
    base = "market-data/price/SPY/2026-09-08.parquet"
    store.put_generation(base, b"v1")
    revision = store.put_restatement(base, b"v2")
    with pytest.raises(ArchiveVerifyError):
        store.put_generation(revision.key, b"v3-other-bytes")
    assert store.get_generation(revision.key, revision.sha256) == b"v2"


def test_macro_put_restatement(fakes: Any) -> None:
    from digiquant.data.prices.r2_history import (
        SOURCE_TABLE_MACRO,
        macro_key,
        macro_latest_pointer_key,
    )

    store, r2, registry = fakes
    base = macro_key("fred", "DGS10", "2026-09-08")
    store.put_generation(
        base,
        b"morning",
        SOURCE_TABLE_MACRO,
        {"source": "fred", "series": "DGS10", "as_of": "2026-09-08"},
    )
    revision = store.put_restatement(
        base,
        b"evening",
        SOURCE_TABLE_MACRO,
        {"source": "fred", "series": "DGS10", "as_of": "2026-09-08"},
    )
    assert revision.key == macro_restatement_key("fred", "DGS10", "2026-09-08", revision.sha256)
    assert r2.objects[base] == b"morning"
    assert len(registry.rows) == 2
    store.swap_latest_pointer(macro_latest_pointer_key("fred", "DGS10"), revision.key)
    assert store.read_latest(macro_latest_pointer_key("fred", "DGS10")) == revision.key


def test_digest_helper_matches_store() -> None:
    assert _digest(b"x") == hashlib.sha256(b"x").hexdigest()
