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


@pytest.mark.unit
class TestEvidenceDerivedConviction:
    """#1672 — conviction is computed from itemized evidence, not model vibes.

    Production decision_log 2026-07-01..22: 77% of entries at exactly +2. The
    evidence block takes the number away from the LLM; these tests pin the
    mapping's shape: high conviction structurally rare, spread otherwise.
    """

    @staticmethod
    def _payload(stance: str, **ev: object) -> "AnalystPayload":
        from digiquant.olympus.hermes.models.analyst import AnalystPayload

        base = {
            "independent_confirming_signals": 3,
            "contradicting_signals": 1,
            "catalyst_within_horizon": False,
            "trend_alignment": "with",
            "evidence_quality": "medium",
        }
        base.update(ev)
        return AnalystPayload.model_validate(
            {
                "ticker": "SPY",
                "conviction_score": 2,  # the model's parked default — must be ignored
                "stance": stance,
                "evidence": base,
            }
        )

    def test_model_provided_score_is_overridden(self) -> None:
        p = self._payload("buy")
        # 3 confirming − 1 contradicting = 2; caps don't bind → 2 (computed, not parked)
        assert p.conviction_score == 2
        p2 = self._payload("buy", contradicting_signals=3)
        assert p2.conviction_score == 0, "net evidence drives the score, not the default"

    def test_high_conviction_requires_the_full_bar(self) -> None:
        full_bar = dict(
            independent_confirming_signals=5,
            contradicting_signals=0,
            catalyst_within_horizon=True,
            trend_alignment="with",
            evidence_quality="high",
        )
        assert self._payload("buy", **full_bar).conviction_score == 5
        # Remove any single requirement → high (>=4) is unreachable
        assert (
            self._payload("buy", **{**full_bar, "catalyst_within_horizon": False}).conviction_score
            <= 3
        )
        assert (
            self._payload("buy", **{**full_bar, "evidence_quality": "medium"}).conviction_score <= 3
        )
        assert self._payload("buy", **{**full_bar, "evidence_quality": "low"}).conviction_score <= 2
        assert (
            self._payload("buy", **{**full_bar, "contradicting_signals": 2}).conviction_score <= 3
        )

    def test_sell_mirrors_negative_and_hold_clamps(self) -> None:
        strong = dict(
            independent_confirming_signals=5,
            contradicting_signals=0,
            catalyst_within_horizon=True,
            trend_alignment="with",
            evidence_quality="high",
        )
        assert self._payload("sell", **strong).conviction_score == -5
        assert abs(self._payload("hold", **strong).conviction_score) <= 1
        assert self._payload("watch", trend_alignment="mixed").conviction_score == 0

    def test_distribution_over_realistic_grid_is_spread_and_high_is_rare(self) -> None:
        from collections import Counter

        scores = []
        for confirming in range(6):
            for contradicting in range(4):
                for catalyst in (True, False):
                    for quality in ("high", "medium", "low"):
                        scores.append(
                            self._payload(
                                "buy",
                                independent_confirming_signals=confirming,
                                contradicting_signals=contradicting,
                                catalyst_within_horizon=catalyst,
                                evidence_quality=quality,
                            ).conviction_score
                        )
        counts = Counter(scores)
        n = len(scores)
        assert max(counts.values()) / n < 0.5, f"single-mode collapse: {counts}"
        high = sum(v for k, v in counts.items() if k >= 4)
        low = sum(v for k, v in counts.items() if k in (0, 1))
        assert high < low, f"high must be scarcer than low: {counts}"
        assert high > 0, "high must remain reachable"

    def test_legacy_payload_without_evidence_keeps_stored_score(self) -> None:
        from digiquant.olympus.hermes.models.analyst import AnalystPayload

        p = AnalystPayload.model_validate({"ticker": "SPY", "conviction_score": 4, "stance": "buy"})
        assert p.conviction_score == 4, "legacy docs keep their stored score"
