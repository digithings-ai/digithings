"""OpenRouter diagnostic — pure formatters / verdict helpers (no network).

The HTTP checks and the live strict ping are exercised in the field; here we cover the
deterministic parsing that turns API ``data`` objects into operator-readable lines and the
exhausted-credit verdict that flips a green run to FAIL.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "atlas"
    / "openrouter_diagnose.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("openrouter_diagnose_script", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


diag = _load_script()


def test_money_formats_and_tolerates_garbage() -> None:
    assert diag._money(1.5) == "$1.5000"
    assert diag._money("0.0123") == "$0.0123"
    assert diag._money(None) == "—"
    assert diag._money("free") == "—"


def test_summarize_key_includes_spend_windows() -> None:
    line = diag.summarize_key(
        {
            "usage": 12.34,
            "usage_daily": 1.0,
            "usage_weekly": 5.0,
            "usage_monthly": 10.0,
            "limit": None,
            "limit_remaining": None,
            "is_free_tier": False,
        }
    )
    assert "used(all-time)=$12.3400" in line
    assert "today=$1.0000" in line
    assert "limit=unlimited" in line
    assert "remaining=n/a" in line
    assert "free_tier=False" in line


def test_key_is_exhausted() -> None:
    # Finite limit fully used → exhausted (a hard cause of empty bodies).
    assert diag.key_is_exhausted({"limit_remaining": 0}) is True
    assert diag.key_is_exhausted({"limit_remaining": -0.5}) is True
    # Credit left, or no finite limit, or unparseable → not exhausted.
    assert diag.key_is_exhausted({"limit_remaining": 4.2}) is False
    assert diag.key_is_exhausted({"limit_remaining": None}) is False
    assert diag.key_is_exhausted({}) is False
    assert diag.key_is_exhausted({"limit_remaining": "n/a"}) is False


def test_summarize_credits_computes_balance() -> None:
    line = diag.summarize_credits({"total_credits": 100.0, "total_usage": 25.5})
    assert "purchased=$100.0000" in line
    assert "used=$25.5000" in line
    assert "balance=$74.5000" in line
    # Missing fields degrade to em-dashes, never raise.
    assert "balance=—" in diag.summarize_credits({"total_credits": None, "total_usage": None})
