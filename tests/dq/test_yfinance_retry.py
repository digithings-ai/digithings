"""Unit tests for digiquant sandbox yfinance_retry helpers (#396 / #3047).

The module lives at ``digiquant/sandbox/yfinance_retry.py`` (on the sandbox
image PYTHONPATH), not as a digiquant package import. Load via importlib and
stub ``yfinance`` so unit tests never hit Yahoo Finance.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

_SANDBOX_RETRY = (
    Path(__file__).resolve().parents[2] / "digiquant" / "sandbox" / "yfinance_retry.py"
)


class _FakeFrame:
    def __init__(self, *, empty: bool) -> None:
        self.empty = empty


def _load_retry_module(fake_yf: types.ModuleType) -> types.ModuleType:
    """Import yfinance_retry with *fake_yf* already registered as ``yfinance``."""
    sys.modules["yfinance"] = fake_yf
    # Drop a prior load so each test gets a fresh module bound to this stub.
    sys.modules.pop("yfinance_retry", None)
    spec = importlib.util.spec_from_file_location("yfinance_retry", _SANDBOX_RETRY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["yfinance_retry"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _cleanup_yf_modules() -> Any:
    yield
    sys.modules.pop("yfinance_retry", None)
    # Leave a real yfinance alone if present; only remove our stub.
    existing = sys.modules.get("yfinance")
    if existing is not None and getattr(existing, "__yfinance_retry_stub__", False):
        sys.modules.pop("yfinance", None)


@pytest.mark.unit
def test_download_with_retry_returns_non_empty_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def download(*_a: Any, **_k: Any) -> _FakeFrame:
        calls.append(1)
        return _FakeFrame(empty=False)

    fake = types.ModuleType("yfinance")
    fake.__yfinance_retry_stub__ = True  # type: ignore[attr-defined]
    fake.download = download  # type: ignore[attr-defined]
    mod = _load_retry_module(fake)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    frame = mod.download_with_retry("SPY", max_attempts=3, base_delay_s=0.01)
    assert frame.empty is False
    assert len(calls) == 1


@pytest.mark.unit
def test_download_with_retry_retries_empty_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes = [_FakeFrame(empty=True), _FakeFrame(empty=False)]
    sleeps: list[float] = []

    def download(*_a: Any, **_k: Any) -> _FakeFrame:
        return outcomes.pop(0)

    fake = types.ModuleType("yfinance")
    fake.__yfinance_retry_stub__ = True  # type: ignore[attr-defined]
    fake.download = download  # type: ignore[attr-defined]
    mod = _load_retry_module(fake)
    monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

    frame = mod.download_with_retry("QQQ", max_attempts=4, base_delay_s=1.5)
    assert frame.empty is False
    assert sleeps == [1.5]  # base_delay * 2**0 before second attempt


@pytest.mark.unit
def test_download_with_retry_raises_after_exhausted_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = types.ModuleType("yfinance")
    fake.__yfinance_retry_stub__ = True  # type: ignore[attr-defined]
    fake.download = lambda *_a, **_k: _FakeFrame(empty=True)  # type: ignore[attr-defined]
    mod = _load_retry_module(fake)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    with pytest.raises(RuntimeError, match="empty data"):
        mod.download_with_retry("IWM", max_attempts=2, base_delay_s=0.01)


@pytest.mark.unit
def test_download_with_retry_surfaces_last_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"n": 0}

    def download(*_a: Any, **_k: Any) -> _FakeFrame:
        attempts["n"] += 1
        raise ConnectionError(f"boom-{attempts['n']}")

    fake = types.ModuleType("yfinance")
    fake.__yfinance_retry_stub__ = True  # type: ignore[attr-defined]
    fake.download = download  # type: ignore[attr-defined]
    mod = _load_retry_module(fake)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    with pytest.raises(ConnectionError, match="boom-3"):
        mod.download_with_retry("DIA", max_attempts=3, base_delay_s=0.01)
    assert attempts["n"] == 3


@pytest.mark.unit
def test_history_with_retry_uses_ticker_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    histories = [_FakeFrame(empty=True), _FakeFrame(empty=False)]
    constructed: list[str] = []

    class _Ticker:
        def __init__(self, symbol: str) -> None:
            constructed.append(symbol)

        def history(self, **_kwargs: Any) -> _FakeFrame:
            return histories.pop(0)

    fake = types.ModuleType("yfinance")
    fake.__yfinance_retry_stub__ = True  # type: ignore[attr-defined]
    fake.Ticker = _Ticker  # type: ignore[attr-defined]
    mod = _load_retry_module(fake)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    frame = mod.history_with_retry("AAPL", max_attempts=3, base_delay_s=0.01, period="1mo")
    assert frame.empty is False
    assert constructed == ["AAPL", "AAPL"]
