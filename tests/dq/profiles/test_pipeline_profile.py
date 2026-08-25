"""Unit tests for PipelineProfile / ProfileConfig (#2607)."""

from __future__ import annotations

import pytest
from digiquant.profiles import (
    HOUSE_PROFILE_ID,
    HOUSE_RUN_ID,
    PipelineProfile,
    ProfileConfig,
    ResearchThemeRequest,
    default_house_profile,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


class TestProfileConfig:
    def test_round_trip_json(self) -> None:
        cfg = ProfileConfig(
            research_themes=[
                ResearchThemeRequest(theme_key="theme:AI-Infra", publish_if_missing=True)
            ]
        )
        restored = ProfileConfig.model_validate_json(cfg.model_dump_json())
        assert restored.research_themes[0].theme_key == "theme:ai-infra"
        assert restored.schema_version == 1

    def test_rejects_future_schema_version(self) -> None:
        with pytest.raises(ValidationError, match="unsupported ProfileConfig"):
            ProfileConfig(schema_version=99)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ProfileConfig.model_validate({"schema_version": 1, "mystery": True})


class TestPipelineProfileHouseInvariants:
    def test_default_house_profile(self) -> None:
        house = default_house_profile()
        assert house.profile_id == HOUSE_PROFILE_ID
        assert house.house_run_id == HOUSE_RUN_ID
        assert house.always_on is True
        assert house.cancel_house_run is False
        assert house.config.universe.asset_classes == ["etf"]

    def test_overlay_cannot_claim_house_id(self) -> None:
        with pytest.raises(ValidationError, match="overlay cannot claim"):
            PipelineProfile(
                profile_id=HOUSE_PROFILE_ID,
                kind="overlay",
                display_name="bad",
                always_on=False,
            )

    def test_overlay_cannot_be_always_on(self) -> None:
        with pytest.raises(ValidationError, match="always_on"):
            PipelineProfile(
                profile_id="tenant-a",
                kind="overlay",
                display_name="A",
                always_on=True,
            )

    def test_overlay_cannot_replace_house_run_id(self) -> None:
        with pytest.raises(ValidationError, match="house_run_id"):
            PipelineProfile(
                profile_id="tenant-a",
                kind="overlay",
                display_name="A",
                house_run_id="some-other-run",
                always_on=False,
            )

    def test_cancel_house_run_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PipelineProfile.model_validate(
                {
                    "profile_id": "tenant-a",
                    "kind": "overlay",
                    "display_name": "A",
                    "always_on": False,
                    "cancel_house_run": True,
                }
            )

    def test_house_wrong_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="house profile_id"):
            PipelineProfile(
                profile_id="not-house",
                kind="house",
                display_name="x",
                always_on=True,
            )
