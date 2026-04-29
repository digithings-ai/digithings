"""Unit tests for ``InvestmentProfile``.

Covers schema-version defaulting, JSON round-trip, field validators, and the
checked-in example fixture. These tests are the contract — bumping the schema
must keep them green (or migrate them deliberately and bump
``schema_version``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from digiquant.profiles import InvestmentProfile

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "example_profile.json"


def _valid_payload(**overrides: Any) -> dict[str, Any]:
    """Return a valid profile payload, optionally overriding individual fields."""
    payload: dict[str, Any] = {
        "risk_tolerance": "moderate",
        "horizon_years": 10,
        "liquidity_needs": "medium",
        "base_currency": "USD",
        "tax_jurisdiction": "US",
        "esg_preference": "tilt",
        "excluded_sectors": [],
        "experience_level": "intermediate",
    }
    payload.update(overrides)
    return payload


@pytest.mark.unit
class TestInvestmentProfile:
    """Schema-level guarantees for ``InvestmentProfile``."""

    def test_valid_profile_round_trips_json(self) -> None:
        original = InvestmentProfile(**_valid_payload(excluded_sectors=["tobacco"]))
        as_json = original.model_dump_json()
        restored = InvestmentProfile.model_validate_json(as_json)
        assert restored == original
        assert restored.model_dump() == original.model_dump()

    def test_invalid_risk_tolerance_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InvestmentProfile(**_valid_payload(risk_tolerance="extreme"))
        assert any(err["loc"] == ("risk_tolerance",) for err in exc_info.value.errors())

    def test_horizon_below_minimum_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InvestmentProfile(**_valid_payload(horizon_years=0))
        assert any(err["loc"] == ("horizon_years",) for err in exc_info.value.errors())

    def test_horizon_above_maximum_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InvestmentProfile(**_valid_payload(horizon_years=51))
        assert any(err["loc"] == ("horizon_years",) for err in exc_info.value.errors())

    @pytest.mark.parametrize("bad_currency", ["us", "USD123", "1USD", ""])
    def test_invalid_currency_format_raises(self, bad_currency: str) -> None:
        # ``us`` normalizes to ``US`` (still 2 chars → fails pattern). The
        # remaining cases are length / charset failures. ``"usd"`` is *valid*
        # because the validator upper-cases input first — see the dedicated
        # test below.
        with pytest.raises(ValidationError) as exc_info:
            InvestmentProfile(**_valid_payload(base_currency=bad_currency))
        assert any(err["loc"] == ("base_currency",) for err in exc_info.value.errors())

    def test_currency_lowercase_normalized_to_uppercase(self) -> None:
        profile = InvestmentProfile(**_valid_payload(base_currency="eur"))
        assert profile.base_currency == "EUR"

    def test_excluded_sectors_normalized(self) -> None:
        profile = InvestmentProfile(
            **_valid_payload(excluded_sectors=["Tobacco", "tobacco", "Defense"])
        )
        # Lower-cased, de-duplicated, and insertion-order preserved.
        assert profile.excluded_sectors == ["tobacco", "defense"]

    def test_excluded_sectors_strips_whitespace_and_drops_empties(self) -> None:
        profile = InvestmentProfile(
            **_valid_payload(excluded_sectors=["  Tobacco ", "", "  ", "DEFENSE"])
        )
        assert profile.excluded_sectors == ["tobacco", "defense"]

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InvestmentProfile(**_valid_payload(foo="bar"))  # type: ignore[arg-type]
        assert any("foo" in str(err["loc"]) for err in exc_info.value.errors())

    def test_schema_version_default_is_one(self) -> None:
        profile = InvestmentProfile(**_valid_payload())
        assert profile.schema_version == 1

    def test_schema_version_below_one_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            InvestmentProfile(**_valid_payload(schema_version=0))
        assert any(err["loc"] == ("schema_version",) for err in exc_info.value.errors())

    def test_example_fixture_loads(self) -> None:
        assert FIXTURE_PATH.exists(), f"missing fixture at {FIXTURE_PATH}"
        raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        profile = InvestmentProfile.model_validate(raw)
        assert profile.schema_version == 1
        assert profile.base_currency == "USD"
        # Round-trip the fixture too — it must be byte-stable under ``model_dump``.
        assert profile.model_dump() == raw
