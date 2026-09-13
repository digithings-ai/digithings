"""WP10.4 — shared-cash Nautilus portfolio replay (#2784).

Real engine work runs only inside spawned workers (one engine per process).
"""

from __future__ import annotations

import ast
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    HoldingQuantity,
    InstrumentBarSeries,
    OhlcvBar,
    PortfolioReplayRequest,
    PortfolioReplayStatus,
    ScheduledTargetWeights,
    TargetWeight,
)
from digiquant.dashboard.replay.worker import run_portfolio_replay_isolated

pytestmark = pytest.mark.unit

nautilus = pytest.importorskip("nautilus_trader")

_UTC = timezone.utc
_REPLAY_ROOT = (
    Path(__file__).resolve().parents[3] / "digiquant" / "src" / "digiquant" / "dashboard" / "replay"
)
_PRODUCTION_GUARD_PATHS = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "portfolio"
    / "chain.py",
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "portfolio"
    / "phases"
    / "phase7e_risk_sizing.py",
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "portfolio"
    / "phases"
    / "h9_commit_run.py",
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "portfolio"
    / "shadow_artifact.py",
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


def _two_asset_request(
    *,
    request_id: str,
    commission: str = "0",
    targets: tuple[tuple[str, str], ...] = (("AAPL", "0.4"), ("MSFT", "0.4")),
    initial: tuple[tuple[str, str], ...] = (),
    fill_fraction: str = "1",
    aapl_closes: list[str] | None = None,
    msft_closes: list[str] | None = None,
    cash: str = "100000",
) -> PortfolioReplayRequest:
    aapl = aapl_closes or ["100", "101", "102", "103", "104"]
    msft = msft_closes or ["200", "201", "202", "203", "204"]
    return PortfolioReplayRequest(
        request_id=request_id,
        starting_cash=Decimal(cash),
        series=(
            InstrumentBarSeries(
                ticker="AAPL",
                bars=tuple(_bar(i + 2, c) for i, c in enumerate(aapl)),
            ),
            InstrumentBarSeries(
                ticker="MSFT",
                bars=tuple(_bar(i + 2, c) for i, c in enumerate(msft)),
            ),
        ),
        target_weights=tuple(TargetWeight(ticker=t, weight=Decimal(w)) for t, w in targets),
        initial_holdings=tuple(HoldingQuantity(ticker=t, quantity=Decimal(q)) for t, q in initial),
        execution=ExecutionPolicy(
            commission_rate=Decimal(commission),
            fill_fraction=Decimal(fill_fraction),
            next_bar_execution=True,
        ),
    )


def test_shared_cash_replay_ok_and_deterministic(tmp_path: Path) -> None:
    req = _two_asset_request(request_id="det-1", commission="0.001")
    a = run_portfolio_replay_isolated(req, work_dir=tmp_path / "a")
    b = run_portfolio_replay_isolated(req, work_dir=tmp_path / "b")
    assert a.status == PortfolioReplayStatus.OK
    assert b.status == PortfolioReplayStatus.OK
    assert a.result_content_hash == b.result_content_hash
    assert a.ending_nav == b.ending_nav
    assert a.ending_cash is not None
    assert a.holdings
    assert a.nav_path
    assert len(a.nav_path) == len(b.nav_path)
    assert a.nav_path == b.nav_path
    assert a.total_commission is not None
    assert a.total_commission > 0
    # Costs reduce shared NAV vs a zero-commission twin.
    free = run_portfolio_replay_isolated(
        _two_asset_request(request_id="det-free", commission="0"),
        work_dir=tmp_path / "free",
    )
    assert free.status == PortfolioReplayStatus.OK
    assert free.ending_nav is not None and a.ending_nav is not None
    assert a.ending_nav < free.ending_nav


