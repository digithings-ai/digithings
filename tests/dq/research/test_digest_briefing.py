"""WP-E: daily digest is a stitched markdown briefing, not DigestSnapshot JSON slots."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.research.phases.phase7_synthesis import (
    DIGEST_SUBSECTION_SPECS,
    DigestSnapshot,
    _digest_phase_inputs,
    _digest_shared_context,
    _prior_digest_bodies,
    build_phase7,
)
from digiquant.research.segments import (
    compose_legacy_digest_body,
    digest_briefing_for_portfolio,
)
from digiquant.research.skills import (
    DIGEST_BRIEFING_RULES,
    RESEARCH_MEMO_RULES,
    load_skill,
    load_skill_edit,
)
from digiquant.research.state import PriorContext, ResearchConfigBundle, ResearchState

pytestmark = pytest.mark.unit


def _legacy_digest_row() -> dict[str, object]:
    return {
        "segment": "master-digest",
        "date": "2026-08-31",
        "bias": "bearish",
        "headline": "Growth slowing into a sticky inflation print.",
        "material_findings": [
            {
                "label": "Curve",
                "summary": "2s10s re-steepened.",
                "source_ids": ["s1"],
            }
        ],
        "sources": [{"id": "s1", "title": "Treasury", "url": "https://example.com"}],
        "notes": "Watch the 10y.",
        "data_quality": "high",
        "confidence": 0.8,
        "market_regime_snapshot": "Slowing / cooling.",
        "alt_data_dashboard": "CTA covering.",
        "institutional_summary": "Modest outflows.",
        "asset_classes_summary": "Bonds bid.",
        "us_equities_summary": "Narrow breadth.",
        "actionable_summary": [
            {"priority": 1, "label": "Watch DXY 105", "rationale": "Break would confirm."}
        ],
        "risk_radar": [{"horizon_hours": 24, "label": "CPI", "trigger": "Core above 0.3%."}],
        "regime_label": "Slowing / Cooling",
    }


def test_digest_snapshot_is_thin_markdown_envelope() -> None:
    snap = DigestSnapshot(
        segment="master-digest",
        date=date(2026, 8, 31),
        body="# Daily Digest — 2026-08-31\n\n## Market regime\n\nSlowing.\n",
        regime_label="Slowing / Cooling",
    )
    dumped = snap.model_dump(mode="json")
    assert dumped["body"].startswith("# Daily Digest")
    assert dumped["regime_label"] == "Slowing / Cooling"
    assert "bias" not in DigestSnapshot.model_fields
    assert "headline" not in DigestSnapshot.model_fields
    assert "material_findings" not in DigestSnapshot.model_fields
    assert "actionable_summary" not in DigestSnapshot.model_fields
    assert "data_quality" not in DigestSnapshot.model_fields
    assert "confidence" not in DigestSnapshot.model_fields


def test_legacy_json_slots_compose_into_body_without_fake_metrics() -> None:
    body = compose_legacy_digest_body(_legacy_digest_row())
    assert "Growth slowing" in body
    assert "Slowing / cooling" in body
    assert "CTA covering" in body
    assert "Watch DXY 105" in body
    assert "Overall bias" not in body
    assert "data_quality" not in body
    assert "confidence" not in body.lower() or "0.8" not in body


def test_digest_snapshot_composes_legacy_row_when_body_missing() -> None:
    snap = DigestSnapshot.model_validate(_legacy_digest_row())
    assert "Growth slowing" in snap.body
    assert "Narrow breadth" in snap.body


def test_digest_briefing_for_portfolio_is_date_body_regime_only() -> None:
    briefing = digest_briefing_for_portfolio(
        {
            "date": "2026-08-31",
            "body": "# Daily Digest — 2026-08-31\n\n## Market regime\n\nSlowing.\n",
            "regime_label": "Slowing / Cooling",
            "bias": "bearish",
            "headline": "should not reach H1",
            "material_findings": [{"label": "x", "summary": "y"}],
        }
    )
    assert briefing == {
        "date": "2026-08-31",
        "body": "# Daily Digest — 2026-08-31\n\n## Market regime\n\nSlowing.\n",
        "regime_label": "Slowing / Cooling",
    }
    assert "bias" not in briefing
    assert "headline" not in briefing
    assert "material_findings" not in briefing


def test_digest_briefing_composes_legacy_when_body_absent() -> None:
    briefing = digest_briefing_for_portfolio(_legacy_digest_row())
    assert briefing["date"] == "2026-08-31"
    assert "Growth slowing" in briefing["body"]
    assert briefing["regime_label"] == "Slowing / Cooling"
    assert set(briefing) <= {"date", "body", "regime_label"}


def test_subsection_roster_is_capped_to_current_digest_topics() -> None:
    slugs = [spec.slug for spec in DIGEST_SUBSECTION_SPECS]
    assert slugs == ["macro", "alt-data", "institutional", "asset-classes", "us-equities"]
    assert "sector-technology" not in slugs


def test_build_phase7_is_subsections_then_stitcher() -> None:
    phases = build_phase7()
    assert [p.name for p in phases] == ["phase7_subsections", "phase7_synthesis"]
    assert [n.name for n in phases[0].nodes] == [
        "digest-macro",
        "digest-alt-data",
        "digest-institutional",
        "digest-asset-classes",
        "digest-us-equities",
    ]
    assert [n.name for n in phases[1].nodes] == ["master-digest"]


def test_digest_and_subsection_skills_are_markdown_briefings() -> None:
    digest = load_skill("digest")
    subsection = load_skill("digest-subsection")
    assert RESEARCH_MEMO_RULES not in digest
    assert RESEARCH_MEMO_RULES not in subsection
    assert DIGEST_BRIEFING_RULES in digest
    assert DIGEST_BRIEFING_RULES in subsection
    assert "Do **not** emit `**Overall bias:**`" in digest
    assert not any(line.lstrip().startswith("**Overall bias:**") for line in digest.splitlines())
    lowered = digest.lower()
    assert "markdown" in lowered
    assert "briefing" in lowered or "stitched" in lowered
    edit = load_skill_edit("digest")
    assert "/body" in edit
    assert RESEARCH_MEMO_RULES not in edit


def test_prior_digest_bodies_are_two_full_reports_not_300_char_slims() -> None:
    yesterday = "# Daily Digest — 2026-08-30\n\n## Market regime\n\n" + (
        "Yesterday called for cooling. " * 40
    )
    day_before = "# Daily Digest — 2026-08-29\n\n## Market regime\n\n" + (
        "Day-before held a risk-off stance. " * 40
    )
    state = ResearchState(
        run_type="delta",
        run_date=date(2026, 8, 31),
        config=ResearchConfigBundle(watchlist=["SPY"]),
        prior_context=PriorContext(
            last_snapshots=[
                {
                    "date": "2026-08-30",
                    "run_type": "delta",
                    "snapshot": {
                        "date": "2026-08-30",
                        "body": yesterday,
                        "regime_label": "Cooling",
                    },
                },
                {
                    "date": "2026-08-29",
                    "run_type": "delta",
                    "snapshot": {
                        "date": "2026-08-29",
                        "body": day_before,
                        "regime_label": "Risk-off",
                    },
                },
            ]
        ),
    )
    priors = _prior_digest_bodies(state, limit=2)
    assert len(priors) == 2
    assert priors[0]["date"] == "2026-08-30"
    assert priors[1]["date"] == "2026-08-29"
    assert yesterday.strip() in priors[0]["body"]
    assert day_before.strip() in priors[1]["body"]
    assert "..." not in priors[0]["body"][-10:]
    assert len(priors[0]["body"]) > 300

    shared = _digest_shared_context(state)
    latest = shared["prior_context"]["latest_segments"]
    assert set(latest) <= {"digest", "digest-delta"}
    stitch_inputs = _digest_phase_inputs(state)
    assert "phase1" not in stitch_inputs
    assert "phase5" not in stitch_inputs
    assert "subsections" in stitch_inputs
    assert "prior_digests" in stitch_inputs
    assert len(stitch_inputs["prior_digests"]) == 2
