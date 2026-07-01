"""H5 edit-mode tests (Olympus #930 PR 4b)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa  # scored-lint: heterogeneous fake-row / fixture dicts
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    FocusRosterEntry,
    PhaseHermesState,
    PriorContext,
)
from digiquant.olympus.edit_mode import DocumentPatch, PatchOp
from digiquant.olympus.hermes.models.analyst import AnalystPayload
from digiquant.olympus.hermes.phases.h5_asset_analyst import build_h5_asset_analyst


def _state(*, prior: dict[str, Any] | None = None) -> AtlasResearchState:
    prior_ctx = PriorContext(
        prior_analyst_by_ticker={"AAPL": prior} if prior else {},
        latest_segments={
            "analyst/AAPL": {
                "date": "2026-06-19",
                "payload": {
                    "body": {
                        "ticker": "AAPL",
                        "conviction_score": 2,
                        "stance": "hold",
                        "thesis": "prior thesis",
                        "risks": "prior risk",
                        "sources": [],
                    }
                },
            }
        }
        if prior
        else {},
    )
    state = AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 6, 20),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
        prior_context=prior_ctx,
        price_deltas={"AAPL": 0.02},
    )
    state.phase_hermes = PhaseHermesState(
        focus_roster=[FocusRosterEntry(ticker="AAPL", roster_reason="held")]
    )
    return state


@pytest.mark.unit
class TestAnalystEdit:
    def test_stale_fingerprint_uses_document_patch(self) -> None:
        state = _state(
            prior={
                "date": "2026-06-19",
                "stance": "hold",
                "conviction_score": 2,
                "fingerprint_news_hash": "abc",
            }
        )
        compiled = build_pipeline(
            AtlasResearchState, [build_h5_asset_analyst(["AAPL"], held={"AAPL"})]
        )

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            schema = next(
                p["text"]
                for msg in msgs
                for p in msg.get("content", [])
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            assert "DocumentPatch" in schema
            patch = DocumentPatch(
                date=date(2026, 6, 20),
                prior_date=date(2026, 6, 19),
                target_document_key="analyst/AAPL",
                status="updated",
                ops=[PatchOp(op="set", path="/body/stance", value="buy")],
            )
            return json.dumps(patch.model_dump(mode="json"))

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result)
        payload = AnalystPayload.model_validate(final.phase_hermes.asset_analysts["AAPL"])
        assert payload.stance == "buy"
        assert payload.thesis == "prior thesis"
