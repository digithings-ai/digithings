"""Integration tests for Phase 3 macro + Phase 4 asset classes."""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — used for fake-completion dict shape
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.atlas.phases.phase3_macro import MacroRegimeReport, build_phase3
from digiquant.olympus.atlas.phases.phase4_assetclass import (
    BondsReport,
    CommoditiesReport,
    CryptoReport,
    ForexReport,
    InternationalReport,
    build_phase4,
)
from digiquant.olympus.atlas.state import AtlasResearchState


def _macro_payload() -> str:
    return json.dumps(
        {
            "segment": "macro",
            "date": "2026-04-26",
            "bias": "neutral",
            "headline": "Late-cycle consolidation",
            "material_findings": [],
            "sources": [],
            "notes": "",
            "growth": "slowing",
            "inflation": "cooling",
            "policy": "neutral",
            "risk_appetite": "mixed",
            "regime_label": "Slowing / Cooling / Neutral / Mixed",
            "portfolio_implications": "",
        }
    )


def _asset_class_payload() -> str:
    return json.dumps(
        {
            "segment": "test",
            "date": "2026-04-26",
            "bias": "neutral",
            "headline": "Range-bound",
            "material_findings": [],
            "sources": [],
            "notes": "",
        }
    )


def _dispatch(_model: str, messages: list[dict[str, Any]], **_: Any) -> str:
    user_block = messages[1]["content"]
    schema_part = next(
        (p for p in user_block if isinstance(p, dict) and "OUTPUT_SCHEMA" in p.get("text", "")),
        None,
    )
    assert schema_part is not None
    text = schema_part["text"]
    if MacroRegimeReport.__name__ in text:
        return _macro_payload()
    for cls in (BondsReport, CommoditiesReport, ForexReport, CryptoReport, InternationalReport):
        if cls.__name__ in text:
            return _asset_class_payload()
    raise AssertionError("unrecognized output schema in dispatch")


@pytest.mark.unit
class TestPhase3Macro:
    def test_single_node_produces_regime(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase3()])
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=_dispatch,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result
        assert final.phase3_output is not None
        assert final.phase3_output.payload.source == "today"
        assert final.phase3_output.payload.body["regime_label"].startswith("Slowing")


@pytest.mark.unit
class TestPhase4AssetClasses:
    def test_five_way_fan_out(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase3(), build_phase4()])
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=_dispatch,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result
        assert set(final.phase4_outputs.keys()) == {
            "bonds",
            "commodities",
            "forex",
            "crypto",
            "international",
        }

    def test_asset_class_nodes_receive_macro_regime(self) -> None:
        """Asset-class nodes must pass phase3 output into the LLM's phase_inputs."""
        received_inputs: list[dict[str, Any]] = []

        def capture(_model: str, messages: list[dict[str, Any]], **_: Any) -> str:
            user_block = messages[1]["content"]
            inputs_part = next(
                (
                    p
                    for p in user_block
                    if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
                ),
                None,
            )
            if inputs_part is not None:
                try:
                    text = inputs_part["text"].split(":", 1)[1].strip()
                    received_inputs.append(json.loads(text))
                except (ValueError, json.JSONDecodeError):
                    pass
            return _dispatch(_model, messages)

        compiled = build_pipeline(AtlasResearchState, [build_phase3(), build_phase4()])
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=capture,
        ):
            compiled.invoke(state)

        # Skip the macro call itself; assert every subsequent asset-class call
        # received the macro regime in its phase_inputs.
        asset_class_calls = [
            inp
            for inp in received_inputs
            if inp.get("segment") in {"bonds", "commodities", "forex", "crypto", "international"}
        ]
        assert len(asset_class_calls) == 5
        for inp in asset_class_calls:
            assert inp.get("macro_regime", {}).get("regime_label", "").startswith("Slowing")
