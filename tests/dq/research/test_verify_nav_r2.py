"""R2 market-data reads for the NAV replay price fetch (#4013, Phase A Task 4).

``verify_nav_replay._fetch_price_rows`` returns sealed R2 OHLCV rows when
``DIGIQUANT_MARKET_DATA_BACKEND=r2`` and keeps the #3990 unscoped Supabase
keyset fetch (``workspace_scoped=False`` + ``tickers``) otherwise. The rows
flow through the same ``_rows_from_inception`` clip and row-dict shape the
#3995 envelope repair and #4002 grid alignment consume.

Loaded via ``importlib.util`` like the other script-level tests
(``digiquant/scripts/`` is not an installed package).
"""

from __future__ import annotations

import importlib.util
from datetime import date
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


vnr = _load("verify_nav_replay_r2", "verify_nav_replay.py")


def test_price_rows_come_from_r2_when_enabled(r2_market) -> None:
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
    rows = vnr._fetch_price_rows(None, "house-id", ["GLD"], date(2026, 9, 1))
    assert rows and rows[0]["ticker"] == "GLD" and rows[0]["close"] is not None


def test_price_rows_fall_back_to_supabase_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "supabase")
    calls: list[tuple] = []

    def fake_fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return [
            {
                "date": "2026-09-10",
                "ticker": "GLD",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 1,
            }
        ]

    monkeypatch.setattr(vnr, "_fetch_table", fake_fetch)
    rows = vnr._fetch_price_rows(object(), "house-id", ["GLD"], date(2026, 9, 1))
    assert rows and calls and calls[0][0][1] == "price_history"


def test_price_rows_accept_the_iso_inception_main_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``main()`` hands over ``args.inception_date`` (an ISO string), not a ``date``."""
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "supabase")
    monkeypatch.setattr(
        vnr,
        "_fetch_table",
        lambda *args, **kwargs: [
            {"date": "2026-06-23", "ticker": "OLD", "close": 1},
            {"date": "2026-07-17", "ticker": "GLD", "close": 2},
        ],
    )
    rows = vnr._fetch_price_rows(object(), "house-id", ["GLD"], "2026-07-17")
    assert [r["ticker"] for r in rows] == ["GLD"]
