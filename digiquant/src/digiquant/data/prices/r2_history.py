"""Immutable versioned market-data generations in R2 (#3780).

Mirrors the checkpoint archiver ordering verbatim: put -> get -> SHA-256
compare -> registry -> swap pointer. Never overwrites a generation in place:
each refresh writes a NEW object keyed by generation
(``price/{TICKER}/{as_of}.parquet``); the prior generation stays readable
until the next successful refresh swaps the ``latest`` pointer.

Market-data pointers live in ``archive_objects`` with namespaced
``source_table`` values (``market-data/price`` etc.) carrying the same
invariants as checkpoint pointers (idempotent insert: same-sha skip,
different-sha raise, SHA-verified reads).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from digiquant.ops.checkpoint_archive import ArchiveVerifyError, StorageBackend

MANIFEST_VERSION = 1
MANIFEST_KEY = "market-data/manifest.json"

SOURCE_TABLE_PRICE = "market-data/price"
SOURCE_TABLE_MACRO = "market-data/macro"
SOURCE_TABLE_SNAPSHOT = "market-data/snapshot"

RegistryInsert = Callable[[str, dict[str, Any], str, str, int], None]


def normalize_ticker(ticker: str) -> str:
    """Uppercase a yfinance symbol for R2 keys (``/`` -> ``-``, e.g. ``BRK/B``)."""
    return ticker.upper().replace("/", "-")


def generation_key(ticker: str, as_of: str) -> str:
    """R2 key layout: ``market-data/price/{TICKER}/{as_of}.parquet``."""
    return f"market-data/price/{normalize_ticker(ticker)}/{as_of}.parquet"


def latest_pointer_key(ticker: str) -> str:
    """Pointer object naming the newest sealed generation for *ticker*."""
    return f"market-data/price/{normalize_ticker(ticker)}/latest"


def macro_key(source: str, series: str, as_of: str) -> str:
    """R2 key layout: ``market-data/macro/{SOURCE}__{SERIES}/{as_of}.parquet``."""
    return f"market-data/macro/{source}__{series}/{as_of}.parquet"


def macro_latest_pointer_key(source: str, series: str) -> str:
    """Pointer object naming the newest sealed macro generation."""
    return f"market-data/macro/{source}__{series}/latest"


def snapshot_key(yyyymm: str, ticker: str) -> str:
    """R2 key layout: ``market-data/snapshots/{yyyymm}/{TICKER}.parquet``."""
    return f"market-data/snapshots/{yyyymm}/{normalize_ticker(ticker)}.parquet"


def build_manifest(
    as_of: str,
    datasets: dict[str, dict[str, Any]],
    *,
    stale: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a manifest payload: ``{version, as_of, generated_at, stale, datasets}``."""
    return {
        "version": MANIFEST_VERSION,
        "as_of": as_of,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "stale": stale,
        "datasets": datasets,
    }


@dataclass(frozen=True)
class Generation:
    key: str
    sha256: str
    rows: int
    as_of: str


class R2HistoryStore:
    """Versioned market-data history over a :class:`StorageBackend` + registry insert."""

    def __init__(self, backend: StorageBackend, registry_insert: RegistryInsert) -> None:
        self._backend = backend
        self._registry_insert = registry_insert

    def put_generation(
        self,
        key: str,
        payload: bytes,
        source_table: str = SOURCE_TABLE_PRICE,
        source_key: dict[str, Any] | None = None,
        rows: int = -1,
    ) -> Generation:
        """Store one immutable generation: put -> verify -> registry.

        Raises :class:`ArchiveVerifyError` before any registry write when the
        read-back hash mismatches, and propagates registry conflicts (same key,
        different bytes) so callers never swap a pointer to a failed write.
        """
        key_source = dict(source_key) if source_key is not None else {}
        digest = hashlib.sha256(payload).hexdigest()
        self._backend.put(key, payload)
        if hashlib.sha256(self._backend.get(key)).hexdigest() != digest:
            raise ArchiveVerifyError(f"read-back mismatch for {key}; pointer untouched")
        self._registry_insert(source_table, key_source, key, digest, len(payload))
        return Generation(key=key, sha256=digest, rows=rows, as_of=str(key_source.get("as_of", "")))

    def get_generation(self, key: str, sha256: str) -> bytes:
        """Read one generation, SHA-verified against the registry digest."""
        raw = self._backend.get(key)
        if hashlib.sha256(raw).hexdigest() != sha256:
            raise ArchiveVerifyError(f"SHA mismatch reading {key}")
        return raw

    def read_generation(self, key: str, sha256: str) -> bytes:
        """Alias of :meth:`get_generation` (read-path naming)."""
        return self.get_generation(key, sha256)

    def swap_latest_pointer(self, pointer_key: str, generation_key_: str) -> None:
        """Atomically point *pointer_key* at *generation_key_*: a single put."""
        self._backend.put(pointer_key, generation_key_.encode("utf-8"))

    def read_latest(self, pointer_key: str) -> str:
        """Resolve a ``latest`` pointer to its generation key."""
        return self._backend.get(pointer_key).decode("utf-8")

    def write_manifest(self, manifest: dict[str, Any]) -> str:
        """Persist the manifest: version-checked, single put, read-back verified."""
        if manifest.get("version") != MANIFEST_VERSION:
            raise ValueError(
                f"unsupported manifest version {manifest.get('version')!r}: "
                f"expected {MANIFEST_VERSION}"
            )
        raw = json.dumps(manifest, sort_keys=True).encode("utf-8")
        self._backend.put(MANIFEST_KEY, raw)
        digest = hashlib.sha256(raw).hexdigest()
        if hashlib.sha256(self._backend.get(MANIFEST_KEY)).hexdigest() != digest:
            raise ArchiveVerifyError(f"read-back mismatch for {MANIFEST_KEY}")
        return digest

    def read_manifest(self) -> dict[str, Any]:
        """Read the manifest; reject any ``version != MANIFEST_VERSION``."""
        payload = json.loads(self._backend.get(MANIFEST_KEY).decode("utf-8"))
        if payload.get("version") != MANIFEST_VERSION:
            raise ValueError(
                f"unsupported manifest version {payload.get('version')!r}: "
                f"expected {MANIFEST_VERSION}"
            )
        return payload


__all__ = [
    "MANIFEST_KEY",
    "MANIFEST_VERSION",
    "SOURCE_TABLE_MACRO",
    "SOURCE_TABLE_PRICE",
    "SOURCE_TABLE_SNAPSHOT",
    "ArchiveVerifyError",
    "Generation",
    "R2HistoryStore",
    "RegistryInsert",
    "build_manifest",
    "generation_key",
    "latest_pointer_key",
    "macro_key",
    "macro_latest_pointer_key",
    "normalize_ticker",
    "snapshot_key",
]
