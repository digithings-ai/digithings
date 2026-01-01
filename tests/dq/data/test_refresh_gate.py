"""Unit tests for digiquant.data.prices.refresh_gate (#3780, Task 6).

The staleness gate refuses a manifest whose seal is more than
``bound_trading_days`` trading days behind the run date. Pure date math:
an optional explicit trading-day calendar (Supabase ``trading_calendar``
rows, fetched by the caller) overrides the default Mon-Fri counting.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from digiquant.data.prices.refresh_gate import (  # noqa: E402
    staleness_gate,
    trading_days_between,
)


def test_staleness_gate_refuses():
    from digiquant.data.prices.refresh_gate import staleness_gate

    assert staleness_gate(manifest_as_of="2026-08-01", run_date="2026-09-09")["ok"] is False


def test_fresh_manifest_passes_with_zero_stale_days() -> None:
    gate = staleness_gate(manifest_as_of="2026-09-09", run_date="2026-09-09")
    assert gate == {"ok": True, "stale_days": 0}


def test_boundary_five_trading_days_passes() -> None:
    # 2026-09-02 (Wed) -> 2026-09-09 (Wed): Thu, Fri, Mon, Tue, Wed = 5.
    gate = staleness_gate(manifest_as_of="2026-09-02", run_date="2026-09-09")
    assert gate == {"ok": True, "stale_days": 5}


def test_six_trading_days_refuses() -> None:
    gate = staleness_gate(manifest_as_of="2026-09-01", run_date="2026-09-09")
    assert gate == {"ok": False, "stale_days": 6}


def test_weekend_does_not_count() -> None:
    # Friday seal -> Wednesday run: Mon, Tue, Wed = 3 open days.
    assert trading_days_between("2026-09-04", "2026-09-09") == 3
    gate = staleness_gate(manifest_as_of="2026-09-04", run_date="2026-09-09")
    assert gate == {"ok": True, "stale_days": 3}


def test_explicit_calendar_overrides_weekday_count() -> None:
    # Exchange holiday on Mon 2026-09-07: only Tue + Wed are open.
    calendar = ["2026-09-08", "2026-09-09"]
    assert trading_days_between("2026-09-04", "2026-09-09", calendar) == 2
    gate = staleness_gate(manifest_as_of="2026-09-04", run_date="2026-09-09", trading_days=calendar)
    assert gate == {"ok": True, "stale_days": 2}


def test_run_date_before_seal_is_fresh() -> None:
    gate = staleness_gate(manifest_as_of="2026-09-10", run_date="2026-09-09")
    assert gate == {"ok": True, "stale_days": 0}


def test_custom_bound() -> None:
    gate = staleness_gate(manifest_as_of="2026-09-04", run_date="2026-09-09", bound_trading_days=2)
    assert gate == {"ok": False, "stale_days": 3}
