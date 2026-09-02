"""Tests for the Bitview/BRK on-chain series client (#1086 platform ingest).

Captured SeriesData shape is from live Bitview ``GET /api/series/mvrv/day1``
on 2026-08-30 (start=800, five f32 values). Parser is HTTP-free; the client
is exercised with an injected session (no network).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any  # score:allow untyped any — fake HTTP session / JSON bodies

import polars as pl
import pytest
from digiquant.data.onchain.bitview import (
    BITVIEW_BASE_URL,
    DAY1_EPOCH,
    DEFAULT_SERIES,
    FORBIDDEN_SERIES,
    BitviewClient,
    day1_index_to_date,
    fetch_bitview_series,
    series_data_to_frame,
)

pytestmark = pytest.mark.unit


def _mvrv_slice() -> dict[str, Any]:
    """Captured-shape SeriesData: day1 indexes 800–805 (2011-03-14…18)."""
    return {
        "version": 4126600656,
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
            raise httpx_status(self.status_code)

    def json(self) -> object:
        return self._body


def httpx_status(code: int) -> Exception:
    return RuntimeError(f"HTTP {code}")


class _FakeSession:
    def __init__(
        self,
        *,
        by_url: dict[str, object] | None = None,
        body: object | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._by_url = by_url or {}
        self._body = body
        self._exc = exc
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        self.calls.append((url, kwargs))
        if self._exc is not None:
            raise self._exc
        if url in self._by_url:
            return _FakeResp(self._by_url[url])
        for key, payload in self._by_url.items():
            if key in url:
                return _FakeResp(payload)
        return _FakeResp(self._body if self._body is not None else {})


class TestDay1Index:
    def test_genesis_is_index_zero(self) -> None:
        assert day1_index_to_date(0) == DAY1_EPOCH
        assert DAY1_EPOCH == date(2009, 1, 3)

    def test_captured_start_800_is_2011_03_14(self) -> None:
        assert day1_index_to_date(800) == date(2011, 3, 14)


class TestSeriesDataParser:
    def test_parses_captured_shape_to_polars(self) -> None:
        frame = series_data_to_frame(_mvrv_slice(), series_id="mvrv")
        assert frame.height == 5
        assert frame["date"].dtype == pl.Date
        assert frame["date"][0] == date(2011, 3, 14)
        assert frame["date"][-1] == date(2011, 3, 18)
        assert frame["value"][0] == pytest.approx(3.214286)
        assert frame["value"][-1] == pytest.approx(2.931034)

    def test_keeps_null_warmup_days(self) -> None:
        payload = {
            "index": "day1",
            "start": 0,
            "end": 3,
            "data": [None, None, 1.0],
        }
        frame = series_data_to_frame(payload, series_id="mvrv")
        assert frame.height == 3
        assert frame["value"].null_count() == 2
        assert frame["value"][-1] == pytest.approx(1.0)
        assert frame["date"][0] == date(2009, 1, 3)

    def test_malformed_is_empty_not_raise(self) -> None:
        assert series_data_to_frame(None).height == 0
        assert series_data_to_frame("nope").height == 0
        assert series_data_to_frame({"data": "x"}).height == 0
        assert series_data_to_frame({"start": "x", "data": [1]}).height == 0


class TestBitviewClient:
    def test_bulk_parses_v1_catalog(self, tmp_path: Path) -> None:
        bodies = [
            _mvrv_slice(),
            {**_mvrv_slice(), "data": [1.01, 1.02, 1.00, 0.99, 1.03]},
            {**_mvrv_slice(), "data": [0.5, 0.6, 0.55, 0.7, 0.65]},
            {**_mvrv_slice(), "data": [0.1, 0.2, 0.15, 0.18, 0.12]},
        ]
        session = _FakeSession(body=bodies)
        result = BitviewClient(session=session, cache_dir=tmp_path).fetch()
        assert result.error is None
        assert set(result.series) == set(DEFAULT_SERIES)
        mvrv = result.series["mvrv"]
        assert mvrv.has_data
        assert mvrv.row_count == 5
        assert mvrv.date_start == date(2011, 3, 14)
        assert Path(mvrv.path or "").exists()
        loaded = pl.read_parquet(mvrv.path)
        assert loaded.columns == ["date", "value"]
        assert "bulk" in session.calls[0][0]

    def test_refuses_nupl_without_http(self) -> None:
        session = _FakeSession(exc=AssertionError("must not fetch nupl"))
        result = BitviewClient(session=session).fetch(["nupl"])
        assert "nupl" in FORBIDDEN_SERIES
        nupl = result.series["nupl"]
        assert nupl.error is not None
        assert "dual-count" in nupl.error
        assert session.calls == []

    def test_fail_soft_on_network_error(self) -> None:
        session = _FakeSession(exc=ConnectionError("boom"))
        result = BitviewClient(session=session).fetch(["mvrv"])
        assert result.error is not None
        assert result.series["mvrv"].error is not None
        assert result.series["mvrv"].has_data is False

    def test_per_series_fallback_when_bulk_shape_wrong(self) -> None:
        session = _FakeSession(
            by_url={
                "/api/series/bulk": {"error": {"message": "nope"}},
                "/api/series/mvrv/day1": _mvrv_slice(),
            }
        )
        result = BitviewClient(session=session).fetch(["mvrv"])
        assert result.series["mvrv"].has_data
        urls = [u for u, _ in session.calls]
        assert any("/bulk" in u for u in urls)
        assert any(u.endswith("/api/series/mvrv/day1") for u in urls)

    def test_env_kill_switch_skips_network(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_BITVIEW_FETCH", "0")
        result = fetch_bitview_series(["mvrv"])
        assert result.error is not None
        assert "disabled" in (result.error or "")
        assert result.series["mvrv"].error is not None

    def test_user_agent_identifies_digiquant(self) -> None:
        session = _FakeSession(body=[_mvrv_slice()])
        BitviewClient(session=session).fetch(["mvrv"])
        _url, kwargs = session.calls[0]
        assert "digiquant" in kwargs["headers"]["User-Agent"]
        assert BITVIEW_BASE_URL.startswith("https://")
