"""Same-day opens via a live fetch (#4053 Task 1). No network: yfinance is stubbed."""

from __future__ import annotations

import sys
import types

import pytest
from digiquant.data.prices.live_opens import fetch_live_open, fetch_live_opens

pytestmark = pytest.mark.unit


class _Iloc:
    def __init__(self, values: list) -> None:
        self._values = values

    def __getitem__(self, idx: int):
        return self._values[idx]


class _Ser:
    def __init__(self, v) -> None:
        self.iloc = _Iloc([v])


class _Frame:
    def __init__(self, v) -> None:
        self._v = v

    def __getitem__(self, key: str) -> _Ser:
        assert key == "Open"
        return _Ser(self._v)


def _frame(open) -> _Frame:
    return _Frame(open)


def _stub_yf(monkeypatch: pytest.MonkeyPatch, download) -> None:
    """Register a stub ``yfinance`` so tests never need the real package or network."""
    stub = types.ModuleType("yfinance")
    stub.download = download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", stub)


def _raise(*a, **k):
    raise RuntimeError("boom")


def test_live_open_returns_none_on_fetch_failure(monkeypatch) -> None:
    _stub_yf(monkeypatch, _raise)
    assert fetch_live_open("AAA", "2026-09-14") is None


def test_live_open_reads_first_open(monkeypatch) -> None:
    _stub_yf(monkeypatch, lambda *a, **k: _frame(open=101.5))
    assert fetch_live_open("AAA", "2026-09-14") == 101.5


def test_live_open_returns_none_for_unusable_opens(monkeypatch) -> None:
    for bad in (0.0, -1.0, float("nan"), float("inf"), None, "n/a"):
        _stub_yf(monkeypatch, lambda *a, _v=bad, **k: _frame(open=_v))
        assert fetch_live_open("AAA", "2026-09-14") is None


def test_live_open_returns_none_for_unparseable_date(monkeypatch) -> None:
    _stub_yf(monkeypatch, lambda *a, **k: _frame(open=101.5))
    assert fetch_live_open("AAA", "not-a-date") is None


def test_live_opens_batch_skips_failures(monkeypatch) -> None:
    def _fake(ticker: str, *a, **k):
        if ticker == "BAD":
            raise RuntimeError("boom")
        return _frame(open=10.0)

    _stub_yf(monkeypatch, _fake)
    assert fetch_live_opens(["AAA", "BAD"], "2026-09-14") == {"AAA": 10.0}
    assert fetch_live_opens([], "2026-09-14") == {}
