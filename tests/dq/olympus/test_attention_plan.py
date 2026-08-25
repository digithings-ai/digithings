"""Unit tests for Track B WP13-class AttentionPlan shadow (#2616)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest
from digiquant.olympus.attention_plan import (
    AttentionPlan,
    AttentionPlanError,
    AttentionPlanShadowResult,
    RefreshReasonCode,
    assert_plan_has_no_h7_h8_authority,
    assert_plan_preserves_h4_roster,
    attention_plan_id,
    h4_roster_fingerprint,
    plan_attention_shadow,
    resolve_profile_pin_for_planner,
)
from digiquant.olympus.edit_mode.models import PriorPublished, TriageSignal
from digiquant.olympus.profile_config import (
    ProfileConfig,
    ProfileConfigMissingError,
    house_profile_config,
    profile_config_version_id,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

RUN = date(2026, 8, 25)


class _MapPriorLoader:
    def __init__(self, priors: dict[tuple[str, str], PriorPublished | None]) -> None:
        self._priors = priors

    def load(self, artifact_key: tuple[str, str], run_date: date) -> PriorPublished | None:
        return self._priors.get(artifact_key)


def test_shadow_produces_plan_without_actuation() -> None:
    loader = _MapPriorLoader(
        {
            ("segment", "macro"): PriorPublished(
                date=date(2026, 8, 24),
                document_key="segment:macro",
                payload={"body": "x"},
            )
        }
    )
    result = plan_attention_shadow(
        run_date=RUN,
        artifacts=[("segment", "macro")],
        prior_loader=loader,
        triages={("segment", "macro"): TriageSignal(mode="quiet")},
        h4_roster=["SPY", "QQQ"],
        planner_mode="shadow",
    )
    assert result.planner_mode == "shadow"
    assert result.actuated is False
    assert result.plan is not None
    assert result.plan.is_house_default is True
    assert result.plan.profile_key == "house"
    assert result.incumbent_edit_modes["segment:macro"] == "skip"
    decision = result.plan.decisions[0]
    assert decision.proposed_edit_mode == "skip"
    assert decision.action == "carry"
    assert RefreshReasonCode.TRIAGE_QUIET in decision.refresh_reasons
    assert RefreshReasonCode.INCUMBENT_SKIP in decision.refresh_reasons


def test_off_mode_skips_plan_keeps_incumbent() -> None:
    loader = _MapPriorLoader({})
    result = plan_attention_shadow(
        run_date=RUN,
        artifacts=[("theme", "ai")],
        prior_loader=loader,
        planner_mode="off",
    )
    assert result.plan is None
    assert result.actuated is False
    assert result.incumbent_edit_modes["theme:ai"] == "full"


def test_deterministic_plan_id() -> None:
    loader = _MapPriorLoader({})
    a = plan_attention_shadow(
        run_date=RUN,
        artifacts=[("asset", "spy")],
        prior_loader=loader,
        h4_roster=["AAPL", "MSFT"],
    )
    b = plan_attention_shadow(
        run_date=RUN,
        artifacts=[("asset", "spy")],
        prior_loader=loader,
        h4_roster=["AAPL", "MSFT"],
    )
    assert a.plan is not None and b.plan is not None
    assert a.plan.plan_id == b.plan.plan_id
    house = house_profile_config()
    assert a.plan.plan_id == attention_plan_id(
        run_date=RUN,
        profile_config_version_id=house.version_id,
        roster_fingerprint=h4_roster_fingerprint(["AAPL", "MSFT"]),
    )


def test_cannot_expand_h4_roster() -> None:
    loader = _MapPriorLoader({})
    result = plan_attention_shadow(
        run_date=RUN,
        artifacts=[],
        prior_loader=loader,
        h4_roster=["SPY"],
    )
    assert result.plan is not None
    assert_plan_preserves_h4_roster(result.plan, ["SPY"])
    with pytest.raises(AttentionPlanError):
        assert_plan_preserves_h4_roster(result.plan, ["SPY", "EXTRA"])


def test_plan_rejects_fingerprint_tamper() -> None:
    house = house_profile_config()
    roster = ["SPY"]
    fp = h4_roster_fingerprint(roster)
    with pytest.raises(ValidationError):
        AttentionPlan(
            plan_id=attention_plan_id(
                run_date=RUN,
                profile_config_version_id=house.version_id,
                roster_fingerprint=fp,
            ),
            planner_mode="shadow",
            profile_config_version_id=house.version_id,
            profile_key="house",
            is_house_default=True,
            run_date=RUN,
            h4_roster=["SPY", "HACK"],
            h4_roster_fingerprint=fp,
            decisions=[],
        )


def test_no_h7_h8_authority_fields() -> None:
    loader = _MapPriorLoader({})
    result = plan_attention_shadow(
        run_date=RUN,
        artifacts=[("segment", "rates")],
        prior_loader=loader,
        h4_roster=["TLT"],
    )
    assert result.plan is not None
    assert_plan_has_no_h7_h8_authority(result.plan)
    dumped = result.plan.model_dump()
    assert "weights" not in dumped
    assert "mandate" not in dumped
    assert "h8" not in dumped


def test_actuated_true_forbidden() -> None:
    with pytest.raises(ValidationError):
        AttentionPlanShadowResult(
            planner_mode="off",
            plan=None,
            actuated=True,
            incumbent_edit_modes={},
        )


def test_overlay_missing_pin_fails_closed() -> None:
    missing = UUID("00000000-0000-4000-8000-000000000099")
    with pytest.raises(ProfileConfigMissingError):
        resolve_profile_pin_for_planner(requested_version_id=missing, store={})
    with pytest.raises(ProfileConfigMissingError):
        plan_attention_shadow(
            run_date=RUN,
            artifacts=[],
            prior_loader=_MapPriorLoader({}),
            profile_config_version_id=missing,
            profile_store={},
        )


def test_overlay_pin_allowed_when_present() -> None:
    overlay = ProfileConfig(
        version_id=profile_config_version_id("overlay-alpha"),
        profile_key="overlay-alpha",
        schema_version=1,
        is_house_default=False,
        label="alpha overlay",
    )
    store = {str(overlay.version_id): overlay}
    result = plan_attention_shadow(
        run_date=RUN,
        artifacts=[],
        prior_loader=_MapPriorLoader({}),
        profile_config_version_id=overlay.version_id,
        profile_store=store,
        h4_roster=["IWM"],
    )
    assert result.plan is not None
    assert result.plan.is_house_default is False
    assert result.plan.profile_key == "overlay-alpha"
    assert result.actuated is False


def test_house_default_when_no_pin() -> None:
    cfg = resolve_profile_pin_for_planner(requested_version_id=None)
    assert cfg.is_house_default is True
    assert cfg.version_id == profile_config_version_id("house")


def test_force_full_reasons() -> None:
    loader = _MapPriorLoader(
        {
            ("asset", "spy"): PriorPublished(
                date=date(2026, 8, 20),
                document_key="asset:spy",
                payload={},
            )
        }
    )
    result = plan_attention_shadow(
        run_date=RUN,
        artifacts=[("asset", "spy")],
        prior_loader=loader,
        force_full_rewrite=True,
    )
    assert result.plan is not None
    reasons = result.plan.decisions[0].refresh_reasons
    assert RefreshReasonCode.FORCE_FULL in reasons
    assert RefreshReasonCode.INCUMBENT_FULL in reasons
