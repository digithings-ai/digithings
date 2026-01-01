"""In-memory R2 market-data store for parity tests (#4013)."""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any

import polars as pl
import pytest
from digiquant.data.prices.r2_history import (
    MANIFEST_KEY,
    SOURCE_TABLE_PRICE,
    generation_key,
    latest_pointer_key,
    normalize_ticker,
)


class MemoryR2:
    """Dict-backed stand-in for R2HistoryStore's read surface."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.manifest: dict[str, Any] = {"version": 1, "as_of": "1970-01-01", "datasets": {}}

    def read_manifest(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.manifest))  # defensive copy

    def read_latest(self, pointer_key: str) -> str:
        return self.objects[pointer_key].decode("utf-8")

    def get_generation(self, key: str, sha256: str) -> bytes:
        payload = self.objects[key]
        assert hashlib.sha256(payload).hexdigest() == sha256, f"sha mismatch for {key}"
        return payload


def build_r2_market(rows_by_ticker: dict[str, list[dict[str, Any]]], *, as_of: str) -> MemoryR2:
    store = MemoryR2()
    store.manifest["as_of"] = as_of
    for ticker, rows in rows_by_ticker.items():
        frame = pl.DataFrame(rows).with_columns(pl.col("date").str.to_date())
        buf = io.BytesIO()
        frame.write_parquet(buf)
        payload = buf.getvalue()
        sha = hashlib.sha256(payload).hexdigest()
        key = generation_key(ticker, as_of)
        store.objects[key] = payload
        store.objects[latest_pointer_key(ticker)] = key.encode("utf-8")
        store.manifest["datasets"][normalize_ticker(ticker)] = {
            "object": key,
            "sha256": sha,
            "rows": frame.height,
            "source_table": SOURCE_TABLE_PRICE,
            "as_of": as_of,
        }
    store.objects[MANIFEST_KEY] = json.dumps(store.manifest).encode("utf-8")
    return store


@pytest.fixture
def r2_market(monkeypatch: pytest.MonkeyPatch):
    created: list[MemoryR2] = []

    def _build(rows_by_ticker: dict[str, list[dict[str, Any]]], *, as_of: str) -> MemoryR2:
        store = build_r2_market(rows_by_ticker, as_of=as_of)
        created.append(store)
        monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
        monkeypatch.setattr("digiquant.mcp_server._get_r2_store", lambda: store)
        return store

    return _build
