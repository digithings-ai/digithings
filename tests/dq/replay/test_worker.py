"""WP10.4 — spawn worker isolation for portfolio replay (#2784)."""

from __future__ import annotations

import json
import multiprocessing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    InstrumentBarSeries,
    OhlcvBar,
    PortfolioReplayRequest,
    PortfolioReplayResult,
    PortfolioReplayStatus,
    TargetWeight,
)
from digiquant.dashboard.replay.worker import run_portfolio_replay_isolated

pytestmark = pytest.mark.unit

_UTC = timezone.utc


def _bar(day: int, close: str) -> OhlcvBar:
    px = Decimal(close)
    return OhlcvBar(
        ts=datetime(2024, 1, day, tzinfo=_UTC),
        open=px,
        high=px + Decimal("1"),
        low=px - Decimal("1"),
        close=px,
        volume=Decimal("1000000"),
    )


def _minimal_request(request_id: str = "iso-1") -> PortfolioReplayRequest:
    return PortfolioReplayRequest(
        request_id=request_id,
        starting_cash=Decimal("100000"),
        series=(
            InstrumentBarSeries(
                ticker="AAPL",
                bars=(_bar(2, "100"), _bar(3, "101"), _bar(4, "102"), _bar(5, "103")),
            ),
            InstrumentBarSeries(
                ticker="MSFT",
                bars=(_bar(2, "200"), _bar(3, "201"), _bar(4, "202"), _bar(5, "203")),
            ),
        ),
        target_weights=(
            TargetWeight(ticker="AAPL", weight=Decimal("0.4")),
            TargetWeight(ticker="MSFT", weight=Decimal("0.4")),
        ),
        execution=ExecutionPolicy(commission_rate=Decimal("0")),
    )


def test_timeout_is_typed_inconclusive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _HangProcess:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.exitcode: int | None = None

        def start(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return True

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            self.exitcode = -9

    monkeypatch.setattr(
        "digiquant.dashboard.replay.worker._SPAWN_CTX.Process",
        _HangProcess,
    )
    result = run_portfolio_replay_isolated(
        _minimal_request("timeout-1"),
        timeout_s=0.01,
        work_dir=tmp_path,
    )
    assert result.status == PortfolioReplayStatus.TIMEOUT
    assert result.ending_nav is None
    assert "timeout" in result.message.lower()


def test_crash_without_result_json_is_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _CrashProcess:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.exitcode: int | None = None

        def start(self) -> None:
            self.exitcode = -6

        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return False

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    monkeypatch.setattr(
        "digiquant.dashboard.replay.worker._SPAWN_CTX.Process",
        _CrashProcess,
    )
    result = run_portfolio_replay_isolated(
        _minimal_request("crash-1"),
        timeout_s=5,
        work_dir=tmp_path,
    )
    assert result.status == PortfolioReplayStatus.CRASH
    assert "SIGABRT" in result.message
    assert result.ending_nav is None


def test_worker_json_roundtrip_writes_result(tmp_path: Path) -> None:
    pytest.importorskip("nautilus_trader")
    result = run_portfolio_replay_isolated(
        _minimal_request("json-1"),
        timeout_s=60,
        work_dir=tmp_path,
    )
    assert result.status == PortfolioReplayStatus.OK
    out = tmp_path / "portfolio-replay-json-1-result.json"
    assert out.is_file()
    loaded = PortfolioReplayResult.model_validate(json.loads(out.read_text()))
    assert loaded.result_content_hash == result.result_content_hash


def test_spawn_context_is_spawn_not_fork() -> None:
    from digiquant.dashboard.replay import worker as worker_mod

    assert worker_mod._SPAWN_CTX.get_start_method() == "spawn"
    assert multiprocessing.get_context("spawn").get_start_method() == "spawn"
