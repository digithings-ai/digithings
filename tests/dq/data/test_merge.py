"""Unit tests for digiquant.data.prices.merge (#3780, Task 3).

Normative merge rule: R2 history wins for date <= manifest.as_of; live wins
only for manifest.as_of < date <= as_of; the live as_of-dated bar is excluded
unless sealed (settled-close semantics).
"""

from __future__ import annotations

import polars as pl
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.prices.merge import (  # noqa: E402
    apply_settled_close,
    canonical_date,
    merge_history_live,
    overlap_hash,
)


def test_live_wins_only_inside_overlap_and_asof_bar_excluded():
    hist = pl.DataFrame({"date": ["2026-09-01", "2026-09-02"], "close": [1.0, 2.0]})
    live = pl.DataFrame(
        {"date": ["2026-09-02", "2026-09-03", "2026-09-04"], "close": [20.0, 3.0, 4.0]}
    )
    out = merge_history_live(
        hist, live, manifest_as_of="2026-09-02", as_of="2026-09-04", sealed=False
    )
    by_date = {str(r["date"]): r["close"] for r in out.to_dicts()}
    assert by_date["2026-09-02"] == 2.0
    assert "2026-09-04" not in by_date
    assert by_date["2026-09-03"] == 3.0


def test_sealed_includes_asof_bar() -> None:
    hist = pl.DataFrame({"date": ["2026-09-01", "2026-09-02"], "close": [1.0, 2.0]})
    live = pl.DataFrame(
        {"date": ["2026-09-02", "2026-09-03", "2026-09-04"], "close": [20.0, 3.0, 4.0]}
    )
    out = merge_history_live(
        hist, live, manifest_as_of="2026-09-02", as_of="2026-09-04", sealed=True
    )
    by_date = {str(r["date"]): r["close"] for r in out.to_dicts()}
    assert by_date["2026-09-02"] == 2.0
    assert by_date["2026-09-04"] == 4.0
    assert by_date["2026-09-03"] == 3.0


def test_apply_settled_close_drops_unsealed_asof_bar() -> None:
    frame = pl.DataFrame({"date": ["2026-09-03", "2026-09-04"], "close": [3.0, 4.0]})
    unsealed = apply_settled_close(frame, as_of="2026-09-04", sealed=False)
    assert [str(r["date"]) for r in unsealed.to_dicts()] == ["2026-09-03"]
    sealed = apply_settled_close(frame, as_of="2026-09-04", sealed=True)
    assert [str(r["date"]) for r in sealed.to_dicts()] == ["2026-09-03", "2026-09-04"]


def test_canonical_date_casts_and_sorts() -> None:
    frame = pl.DataFrame({"date": ["2026-09-03", "2026-09-01"], "close": [3.0, 1.0]})
    out = canonical_date(frame)
    assert out.schema["date"] == pl.Date
    assert out["date"].to_list() == sorted(out["date"].to_list())


def test_overlap_hash_stable_and_sensitive() -> None:
    frame = pl.DataFrame({"date": ["2026-09-01", "2026-09-02"], "close": [1.0, 2.0]})
    assert overlap_hash(frame) == overlap_hash(frame)
    restated = pl.DataFrame({"date": ["2026-09-01", "2026-09-02"], "close": [1.0, 99.0]})
    assert overlap_hash(frame) != overlap_hash(restated)
