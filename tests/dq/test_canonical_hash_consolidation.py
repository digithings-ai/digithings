"""One canonical-JSON dialect for stored content hashes.

Six modules carried a private ``_canonical_json`` plus an inline
``hashlib.sha256(...).hexdigest()``. They now call
:func:`digiquant.portfolio.allocation_hashes.canonical_json` /
:func:`~digiquant.portfolio.allocation_hashes.sha256_hex`, the dialect the
replay and portfolio-shadow code already used.

The bytes must not move: these digests sit inside persisted ids, so a change
would silently invalidate rows written by the previous copy. The first test
pins the shared dialect against the historical expression byte for byte.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest
from digiquant.portfolio.allocation_hashes import canonical_json, sha256_hex

_MODULES = (
    "digiquant.dashboard.learning.component_attribution",
    "digiquant.dashboard.learning.outcome_models",
    "digiquant.dashboard.research_retrieval.models",
    "digiquant.portfolio.models.cost_liquidity",
    "digiquant.portfolio.models.forecast_calibration",
    "digiquant.portfolio.models.risk_policy",
)


def _legacy_digest(payload: object) -> str:
    """The expression the six copies inlined, kept here as the reference."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@pytest.mark.unit
def test_shared_dialect_is_byte_identical_to_the_legacy_copies() -> None:
    payload = {
        "z": "last",
        "a": [1, 2.5, None, True],
        "nested": {"b": "2026-10-23T00:00:00+00:00", "a": "1E+2"},
    }
    assert canonical_json(payload) == json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    )
    assert sha256_hex(payload) == _legacy_digest(payload)


@pytest.mark.unit
def test_non_json_objects_are_stringified_not_dropped() -> None:
    # ``default=str`` is load-bearing: Decimal/UUID/date payload values reach
    # these hashes directly.
    from decimal import Decimal
    from uuid import UUID

    value = UUID("00000000-0000-0000-0000-000000000001")
    payload = {"amount": Decimal("1.10"), "id": value}
    assert canonical_json(payload) == f'{{"amount":"1.10","id":"{value}"}}'


@pytest.mark.unit
def test_no_module_keeps_a_private_canonical_json() -> None:
    for module in _MODULES:
        source = pathlib.Path(__import__(module).__file__).read_text()  # type: ignore[arg-type]
        assert "def _canonical_json" not in source, module
        assert "hashlib.sha256(" not in source, module
