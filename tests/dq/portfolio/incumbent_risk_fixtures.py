"""Golden fixture loader for incumbent H8 risk policy characterization (WP6.1 / #2687).

Freezes current production defaults and representative sizing outcomes before
``RiskPolicy`` / ``CovarianceSnapshot`` modeling in WP6.2. Tests import this
module; the JSON is generated once from the incumbent code path and checked in.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

from digiquant.portfolio.sizing import SizingResult

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "incumbent_h8_risk_policy.json"


def load_incumbent_risk_fixture() -> dict[str, Any]:
    """Load the checked-in golden behavior matrix."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def sizing_result_snapshot(result: SizingResult) -> dict[str, Any]:
    """Serialize a :class:`SizingResult` to the fixture's book snapshot shape."""
    return {
        "targets": {p.ticker: round(p.target_pct, 4) for p in result.positions},
        "cash_pct": round(result.cash_pct, 4),
        "gross_pct": round(result.gross_pct, 4),
        "realized_portfolio_vol": round(result.realized_portfolio_vol or 0.0, 4),
        "applied_scales": {k: round(v, 4) for k, v in result.applied_scales.items()},
        "flat_reason": result.flat_reason,
        "adjustment_types": sorted({a.adjustment_type.value for a in result.adjustments}),
    }


def assert_book_matches_golden(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    """Compare two book snapshots with pytest-friendly float tolerance."""
    import pytest

    assert actual["targets"] == expected["targets"]
    assert actual["cash_pct"] == pytest.approx(expected["cash_pct"], abs=1e-3)
    assert actual["gross_pct"] == pytest.approx(expected["gross_pct"], abs=1e-3)
    assert actual["realized_portfolio_vol"] == pytest.approx(
        expected["realized_portfolio_vol"], abs=0.05
    )
    for key in ("vol_scale", "breaker_scale"):
        if key in expected["applied_scales"]:
            assert actual["applied_scales"][key] == pytest.approx(
                expected["applied_scales"][key], abs=0.02
            )
    assert actual["flat_reason"] == expected["flat_reason"]
    assert actual["adjustment_types"] == expected["adjustment_types"]


def dataclass_matches_fixture(obj: Any, expected: dict[str, Any]) -> bool:
    """Shallow equality check for frozen dataclass defaults vs fixture dict."""
    return asdict(obj) == expected
