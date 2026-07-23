"""H2 market-thesis identity and duplicate-prevention contract."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from digiquant.olympus.hermes.models.thesis import MarketThesisExplorationOutput, ThesisProposal
from digiquant.olympus.hermes.phases.h2_market_thesis_exploration import _reviewed_status_by_id
from digiquant.olympus.hermes.writers.thesis_io import (
    persist_market_thesis_exploration,
    validate_market_thesis_proposals,
    upsert_thesis_row,
)
from digiquant.olympus.atlas.state import AtlasResearchState, PhaseHermesState, PriorContext
from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "olympus"
    / "hermes"
    / "templates"
    / "schemas"
    / "market-thesis-exploration.schema.json"
)


def _proposal(**overrides: object) -> ThesisProposal:
    values: dict[str, object] = {
        "thesis_id": "cta-risk-management",
        "topic_key": "cta-equity-positioning-risk",
        "action": "update",
        "existing_thesis_id": "cta-risk-management",
        "title": "CTA positioning indicates asymmetric equity downside",
        "direction": "hedge",
        "statement": "Crowded CTA equity exposure creates asymmetric selling risk.",
        "validation_criteria": ["CTA equity exposure remains elevated"],
        "invalidation_criteria": ["CTA equity exposure normalizes"],
    }
    values.update(overrides)
    return ThesisProposal.model_validate(values)


def test_update_requires_matching_existing_thesis_id() -> None:
    with pytest.raises(ValidationError, match="requires matching existing_thesis_id"):
        _proposal(existing_thesis_id="cta-equity-volatility")


def test_create_forbids_existing_thesis_id() -> None:
    with pytest.raises(ValidationError, match="cannot set existing_thesis_id"):
        _proposal(
            thesis_id="advanced-materials-growth",
            topic_key="advanced-materials-growth",
            action="create",
        )


def test_checked_in_schema_matches_pydantic_horizon_and_confidence_types() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    properties = schema["properties"]["body"]["properties"]["theses"]["items"]["properties"]

    assert "time_horizon" not in properties
    assert properties["horizon"]["enum"] == ["short_term", "long_term", None]
    assert properties["confidence"] == {
        "type": ["number", "null"],
        "minimum": 0,
        "maximum": 1,
    }


def test_rejects_new_id_for_an_existing_active_topic() -> None:
    active = [
        {
            "thesis_id": "cta-risk-management",
            "topic_key": "cta-equity-positioning-risk",
            "thesis_kind": "market",
            "status": "ACTIVE",
        }
    ]
    proposal = _proposal(
        thesis_id="cta-equity-volatility",
        action="create",
        existing_thesis_id=None,
    )

    accepted, errors = validate_market_thesis_proposals([proposal], active)

    assert accepted == []
    assert errors == [
        "cta-equity-volatility: topic 'cta-equity-positioning-risk' already belongs to "
        "active thesis 'cta-risk-management'; update that thesis instead"
    ]


def test_rejects_two_ids_for_the_same_topic_in_one_run() -> None:
    first = _proposal(
        thesis_id="advanced-materials-growth",
        topic_key="advanced-materials-growth",
        action="create",
        existing_thesis_id=None,
    )
    duplicate = _proposal(
        thesis_id="advanced-materials-demand",
        topic_key="advanced-materials-growth",
        action="create",
        existing_thesis_id=None,
    )

    accepted, errors = validate_market_thesis_proposals([first, duplicate], [])

    assert accepted == [first]
    assert errors == [
        "advanced-materials-demand: topic 'advanced-materials-growth' is already proposed "
        "in this run by 'advanced-materials-growth'"
    ]


def test_accepts_update_of_the_canonical_active_thesis() -> None:
    active = [
        {
            "thesis_id": "cta-risk-management",
            "topic_key": "cta-equity-positioning-risk",
            "thesis_kind": "market",
            "status": "ACTIVE",
        }
    ]
    proposal = _proposal()

    accepted, errors = validate_market_thesis_proposals([proposal], active)

    assert accepted == [proposal]
    assert errors == []


def test_rejects_ambiguous_legacy_active_topic() -> None:
    active = [
        {
            "thesis_id": "cta-risk-management",
            "topic_key": "cta-equity-positioning-risk",
            "thesis_kind": "market",
        },
        {
            "thesis_id": "cta-equity-volatility",
            "topic_key": "cta-equity-positioning-risk",
            "thesis_kind": "market",
        },
    ]

    accepted, errors = validate_market_thesis_proposals([_proposal()], active)

    assert accepted == []
    assert errors == [
        "cta-risk-management: topic 'cta-equity-positioning-risk' has multiple active "
        "theses ['cta-equity-volatility', 'cta-risk-management']; consolidate the register "
        "before writing"
    ]


def test_h2_update_preserves_h1_same_run_status() -> None:
    state = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 7, 20),
        prior_context=PriorContext(
            active_theses=[{"thesis_id": "cta-risk-management", "status": "ACTIVE"}]
        ),
        phase_hermes=PhaseHermesState(
            thesis_review={
                "body": {
                    "reviewed_theses": [
                        {
                            "thesis_id": "cta-risk-management",
                            "prior_status": "ACTIVE",
                            "new_status": "CHALLENGED",
                            "evidence": ["Positioning normalized"],
                        }
                    ]
                }
            }
        ),
    )
    client = FakeSupabaseClient()

    persist_market_thesis_exploration(
        client,  # type: ignore[arg-type]
        run_date=state.run_date,
        exploration=MarketThesisExplorationOutput(theses=[_proposal()]),
        status_by_id=_reviewed_status_by_id(state),
    )

    assert client.store["theses"][0]["status"] == "CHALLENGED"


def test_market_thesis_writer_persists_topic_key() -> None:
    client = FakeSupabaseClient()

    upsert_thesis_row(
        client,  # type: ignore[arg-type]
        run_date=date(2026, 7, 20),
        thesis_id="cta-risk-management",
        topic_key="cta-equity-positioning-risk",
        name="CTA positioning risk",
        status="ACTIVE",
        thesis_kind="market",
    )

    assert client.store["theses"][0]["topic_key"] == "cta-equity-positioning-risk"
