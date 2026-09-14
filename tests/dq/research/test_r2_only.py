"""R2-only market reads: no Supabase market bodies remain (#4053 Task 4).

The nine script market readers + ``get_price_technicals`` no longer carry a
``table("price_history")`` / ``table("price_technicals")`` body. The R2 seam in
``digiquant.research.data.queries`` (``r2_close_rows`` / ``r2_ohlcv_rows`` /
``r2_manifest_seal``) is the only market-data path; a reappearing string body
means a Supabase fallback was added back, which is not the rollback strategy
after #4053 (restore-from-generation + replay, not a flag flip).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "digiquant" / "scripts" / "research"

R2_ONLY_SCRIPTS: tuple[str, ...] = (
    "backfill_context.py",
    "backfill_execution_prices.py",
    "execute_at_open.py",
    "fill-entry-prices.py",
    "finalize_period_accounting.py",
    "position_entry_from_events.py",
    "refresh_attribution.py",
    "refresh_performance_metrics.py",
    "verify_nav_replay.py",
)

_SUPABASE_MARKET_BODIES = ('table("price_history")', 'table("price_technicals")')


@pytest.mark.parametrize("filename", R2_ONLY_SCRIPTS)
def test_no_supabase_market_body_in_script(filename: str) -> None:
    src = (_SCRIPTS / filename).read_text(encoding="utf-8")
    offenders = [body for body in _SUPABASE_MARKET_BODIES if body in src]
    assert not offenders, f"{filename} still carries a retired Supabase market body: {offenders}"


def test_no_backend_flag_gate_in_scripts() -> None:
    """R2 is unconditional — the retired ``DIGIQUANT_MARKET_DATA_BACKEND`` flag is not read."""
    offenders = [
        filename
        for filename in R2_ONLY_SCRIPTS
        if "r2_backend_enabled" in (_SCRIPTS / filename).read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"R2-only scripts still gate market reads on the backend flag: {offenders}"
    )


def test_get_price_technicals_has_no_supabase_body() -> None:
    from digiquant.research.data import queries

    src = inspect.getsource(queries.get_price_technicals) + inspect.getsource(
        queries._r2_price_technicals
    )
    assert 'table("price_technicals")' not in src