def test_hold_add_trim_exit_noop_partial(tmp_path: Path) -> None:
    # Seed a funded book near 40/40, then hold (same targets).
    hold = run_portfolio_replay_isolated(
        _two_asset_request(
            request_id="hold",
            initial=(("AAPL", "100"), ("MSFT", "50")),
            cash="80000",
            targets=(("AAPL", "0.4"), ("MSFT", "0.4")),
        ),
        work_dir=tmp_path / "hold",
    )
    assert hold.status == PortfolioReplayStatus.OK

    add = run_portfolio_replay_isolated(
        _two_asset_request(
            request_id="add",
            targets=(("AAPL", "0.6"), ("MSFT", "0.2")),
        ),
        work_dir=tmp_path / "add",
    )
    assert add.status == PortfolioReplayStatus.OK
    assert any(f.side == "BUY" and f.ticker == "AAPL" and not f.is_seed for f in add.fills)

    trim = run_portfolio_replay_isolated(
        _two_asset_request(
            request_id="trim",
            initial=(("AAPL", "400"), ("MSFT", "50")),
            cash="50000",
            targets=(("AAPL", "0.2"), ("MSFT", "0.2")),
        ),
        work_dir=tmp_path / "trim",
    )
    assert trim.status == PortfolioReplayStatus.OK
    assert any(f.side == "SELL" and f.ticker == "AAPL" and not f.is_seed for f in trim.fills)

    exit_ = run_portfolio_replay_isolated(
        _two_asset_request(
            request_id="exit",
            initial=(("AAPL", "100"),),
            cash="90000",
            targets=(),
        ),
        work_dir=tmp_path / "exit",
    )
    assert exit_.status == PortfolioReplayStatus.OK
    assert any(f.side == "SELL" and f.ticker == "AAPL" and not f.is_seed for f in exit_.fills)
    aapl_end = next(h for h in exit_.holdings if h.ticker == "AAPL")
    assert aapl_end.quantity == 0

    noop = run_portfolio_replay_isolated(
        _two_asset_request(
            request_id="noop",
            targets=(),
            cash="100000",
        ),
        work_dir=tmp_path / "noop",
    )
    assert noop.status == PortfolioReplayStatus.OK
    assert all(f.is_seed for f in noop.fills) or not noop.fills
    assert noop.ending_nav == Decimal("100000.00")

    partial = run_portfolio_replay_isolated(
        _two_asset_request(
            request_id="partial",
            fill_fraction="0.5",
            targets=(("AAPL", "0.8"), ("MSFT", "0.0")),
        ),
        work_dir=tmp_path / "partial",
    )
    full = run_portfolio_replay_isolated(
        _two_asset_request(
            request_id="full",
            fill_fraction="1",
            targets=(("AAPL", "0.8"), ("MSFT", "0.0")),
        ),
        work_dir=tmp_path / "full",
    )
    assert partial.status == full.status == PortfolioReplayStatus.OK
    p_qty = next(h.quantity for h in partial.holdings if h.ticker == "AAPL")
    f_qty = next(h.quantity for h in full.holdings if h.ticker == "AAPL")
    assert p_qty < f_qty


def test_shared_cash_differs_from_independent_fully_funded_average(tmp_path: Path) -> None:
    """Metric: shared-cash NAV ≠ mean of independently fully funded single-asset engines."""
    shared = run_portfolio_replay_isolated(
        _two_asset_request(
            request_id="shared",
            cash="100000",
            commission="0.001",
            targets=(("AAPL", "0.5"), ("MSFT", "0.5")),
            aapl_closes=["100", "110", "120", "130", "140"],
            msft_closes=["200", "180", "160", "140", "120"],
        ),
        work_dir=tmp_path / "shared",
    )
    assert shared.status == PortfolioReplayStatus.OK
    assert shared.ending_nav is not None

    # Independently fully funded: each symbol gets the full $100k in its own request.
    aapl_only = run_portfolio_replay_isolated(
        PortfolioReplayRequest(
            request_id="ind-aapl",
            starting_cash=Decimal("100000"),
            series=(
                InstrumentBarSeries(
                    ticker="AAPL",
                    bars=tuple(
                        _bar(i + 2, c) for i, c in enumerate(["100", "110", "120", "130", "140"])
                    ),
                ),
            ),
            target_weights=(TargetWeight(ticker="AAPL", weight=Decimal("1.0")),),
            execution=ExecutionPolicy(commission_rate=Decimal("0.001")),
        ),
        work_dir=tmp_path / "ind-aapl",
    )
    msft_only = run_portfolio_replay_isolated(
        PortfolioReplayRequest(
            request_id="ind-msft",
            starting_cash=Decimal("100000"),
            series=(
                InstrumentBarSeries(
                    ticker="MSFT",
                    bars=tuple(
                        _bar(i + 2, c) for i, c in enumerate(["200", "180", "160", "140", "120"])
                    ),
                ),
            ),
            target_weights=(TargetWeight(ticker="MSFT", weight=Decimal("1.0")),),
            execution=ExecutionPolicy(commission_rate=Decimal("0.001")),
        ),
        work_dir=tmp_path / "ind-msft",
    )
    assert aapl_only.status == msft_only.status == PortfolioReplayStatus.OK
    assert aapl_only.ending_nav is not None and msft_only.ending_nav is not None
    independent_avg = (aapl_only.ending_nav + msft_only.ending_nav) / 2
    assert shared.ending_nav != independent_avg

    # Reconcile shared cash/holdings/NAV/costs.
    holdings_value = sum((h.market_value for h in shared.holdings), Decimal("0"))
    assert shared.ending_cash is not None
    assert shared.ending_nav == (shared.ending_cash + holdings_value).quantize(Decimal("0.01"))
    assert shared.total_commission is not None and shared.total_commission > 0
    assert shared.rebalance_commission == shared.total_commission


