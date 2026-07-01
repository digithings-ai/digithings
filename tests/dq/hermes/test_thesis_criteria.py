"""Thesis invalidation criteria — H1 must mark CHALLENGED on hit (spec §16)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState, PriorContext
from digiquant.olympus.hermes.models.thesis import ThesisReviewOutput, ThesisStatusUpdate
from digiquant.olympus.hermes.phases.h1_thesis_review import build_h1_thesis_review
from digiquant.olympus.hermes.writers.thesis_io import (
    apply_invalidation_hits,
    merge_review_with_invalidation_hits,
    normalize_thesis_status,
)
from digigraph.graph.pipeline_builder import build_pipeline
from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


@pytest.mark.unit
class TestThesisIoInvalidationHits:
    def test_normalize_thesis_status_uppercases(self) -> None:
        assert normalize_thesis_status("active") == "ACTIVE"
        assert normalize_thesis_status("challenged") == "CHALLENGED"

    def test_apply_invalidation_hits_marks_challenged(self) -> None:
        active = [
            {
                "thesis_id": "geo-gold",
                "name": "Gold on geo risk",
                "status": "ACTIVE",
                "invalidation_criteria": ["USD index above 110"],
            }
        ]
        updates = apply_invalidation_hits(active, {"geo-gold": ["USD index above 110"]})
        assert len(updates) == 1
        assert updates[0].thesis_id == "geo-gold"
        assert updates[0].new_status == "CHALLENGED"
        assert updates[0].prior_status == "ACTIVE"
        assert updates[0].challenged_by == ["USD index above 110"]

    def test_merge_review_preserves_existing_and_adds_challenged(self) -> None:
        review = ThesisReviewOutput(
            reviewed_theses=[
                ThesisStatusUpdate(
                    thesis_id="rates",
                    prior_status="ACTIVE",
                    new_status="ACTIVE",
                    evidence=["still valid"],
                )
            ]
        )
        active = [
            {"thesis_id": "geo-gold", "status": "ACTIVE"},
            {"thesis_id": "rates", "status": "ACTIVE"},
        ]
        merged = merge_review_with_invalidation_hits(
            review,
            active,
            {"geo-gold": ["oil below 60"]},
        )
        by_id = {u.thesis_id: u for u in merged.reviewed_theses}
        assert by_id["geo-gold"].new_status == "CHALLENGED"
        assert by_id["rates"].new_status == "ACTIVE"


@pytest.mark.unit
class TestH1ThesisReviewInvalidation:
    def test_h1_node_marks_challenged_on_invalidation_hit(self) -> None:
        state = AtlasResearchState(
            run_type="baseline",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["GLD"]),
            prior_context=PriorContext(
                active_theses=[
                    {
                        "thesis_id": "geo-gold",
                        "name": "Gold hedge",
                        "status": "ACTIVE",
                        "invalidation_criteria": ["USD index above 110"],
                    }
                ]
            ),
        )
        client = FakeSupabaseClient()
        compiled = build_pipeline(
            AtlasResearchState,
            [build_h1_thesis_review(client=client)],
        )

        llm_review = ThesisReviewOutput(
            reviewed_theses=[
                ThesisStatusUpdate(
                    thesis_id="geo-gold",
                    prior_status="ACTIVE",
                    new_status="ACTIVE",
                    evidence=["no change from model"],
                )
            ]
        )

        with patch(
            "digiquant.olympus.hermes.phases.h1_thesis_review._run_h1_llm",
            return_value=llm_review,
        ):
            with patch(
                "digiquant.olympus.hermes.phases.h1_thesis_review._invalidation_hits_for_state",
                return_value={"geo-gold": ["USD index above 110"]},
            ):
                result = compiled.invoke(state)

        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result
        body = final.phase_hermes.thesis_review
        assert body is not None
        reviewed = body.get("body", body).get("reviewed_theses", [])
        geo = next(r for r in reviewed if r["thesis_id"] == "geo-gold")
        assert geo["new_status"] == "CHALLENGED"

        rows = client.store.get("theses", [])
        geo_row = next(r for r in rows if r["thesis_id"] == "geo-gold")
        assert geo_row["status"] == "CHALLENGED"
