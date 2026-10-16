"""Missing-exit detection in the tearsheet trade round-trip (CodeQL #2664).

``trades_from_positions`` reads the Nautilus positions report row-wise. For
every scalar in a row it must decide whether the exit is missing. The check
was self-inequality (``x is None or x != x``); it is now ``pandas.isna``.

These tests pin the four input kinds the old form handled only by accident
(``pd.Timestamp``, ``pd.NaT``, ``np.datetime64('NaT')``, ``None``) and the real
values that must not be treated as missing. No Nautilus and no Polars frame is
required: the decision is driven through the public function with a stub that
supplies only ``iterrows``.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "generate_tearsheets.py"
# Register under a private module name. test_tearsheet_isolation.py owns the
# name "generate_tearsheets" because it spawns workers that pickle
# _strategy_worker by module name; rebinding that name here would make its
# pickle target a different module object and fail the run.
_MODULE_NAME = "generate_tearsheets_missing_values"
_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _SCRIPT)
assert _spec is not None and _spec.loader is not None
gts = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = gts
_spec.loader.exec_module(gts)

pytestmark = pytest.mark.unit

# Values that mean "the position is still open". Every one of them is a scalar.
MISSING = [
    pytest.param(pd.NaT, id="pd-NaT"),
    pytest.param(np.datetime64("NaT"), id="numpy-datetime64-NaT"),
    pytest.param(None, id="None"),
    pytest.param(float("nan"), id="float-nan"),
    pytest.param(Decimal("NaN"), id="decimal-NaN"),
]

# Closed-exit timestamps. Each of them must format to the same exit date, so
# one expected string serves every parameter.
CLOSED_DATE = [
    pytest.param(pd.Timestamp("2026-01-03 09:30:00"), id="pd-Timestamp"),
    pytest.param(np.datetime64("2026-01-03T09:30:00"), id="numpy-datetime64"),
    pytest.param(datetime(2026, 1, 3, 9, 30, 0, tzinfo=timezone.utc), id="datetime"),
]


class _StubPositions:
    """Stand-in for the positions report. The generator uses only ``iterrows``."""

    def __init__(self, rows: list[pd.Series]) -> None:
        self._rows = rows

    def iterrows(self):
        return enumerate(self._rows)


def _row(**overrides) -> pd.Series:
    """Build one report row. Omitted keys stay absent, so ``get`` returns None."""
    row = {
        "entry": "BUY",
        "ts_opened": pd.Timestamp("2026-01-02 09:30:00"),
        "avg_px_open": 100.0,
        "ts_closed": pd.Timestamp("2026-01-03 09:30:00"),
        "avg_px_close": 105.0,
    }
    row.update(overrides)
    return pd.Series(row)


@pytest.mark.parametrize("missing", MISSING)
def test_missing_exit_becomes_an_empty_date_and_no_price(missing) -> None:
    got = gts.trades_from_positions(_StubPositions([_row(ts_closed=missing, avg_px_close=missing)]))

    assert len(got) == 1
    assert got[0]["exit_date"] == ""
    assert got[0]["exit_price"] is None


@pytest.mark.parametrize("present", CLOSED_DATE)
def test_present_exit_keeps_its_date_and_price(present) -> None:
    got = gts.trades_from_positions(_StubPositions([_row(ts_closed=present)]))

    assert len(got) == 1
    assert got[0]["exit_date"] == "2026-01-03"
    assert got[0]["exit_price"] == 105.0


def test_an_infinite_close_price_is_a_price_and_not_a_missing_value() -> None:
    # ``float("inf")`` is not equal to itself nowhere and is not None, but it
    # also must not read as missing: the row closed, at an unbounded price.
    got = gts.trades_from_positions(_StubPositions([_row(avg_px_close=float("inf"))]))

    assert len(got) == 1
    assert got[0]["exit_date"] == "2026-01-03"
    assert got[0]["exit_price"] == float("inf")


def test_an_absent_close_column_is_treated_as_missing() -> None:
    # ``r.get`` returns None when the key is absent. This is the same decision
    # as an explicit None, so it must produce the same open position.
    row = _row()
    del row["ts_closed"]
    del row["avg_px_close"]

    got = gts.trades_from_positions(_StubPositions([row]))

    assert len(got) == 1
    assert got[0]["exit_date"] == ""
    assert got[0]["exit_price"] is None


def test_a_closed_row_is_still_complete() -> None:
    got = gts.trades_from_positions(_StubPositions([_row()]))

    assert got == [
        {
            "direction": "long",
            "entry_date": "2026-01-02",
            "entry_price": 100.0,
            "exit_date": "2026-01-03",
            "exit_price": 105.0,
        }
    ]


def test_rows_stay_in_chronological_order_with_a_mixed_pair() -> None:
    later = _row(ts_opened=pd.Timestamp("2026-02-10 09:30:00"), ts_closed=pd.NaT)
    earlier = _row(ts_opened=pd.Timestamp("2026-01-02 09:30:00"))
    rows = [later, earlier]

    got = gts.trades_from_positions(_StubPositions(rows))

    assert [t["entry_date"] for t in got] == ["2026-01-02", "2026-02-10"]
    assert got[1]["exit_date"] == ""
