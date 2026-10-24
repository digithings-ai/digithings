"""Tests for the Bitview/BRK on-chain series client (#1086 platform ingest).

Captured SeriesData shape is from live Bitview ``GET /api/series/mvrv/day1``
on 2026-08-30 (start=800, five f32 values). Parser is HTTP-free; the client
is exercised with an injected session (no network).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

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

from tests.dq.data.onchain_fakes import FakeSession, mvrv_slice

pytestmark = pytest.mark.unit


class TestDay1Index:
    def test_genesis_is_index_zero(self) -> None:
        assert day1_index_to_date(0) == DAY1_EPOCH
        assert DAY1_EPOCH == date(2009, 1, 3)

    def test_captured_start_800_is_2011_03_14(self) -> None:
        assert day1_index_to_date(800) == date(2011, 3, 14)


class TestSeriesDataParser:
    def test_parses_captured_shape_to_polars(self) -> None:
        frame = series_data_to_frame(mvrv_slice(), series_id="mvrv")
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
    def test_bulk_parses_v1_catalog(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_DATA_ROOT", str(tmp_path))
        bodies = [
            mvrv_slice(),
            {**mvrv_slice(), "data": [1.01, 1.02, 1.00, 0.99, 1.03]},
            {**mvrv_slice(), "data": [0.5, 0.6, 0.55, 0.7, 0.65]},
            {**mvrv_slice(), "data": [0.1, 0.2, 0.15, 0.18, 0.12]},
        ]
        session = FakeSession(body=bodies)
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

    def test_rejects_cache_dir_outside_data_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # DIG-4057 batch B: the cache sink is confined to DIGIQUANT_DATA_ROOT.
        monkeypatch.setenv("DIGIQUANT_DATA_ROOT", str(tmp_path / "root"))
        session = FakeSession(body=[mvrv_slice()])
        client = BitviewClient(session=session, cache_dir=tmp_path / "outside")
        result = client.fetch(["mvrv"])
        assert "DIGIQUANT_DATA_ROOT" in str(result.series["mvrv"].error)

    def test_refuses_nupl_without_http(self) -> None:
        session = FakeSession(exc=AssertionError("must not fetch nupl"))
        result = BitviewClient(session=session).fetch(["nupl"])
        assert "nupl" in FORBIDDEN_SERIES
        nupl = result.series["nupl"]
        assert nupl.error is not None
        assert "dual-count" in nupl.error
        assert session.calls == []

    def test_fail_soft_on_network_error(self) -> None:
        session = FakeSession(exc=ConnectionError("boom"))
        result = BitviewClient(session=session).fetch(["mvrv"])
        assert result.error is not None
        assert result.series["mvrv"].error is not None
        assert result.series["mvrv"].has_data is False

    def test_per_series_fallback_when_bulk_shape_wrong(self) -> None:
        session = FakeSession(
            by_url={
                "/api/series/bulk": {"error": {"message": "nope"}},
                "/api/series/mvrv/day1": mvrv_slice(),
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
        session = FakeSession(body=[mvrv_slice()])
        BitviewClient(session=session).fetch(["mvrv"])
        _url, kwargs = session.calls[0]
        assert "digiquant" in kwargs["headers"]["User-Agent"]
        assert BITVIEW_BASE_URL.startswith("https://")

    def test_allow_derived_bypasses_nupl_refusal(self) -> None:
        session = FakeSession(body=[mvrv_slice()])
        result = BitviewClient(session=session).fetch(["nupl"], allow_derived=True)
        nupl = result.series["nupl"]
        assert nupl.has_data
        assert session.calls != []

    def test_allow_derived_false_still_refuses_nupl(self) -> None:
        session = FakeSession(exc=AssertionError("must not fetch nupl"))
        result = BitviewClient(session=session).fetch(["nupl"], allow_derived=False)
        assert result.series["nupl"].error is not None
        assert session.calls == []

    def test_fetch_bitview_series_allow_derived_bypasses_nupl_refusal(self) -> None:
        session = FakeSession(body=[mvrv_slice()])
        result = fetch_bitview_series(["nupl"], session=session, allow_derived=True)
        assert result.series["nupl"].has_data

    def test_client_refuses_untrusted_base_url(self) -> None:
        with pytest.raises(ValueError, match="not allowlisted"):
            BitviewClient(
                session=FakeSession(body=[mvrv_slice()]), base_url="https://evil.example.com"
            )

    def test_fetch_function_refuses_attacker_base_url_without_fetch(self) -> None:
        session = FakeSession(body=[mvrv_slice()])
        result = fetch_bitview_series(
            ["mvrv"], session=session, base_url="http://169.254.169.254/latest/meta-data"
        )
        assert result.error is not None
        assert "refusing untrusted base_url" in result.error
        assert session.calls == []

    def test_series_id_path_injection_rejected_without_fetch(self) -> None:
        session = FakeSession(body=[mvrv_slice()])
        result = BitviewClient(session=session).fetch(["../../etc/passwd"])
        assert result.series["../../etc/passwd"].error is not None
        assert session.calls == []
