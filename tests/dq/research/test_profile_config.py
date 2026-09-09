"""Unit tests for Track B ProfileConfig contracts and pin loader (#2609)."""

from __future__ import annotations

from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from digiquant.dashboard.profile_config import (
    HOUSE_PROFILE_KEY,
    ProfileConfig,
    ProfileConfigMissingError,
    house_profile_config,
    load_profile_config_by_version_id,
    profile_config_version_id,
)
from digiquant.profiles.investment_profile import InvestmentProfile
from pydantic import ValidationError

pytestmark = pytest.mark.unit

HOUSE_VERSION = profile_config_version_id(HOUSE_PROFILE_KEY, schema_version=1)


def _moderate_investment() -> InvestmentProfile:
    return InvestmentProfile(
        risk_tolerance="moderate",
        horizon_years=10,
        liquidity_needs="medium",
        base_currency="USD",
        tax_jurisdiction="US",
        esg_preference="none",
        experience_level="intermediate",
    )


def test_house_profile_is_immutable_default() -> None:
    cfg = house_profile_config()
    assert cfg.is_house_default is True
    assert cfg.profile_key == HOUSE_PROFILE_KEY
    assert cfg.version_id == HOUSE_VERSION
    assert cfg.schema_version == 1
    assert cfg.pipeline_schedule is not None
    assert cfg.execution_policy is not None


def test_overlay_cannot_claim_house_key() -> None:
    with pytest.raises(ValidationError):
        ProfileConfig(
            version_id=uuid5(NAMESPACE_URL, "overlay-bad"),
            profile_key=HOUSE_PROFILE_KEY,
            is_house_default=False,
            label="user overlay",
            investment=_moderate_investment(),
        )


def test_house_flag_requires_house_key() -> None:
    with pytest.raises(ValidationError):
        ProfileConfig(
            version_id=uuid5(NAMESPACE_URL, "house-bad"),
            profile_key="user:alice",
            is_house_default=True,
            label="fake house",
            investment=_moderate_investment(),
        )


def test_overlay_profile_accepts_themes_and_budget() -> None:
    cfg = ProfileConfig(
        version_id=uuid5(NAMESPACE_URL, "user:alice:v1"),
        profile_key="user:alice",
        is_house_default=False,
        label="Alice",
        watchlist=["AAPL", "MSFT"],
        themes=["ai", "energy"],
        research_budget_usd=Decimal("25.00"),
        investment=_moderate_investment(),
    )
    assert cfg.themes == ["ai", "energy"]
    assert cfg.research_budget_usd == Decimal("25.00")


def test_profile_config_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ProfileConfig.model_validate(
            {
                "version_id": str(uuid5(NAMESPACE_URL, "x")),
                "profile_key": "user:x",
                "is_house_default": False,
                "label": "x",
                "run_type": "fork",  # anti-goal: graph fork field
            }
        )


def test_load_by_version_id_exact_pin() -> None:
    house = house_profile_config()
    overlay = ProfileConfig(
        version_id=uuid5(NAMESPACE_URL, "user:bob:v1"),
        profile_key="user:bob",
        is_house_default=False,
        label="Bob",
        investment=_moderate_investment(),
    )
    store = {
        str(house.version_id): house,
        str(overlay.version_id): overlay,
    }
    pinned = load_profile_config_by_version_id(store, overlay.version_id)
    assert pinned.version_id == overlay.version_id
    assert pinned.profile_key == "user:bob"


def test_load_missing_pin_fails_closed() -> None:
    with pytest.raises(ProfileConfigMissingError):
        load_profile_config_by_version_id({}, UUID("00000000-0000-4000-8000-000000000001"))


def test_deterministic_version_id_for_house() -> None:
    assert profile_config_version_id(HOUSE_PROFILE_KEY, 1) == HOUSE_VERSION
    assert isinstance(HOUSE_VERSION, UUID)


def test_preflight_pin_defaults_to_house() -> None:
    from digiquant.dashboard.profile_config import pin_profile_config_for_preflight

    pinned = pin_profile_config_for_preflight(requested_version_id=None)
    assert pinned.is_house_default is True
    assert pinned.version_id == HOUSE_VERSION


def test_preflight_pin_missing_store_fails_closed() -> None:
    from digiquant.dashboard.profile_config import pin_profile_config_for_preflight

    with pytest.raises(ProfileConfigMissingError):
        pin_profile_config_for_preflight(
            requested_version_id=UUID("00000000-0000-4000-8000-000000000099"),
            store=None,
        )
