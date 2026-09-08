"""Integration tests for Phase 6 bias row + Phase 7 digest synthesis +
Phase 7C analysts + Phase 7D PM rebalance.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # score:allow untyped any — used for fake-completion dict shape
from unittest.mock import patch

import pytest
from digigraph.graph.pipeline_builder import build_pipeline
from digiquant.dashboard.edit_mode import DocumentPatch, PatchOp
from digiquant.portfolio.models.analyst import AnalystPayload
from digiquant.portfolio.phases.h5_asset_analyst import build_h5_asset_analyst
from digiquant.portfolio.phases.phase7d_pm import RebalanceDecision, build_phase7d
from digiquant.research import diagnostics
from digiquant.research.phases.phase6_consolidate import build_phase6
from digiquant.research.phases.phase7_synthesis import (
    _DIGEST_MODEL_CONTEXT_TOKENS,
    _DIGEST_SEGMENT_MIN_CHARS,
    DigestSnapshot,
    _bodies,
    _count_today_segments,
    _digest_phase_inputs,
    _digest_shared_context,
    _enforce_research_only_boundary,
    _per_segment_char_budget,
    _slim_segment_body,
    _subsection_phase_inputs,
    build_phase7,
)
from digiquant.research.skills import load_skill
from digiquant.research.state import (
    Carried,
    PhasePortfolioState,
    PriorContext,
    ResearchConfigBundle,
    ResearchState,
    SegmentPayload,
    SegmentSlot,
)
from digiquant.research.testing.simulator import parse_schema_name


def _seed_state_through_phase5() -> ResearchState:
    """Populate phases 1–5 with minimal fresh slots so Phase 6+ has input."""
    state = ResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        config=ResearchConfigBundle(watchlist=["AAPL", "MSFT"]),
    )

    def _slot(slug: str, bias: str = "bullish", **extra: Any) -> SegmentSlot:
        body = {"segment": slug, "bias": bias, **extra}
        return SegmentSlot(payload=SegmentPayload(segment=slug, body=body, as_of=date(2026, 4, 26)))

    state.phase1_outputs = {
        "alt-sentiment-news": _slot("alt-sentiment-news"),
        "alt-cta-positioning": _slot("alt-cta-positioning", bias="neutral"),
        "alt-options-derivatives": _slot("alt-options-derivatives", vix_level=15.2),
        "alt-politician-signals": _slot("alt-politician-signals"),
    }
    state.phase2_outputs = {
        "inst-institutional-flows": _slot("inst-institutional-flows"),
        "inst-hedge-fund-intel": _slot("inst-hedge-fund-intel"),
    }
    state.phase3_output = _slot("macro", regime_label="Slowing / Cooling / Neutral / Mixed")
    state.phase4_outputs = {
        "bonds": _slot("bonds"),
        "commodities": _slot("commodities"),
        "forex": _slot("forex"),
        "crypto": _slot("crypto"),
        "international": _slot("international"),
    }
    state.phase5_outputs = {"equity": _slot("equity")}
    return state


# ─── Phase 6 tests ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPhase6BiasRow:
    def test_row_captures_phases_1_through_5(self) -> None:
        compiled = build_pipeline(ResearchState, [build_phase6()])
        state = _seed_state_through_phase5()
        result = compiled.invoke(state)
        final = ResearchState.model_validate(result) if isinstance(result, dict) else result

        row = final.phase6_bias_row
        assert row is not None
        assert row["date"] == "2026-04-26"
        assert row["macro_regime"].startswith("Slowing")
        assert row["equity_bias"] == "bullish"
        assert row["crypto_bias"] == "bullish"
        assert row["bond_bias"] == "bullish"
        assert row["vix_level"] == 15.2
        assert row["cta_direction"] == "neutral"
        assert row["notes"] == ""  # filled by Phase 7

    def test_prefers_internal_bias_over_legacy_bias(self) -> None:
        compiled = build_pipeline(ResearchState, [build_phase6()])
        state = _seed_state_through_phase5()
        equity = state.phase5_outputs["equity"]
        equity.payload.body["internal_bias"] = "bearish"
        equity.payload.body["bias"] = "bullish"
        result = compiled.invoke(state)
        final = ResearchState.model_validate(result) if isinstance(result, dict) else result
        assert final.phase6_bias_row is not None
        assert final.phase6_bias_row["equity_bias"] == "bearish"

    def test_no_llm_call(self) -> None:
        """Phase 6 is pure aggregation."""
        compiled = build_pipeline(ResearchState, [build_phase6()])
        state = _seed_state_through_phase5()
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=AssertionError("Phase 6 must not call the LLM"),
        ):
            compiled.invoke(state)

    def test_bias_row_carried_when_all_upstream_segments_carried(self) -> None:
        """Quiet day: carry prior snapshot bias fields without recomputing."""
        state = _seed_state_through_phase5()
        state.run_type = "delta"
        state.baseline_date = date(2026, 4, 25)
        for bag_name in ("phase1_outputs", "phase4_outputs"):
            bag = getattr(state, bag_name)
            carried_bag = {slug: _carried_slot(slug) for slug in bag}
            setattr(state, bag_name, carried_bag)
        state.phase2_outputs = {slug: _carried_slot(slug) for slug in state.phase2_outputs}
        state.phase3_output = _carried_slot("macro")
        state.phase5_outputs = {"equity": _carried_slot("equity")}
        from digiquant.research.state import DeltaTriageDecision, DeltaTriageResult

        state.triage = DeltaTriageResult(
            evaluated_at=date(2026, 4, 26),
            baseline_date=date(2026, 4, 25),
            decisions=[
                DeltaTriageDecision(
                    segment="macro",
                    decision="carry",
                    reason="quiet",
                    tier="mandatory",
                )
            ],
        )
        state.prior_context = PriorContext(
            last_snapshots=[
                {
                    "date": "2026-04-25",
                    "run_type": "delta",
                    "snapshot": {
                        "macro_regime": "Prior regime",
                        "equity_bias": "neutral",
                        "crypto_bias": "bearish",
                        "bond_bias": "bullish",
                        "commodity_bias": "neutral",
                        "forex_bias": "mixed",
                    },
                }
            ]
        )

        compiled = build_pipeline(ResearchState, [build_phase6()])
        final = ResearchState.model_validate(compiled.invoke(state))

        row = final.phase6_bias_row
        assert row is not None
        assert row["macro_regime"] == "Prior regime"
        assert row["crypto_bias"] == "bearish"
        assert row["equity_bias"] == "neutral"
        assert row["date"] == "2026-04-26"

    def test_bias_row_recompute_emits_document_delta_when_fields_change(self) -> None:
        """Deterministic recompute with prior → merge patch + audit delta."""
        state = _seed_state_through_phase5()
        state.prior_context = PriorContext(
            last_snapshots=[
                {
                    "date": "2026-04-25",
                    "run_type": "delta",
                    "snapshot": {
                        "macro_regime": "Old regime",
                        "equity_bias": "neutral",
                        "crypto_bias": "neutral",
                        "bond_bias": "neutral",
                        "commodity_bias": "neutral",
                        "forex_bias": "neutral",
                    },
                }
            ]
        )

        compiled = build_pipeline(ResearchState, [build_phase6()])
        final = ResearchState.model_validate(compiled.invoke(state))

        assert final.phase6_bias_row is not None
        assert final.phase6_bias_row["macro_regime"].startswith("Slowing")
        assert "digest" in final.document_deltas
        delta = DocumentPatch.model_validate(final.document_deltas["digest"])
        assert delta.status == "updated"
        assert delta.ops


# ─── Phase 7 tests ──────────────────────────────────────────────────────────


def _digest_payload() -> str:
    return json.dumps(
        {
            "segment": "master-digest",
            "date": "2026-04-26",
            "body": (
                "# Daily Digest — 2026-04-26\n\n"
                "## Market regime\n\nGrowth slowing\n\n"
                "## Alt-data\n\nRetail bullish; CTAs neutral\n\n"
                "## Institutional\n\nModest outflows\n\n"
                "## Asset classes\n\nBonds rallying\n\n"
                "## US equities\n\nNarrow breadth\n"
            ),
            "regime_label": "",
            "sources": [],
            "segment_freshness": {},
        }
    )


def _subsection_payload(slug: str = "macro") -> str:
    return json.dumps(
        {
            "slug": slug,
            "date": "2026-04-26",
            "body": f"## {slug}\n\nGrowth slowing",
            "sources": [],
        }
    )


def _fake_phase7_completion(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
    name = parse_schema_name(msgs)
    if name == "DigestSubsection":
        slug = "macro"
        for part in msgs[1]["content"]:
            if isinstance(part, dict) and str(part.get("text", "")).startswith("PHASE_INPUTS"):
                try:
                    payload = json.loads(part["text"].split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    payload = {}
                slug = str(payload.get("subsection") or "macro")
                break
        return _subsection_payload(slug)
    return _digest_payload()


@pytest.mark.unit
class TestPhase7Synthesis:
    def test_digest_synthesized_and_freshness_overwritten(self) -> None:
        compiled = build_pipeline(ResearchState, [build_phase6(), *build_phase7()])
        state = _seed_state_through_phase5()

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            return _fake_phase7_completion(_m, msgs)

        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=fake,
        ):
            result = compiled.invoke(state)
        final = ResearchState.model_validate(result) if isinstance(result, dict) else result

        digest = final.phase7_digest
        assert digest is not None
        # Freshness map was overwritten with deterministic derivation; LLM's
        # empty dict does not leak into the persisted payload.
        assert digest["segment_freshness"], "freshness map must not be empty"
        assert digest["segment_freshness"]["macro"]["source"] == "today"
        assert digest["segment_freshness"]["equity"]["source"] == "today"

    def test_digest_edit_merges_document_patch(self) -> None:
        """Edit mode: DocumentPatch merges into prior digest (spec §16)."""
        prior_digest = {
            "segment": "master-digest",
            "date": "2026-04-25",
            "bias": "neutral",
            "headline": "Prior headline",
            "material_findings": [],
            "sources": [],
            "notes": "",
            "market_regime_snapshot": "Old regime snapshot",
            "alt_data_dashboard": "Old alt",
            "institutional_summary": "Old inst",
            "asset_classes_summary": "Old assets",
            "us_equities_summary": "Old equities",
            "thesis_tracker": "",
            "portfolio_recommendations": "",
            "actionable_summary": [{"priority": 1, "label": "old", "rationale": "old"}],
            "risk_radar": [],
            "segment_freshness": {},
            "regime_label": "Old label",
        }
        state = _seed_state_through_phase5()
        state.run_type = "delta"
        state.baseline_date = date(2026, 4, 25)
        state.prior_context = PriorContext(
            last_snapshots=[{"date": "2026-04-25", "run_type": "delta", "snapshot": {}}],
            latest_segments={
                "digest-delta": {
                    "date": "2026-04-25",
                    "document_key": "digest-delta",
                    "doc_type": "Daily Delta",
                    "payload": prior_digest,
                }
            },
        )
        # One fresh segment so digest is not skipped.
        state.phase4_outputs["bonds"] = SegmentSlot(
            payload=SegmentPayload(
                segment="bonds",
                body={"segment": "bonds", "bias": "bullish"},
                as_of=date(2026, 4, 26),
            )
        )

        doc_patch = DocumentPatch(
            schema_version="1.0",
            date=date(2026, 4, 26),
            prior_date=date(2026, 4, 25),
            target_document_key="digest-delta",
            status="updated",
            ops=[
                PatchOp(
                    op="set",
                    path="/body",
                    value="# Daily Digest — 2026-04-26\n\n## Market regime\n\nGrowth slowing after CPI\n",
                    reason="macro shift",
                ),
            ],
        )

        from digiquant.research.phases.phase7_synthesis import DigestSubsection

        def fake_agent(*, output_model: type, **kwargs: Any) -> Any:
            del kwargs
            if output_model is DocumentPatch:
                return doc_patch
            if output_model is DigestSubsection:
                return DigestSubsection(
                    slug="macro",
                    date=date(2026, 4, 26),
                    body="## Macro\n\nGrowth slowing after CPI",
                )
            return DigestSnapshot.model_validate(json.loads(_digest_payload()))

        compiled = build_pipeline(ResearchState, [build_phase6(), *build_phase7()])

        with patch(
            "digiquant.research.phases.phase7_synthesis.run_research_agent",
            side_effect=fake_agent,
        ):
            final = ResearchState.model_validate(compiled.invoke(state))

        digest = final.phase7_digest
        assert digest is not None
        assert "Growth slowing after CPI" in digest["body"]
        assert digest["segment_freshness"]["bonds"]["source"] == "today"
        assert "digest-delta" in final.document_deltas


# ─── Phase 7 research-only boundary ─────────────────────────────────────────


@pytest.mark.unit
class TestPhase7ResearchOnlyBoundary:
    def test_enforce_strips_trade_verbs_from_body(self) -> None:
        digest = DigestSnapshot.model_validate(
            {
                "segment": "master-digest",
                "date": "2026-04-26",
                "body": (
                    "# Daily Digest\n\n"
                    "Overweight XLK; underweight XLF. Reduce exposure to cyclicals.\n"
                ),
            }
        )
        stripped = _enforce_research_only_boundary(digest)
        lowered = stripped.body.lower()
        assert "overweight" not in lowered
        assert "underweight" not in lowered
        assert "reduce exposure" not in lowered
        published = json.loads(json.dumps(stripped.model_dump(mode="json")))
        # Extras may remain on the model; the stitcher publishes a thin envelope.
        assert "body" in published

    def test_position_fields_stripped_after_synthesis(self) -> None:
        """LLM output with position fields must not leak into persisted digest."""
        compiled = build_pipeline(ResearchState, [build_phase6(), *build_phase7()])
        state = _seed_state_through_phase5()

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            name = parse_schema_name(msgs)
            if name == "DigestSubsection":
                return _fake_phase7_completion(_m, msgs)
            payload = json.loads(_digest_payload())
            payload["body"] = "# Daily Digest\n\nOverweight XLK; trim XLF.\n"
            payload["thesis_tracker"] = "SPY momentum: intact"
            payload["portfolio_recommendations"] = "Overweight XLK; trim XLF"
            return json.dumps(payload)

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = ResearchState.model_validate(result) if isinstance(result, dict) else result

        assert final.phase7_digest is not None
        assert "thesis_tracker" not in final.phase7_digest
        assert "portfolio_recommendations" not in final.phase7_digest
        lowered = final.phase7_digest["body"].lower()
        assert "overweight" not in lowered
        assert "trim" not in lowered


# ─── Phase 7 today-only digest inputs (#927) ────────────────────────────────


def _carried_slot(slug: str, baseline: date = date(2026, 4, 19)) -> SegmentSlot:
    """A carry-forward slot (source='carried') as produced on a delta run."""
    return SegmentSlot(payload=Carried(baseline_date=baseline, reason="below_triage_threshold"))


@pytest.mark.unit
class TestSlimSegmentBodyForDigest:
    def test_memo_body_is_the_digest_input_not_json_slots(self) -> None:
        """WP-C: slim the markdown memo; do not feed bias/findings/data_quality."""
        body = {
            "segment": "alt-sentiment-news",
            "date": "2026-08-31",
            "body": "# Sentiment — 2026-08-31\n\n" + ("risk faded. " * 400),
            "sources": [
                {"id": "fed", "title": "Powell", "url": "https://example.com/fed"},
            ],
            "internal_bias": "bearish",
            "data_quality": "high",
            "confidence": 0.7,
            "headline": "should not be preferred over body",
            "bias": "bullish",
            "material_findings": [{"label": "x", "summary": "y"}],
        }
        slim = _slim_segment_body(body, 2000)
        assert len(json.dumps(slim, default=str, sort_keys=True)) <= 2000
        assert slim["segment"] == "alt-sentiment-news"
        assert slim["internal_bias"] == "bearish"
        assert "risk faded" in slim["body"]
        assert slim["body"].endswith("...")
        assert "data_quality" not in slim
        assert "confidence" not in slim
        assert "material_findings" not in slim
        assert "bias" not in slim
        assert "headline" not in slim
        assert slim["sources"][0]["id"] == "fed"

    def test_truncates_and_prioritizes_under_budget(self) -> None:
        """Legacy JSON rows compose into a memo body; data_quality/confidence drop."""
        long_text = "x" * 500
        body = {
            "segment": "macro",
            "bias": "bullish",
            "headline": "Rates easing",
            "regime_label": "Risk-on / Policy easing",
            "data_quality": "high",
            "confidence": 0.7,
            "notes": long_text,
            "macro_summary": long_text,  # arbitrary extension prose — dropped
            "material_findings": [
                {"label": "Fed", "summary": long_text, "source_ids": ["s1", "s2", "s3", "s4"]},
                {"label": "CPI", "summary": "stable"},
            ],
            "sources": [
                {"id": f"s{i}", "title": f"Source {i}", "url": f"https://x/{i}"} for i in range(20)
            ],
            "nested_blob": {"should": "drop"},
        }
        budget = 5000
        slim = _slim_segment_body(body, budget)
        assert len(json.dumps(slim, default=str, sort_keys=True)) <= budget
        assert slim["segment"] == "macro"
        assert slim["internal_bias"] == "bullish"
        assert slim["regime_label"] == "Risk-on / Policy easing"
        assert "Rates easing" in slim["body"]
        assert "Fed" in slim["body"]
        assert "data_quality" not in slim
        assert "confidence" not in slim
        assert "material_findings" not in slim
        assert "macro_summary" not in slim
        assert "nested_blob" not in slim

    def test_tight_budget_keeps_headline_over_verbose_fields(self) -> None:
        """Under a tight budget, identity + memo body survive."""
        body = {
            "segment": "bonds",
            "bias": "bearish",
            "headline": "Curve steepening as the long end sells off",
            "notes": "y" * 400,
            "material_findings": [
                {"label": f"F{i}", "summary": "z" * 200, "source_ids": []} for i in range(8)
            ],
            "sources": [{"id": f"s{i}", "title": "t" * 80, "url": "u" * 80} for i in range(10)],
        }
        budget = _DIGEST_SEGMENT_MIN_CHARS  # the floor
        slim = _slim_segment_body(body, budget)
        assert len(json.dumps(slim, default=str, sort_keys=True)) <= budget
        assert slim["segment"] == "bonds"
        assert "Curve steepening" in slim["body"]
        assert "material_findings" not in slim
        assert "headline" not in slim


@pytest.mark.unit
class TestPhase7TodayOnlyInputs:
    def test_bodies_excludes_carried_segments(self) -> None:
        """``_bodies`` must drop carried slots — only today-source bodies feed the LLM."""
        bag = {
            "bonds": SegmentSlot(
                payload=SegmentPayload(
                    segment="bonds", body={"segment": "bonds"}, as_of=date(2026, 4, 26)
                )
            ),
            "commodities": _carried_slot("commodities"),
            "forex": _carried_slot("forex"),
        }
        out = _bodies(bag, 5000)
        assert set(out) == {"bonds"}, "carried segments must not appear in digest inputs"

    def test_delta_inputs_smaller_than_unfiltered(self) -> None:
        """A delta state with many carried segments → the dict passed to the Phase-7
        prompt is strictly smaller than the unfiltered slot bag (carried bodies dropped).
        """
        state = _seed_state_through_phase5()
        state.run_type = "delta"
        # Carry-forward most of phases 4 and 1 (delta-run baseline carries).
        state.phase4_outputs = {
            "bonds": state.phase4_outputs["bonds"],  # only this one is fresh
            "commodities": _carried_slot("commodities"),
            "forex": _carried_slot("forex"),
            "crypto": _carried_slot("crypto"),
            "international": _carried_slot("international"),
        }
        state.phase1_outputs = {
            "alt-sentiment-news": state.phase1_outputs["alt-sentiment-news"],
            "alt-cta-positioning": _carried_slot("alt-cta-positioning"),
            "alt-options-derivatives": _carried_slot("alt-options-derivatives"),
            "alt-politician-signals": _carried_slot("alt-politician-signals"),
        }

        compiled = build_pipeline(ResearchState, [build_phase6(), *build_phase7()])
        captured: list[dict[str, Any]] = []

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            for part in msgs[1]["content"]:
                if isinstance(part, dict) and part.get("text", "").startswith("PHASE_INPUTS"):
                    captured.append(json.loads(part["text"].split(":", 1)[1].strip()))
                    break
            return _fake_phase7_completion(_m, msgs)

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            compiled.invoke(state)

        assert captured, "LLM must have been called"
        asset = next(c for c in captured if c.get("subsection") == "asset-classes")
        alt = next(c for c in captured if c.get("subsection") == "alt-data")
        assert set(asset["phase4"]) == {"bonds"}
        assert len(asset["phase4"]) < len(state.phase4_outputs)
        assert set(alt["phase1"]) == {"alt-sentiment-news"}
        assert len(alt["phase1"]) < len(state.phase1_outputs)


# ─── Phase 7 strip trade verbs from actionable_summary (#927) ───────────────


@pytest.mark.unit
class TestPhase7StripTradeVerbs:
    def test_trade_verbs_rewritten_to_research_language(self) -> None:
        """Trade/allocation verbs in the briefing body are rewritten."""
        digest = DigestSnapshot.model_validate(
            {
                "segment": "master-digest",
                "date": "2026-04-26",
                "body": (
                    "Overweight semiconductors into earnings. "
                    "Add to AI exposure; reduce exposure to financials. "
                    "Rotate into defensives. Trim cyclicals and increase exposure to staples."
                ),
            }
        )
        stripped = _enforce_research_only_boundary(digest)
        lowered = stripped.body.lower()
        for verb in (
            "overweight",
            "underweight",
            "reduce exposure",
            "increase exposure",
            "add to",
            "trim",
            "rotate into",
        ):
            assert verb not in lowered, f"trade verb {verb!r} must be rewritten"

    def test_research_language_left_untouched(self) -> None:
        """Watchlist/research phrasing must pass through unchanged."""
        digest = DigestSnapshot.model_validate(
            {
                "segment": "master-digest",
                "date": "2026-04-26",
                "body": (
                    "## Watchlist\n\n"
                    "Watch semiconductor breadth. Monitor AI capex commentary into earnings."
                ),
            }
        )
        stripped = _enforce_research_only_boundary(digest)
        assert "Watch semiconductor breadth" in stripped.body
        assert "Monitor AI capex commentary into earnings." in stripped.body


# ─── H5 unified analyst tests ───────────────────────────────────────────────


def _analyst_payload(ticker: str) -> str:
    return json.dumps(
        {
            "ticker": ticker,
            "conviction_score": 2,
            "stance": "buy",
            "thesis": "Strong fundamentals",
            "risks": "macro headwinds",
            "sources": [],
        }
    )


@pytest.mark.unit
class TestH5AssetAnalysts:
    def test_per_ticker_fan_out(self) -> None:
        tickers = ["AAPL", "MSFT"]
        compiled = build_pipeline(
            ResearchState,
            [build_h5_asset_analyst(tickers)],
        )
        state = _seed_state_through_phase5()

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            return _analyst_payload(str(body["ticker"]))

        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=fake,
        ):
            result = compiled.invoke(state)
        final = ResearchState.model_validate(result) if isinstance(result, dict) else result

        assert set(final.phase_portfolio.asset_analysts.keys()) == {"AAPL", "MSFT"}
        for ticker in tickers:
            payload = AnalystPayload.model_validate(final.phase_portfolio.asset_analysts[ticker])
            assert payload.stance == "buy"
            assert payload.conviction_score >= 1

    def test_empty_watchlist_does_not_explode(self) -> None:
        compiled = build_pipeline(ResearchState, [build_h5_asset_analyst([])])
        state = _seed_state_through_phase5()
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=AssertionError("empty-watchlist node must not call LLM"),
        ):
            compiled.invoke(state)


# ─── Phase 7D tests ─────────────────────────────────────────────────────────


def _rebalance_payload() -> str:
    return json.dumps(
        {
            "recommended_portfolio": [
                {"ticker": "AAPL", "target_pct": 5.0},
                {"ticker": "MSFT", "target_pct": 5.0},
            ],
            "actions": [
                {
                    "ticker": "AAPL",
                    "action": "hold",
                    "current_pct": 5.0,
                    "target_pct": 5.0,
                    "rationale": "On target",
                }
            ],
            "notes": "Maintain defensive stance",
        }
    )


@pytest.mark.unit
class TestPhase7dPm:
    def test_rebalance_decision_produced(self) -> None:
        # build_phase7d returns three sub-phases (risk-aggressive →
        # risk-conservative → pm-rebalance) per #431. Spread them.
        compiled = build_pipeline(ResearchState, list(build_phase7d()))
        state = _seed_state_through_phase5()
        state.phase_portfolio = PhasePortfolioState(
            asset_analysts={
                "AAPL": {
                    "ticker": "AAPL",
                    "conviction_score": 2,
                    "stance": "buy",
                    "thesis": "x",
                    "risks": "",
                    "sources": [],
                }
            }
        )

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            schema_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")
            )
            schema_text = schema_part["text"]
            # Dispatch on the validated schema name in the prompt.
            if "RiskCase" in schema_text and "RiskDebateSummary" not in schema_text:
                return json.dumps({"case": "Aggressive case for the rebalance."})
            if "RiskDebateSummary" in schema_text:
                return json.dumps(
                    {
                        "aggressive_case": "Aggressive case for the rebalance.",
                        "conservative_case": "Conservative case warns of late-cycle risk.",
                        "key_tension": "Growth vs. drawdown.",
                    }
                )
            assert RebalanceDecision.__name__ in schema_text
            return _rebalance_payload()

        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=fake,
        ):
            result = compiled.invoke(state)
        final = ResearchState.model_validate(result) if isinstance(result, dict) else result

        reb = final.phase7d_rebalance
        assert reb is not None
        assert len(reb["recommended_portfolio"]) == 2
        assert reb["actions"][0]["action"] == "hold"
        # Risk debate must have populated both halves.
        debate = final.phase7d_risk_debate
        assert debate is not None
        assert debate["aggressive_case"] == "Aggressive case for the rebalance."
        assert "late-cycle" in debate["conservative_case"]
        assert debate["key_tension"] == "Growth vs. drawdown."


# ─── Phase 7 master-digest context budget (#1559) ───────────────────────────


_BUDGET_LONG = (
    "The regime is late-cycle with slowing growth and sticky core inflation; "
    "cross-asset signals conflict as rates volatility stays elevated. "
) * 6


def _verbose_segment_body(slug: str) -> dict[str, Any]:
    """An oversized, realistic segment body — 12 findings, 18 sources, long
    summaries + extension prose — so the budget slimmer must actually truncate."""
    return {
        "segment": slug,
        "date": "2026-07-12",
        "bias": "neutral",
        "headline": f"{slug}: mixed signals into the close " + _BUDGET_LONG[:120],
        "material_findings": [
            {
                "label": f"Finding {i} for {slug} with a fairly long descriptive label",
                "summary": _BUDGET_LONG,
                "source_ids": [f"{slug}-s{i}", f"{slug}-s{i}b", f"{slug}-s{i}c", f"{slug}-s{i}d"],
            }
            for i in range(12)
        ],
        "sources": [
            {
                "id": f"{slug}-s{i}",
                "title": f"Source {i} title for {slug} — a moderately long headline",
                "url": f"https://example.com/{slug}/article-number-{i}",
            }
            for i in range(18)
        ],
        "body": f"# {slug} — 2026-07-12\n\n" + _BUDGET_LONG * 4,
        "notes": _BUDGET_LONG,
        "data_quality": "medium",
        "confidence": 0.55,
        # Extension prose the digest does not synthesize from — must be dropped.
        "detailed_analysis": _BUDGET_LONG,
        "outlook": _BUDGET_LONG,
        "key_levels": _BUDGET_LONG,
        "catalysts": _BUDGET_LONG,
    }


def _verbose_slot(slug: str) -> SegmentSlot:
    return SegmentSlot(
        payload=SegmentPayload(
            segment=slug, body=_verbose_segment_body(slug), as_of=date(2026, 7, 12)
        )
    )


def _full_baseline_state(sector_count: int) -> ResearchState:
    """A full baseline day: every phase-1..5 segment fresh and verbose, plus a
    fat prior context (a full prior digest + every prior segment carried)."""
    phase1 = [
        "alt-sentiment-news",
        "alt-cta-positioning",
        "alt-options-derivatives",
        "alt-politician-signals",
        "alt-onchain-positioning",
        "alt-ai-portfolios",
    ]
    phase2 = ["inst-institutional-flows", "inst-hedge-fund-intel"]
    phase4 = ["bonds", "commodities", "forex", "crypto", "international"]
    phase5 = ["equity", *[f"sector-{i}" for i in range(sector_count)]]
    all_slugs = phase1 + phase2 + ["macro"] + phase4 + phase5

    latest_segments: dict[str, Any] = {
        slug: {
            "date": "2026-07-05",
            "document_key": slug,
            "doc_type": None,
            "payload": _verbose_segment_body(slug),
        }
        for slug in all_slugs
    }
    # A full prior digest under both digest keys (the residual after filtering).
    prior_digest = dict(_verbose_segment_body("master-digest"))
    prior_digest["segment_freshness"] = {
        s: {"source": "today", "as_of": "2026-07-05"} for s in all_slugs
    }
    prior_digest["market_regime_snapshot"] = _BUDGET_LONG
    prior_digest["us_equities_summary"] = _BUDGET_LONG
    for key in ("digest", "digest-delta"):
        latest_segments[key] = {
            "date": "2026-07-05",
            "document_key": key,
            "doc_type": "Daily Digest",
            "payload": prior_digest,
        }

    state = ResearchState(
        run_type="baseline",
        run_date=date(2026, 7, 12),
        baseline_date=date(2026, 7, 5),
        config=ResearchConfigBundle(watchlist=["AAPL", "MSFT", "NVDA"]),
        prior_context=PriorContext(latest_segments=latest_segments),
        phase1_outputs={s: _verbose_slot(s) for s in phase1},
        phase2_outputs={s: _verbose_slot(s) for s in phase2},
        phase3_output=_verbose_slot("macro"),
        phase4_outputs={s: _verbose_slot(s) for s in phase4},
        phase5_outputs={s: _verbose_slot(s) for s in phase5},
    )
    return state


@pytest.mark.unit
class TestDigestInputBudget:
    def _assembled_tokens(self, state: ResearchState) -> float:
        """Serialized prompt size in tokens, mirroring research_agent's assembly:
        SHARED_CONTEXT + skill + PHASE_INPUTS + OUTPUT_SCHEMA."""
        phase_inputs = _digest_phase_inputs(state)
        shared = _digest_shared_context(state)
        total_chars = (
            len(json.dumps(shared, default=str, sort_keys=True))
            + len(load_skill("digest"))
            + len(json.dumps(phase_inputs, default=str, sort_keys=True))
            + len(json.dumps(DigestSnapshot.model_json_schema(), sort_keys=True))
        )
        # Pessimistic chars-per-token (matches the module's conservative ratio) so
        # the assertion holds even when the real tokenizer packs fewer chars/token.
        return total_chars / 3.0

    def test_full_baseline_roster_fits_under_model_context(self) -> None:
        """A verbose full-roster baseline (~27 segments) assembles well under the
        64k model context, leaving completion headroom (#1559)."""
        state = _full_baseline_state(sector_count=20)  # 6+2+1+5+1+20 = 35 segments
        assert _count_today_segments(state) >= 27
        est_tokens = self._assembled_tokens(state)
        # Under the 64k ceiling with an ~8k completion reserve.
        assert est_tokens < _DIGEST_MODEL_CONTEXT_TOKENS - 8_000, (
            f"assembled digest prompt ~{est_tokens:.0f} tok exceeds budget"
        )

    def test_budget_adapts_to_larger_roster(self) -> None:
        """Doubling the sector roster must NOT double the prompt — the per-segment
        allowance shrinks so the aggregate stays bounded (#1559)."""
        small = self._assembled_tokens(_full_baseline_state(sector_count=20))
        large = self._assembled_tokens(_full_baseline_state(sector_count=60))
        assert large < _DIGEST_MODEL_CONTEXT_TOKENS - 8_000
        # Not proportional to segment count: 3x the sectors is far from 3x the prompt.
        assert large < small * 1.5

    def test_slimming_actually_truncates_oversized_bodies(self) -> None:
        """Guard against a vacuous budget pass: verbose bodies are genuinely
        truncated and extension prose is dropped in the assembled inputs."""
        state = _full_baseline_state(sector_count=20)
        phase_inputs = _subsection_phase_inputs("us-equities", state)
        body = phase_inputs["phase5"]["sector-0"]["body"]
        # WP-C: the markdown memo is the digest input; JSON findings/slots are dropped.
        assert isinstance(body.get("body"), str) and body["body"].strip()
        assert body["body"].endswith("...")
        assert "material_findings" not in body
        assert "headline" not in body
        # Arbitrary extension prose is dropped, not synthesized from.
        assert "detailed_analysis" not in body
        assert "outlook" not in body
        # Each segment body stays within its adaptive per-segment allowance.
        budget = _per_segment_char_budget(_count_today_segments(state))
        assert len(json.dumps(body, default=str, sort_keys=True)) <= budget

    def test_shared_context_prior_carry_is_bounded(self) -> None:
        """The prior per-segment dump (the dominant overflow driver) is filtered to
        the digest keys and the retained digests are trimmed (#1559)."""
        state = _full_baseline_state(sector_count=20)
        shared = _digest_shared_context(state)
        latest = shared["prior_context"]["latest_segments"]
        # Only the digest keys survive — not the 20+ prior per-segment payloads.
        assert set(latest) <= {"digest", "digest-delta"}
        # Retained prior-digest payloads are trimmed (no fat segment_freshness map).
        for row in latest.values():
            assert "segment_freshness" not in row["payload"]


# ─── Phase 7 master-digest failure visibility (#1559) ────────────────────────


def _valid_prior_digest(day: str) -> dict[str, Any]:
    payload = json.loads(_digest_payload())
    payload["date"] = day
    payload["body"] = (
        f"# Daily Digest — {day}\n\n## Headline\n\nPrior-day headline\n\n"
        "## Market regime\n\nGrowth slowing\n"
    )
    return payload


@pytest.mark.unit
class TestDigestFailureVisibility:
    def test_synthesis_failure_carries_prior_and_marks_degraded(self) -> None:
        """A master-digest synthesis exception carries the prior digest forward
        STAMPED with provenance, and the run is degraded with the failure leading
        the error summary — not a silent 'ok' with a stale headline (#1559)."""
        state = _seed_state_through_phase5()  # baseline, fresh phases 1-5
        state.baseline_date = date(2026, 4, 25)
        # Force the full-rewrite path so the (patched, failing) LLM call is reached.
        state.refresh_scope = "digest"
        state.prior_context = PriorContext(
            latest_segments={
                "digest": {
                    "date": "2026-04-25",
                    "document_key": "digest",
                    "doc_type": "Daily Digest",
                    "payload": _valid_prior_digest("2026-04-25"),
                }
            }
        )
        compiled = build_pipeline(ResearchState, [build_phase6(), *build_phase7()])

        overflow = RuntimeError(
            "BadRequestError 400: endpoint maximum context length is 64000 tokens, requested ~90690"
        )
        with patch(
            "digiquant.research.phases.phase7_synthesis.run_research_agent",
            side_effect=overflow,
        ):
            final = ResearchState.model_validate(compiled.invoke(state))

        digest = final.phase7_digest
        assert digest is not None, "must carry the prior digest forward, not crash"
        # Carried-forward provenance stamped on the payload.
        assert digest["carried_from"] == "2026-04-25"
        assert "carried_forward" in digest["continuity"]
        assert "Prior-day headline" in digest["body"]

        # The run is degraded (not 'ok'), and the failure LEADS the error summary.
        summary = diagnostics.summarize_run(final)
        assert summary.status == "degraded"
        assert summary.error_summary.startswith("MASTER-DIGEST SYNTHESIS FAILED")
        assert "master_digest_failed" in summary.breakdown
        assert diagnostics.is_degraded(final) is True

    def test_successful_synthesis_has_no_carried_marker(self) -> None:
        """A fresh synthesis must NOT carry a provenance marker — the marker is the
        signal that distinguishes carried-forward from fresh (#1559)."""
        compiled = build_pipeline(ResearchState, [build_phase6(), *build_phase7()])
        state = _seed_state_through_phase5()

        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=_fake_phase7_completion,
        ):
            final = ResearchState.model_validate(compiled.invoke(state))

        digest = final.phase7_digest
        assert digest is not None
        assert not digest.get("carried_from"), "fresh synthesis must not be marked carried"
        # This asserted a global ``status == "ok"`` until #1736. It cannot any more: the
        # fixture is research-only, so it commits no book and the no-book gate degrades it. The
        # claim under test is *digest* health, so assert that directly — the synthesis left
        # no failure marker and no error behind.
        summary = diagnostics.summarize_run(final)
        assert "master_digest_failed" not in summary.breakdown
        assert summary.error_summary == ""
        assert summary.breakdown["degraded_reasons"] == ["no_committed_book"]
