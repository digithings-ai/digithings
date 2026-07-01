from __future__ import annotations
import pytest
from digiquant.olympus.atlas.data.queries import get_price_technicals, get_macro_series


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows
        self._f = {}

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._f[col] = val
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
        ]
        return type("R", (), {"data": rows[: getattr(self, "_n", len(rows))]})


class _FakeClient:
    def __init__(self, tables):
        self._t = tables

    def table(self, name):
        return _FakeTable(self._t.get(name, []))


@pytest.mark.unit
def test_get_price_technicals_returns_latest_window():
    client = _FakeClient(
        {
            "price_technicals": [
                {
                    "ticker": "SPY",
                    "date": "2026-06-08",
                    "sma_50": 1.0,
                    "sma_200": 2.0,
                    "rsi_14": 55.0,
                    "pct_vs_sma200": 3.1,
                    "macd_hist": 0.2,
                    "adx_14": 21.0,
                    "atr_pct": 1.1,
                    "zscore_200": 0.4,
                },
                {
                    "ticker": "SPY",
                    "date": "2026-06-05",
                    "sma_50": 1.0,
                    "sma_200": 2.0,
                    "rsi_14": 54.0,
                    "pct_vs_sma200": 3.0,
                    "macd_hist": 0.1,
                    "adx_14": 20.0,
                    "atr_pct": 1.0,
                    "zscore_200": 0.3,
                },
                {
                    "ticker": "QQQ",
                    "date": "2026-06-08",
                    "sma_50": 9.0,
                    "sma_200": 8.0,
                    "rsi_14": 60.0,
                    "pct_vs_sma200": 5.0,
                    "macd_hist": 0.5,
                    "adx_14": 25.0,
                    "atr_pct": 1.5,
                    "zscore_200": 0.9,
                },
            ]
        }
    )
    out = get_price_technicals(client=client, ticker="SPY", lookback=2)
    assert out["ticker"] == "SPY"
    assert out["latest"]["date"] == "2026-06-08"
    assert out["latest"]["rsi_14"] == 55.0
    assert len(out["window"]) == 2
    assert "sma_200" in out["latest"]


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
