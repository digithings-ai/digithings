"""Segment edit-mode pilot tests (Olympus #930 slice A2 — macro)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any  # noqa  # scored-lint: heterogeneous fake-row / fixture dicts
from unittest.mock import patch

import pytest

from digiquant.olympus.edit_mode import DocumentPatch, PatchOp
from digiquant.olympus.atlas.phases._node_factory import (
    SegmentNodeSpec,
    build_segment_node,
    scalar_slot_write_adapter,
)
from digiquant.olympus.atlas.phases.phase3_macro import MacroRegimeReport
from digiquant.olympus.atlas.phases.phase5_equities import EquityOverviewReport
from digiquant.olympus.atlas.skills import SkillNotFoundError, load_skill_edit
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    Carried,
    DeltaTriageDecision,
    DeltaTriageResult,
    PriorContext,
    SegmentPayload,
)
from digiquant.olympus.atlas.triage import evaluate
from tests.dq.atlas.test_triage_monthly_phase9 import _delta_state, _quiet_bias_for_all_segments

_ATLAS_EDIT_SKILL_SLUGS = (
    "macro",
    "digest",
    "equity",
    "sector-research",
    "bonds",
    "commodities",
    "forex",
    "crypto",
    "international",
    "alt-sentiment-news",
    "alt-cta-positioning",
    "alt-options-derivatives",
    "alt-politician-signals",
    "alt-onchain-positioning",
    "alt-ai-portfolios",
    "inst-institutional-flows",
    "inst-hedge-fund-intel",
)


def _macro_prior_body() -> dict[str, Any]:
    return {
        "segment": "macro",
        "date": "2026-04-26",
        "bias": "neutral",
        "headline": "prior macro headline",
        "material_findings": [],
        "sources": [],
        "notes": "",
        "growth": "slowing",
        "inflation": "cooling",
        "policy": "neutral",
        "risk_appetite": "mixed",
        "regime_label": "Prior / Mixed / Neutral / Mixed",
        "portfolio_implications": "prior implications",
    }


def _macro_state_with_prior(
    *,
    run_date: date = date(2026, 4, 27),
    baseline_date: date = date(2026, 4, 26),
    triage_decision: str = "regenerate",
) -> AtlasResearchState:
    state = _delta_state(
        run_date,
        baseline_date,
        bias_by_segment=_quiet_bias_for_all_segments(),
        price_deltas={"TLT": 0.001, "IEF": 0.001, "SHY": 0.001},
    )
    state = state.model_copy(
        update={
            "prior_context": PriorContext(
                last_snapshots=state.prior_context.last_snapshots,
                latest_segments={
                    "macro": {
                        "date": baseline_date.isoformat(),
                        "document_key": "macro",
                        "doc_type": "Macro Regime",
                        "payload": _macro_prior_body(),
                    }
                },
            ),
            "triage": DeltaTriageResult(
                evaluated_at=run_date,
                baseline_date=baseline_date,
                decisions=[
                    DeltaTriageDecision(
                        segment="macro",
                        decision=triage_decision,  # type: ignore[arg-type]
                        reason="mandatory_tier" if triage_decision == "regenerate" else "price_quiet",
                        tier="mandatory",
                    )
                ],
            ),
        }
    )
    return state


@pytest.mark.unit
class TestMacroEditSkill:
    def test_load_skill_edit_returns_macro_edit_body(self) -> None:
        body = load_skill_edit("macro")
        assert body
        assert "DocumentPatch" in body or "document_delta" in body.lower()

    @pytest.mark.parametrize("slug", _ATLAS_EDIT_SKILL_SLUGS)
    def test_all_segment_edit_skills_exist(self, slug: str) -> None:
        body = load_skill_edit(slug)
        assert body
        assert "DocumentPatch" in body
        edit_path = (
            Path(__file__).resolve().parents[3]
            / "digiquant/src/digiquant/olympus/atlas/skills"
            / slug
            / f"{slug}-edit.md"
        )
        assert edit_path.is_file(), f"missing edit skill file: {edit_path}"


@pytest.mark.unit
class TestBuildSegmentNodeEditMode:
    def test_skip_emits_carried_without_llm(self) -> None:
        state = _macro_state_with_prior(triage_decision="carry")
        spec = SegmentNodeSpec(
            segment_slug="macro",
            skill_slug="macro",
            output_model=MacroRegimeReport,
            phase_outputs_field="phase3_output",
        )
        node = build_segment_node(spec, write_adapter=scalar_slot_write_adapter)

        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=AssertionError("skip mode must not call LLM"),
        ):
            out = node(state)

        slot = out["phase3_output"]
        assert isinstance(slot.payload, Carried)
        assert slot.payload.baseline_date == date(2026, 4, 26)

    def test_edit_merges_document_patch_into_prior(self) -> None:
        state = _macro_state_with_prior(triage_decision="regenerate")
        spec = SegmentNodeSpec(
            segment_slug="macro",
            skill_slug="macro",
            output_model=MacroRegimeReport,
            phase_outputs_field="phase3_output",
        )
        node = build_segment_node(spec, write_adapter=scalar_slot_write_adapter)

        patch_body = DocumentPatch(
            schema_version="1.0",
            date=date(2026, 4, 27),
            prior_date=date(2026, 4, 26),
            target_document_key="macro",
            status="updated",
            ops=[
                PatchOp(
                    op="set",
                    path="/regime_label",
                    value="Edited / Cooling / Neutral / Mixed",
                    reason="policy shift",
                )
            ],
        )

        with patch(
            "digiquant.olympus.atlas.phases._node_factory.run_research_agent",
            return_value=patch_body,
        ) as mock_run:
            out = node(state)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert "edit" in call_kwargs["skill_text"].lower() or "patch" in call_kwargs["skill_text"].lower()
        assert call_kwargs["output_model"] is DocumentPatch
        assert "prior_document" in call_kwargs["phase_inputs"]

        slot = out["phase3_output"]
        assert isinstance(slot.payload, SegmentPayload)
        assert slot.payload.body["regime_label"] == "Edited / Cooling / Neutral / Mixed"
        assert slot.payload.body["headline"] == "prior macro headline"
        MacroRegimeReport.model_validate(slot.payload.body)

    def test_full_runs_when_no_prior_exists(self) -> None:
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 4, 27),
            baseline_date=date(2026, 4, 26),
            triage=DeltaTriageResult(
                evaluated_at=date(2026, 4, 27),
                baseline_date=date(2026, 4, 26),
                decisions=list(evaluate(_delta_state(date(2026, 4, 27), date(2026, 4, 26))).decisions),
            ),
        )
        spec = SegmentNodeSpec(
            segment_slug="macro",
            skill_slug="macro",
            output_model=MacroRegimeReport,
            phase_outputs_field="phase3_output",
        )
        node = build_segment_node(spec, write_adapter=scalar_slot_write_adapter)

        full_body = MacroRegimeReport(
            segment="macro",
            date=date(2026, 4, 27),
            bias="neutral",
            headline="fresh macro",
            growth="expanding",
            inflation="cooling",
            policy="neutral",
            risk_appetite="risk_on",
            regime_label="Fresh regime",
        )

        with patch(
            "digiquant.olympus.atlas.phases._node_factory.run_research_agent",
            return_value=full_body,
        ) as mock_run:
            out = node(state)

        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["output_model"] is MacroRegimeReport
        slot = out["phase3_output"]
        assert slot.payload.body["headline"] == "fresh macro"


@pytest.mark.unit
class TestSegmentEditE2EPilot:
    def test_macro_mandatory_regenerate_resolves_edit_with_prior(self) -> None:
        """Pilot: mandatory macro + prior → edit mode (not full regen)."""
        state = _macro_state_with_prior()
        macro_decision = next(d for d in state.triage.decisions if d.segment == "macro")
        assert macro_decision.decision == "regenerate"

        spec = SegmentNodeSpec(
            segment_slug="macro",
            skill_slug="macro",
            output_model=MacroRegimeReport,
            phase_outputs_field="phase3_output",
        )

        patch_body = DocumentPatch(
            schema_version="1.0",
            date=date(2026, 4, 27),
            prior_date=date(2026, 4, 26),
            target_document_key="macro",
            status="updated",
            ops=[PatchOp(op="set", path="/growth", value="contracting", reason="data shift")],
        )

        with patch(
            "digiquant.olympus.atlas.phases._node_factory.run_research_agent",
            return_value=patch_body,
        ):
            out = build_segment_node(spec, write_adapter=scalar_slot_write_adapter)(state)

        body = out["phase3_output"].payload.body
        assert body["growth"] == "contracting"
        assert body["regime_label"] == "Prior / Mixed / Neutral / Mixed"


def _equity_prior_body() -> dict[str, Any]:
    return {
        "segment": "equity",
        "date": "2026-04-26",
        "bias": "neutral",
        "headline": "prior equity headline",
        "material_findings": [],
        "sources": [],
        "notes": "",
        "spy_trend": "neutral",
        "market_breadth": "mixed",
        "factor_leader": "growth",
    }


def _equity_state_with_prior(*, triage_decision: str = "regenerate") -> AtlasResearchState:
    state = _delta_state(
        date(2026, 4, 27),
        date(2026, 4, 26),
        bias_by_segment=_quiet_bias_for_all_segments(),
    )
    return state.model_copy(
        update={
            "prior_context": PriorContext(
                last_snapshots=state.prior_context.last_snapshots,
                latest_segments={
                    "equity": {
                        "date": "2026-04-26",
                        "document_key": "equity",
                        "doc_type": "Equity Overview",
                        "payload": _equity_prior_body(),
                    }
                },
            ),
            "triage": DeltaTriageResult(
                evaluated_at=date(2026, 4, 27),
                baseline_date=date(2026, 4, 26),
                decisions=[
                    DeltaTriageDecision(
                        segment="equity",
                        decision=triage_decision,  # type: ignore[arg-type]
                        reason="mandatory_tier" if triage_decision == "regenerate" else "price_quiet",
                        tier="mandatory",
                    )
                ],
            ),
        }
    )


@pytest.mark.unit
class TestEquityEditMode:
    def test_equity_edit_merges_document_patch(self) -> None:
        state = _equity_state_with_prior()
        spec = SegmentNodeSpec(
            segment_slug="equity",
            skill_slug="equity",
            output_model=EquityOverviewReport,
            phase_outputs_field="phase5_outputs",
            use_data_tools=True,
            extra_context_keys=("macro",),
        )
        patch_body = DocumentPatch(
            schema_version="1.0",
            date=date(2026, 4, 27),
            prior_date=date(2026, 4, 26),
            target_document_key="equity",
            status="updated",
            ops=[
                PatchOp(
                    op="set",
                    path="/spy_trend",
                    value="bullish",
                    reason="SPY broke above SMA50",
                )
            ],
        )

        with patch(
            "digiquant.olympus.atlas.phases._node_factory.run_research_agent",
            return_value=patch_body,
        ) as mock_run:
            out = build_segment_node(spec)(state)

        assert mock_run.call_args.kwargs["output_model"] is DocumentPatch
        slot = out["phase5_outputs"]["equity"]
        assert isinstance(slot.payload, SegmentPayload)
        assert slot.payload.body["spy_trend"] == "bullish"
        assert slot.payload.body["headline"] == "prior equity headline"
        EquityOverviewReport.model_validate(slot.payload.body)

    def test_missing_edit_skill_raises(self) -> None:
        with pytest.raises(SkillNotFoundError):
            load_skill_edit("nonexistent-segment-slug")
