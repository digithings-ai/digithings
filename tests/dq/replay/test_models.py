"""WP10.4 — portfolio replay model contracts (#2784)."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from digiquant.dashboard.replay.models import (
    FORBIDDEN_IMPORT_PREFIXES,
    ExecutionPolicy,
    HoldingQuantity,
    InstrumentBarSeries,
    NavPoint,
    OhlcvBar,
    PortfolioReplayRequest,
    PortfolioReplayStatus,
    TargetWeight,
    inconclusive_result,
    max_drawdown_from_nav_path,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_REPLAY_ROOT = (
    Path(__file__).resolve().parents[3] / "digiquant" / "src" / "digiquant" / "dashboard" / "replay"
)


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


def _series(ticker: str, closes: list[str]) -> InstrumentBarSeries:
    return InstrumentBarSeries(
        ticker=ticker,
        bars=tuple(_bar(i + 2, c) for i, c in enumerate(closes)),
    )


def test_request_rejects_mismatched_timestamps() -> None:
    with pytest.raises(ValueError, match="identical bar timestamps"):
        PortfolioReplayRequest(
            request_id="r1",
            starting_cash=Decimal("100000"),
            series=(
                _series("AAPL", ["100", "101", "102"]),
                InstrumentBarSeries(
                    ticker="MSFT",
                    bars=(
                        _bar(2, "200"),
                        _bar(3, "201"),
                        _bar(5, "203"),  # day 5 ≠ AAPL day 4
                    ),
                ),
            ),
            target_weights=(
                TargetWeight(ticker="AAPL", weight=Decimal("0.4")),
                TargetWeight(ticker="MSFT", weight=Decimal("0.4")),
            ),
        )


def test_request_rejects_weight_sum_over_one() -> None:
    with pytest.raises(ValueError, match="cannot exceed 1"):
        PortfolioReplayRequest(
            request_id="r1",
            starting_cash=Decimal("100000"),
            series=(
                _series("AAPL", ["100", "101", "102"]),
                _series("MSFT", ["200", "201", "202"]),
            ),
            target_weights=(
                TargetWeight(ticker="AAPL", weight=Decimal("0.6")),
                TargetWeight(ticker="MSFT", weight=Decimal("0.6")),
            ),
        )


def test_request_content_hash_stable() -> None:
    req = PortfolioReplayRequest(
        request_id="r1",
        starting_cash=Decimal("100000"),
        series=(
            _series("AAPL", ["100", "101", "102"]),
            _series("MSFT", ["200", "201", "202"]),
        ),
        target_weights=(
            TargetWeight(ticker="AAPL", weight=Decimal("0.4")),
            TargetWeight(ticker="MSFT", weight=Decimal("0.4")),
        ),
        initial_holdings=(HoldingQuantity(ticker="AAPL", quantity=Decimal("10")),),
        execution=ExecutionPolicy(commission_rate=Decimal("0.001")),
    )
    assert req.content_hash() == req.content_hash()
    assert len(req.content_hash()) == 64


def test_inconclusive_rejects_ok_status() -> None:
    with pytest.raises(ValueError, match="cannot use status=ok"):
        inconclusive_result(
            request_id="r1",
            request_content_hash="a" * 64,
            status=PortfolioReplayStatus.OK,
            message="nope",
        )


def test_max_drawdown_from_nav_path() -> None:
    assert max_drawdown_from_nav_path(()) is None
    single = (
        NavPoint(ts=datetime(2024, 1, 2, tzinfo=_UTC), nav=Decimal("100")),
    )
    assert max_drawdown_from_nav_path(single) == Decimal("0")
    path = (
        NavPoint(ts=datetime(2024, 1, 2, tzinfo=_UTC), nav=Decimal("100")),
        NavPoint(ts=datetime(2024, 1, 3, tzinfo=_UTC), nav=Decimal("110")),
        NavPoint(ts=datetime(2024, 1, 4, tzinfo=_UTC), nav=Decimal("88")),
        NavPoint(ts=datetime(2024, 1, 5, tzinfo=_UTC), nav=Decimal("100")),
    )
    assert max_drawdown_from_nav_path(path) == (Decimal("88") - Decimal("110")) / Decimal("110")


def test_replay_modules_forbid_production_imports() -> None:
    for path in sorted(_REPLAY_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        for module in imported:
            assert not any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            ), f"{path.name} imports {module}"


def test_replay_never_imports_multi_symbol_runner() -> None:
    for path in sorted(_REPLAY_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "nautilus_runner" not in node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "nautilus_runner" not in alias.name
            elif isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                assert name != "_run_multi_symbol_backtest"
                assert name != "run_nautilus_backtest"
