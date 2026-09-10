"""Tests for the CoinMetrics Community API on-chain series client (#3694).

Captured response shape is from live
``GET https://community-api.coinmetrics.io/v4/timeseries/asset-metrics``
on 2026-09-10. Parser is HTTP-free; the client is exercised with an
injected session (no network).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any  # score:allow untyped any — fake HTTP session / JSON bodies

import polars as pl
import pytest
from digiquant.data.onchain.coinmetrics import (
    COINMETRICS_BASE_URL,
    LICENSE_NOTE,
    CoinMetricsClient,
    asset_metrics_rows_to_frame,
    fetch_coinmetrics_series,
)

pytestmark = pytest.mark.unit


def _mvrv_payload() -> dict[str, Any]:
    """Captured shape (metric=CapMVRVCur, asset=btc)."""
    return {
        "data": [
            {"asset": "btc", "time": "2018-01-01T00:00:00.000000000Z", "CapMVRVCur": "2.69423548"},
            {"asset": "btc", "time": "2018-01-02T00:00:00.000000000Z", "CapMVRVCur": "2.92544313"},
            {"asset": "btc", "time": "2018-01-03T00:00:00.000000000Z", "CapMVRVCur": "2.96026687"},
        ]
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
    def __init__(self, *, body: object | None = None, exc: Exception | None = None) -> None:
        self._body = body
        self._exc = exc
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        self.calls.append((url, kwargs))
        if self._exc is not None:
            raise self._exc
        return _FakeResp(self._body if self._body is not None else {"data": []})


class TestAssetMetricsParser:
    def test_parses_captured_shape_to_polars(self) -> None:
        frame = asset_metrics_rows_to_frame(_mvrv_payload(), metric="CapMVRVCur")
        assert frame.height == 3
        assert frame["date"].dtype == pl.Date
        assert frame["date"][0] == date(2018, 1, 1)
        assert frame["date"][-1] == date(2018, 1, 3)
        assert frame["value"][0] == pytest.approx(2.69423548)
        assert frame["value"][-1] == pytest.approx(2.96026687)

    def test_string_values_are_converted_to_float(self) -> None:
        frame = asset_metrics_rows_to_frame(_mvrv_payload(), metric="CapMVRVCur")
        assert frame["value"].dtype == pl.Float64

    def test_malformed_is_empty_not_raise(self) -> None:
        assert asset_metrics_rows_to_frame(None, metric="CapMVRVCur").height == 0
        assert asset_metrics_rows_to_frame("nope", metric="CapMVRVCur").height == 0
        assert asset_metrics_rows_to_frame({"data": "x"}, metric="CapMVRVCur").height == 0
        payload = {"data": [{"asset": "btc", "time": "bad-time", "CapMVRVCur": "1.0"}]}
        assert asset_metrics_rows_to_frame(payload, metric="CapMVRVCur").height == 0

    def test_missing_metric_value_dropped(self) -> None:
        payload = {"data": [{"asset": "btc", "time": "2018-01-01T00:00:00.000000000Z"}]}
        assert asset_metrics_rows_to_frame(payload, metric="CapMVRVCur").height == 0


class TestCoinMetricsClient:
    def test_fetch_writes_parquet(self, tmp_path: Path) -> None:
        session = _FakeSession(body=_mvrv_payload())
        result = CoinMetricsClient(session=session, cache_dir=tmp_path).fetch(
            "CapMVRVCur", asset="btc", start_time="2018-01-01", end_time="2018-01-03"
        )
        assert result.error is None
        assert result.has_data
        assert result.row_count == 3
        assert result.date_start == date(2018, 1, 1)
        assert Path(result.path or "").exists()
        loaded = pl.read_parquet(result.path)
        assert loaded.columns == ["date", "value"]
        assert result.license == LICENSE_NOTE

    def test_request_params_include_asset_and_metric(self) -> None:
        session = _FakeSession(body=_mvrv_payload())
        CoinMetricsClient(session=session).fetch("CapMVRVCur", asset="btc")
        _url, kwargs = session.calls[0]
        assert kwargs["params"]["assets"] == "btc"
        assert kwargs["params"]["metrics"] == "CapMVRVCur"
        assert kwargs["params"]["frequency"] == "1d"

    def test_fail_soft_on_network_error(self) -> None:
        session = _FakeSession(exc=ConnectionError("boom"))
        result = CoinMetricsClient(session=session).fetch("CapMVRVCur")
        assert result.error is not None
        assert result.has_data is False

    def test_no_data_is_fail_soft_error(self) -> None:
        session = _FakeSession(body={"data": []})
        result = CoinMetricsClient(session=session).fetch("NoSuchMetric")
        assert result.error is not None
        assert result.has_data is False

    def test_empty_metric_is_error(self) -> None:
        result = CoinMetricsClient(session=_FakeSession()).fetch("")
        assert result.error is not None

    def test_env_kill_switch_skips_network(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_COINMETRICS_FETCH", "0")
        result = fetch_coinmetrics_series("CapMVRVCur")
        assert result.error is not None
        assert "disabled" in (result.error or "")

    def test_base_url_is_https(self) -> None:
        assert COINMETRICS_BASE_URL.startswith("https://")
