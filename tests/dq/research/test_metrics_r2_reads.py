"""R2 market-data reads for the research-metrics trio (#4013, Phase A Task 2).

Each helper keeps its Supabase body for the default backend and gains an R2
branch (``r2_backend_enabled`` / ``r2_close_rows``) when
``DIGIQUANT_MARKET_DATA_BACKEND=r2``. Loaded via ``importlib.util`` like the
other script-level tests (``digiquant/scripts/`` is not an installed package).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any  # score:allow untyped any — script modules loaded by path
from unittest.mock import MagicMock

import pytest

# Registers Task 1's `r2_market` builder fixture for this module; pytest requires
# plugin modules to be named here rather than imported (an imported fixture would
# collide with the fixture-name parameters below under ruff F811).
pytest_plugins = ["tests.fixtures.r2_market"]

pytestmark = pytest.mark.unit

_RESEARCH_SCRIPTS = Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "research"

# refresh_performance_metrics imports this sibling script at module level; stub it
# so the import succeeds outside the script's own directory (same as
# test_refresh_performance_metrics.py).
_sibling_stub = MagicMock()
_sibling_stub.patch_positions_entries_for_date = MagicMock(return_value=0)
sys.modules.setdefault("position_entry_from_events", _sibling_stub)


def _load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _RESEARCH_SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fpa = _load("finalize_period_accounting_r2", "finalize_period_accounting.py")
ra = _load("refresh_attribution_r2", "refresh_attribution.py")
rpm = _load("refresh_performance_metrics_r2", "refresh_performance_metrics.py")


def test_window_return_uses_r2_when_enabled(r2_market) -> None:
    r2_market(
        {
            "GLD": [
                {"date": "2026-09-03", "close": 250.0},
                {"date": "2026-09-10", "close": 260.0},
            ]
        },
        as_of="2026-09-10",
    )
    assert ra._window_return(None, "GLD", "2026-09-03", "2026-09-10") == (260.0 / 250.0 - 1)


def test_fetch_closes_filters_to_requested_dates(r2_market) -> None:
    r2_market(
        {
            "XLF": [
                {"date": "2026-09-09", "close": 50.0},
                {"date": "2026-09-10", "close": 51.0},
                {"date": "2026-09-11", "close": 52.0},
            ]
        },
        as_of="2026-09-11",
    )
    out = rpm._fetch_closes(None, "XLF", ["2026-09-10", "2026-09-11"])
    assert out == {"2026-09-10": 51.0, "2026-09-11": 52.0}


def test_prev_trading_date_uses_r2(r2_market) -> None:
    r2_market(
        {
            "SPY": [
                {"date": "2026-09-09", "close": 100.0},
                {"date": "2026-09-10", "close": 101.0},
            ]
        },
        as_of="2026-09-11",
    )
    assert rpm._prev_trading_date(None, "SPY", "2026-09-11") == "2026-09-10"


def test_mark_from_close_uses_r2(r2_market) -> None:
    r2_market({"GLD": [{"date": "2026-09-10", "close": 260.0}]}, as_of="2026-09-10")
    mark = fpa._mark_from_close(
        client=None,
        symbol="GLD",
        as_of=date(2026, 9, 10),
        observed_at=datetime(2026, 9, 10, 22, 0, tzinfo=timezone.utc),
    )
    assert mark is not None and float(mark.price) == 260.0
