"""WP-B: H1 thesis-review and H4 screener publish inspectable documents."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from digigraph.graph.pipeline_builder import build_pipeline
from digiquant.research.state import ResearchConfigBundle, ResearchState, PriorContext
from digiquant.dashboard.edit_mode.prior import artifact_document_key
from digiquant.portfolio.models.thesis import ThesisReviewOutput, ThesisStatusUpdate
from digiquant.portfolio.phases import h1_thesis_review as h1
from digiquant.portfolio.phases.h1_thesis_review import ARTIFACT_KEY, build_h1_thesis_review
from digiquant.portfolio.phases.h4_opportunity_screener import (
    OPPORTUNITY_SCREENER_DOCUMENT_KEY,
    build_h4_opportunity_screener,
)

from tests.dq.research.test_supabase_io import FakeSupabaseClient

THESIS_REVIEW_DOCUMENT_KEY = artifact_document_key(ARTIFACT_KEY)


@pytest.mark.unit
class TestH1PublishesThesisReviewDocument:
    def test_h1_upserts_thesis_review_document_key(self) -> None:
        state = ResearchState(
            run_type="delta",
            run_date=date(2026, 8, 31),
            config=ResearchConfigBundle(watchlist=["GLD"]),
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
        compiled = build_pipeline(ResearchState, [build_h1_thesis_review(client=client)])
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
            "digiquant.portfolio.phases.h1_thesis_review._run_h1_llm",
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

    def test_h1_receives_stitched_markdown_briefing(self) -> None:
        """WP-E: H1 consumes date/body/regime_label, not JSON findings."""
        state = ResearchState(
            run_type="delta",
            run_date=date(2026, 8, 31),
            config=ResearchConfigBundle(watchlist=["GLD"]),
            prior_context=PriorContext(active_theses=[]),
        )
        state.phase7_digest = {
            "date": "2026-08-31",
            "body": "# Daily Digest — 2026-08-31\n\n## Market regime\n\nSlowing / cooling.\n",
            "regime_label": "Slowing / Cooling",
            "bias": "bearish",
            "headline": "should not reach H1",
            "material_findings": [{"label": "Curve", "summary": "2s10s re-steepened."}],
        }
        captured: dict[str, object] = {}

        def _capture(**kwargs: object) -> tuple[ThesisReviewOutput, None, list[object]]:
            inputs = kwargs["phase_inputs"]  # type: ignore[index]
            captured["digest"] = inputs["digest"]  # type: ignore[index]
            return ThesisReviewOutput(), None, []

        client = FakeSupabaseClient()
        compiled = build_pipeline(ResearchState, [build_h1_thesis_review(client=client)])
        with patch.object(h1, "run_thesis_phase_llm", side_effect=_capture):
            compiled.invoke(state)

        digest = captured["digest"]
        assert isinstance(digest, dict)
        assert digest["date"] == "2026-08-31"
        assert "Slowing / cooling" in str(digest["body"])
        assert digest["regime_label"] == "Slowing / Cooling"
        assert "bias" not in digest
        assert "headline" not in digest
        assert "material_findings" not in digest

    def test_h1_composes_legacy_digest_json_into_markdown(self) -> None:
        state = ResearchState(
            run_type="delta",
            run_date=date(2026, 8, 31),
            config=ResearchConfigBundle(watchlist=["GLD"]),
            prior_context=PriorContext(active_theses=[]),
        )
        state.phase7_digest = {
            "date": "2026-08-31",
            "headline": "Growth slowing into a sticky inflation print.",
            "market_regime_snapshot": "Slowing / cooling.",
            "regime_label": "Slowing / Cooling",
            "bias": "bearish",
            "material_findings": [{"label": "Curve", "summary": "2s10s re-steepened."}],
        }
        captured: dict[str, object] = {}

        def _capture(**kwargs: object) -> tuple[ThesisReviewOutput, None, list[object]]:
            inputs = kwargs["phase_inputs"]  # type: ignore[index]
            captured["digest"] = inputs["digest"]  # type: ignore[index]
            return ThesisReviewOutput(), None, []

        client = FakeSupabaseClient()
        compiled = build_pipeline(ResearchState, [build_h1_thesis_review(client=client)])
        with patch.object(h1, "run_thesis_phase_llm", side_effect=_capture):
            compiled.invoke(state)

        digest = captured["digest"]
        assert isinstance(digest, dict)
        assert "Growth slowing" in str(digest["body"])
        assert set(digest) <= {"date", "body", "regime_label"}


@pytest.mark.unit
class TestH4PublishesOpportunityScreener:
    def test_h4_upserts_flat_opportunity_screener_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.portfolio.phases import h4_opportunity_screener as h4

        monkeypatch.setenv("PORTFOLIO_HELD_GATE", "off")
        monkeypatch.setattr(h4, "assess_budget", lambda *a, **k: (2, 0, None))
        client = FakeSupabaseClient()
        node = build_h4_opportunity_screener(client=client).nodes[0].run
        state = ResearchState(
            run_type="delta",
            run_date=date(2026, 8, 31),
            config=ResearchConfigBundle(watchlist=["SPY", "QQQ", "GLD"]),
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
