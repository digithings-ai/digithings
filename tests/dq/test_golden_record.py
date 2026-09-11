"""Golden recorder for pre-cutover Supabase market-data answers (Task 1).

The recorder snapshots live Supabase answers so later R2-cutover tasks can
diff parity against these files. Pure unit test: ``record_one`` only.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "record_market_data_goldens.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("record_market_data_goldens", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_golden_record_schema(tmp_path):
    mod = _load_script()
    row = mod.record_one(
        ticker="SPY",
        as_of="2024-12-31",
        fetch=lambda t, a: [{"date": "2024-12-31", "close": 1.0}],
    )
    assert row["ticker"] == "SPY"
    assert row["as_of"] == "2024-12-31"
    assert row["rows"][0]["close"] == 1.0