def test_production_surfaces_do_not_import_replay() -> None:
    for path in _PRODUCTION_GUARD_PATHS:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "dashboard.replay" not in node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "dashboard.replay" not in alias.name


def test_nautilus_portfolio_module_never_calls_multi_symbol_runner() -> None:
    tree = ast.parse((_REPLAY_ROOT / "nautilus_portfolio.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "nautilus_runner" not in node.module
        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            assert name != "_run_multi_symbol_backtest"


# ---------------------------------------------------------------------------
# weight_schedule engine (schema 2.0, #3695)
#
# Bar volumes are deliberately huge: Nautilus market-order fills are
# constrained by bar volume, and the 1M default would split/slew orders
# at production notional. Real ETF volumes are tens of millions.
# ---------------------------------------------------------------------------


def _sched_bar(day: int, close: str, volume: str = "10000000000") -> OhlcvBar:
    px = Decimal(close)
    return OhlcvBar(
        ts=datetime(2024, 1, day, tzinfo=_UTC),
        open=px,
        high=px,
        low=px,
        close=px,
        volume=Decimal(volume),
    )


def test_schedule_rotation_same_bar_fills(tmp_path: Path) -> None:
    req = PortfolioReplayRequest(
        request_id="sched-rot",
        starting_cash=Decimal("100000000"),
        series=(
            InstrumentBarSeries(
                ticker="AAPL",
                bars=tuple(_sched_bar(d, "100") for d in (2, 3, 4, 5, 6)),
            ),
            InstrumentBarSeries(
                ticker="MSFT",
                bars=tuple(
                    _sched_bar(d, c)
                    for d, c in zip((2, 3, 4, 5, 6), ("200", "210", "220", "230", "240"))
                ),
            ),
        ),
        target_weights=(),
        schema_version="2.0",
        execution=ExecutionPolicy(commission_rate=Decimal("0"), next_bar_execution=False),
        weight_schedule=(
            ScheduledTargetWeights(
                effective_date=date(2024, 1, 2),
                weights=(
                    TargetWeight(ticker="AAPL", weight=Decimal("0.5")),
                    TargetWeight(ticker="MSFT", weight=Decimal("0.5")),
                ),
            ),
            ScheduledTargetWeights(
                effective_date=date(2024, 1, 4),
                weights=(TargetWeight(ticker="AAPL", weight=Decimal("1.0")),),
            ),
        ),
    )
    res = run_portfolio_replay_isolated(req, work_dir=tmp_path / "sched-rot")
    assert res.status == PortfolioReplayStatus.OK
    assert res.schema_version == "2.0"

    # Day-2 entry fills land at the submitting bar's exact close (causal,
    # same-bar fills — the book dated D earns the move into D+1). Schedule
    # orders are tagged "rebalance", never "seed".
    by_day: dict[str, set[tuple[str, str, Decimal]]] = {}
    for f in res.fills:
        by_day.setdefault(f.ts.date().isoformat(), set()).add((f.ticker, f.side, f.price))
    assert by_day.get("2024-01-02") == {
        ("AAPL", "BUY", Decimal("100")),
        ("MSFT", "BUY", Decimal("200")),
    }

    # Day-4 rotation fills land at that bar's exact close.
    assert ("MSFT", "SELL", Decimal("220")) in by_day.get("2024-01-04", set())
    assert ("AAPL", "BUY", Decimal("100")) in by_day.get("2024-01-04", set())

    # NAV math: 100M → day3 102.5M (MSFT 200→210) → day4 105M
    # (MSFT 210→220) → flat at 105M fully in AAPL.
    assert res.ending_nav == Decimal("105000000.00")
    aapl_end = next(h for h in res.holdings if h.ticker == "AAPL")
    assert aapl_end.quantity == Decimal("1050000")
    msft_end = next(h for h in res.holdings if h.ticker == "MSFT")
    assert msft_end.quantity == 0
    nav_by_day = {p.ts.date().isoformat(): p.nav for p in res.nav_path}
    assert nav_by_day["2024-01-03"] == Decimal("102500000.00")
    assert nav_by_day["2024-01-04"] == Decimal("105000000.00")
