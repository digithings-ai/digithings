"""R2 market-data reads for the execution/backfill cluster (#4013, Phase A Task 3).

Each helper keeps its Supabase body for the default backend and gains a
date-conditional R2 branch (``r2_backend_enabled`` / ``r2_manifest_seal`` /
``r2_ohlcv_rows`` / ``r2_close_rows``): dates at or before the R2 manifest seal
read R2, while same-day prices stay on the Supabase tables the intraday writer
keeps fresh (Decision D3). Loaded via ``importlib.util`` like the other
script-level tests (``digiquant/scripts/`` is not an installed package).
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from typing import Any  # score:allow untyped any — script modules loaded by path

import pytest

from tests.dq.research.test_supabase_io import FakeSupabaseClient

# Registers Task 1's `r2_market` builder fixture for this module; pytest requires
# plugin modules to be named here rather than imported (an imported fixture would
# collide with the fixture-name parameters below under ruff F811).
pytest_plugins = ["tests.fixtures.r2_market"]

pytestmark = pytest.mark.unit

_RESEARCH_SCRIPTS = Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "research"


def _load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _RESEARCH_SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bep = _load("backfill_execution_prices_r2", "backfill_execution_prices.py")
eao = _load("execute_at_open_r2", "execute_at_open.py")
fep = _load("fill_entry_prices_r2", "fill-entry-prices.py")
pfe = _load("position_entry_from_events_r2", "position_entry_from_events.py")


def test_fetch_open_uses_r2_for_sealed_dates(r2_market) -> None:
    r2_market(
        {
            "GLD": [
                {
                    "date": "2026-09-10",
                    "open": 250.0,
                    "high": 251.0,
                    "low": 249.0,
                    "close": 260.0,
                    "volume": 1000,
                }
            ]
        },
        as_of="2026-09-10",
    )
    assert eao._fetch_open(None, "GLD", "2026-09-10") == 250.0


def test_fetch_open_defers_unsealed_dates_to_supabase(r2_market) -> None:
    r2_market(
        {
            "GLD": [
                {
                    "date": "2026-09-09",
                    "open": 240.0,
                    "high": 241.0,
                    "low": 239.0,
                    "close": 250.0,
                    "volume": 1000,
                }
            ]
        },
        as_of="2026-09-09",
    )
    # The canned row must carry the filtered columns or the fake returns nothing:
    # `_fetch_open` filters on ticker+date before reading `open`.
    supabase = FakeSupabaseClient(
        canned_reads={"price_history": [{"ticker": "GLD", "date": "2026-09-10", "open": 999.0}]}
    )
    assert eao._fetch_open(supabase, "GLD", "2026-09-10") == 999.0  # today -> Supabase


def test_backfill_and_fill_helpers_use_r2(r2_market) -> None:
    r2_market(
        {
            "XLV": [
                {
                    "date": "2026-09-10",
                    "open": 150.0,
                    "high": 151.0,
                    "low": 149.0,
                    "close": 152.0,
                    "volume": 10,
                }
            ],
        },
        as_of="2026-09-10",
    )
    assert bep._fetch_open(None, "XLV", "2026-09-10") == 150.0
    assert fep.lookup_close(None, "XLV", "2026-09-10") == 152.0


def test_close_on_or_after_walks_forward_in_r2(r2_market) -> None:
    r2_market(
        {
            "EWZ": [
                {"date": "2026-09-09", "close": 30.0},
                {"date": "2026-09-10", "close": 31.0},
            ]
        },
        as_of="2026-09-10",
    )
    assert pfe._close_on_or_after(None, "EWZ", "2026-09-09") == 30.0
    # Callers may pass a timestamp; the helper slices to [:10] before R2 lookups.
    assert pfe._close_on_or_after(None, "EWZ", "2026-09-09T12:00:00") == 30.0


def test_open_marks_batches_r2_for_sealed_dates(r2_market) -> None:
    r2_market(
        {
            "GLD": [
                {
                    "date": "2026-09-10",
                    "open": 250.5,
                    "high": 251.0,
                    "low": 249.0,
                    "close": 260.0,
                    "volume": 1000,
                }
            ],
            "XLV": [
                {
                    "date": "2026-09-10",
                    "open": 150.0,
                    "high": 151.0,
                    "low": 149.0,
                    "close": 152.0,
                    "volume": 10,
                }
            ],
        },
        as_of="2026-09-10",
    )
    assert eao._open_marks(None, ["XLV", "GLD"], "2026-09-10") == {
        "GLD": Decimal("250.5"),
        "XLV": Decimal("150.0"),
    }
