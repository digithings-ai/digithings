"""Tests for the BGeometrics/bitcoin-data.com on-chain series client (#3694).

Captured row shapes are from live ``GET https://api.bitcoin-data.com/v1/mvrv``
and ``/v1/mvrv/last`` on 2026-09-10. Parser is HTTP-free; the client is
exercised with an injected session (no network).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any  # score:allow untyped any — fake HTTP session / JSON bodies

import polars as pl
import pytest
from digiquant.data.onchain.bgeometrics import (
    BGEOMETRICS_BASE_URL,
    FREE_TIER_NOTE,
    BgeometricsClient,
    bgeometrics_rows_to_frame,
    fetch_bgeometrics_series,
)

pytestmark = pytest.mark.unit


def _mvrv_range() -> list[dict[str, Any]]:
    """Captured shape: ``GET /v1/mvrv?startday=2025-01-01&endday=2025-01-03``."""
    return [
        {"d": "2025-01-01", "unixTs": 1735689600, "mvrv": 2.3579},
        {"d": "2025-01-02", "unixTs": 1735776000, "mvrv": 2.3863},
        {"d": "2025-01-03", "unixTs": 1735862400, "mvrv": 2.3875},
    ]


def _mvrv_last() -> dict[str, Any]:
    """Captured shape: ``GET /v1/mvrv/last``."""
    return {"d": "2026-09-09", "unixTs": 1788912000, "mvrv": 1.4808}


class _FakeResp:
    def __init__(self, body: object, status: int = 200) -> None:
        self._body = body
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "https://api.bitcoin-data.com/v1/mvrv"),
                response=httpx.Response(self.status_code, json=self._body),
            )

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
        return _FakeResp(self._body if self._body is not None else {})


class TestBgeometricsRowsParser:
    def test_parses_range_response_to_polars(self) -> None:
        frame = bgeometrics_rows_to_frame(_mvrv_range())
        assert frame.height == 3
        assert frame["date"].dtype == pl.Date
        assert frame["date"][0] == date(2025, 1, 1)
        assert frame["date"][-1] == date(2025, 1, 3)
        assert frame["value"][0] == pytest.approx(2.3579)
        assert frame["value"][-1] == pytest.approx(2.3875)

    def test_parses_single_row_dict(self) -> None:
        frame = bgeometrics_rows_to_frame(_mvrv_last())
        assert frame.height == 1
        assert frame["date"][0] == date(2026, 9, 9)
        assert frame["value"][0] == pytest.approx(1.4808)

    def test_malformed_is_empty_not_raise(self) -> None:
        assert bgeometrics_rows_to_frame(None).height == 0
        assert bgeometrics_rows_to_frame("nope").height == 0
        assert bgeometrics_rows_to_frame({"d": "not-a-date", "mvrv": 1.0}).height == 0
        assert bgeometrics_rows_to_frame({"d": "2025-01-01"}).height == 0
        assert bgeometrics_rows_to_frame([{"unixTs": 1, "mvrv": 1.0}]).height == 0

    def test_ignores_paging_metadata_fields(self) -> None:
        row = {"d": "2025-01-01", "unixTs": 1, "mvrv": 2.5, "page": 0, "totalPages": 4}
        frame = bgeometrics_rows_to_frame(row)
        assert frame.height == 1
        assert frame["value"][0] == pytest.approx(2.5)


class TestBgeometricsClient:
    def test_range_fetch_writes_parquet(self, tmp_path: Path) -> None:
        session = _FakeSession(body=_mvrv_range())
        result = BgeometricsClient(session=session, cache_dir=tmp_path).fetch(
            "mvrv", startday="2025-01-01", endday="2025-01-03"
        )
        assert result.error is None
        assert result.has_data
        assert result.row_count == 3
        assert result.date_start == date(2025, 1, 1)
        assert Path(result.path or "").exists()
        loaded = pl.read_parquet(result.path)
        assert loaded.columns == ["date", "value"]
        assert result.note == FREE_TIER_NOTE

    def test_last_fetch_uses_last_endpoint(self) -> None:
        session = _FakeSession(body=_mvrv_last())
        result = BgeometricsClient(session=session).fetch("mvrv", last=True)
        assert result.has_data
        assert result.row_count == 1
        url, _kwargs = session.calls[0]
        assert url.endswith("/v1/mvrv/last")

    def test_fail_soft_on_network_error(self) -> None:
        session = _FakeSession(exc=ConnectionError("boom"))
        result = BgeometricsClient(session=session).fetch("mvrv")
        assert result.error is not None
        assert result.has_data is False

    def test_rate_limit_error_message_surfaced(self) -> None:
        body = {
            "error": {
                "status": 429,
                "code": "RATE_LIMIT_HOUR_EXCEEDED",
                "message": "Too many requests. Hourly limit of 10 requests exceeded.",
            }
        }
        class _RateLimited(_FakeSession):
            def get(self, url: str, **kwargs: Any) -> _FakeResp:
                self.calls.append((url, kwargs))
                return _FakeResp(body, status=429)

        limited = _RateLimited()
        result = BgeometricsClient(session=limited).fetch("mvrv")
        assert result.error is not None
        assert "Hourly limit" in result.error

    def test_empty_metric_is_error(self) -> None:
        result = BgeometricsClient(session=_FakeSession(body={})).fetch("")
        assert result.error is not None

    def test_no_data_is_fail_soft_error(self) -> None:
        session = _FakeSession(body=[])
        result = BgeometricsClient(session=session).fetch("mvrv", startday="2014-01-01", endday="2014-01-10")
        assert result.error is not None
        assert result.has_data is False

    def test_env_kill_switch_skips_network(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_BGEOMETRICS_FETCH", "0")
        result = fetch_bgeometrics_series("mvrv")
        assert result.error is not None
        assert "disabled" in (result.error or "")

    def test_token_sent_as_bearer_header(self) -> None:
        session = _FakeSession(body=_mvrv_last())
        BgeometricsClient(session=session, token="secret-token").fetch("mvrv", last=True)
        _url, kwargs = session.calls[0]
        assert kwargs["headers"]["Authorization"] == "Bearer secret-token"

    def test_token_also_sent_as_x_bgapi_token_header(self) -> None:
        session = _FakeSession(body=_mvrv_last())
        BgeometricsClient(session=session, token="secret-token").fetch("mvrv", last=True)
        _url, kwargs = session.calls[0]
        assert kwargs["headers"]["X-Bgapi-Token"] == "secret-token"

    def test_no_token_sends_neither_auth_header(self) -> None:
        session = _FakeSession(body=_mvrv_last())
        BgeometricsClient(session=session).fetch("mvrv", last=True)
        _url, kwargs = session.calls[0]
        assert "Authorization" not in kwargs["headers"]
        assert "X-Bgapi-Token" not in kwargs["headers"]

    def test_base_url_is_https(self) -> None:
        assert BGEOMETRICS_BASE_URL.startswith("https://")

    # ── SSRF + env-token exfiltration guards (#3944) ──────────────────────

    def test_untrusted_base_url_raises_at_client_construction(self) -> None:
        with pytest.raises(ValueError, match="not allowlisted"):
            BgeometricsClient(session=_FakeSession(), base_url="https://evil.example.com")

    def test_fetch_function_refuses_attacker_base_url_without_fetch(self) -> None:
        session = _FakeSession(body=_mvrv_last())
        result = fetch_bgeometrics_series(
            "mvrv", session=session, base_url="http://169.254.169.254/latest/meta-data"
        )
        assert result.error is not None
        assert "refusing untrusted base_url" in result.error
        assert session.calls == []

    def test_env_token_never_sent_to_caller_nominated_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BGEOMETRICS_API_TOKEN", "server-owned-secret")
        session = _FakeSession(body=_mvrv_last())
        result = fetch_bgeometrics_series(
            "mvrv", session=session, last=True, base_url="https://evil.example.com"
        )
        assert result.error is not None
        # Refused before any request, so the token cannot be attached to a
        # caller-nominated host.
        assert session.calls == []

    def test_env_token_sent_only_to_trusted_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BGEOMETRICS_API_TOKEN", "server-owned-secret")
        session = _FakeSession(body=_mvrv_last())
        fetch_bgeometrics_series("mvrv", session=session, last=True)
        _url, kwargs = session.calls[0]
        assert kwargs["headers"]["Authorization"] == "Bearer server-owned-secret"

    @pytest.mark.parametrize(
        "bad_metric",
        ["../secret", "mvrv?x=1", "mvrv/../sopr", "MVRV", "mvrv%2f..", "mvrv last", "a/b"],
    )
    def test_metric_is_not_a_path_or_query_injection_sink(self, bad_metric: str) -> None:
        session = _FakeSession(body=_mvrv_last())
        result = BgeometricsClient(session=session).fetch(bad_metric, last=True)
        assert result.error is not None
        assert "metric must match" in result.error
        assert session.calls == []

    def test_known_metric_still_fetches(self) -> None:
        session = _FakeSession(body=_mvrv_last())
        result = BgeometricsClient(session=session).fetch("mvrv", last=True)
        assert result.has_data
        assert session.calls != []
