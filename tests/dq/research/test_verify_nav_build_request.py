"""Regression tests for ``verify_nav_replay.build_request`` OHLC coherence (#3994).

Production ``price_history`` carries vendor/float64 rows whose ``close`` or
``open`` sits outside ``[low, high]``: SPY 1993-02-12 is one float64 ulp below
``low``, while ATOM-USD / DOT-USD 2026-09-11 and six 2026-09-09 equities are
materially inconsistent. ``OhlcvBar`` enforces the OHLC envelope, so the engine
NAV write died on the first such row in ``(date, ticker)`` order
(run 34778748677). ``build_request`` must widen the envelope to contain the
observed open/close — the engine marks and fills at ``close`` only, so NAV is
unaffected — instead of rejecting the whole replay.

The script is loaded via importlib like the other script-level tests
(``digiquant/scripts`` are not installed packages).
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "research"
    / "verify_nav_replay.py"
)


def _load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_nav_replay_bars", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_verify_module()


def _price_row(
    d: str, ticker: str, open_: float, high: float, low: float, close: float, volume: int = 1000
) -> dict[str, Any]:
    return {
        "date": d,
        "ticker": ticker,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _bars(price_rows: list[dict[str, Any]]) -> tuple[Any, ...]:
    d = str(price_rows[0]["date"])
    ticker = str(price_rows[0]["ticker"])
    request, _closes, _recorded = _mod.build_request(
        price_rows,
        [{"date": d, "ticker": ticker, "weight_pct": 100.0}],
        [{"date": d, "nav": 100.0}],
    )
    return request.series[0].bars


class TestIncoherentEnvelope:
    def test_float64_one_ulp_close_below_low_is_widened(self) -> None:
        """SPY 1993-02-12 as PostgREST delivers it: close one ulp below low."""
        bars = _bars(
            [
                _price_row(
                    "1993-02-12",
                    "SPY",
                    24.691216563042346,
                    24.691216563042346,
                    24.536466598510746,
                    24.536466598510742,
                    42500,
                )
            ]
        )
        assert len(bars) == 1
        bar = bars[0]
        # open/close are preserved exactly — only the envelope is widened.
        assert bar.close == Decimal("24.536466598510742")
        assert bar.open == Decimal("24.691216563042346")
        assert bar.low == Decimal("24.536466598510742")
        assert bar.high == Decimal("24.691216563042346")

    def test_material_close_below_low_is_widened(self) -> None:
        """ATOM-USD 2026-09-11: crypto close below the day's low."""
        bars = _bars(
            [_price_row("2026-09-11", "ATOM-USD", 1.7916, 1.8185, 1.637, 1.6315, 44390728)]
        )
        bar = bars[0]
        assert bar.close == Decimal("1.6315")
        assert bar.low == Decimal("1.6315")
        assert bar.high == Decimal("1.8185")

    def test_open_above_high_is_widened(self) -> None:
        """DHR 2026-09-09: equity open a cent above the day's high."""
        bars = _bars([_price_row("2026-09-09", "DHR", 206.0, 205.99, 201.95, 204.85, 2768855)])
        bar = bars[0]
        assert bar.open == Decimal("206.0")
        assert bar.high == Decimal("206.0")
        assert bar.low == Decimal("201.95")

    def test_coherent_bar_is_unchanged(self) -> None:
        """A well-formed bar must pass through without widening."""
        bars = _bars([_price_row("2026-09-01", "SPY", 100.0, 103.0, 99.0, 102.0)])
        bar = bars[0]
        assert bar.open == Decimal("100.0")
        assert bar.high == Decimal("103.0")
        assert bar.low == Decimal("99.0")
        assert bar.close == Decimal("102.0")

    def test_reversed_envelope_is_repaired(self) -> None:
        """high < low (never seen in prod, but possible in a bad row) is repaired."""
        bars = _bars([_price_row("2026-09-01", "SPY", 100.0, 99.0, 103.0, 101.0)])
        bar = bars[0]
        assert bar.open == Decimal("100.0")
        assert bar.close == Decimal("101.0")
        assert bar.high == Decimal("101.0")
        assert bar.low == Decimal("100.0")
