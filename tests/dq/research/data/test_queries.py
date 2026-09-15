from __future__ import annotations

from datetime import date

import pytest
from digiquant.research.data.queries import get_macro_series


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows
        self._f = {}
        self._lte: dict = {}

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._f[col] = val
        return self

    def lte(self, col, val):
        self._lte[col] = val
        return self

    def in_(self, col, vals):
        self._f[col] = set(vals)
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        self._n = n
        return self

    def execute(self):
        rows = [
            r
            for r in self._rows
            if all(
                r.get(c) == v or (isinstance(v, set) and r.get(c) in v) for c, v in self._f.items()
            )
            and all(str(r.get(c)) <= str(v) for c, v in self._lte.items())
        ]
        return type("R", (), {"data": rows[: getattr(self, "_n", len(rows))]})


class _FakeClient:
    def __init__(self, tables):
        self._t = tables

    def table(self, name):
        return _FakeTable(self._t.get(name, []))


@pytest.mark.unit
def test_get_macro_series_groups_by_series():
    client = _FakeClient(
        {
            "macro_series_observations": [
                {"series_id": "M2SL", "obs_date": "2026-05-01", "value": 21000.0, "unit": "Bil. $"},
                {"series_id": "M2SL", "obs_date": "2026-04-01", "value": 20950.0, "unit": "Bil. $"},
                {"series_id": "DFF", "obs_date": "2026-06-07", "value": 4.5, "unit": "%"},
            ]
        }
    )
    out = get_macro_series(client=client, series_ids=["M2SL", "DFF"], lookback=2)
    assert set(out) == {"M2SL", "DFF"}
    assert out["M2SL"]["latest"]["value"] == 21000.0
    assert out["DFF"]["latest"]["value"] == 4.5


# The two `get_price_technicals` Supabase-body tests that lived here were deleted
# with the body (#4053): the reader is R2-only, and its window semantics are
# pinned against the sealed generations in
# `tests/dq/test_market_data_parity.py::test_get_price_technicals_helper_reads_r2_only`.


@pytest.mark.unit
def test_get_macro_series_as_of_bounds_observations():
    client = _FakeClient(
        {
            "macro_series_observations": [
                {"series_id": "DFF", "obs_date": "2026-06-07", "value": 4.5, "unit": "%"},
                {"series_id": "DFF", "obs_date": "2026-06-06", "value": 4.4, "unit": "%"},
            ]
        }
    )
    out = get_macro_series(client=client, series_ids=["DFF"], lookback=5, as_of=date(2026, 6, 6))
    assert out["DFF"]["latest"]["obs_date"] == "2026-06-06"
    assert len(out["DFF"]["window"]) == 1
