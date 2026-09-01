"""WP-B: H1 thesis-review and H4 screener publish inspectable documents."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from digigraph.graph.pipeline_builder import build_pipeline
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState, PriorContext
from digiquant.olympus.edit_mode.prior import artifact_document_key
from digiquant.olympus.hermes.models.thesis import ThesisReviewOutput, ThesisStatusUpdate
from digiquant.olympus.hermes.phases.h1_thesis_review import ARTIFACT_KEY, build_h1_thesis_review
from digiquant.olympus.hermes.phases.h4_opportunity_screener import (
    OPPORTUNITY_SCREENER_DOCUMENT_KEY,
    build_h4_opportunity_screener,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

THESIS_REVIEW_DOCUMENT_KEY = artifact_document_key(ARTIFACT_KEY)


@pytest.mark.unit
class TestH1PublishesThesisReviewDocument:
    def test_h1_upserts_thesis_review_document_key(self) -> None:
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 8, 31),
            config=AtlasConfigBundle(watchlist=["GLD"]),
            prior_context=PriorContext(
                active_theses=[
                    {
                        "thesis_id": "geo-gold",
                        "name": "Gold hedge",
                        "status": "ACTIVE",
                    }
                ]
            ),
        )
        client = FakeSupabaseClient()
        compiled = build_pipeline(AtlasResearchState, [build_h1_thesis_review(client=client)])
        llm_review = ThesisReviewOutput(
            reviewed_theses=[
                ThesisStatusUpdate(
                    thesis_id="geo-gold",
                    prior_status="ACTIVE",
                    new_status="ACTIVE",
                    evidence=["still valid"],
                )
            ],
            notes="Gold remains the hedge.",
        )
        with patch(
            "digiquant.olympus.hermes.phases.h1_thesis_review._run_h1_llm",
            return_value=llm_review,
        ):
            compiled.invoke(state)

        docs = client.store.get("documents", [])
        row = next(r for r in docs if r["document_key"] == THESIS_REVIEW_DOCUMENT_KEY)
        assert THESIS_REVIEW_DOCUMENT_KEY == "thesis/thesis-review"
        body = row["payload"].get("body", row["payload"])
        assert body["notes"] == "Gold remains the hedge."
        reviewed = body.get("reviewed_theses") or []
        assert reviewed[0]["thesis_id"] == "geo-gold"


@pytest.mark.unit
class TestH4PublishesOpportunityScreener:
    def test_h4_upserts_flat_opportunity_screener_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.olympus.hermes.phases import h4_opportunity_screener as h4

        monkeypatch.setenv("HERMES_HELD_GATE", "off")
        monkeypatch.setattr(h4, "assess_budget", lambda *a, **k: (2, 0, None))
        client = FakeSupabaseClient()
        node = build_h4_opportunity_screener(client=client).nodes[0].run
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 8, 31),
            config=AtlasConfigBundle(watchlist=["SPY", "QQQ", "GLD"]),
            prior_context=PriorContext(prior_book=[{"ticker": "SPY"}, {"ticker": "QQQ"}]),
        )
        node(state)

        docs = client.store.get("documents", [])
        row = next(r for r in docs if r["document_key"] == OPPORTUNITY_SCREENER_DOCUMENT_KEY)
        assert OPPORTUNITY_SCREENER_DOCUMENT_KEY == "opportunity-screener"
        payload = row["payload"]
        assert payload["doc_type"] == "opportunity_screen"
        body = payload["body"]
        tickers = [entry["ticker"] for entry in body["shortlist"]]
        assert "SPY" in tickers
        assert "QQQ" in tickers
