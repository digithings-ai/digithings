"""R2 market-data reads for backfill_context (#4013, Phase A Task 5).

``fetch_context`` keeps its Supabase body for the default backend and gains an
R2 branch (``r2_backend_enabled`` / ``r2_close_rows`` / ``r2_ohlcv_rows`` /
``get_price_technicals`` — the technicals helper owns its own backend switch).
Loaded via ``importlib.util`` like the other script-level tests
(``digiquant/scripts/`` is not an installed package).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any  # score:allow untyped any — script modules loaded by path

import pytest

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


bc = _load("backfill_context_r2", "backfill_context.py")


def test_latest_price_date_and_technicals_from_r2(r2_market, monkeypatch) -> None:
    r2_market(
        {
            "SPY": [
                {
                    "date": "2026-09-10",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 10,
                }
            ],
        },
        as_of="2026-09-10",
    )
    monkeypatch.setattr(bc, "CORE_TICKERS", {"SPY"})
    ctx = bc.fetch_context("2026-09-10")
    assert ctx["latest_price_date"] == "2026-09-10"
    assert ctx["prices"] and ctx["prices"][0]["ticker"] == "SPY"
