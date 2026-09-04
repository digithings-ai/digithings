"""Unit tests for Bitview → macro_series_observations ingest (#1086).

Injected HTTP session — no live Bitview. Fake supabase client records upserts.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from digiquant.data.onchain.ingest import (
    BITVIEW_SOURCE,
    frame_to_macro_rows,
    ingest_bitview,
)

pytestmark = pytest.mark.unit


def _mvrv_slice() -> dict[str, Any]:
    return {
        "version": 1,
        "index": "day1",
        "type": "StoredF32",
        "start": 800,
        "end": 805,
        "stamp": "2026-08-30T22:07:42Z",
        "data": [3.214286, 3.214286, 3.178571, 3.142857, 2.931034],
    }


class _FakeResp:
    def __init__(self, body: object, status: int = 200) -> None:
        self._body = body
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self._body


class _FakeSession:
    def __init__(self, body: object) -> None:
        self._body = body
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        self.calls.append(url)
        return _FakeResp(self._body)


class _FakeTable:
    def __init__(self, store: list[dict[str, Any]]) -> None:
        self._store = store
        self._rows: list[dict[str, Any]] = []

    def upsert(self, rows: list[dict[str, Any]], **kwargs: Any) -> _FakeTable:
        self._rows = list(rows)
        self._store.extend(rows)
        return self

    def execute(self) -> object:
        return object()


class _FakeClient:
    def __init__(self) -> None:
        self.store: list[dict[str, Any]] = []

    def table(self, name: str) -> _FakeTable:
        assert name == "macro_series_observations"
        return _FakeTable(self.store)


class TestFrameToMacroRows:
    def test_skips_null_values(self) -> None:
        frame = pl.DataFrame(
            {
                "date": [date(2020, 1, 1), date(2020, 1, 2)],
                "value": [1.5, None],
            }
        )
        rows = frame_to_macro_rows(frame, series_id="mvrv")
        assert len(rows) == 1
        assert rows[0]["source"] == BITVIEW_SOURCE
        assert rows[0]["series_id"] == "mvrv"
        assert rows[0]["obs_date"] == "2020-01-01"
        assert rows[0]["value"] == pytest.approx(1.5)


class TestIngestBitview:
    def test_writes_parquet_and_upserts(self, tmp_path: Path) -> None:
        session = _FakeSession(
            [
                _mvrv_slice(),
                {**_mvrv_slice(), "data": [1.0] * 5},
                {**_mvrv_slice(), "data": [0.5] * 5},
                {**_mvrv_slice(), "data": [0.2] * 5},
            ]
        )
        client = _FakeClient()
        result = ingest_bitview(
            ["mvrv", "asopr_24h", "puell_multiple", "rhodl_ratio"],
            cache_dir=tmp_path,
            session=session,
            supabase_client=client,
        )
        assert result.ok
        assert result.macro_rows == 20  # 4 series × 5 days
        assert result.upserted == 20
        assert (tmp_path / "mvrv.parquet").is_file()
        assert len(client.store) == 20
        assert {r["series_id"] for r in client.store} == {
            "mvrv",
            "asopr_24h",
            "puell_multiple",
            "rhodl_ratio",
        }

    def test_fail_soft_on_transport_error(self, tmp_path: Path) -> None:
        class _Boom:
            def get(self, url: str, **kwargs: Any) -> _FakeResp:
                raise RuntimeError("network down")

        result = ingest_bitview(["mvrv"], cache_dir=tmp_path, session=_Boom())
        assert result.ok is False
        assert result.error is not None
        assert result.macro_rows == 0
