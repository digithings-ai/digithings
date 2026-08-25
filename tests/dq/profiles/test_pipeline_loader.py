"""Unit tests for pipeline profile loader / preflight pin (#2607)."""

from __future__ import annotations

from typing import Any, cast

import pytest
from digiquant.profiles import (
    HOUSE_PROFILE_ID,
    HOUSE_RUN_ID,
    default_house_config,
    default_house_profile,
)
from digiquant.profiles.pipeline_loader import (
    pin_pipeline_profile,
    pin_pipeline_profile_at_preflight,
    resolve_pipeline_profile_mode,
    row_to_pipeline_profile,
)
from digiquant.profiles.pipeline_profile import ProfileConfig, RiskPrefs

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit


def _house_row() -> dict[str, Any]:
    house = default_house_profile()
    return {
        "profile_id": house.profile_id,
        "kind": house.kind,
        "display_name": house.display_name,
        "schema_version": house.schema_version,
        "config": house.config.model_dump(mode="json"),
        "house_run_id": house.house_run_id,
        "always_on": True,
        "enabled": True,
    }


def _overlay_row(
    profile_id: str = "overlay-alpha",
    *,
    risk: str = "aggressive",
    enabled: bool = True,
) -> dict[str, Any]:
    cfg = ProfileConfig(
        risk=RiskPrefs(risk_tolerance=cast(Any, risk)),
    )
    return {
        "profile_id": profile_id,
        "kind": "overlay",
        "display_name": "Overlay Alpha",
        "schema_version": 1,
        "config": cfg.model_dump(mode="json"),
        "house_run_id": HOUSE_RUN_ID,
        "always_on": False,
        "enabled": enabled,
    }


class TestResolveMode:
    def test_default_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLYMPUS_PIPELINE_PROFILE_MODE", raising=False)
        assert resolve_pipeline_profile_mode() == "off"

    def test_shadow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLYMPUS_PIPELINE_PROFILE_MODE", "shadow")
        assert resolve_pipeline_profile_mode() == "shadow"


class TestLoader:
    def test_missing_config_falls_back_to_house(self) -> None:
        client = FakeSupabaseClient(canned_reads={"olympus_pipeline_profiles": []})
        pinned = pin_pipeline_profile(client)
        assert pinned.house.profile_id == HOUSE_PROFILE_ID
        assert pinned.house_run_id == HOUSE_RUN_ID
        assert pinned.mode == "off"
        assert pinned.applies_overlay is False
        assert pinned.effective_config == default_house_config()

    def test_happy_path_loads_house_from_db(self) -> None:
        client = FakeSupabaseClient(canned_reads={"olympus_pipeline_profiles": [_house_row()]})
        pinned = pin_pipeline_profile(client, mode="off")
        assert pinned.house.profile_id == HOUSE_PROFILE_ID
        assert pinned.h4_roster_cap_unchanged is True
        assert pinned.h7_h8_authority_unchanged is True

    def test_version_mismatch_falls_back_house(self) -> None:
        bad = _house_row()
        bad["config"] = {**bad["config"], "schema_version": 99}
        client = FakeSupabaseClient(canned_reads={"olympus_pipeline_profiles": [bad]})
        pinned = pin_pipeline_profile(client)
        # Invalid house row → in-code baseline
        assert pinned.house.config.schema_version == 1
        assert pinned.house.profile_id == HOUSE_PROFILE_ID

    def test_shadow_keeps_house_effective_config(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "olympus_pipeline_profiles": [_house_row(), _overlay_row()],
            }
        )
        pinned = pin_pipeline_profile(client, overlay_profile_id="overlay-alpha", mode="shadow")
        assert pinned.overlay is not None
        assert pinned.applies_overlay is False
        assert pinned.effective_config.risk.risk_tolerance == "moderate"
        assert pinned.overlay.config.risk.risk_tolerance == "aggressive"
        assert pinned.h4_roster_cap_unchanged is True

    def test_active_still_pins_h4_h7_h8_unchanged(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "olympus_pipeline_profiles": [_house_row(), _overlay_row()],
            }
        )
        pinned = pin_pipeline_profile(client, overlay_profile_id="overlay-alpha", mode="active")
        assert pinned.applies_overlay is True
        assert pinned.effective_config.risk.risk_tolerance == "aggressive"
        assert pinned.h4_roster_cap_unchanged is True
        assert pinned.h7_h8_authority_unchanged is True
        assert pinned.house_run_id == HOUSE_RUN_ID
        assert pinned.house.always_on is True

    def test_overlay_cannot_override_house_immutability(self) -> None:
        # Malicious row claiming a different house_run_id is dropped by loader.
        evil = _overlay_row()
        evil["house_run_id"] = "hijacked-run"
        client = FakeSupabaseClient(
            canned_reads={"olympus_pipeline_profiles": [_house_row(), evil]}
        )
        # row_to_pipeline_profile raises; load returns None → no overlay
        pinned = pin_pipeline_profile(client, overlay_profile_id="overlay-alpha", mode="active")
        assert pinned.overlay is None
        assert pinned.applies_overlay is False
        assert pinned.house_run_id == HOUSE_RUN_ID

    def test_row_to_profile_rejects_cancel(self) -> None:
        row = _overlay_row()
        # cancel_house_run is forced False in row_to_pipeline_profile
        profile = row_to_pipeline_profile(row)
        assert profile.cancel_house_run is False

    def test_preflight_failsoft(self) -> None:
        pinned = pin_pipeline_profile_at_preflight(None)
        assert pinned.house.profile_id == HOUSE_PROFILE_ID
        assert pinned.mode == "off"


class TestPreflightPin:
    """Pin via ``pin_pipeline_profile_at_preflight`` (not ``build_preflight_node``).

    Calling the Atlas preflight node pulls ``digigraph`` → ``openai``, which the
    digiquant-only CI job does not install. Loader + env-mode coverage belongs here;
    graph wiring is covered under ``tests/dq/atlas/`` (skipped without digigraph).
    """

    def _fresh_client(self) -> FakeSupabaseClient:
        return FakeSupabaseClient(
            canned_reads={"olympus_pipeline_profiles": [_house_row(), _overlay_row()]}
        )

    def test_preflight_pins_house_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLYMPUS_PIPELINE_PROFILE_MODE", raising=False)
        pin = pin_pipeline_profile_at_preflight(self._fresh_client())
        assert pin.house.profile_id == HOUSE_PROFILE_ID
        assert pin.mode == "off"
        assert pin.applies_overlay is False
        assert pin.h4_roster_cap_unchanged is True
        assert pin.h7_h8_authority_unchanged is True

    def test_preflight_shadow_overlay_does_not_apply(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLYMPUS_PIPELINE_PROFILE_MODE", "shadow")
        pin = pin_pipeline_profile_at_preflight(
            self._fresh_client(),
            overlay_profile_id="overlay-alpha",
        )
        assert pin.overlay is not None
        assert pin.applies_overlay is False
        assert pin.effective_config.risk.risk_tolerance == "moderate"
