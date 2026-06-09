"""Integration tests for Phase 5 — US equity + 11-sector swarm + scorecard."""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — used for fake-completion dict shape
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.atlas.phases.phase5_equities import (
    EquityOverviewReport,
    SectorReport,
    build_phase5,
    build_phase5_equity,
    build_phase5_scorecard,
    build_phase5_sectors,
)
from digiquant.olympus.atlas.sectors_config import load_sectors
from digiquant.olympus.atlas.state import AtlasResearchState, SegmentPayload, SegmentSlot


def _equity_payload() -> str:
    return json.dumps(
        {
            "segment": "equity",
            "date": "2026-04-26",
            "bias": "neutral",
            "headline": "Consolidating near all-time highs",
            "material_findings": [],
            "sources": [],
            "notes": "",
            "spy_trend": "neutral",
            "market_breadth": "narrow",
            "factor_leader": "growth",
        }
    )


def _sector_payload(slug: str, bias: str = "bullish") -> str:
    return json.dumps(
        {
            "segment": slug,
            "date": "2026-04-26",
            "bias": bias,
            "headline": f"{slug}: test headline",
            "material_findings": [],
            "sources": [],
            "notes": "",
            "relative_strength_vs_spy": "outperforming",
            "sub_segment_leader": None,
            "driver_confirmation_count": 2,
            "conviction": "medium",
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
    inputs_part = next(
        (
            p
            for p in user_block
            if isinstance(p, dict) and p.get("text", "").startswith("PHASE_INPUTS")
        ),
        None,
    )
    if EquityOverviewReport.__name__ in text:
        return _equity_payload()
    if SectorReport.__name__ in text:
        # Pull the sector slug out of PHASE_INPUTS → sector_config → slug.
        slug = "sector-unknown"
        if inputs_part is not None:
            try:
                body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
                slug = body.get("sector_config", {}).get("slug", slug)
            except (ValueError, json.JSONDecodeError):
                pass
        return _sector_payload(slug)
    raise AssertionError("unrecognized output schema in dispatch")


def _seed_state_through_phase4() -> AtlasResearchState:
    """Build state with macro + phase1 + phase4 populated so Phase 5 has inputs."""
    state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
    state.phase3_output = SegmentSlot(
        payload=SegmentPayload(
            segment="macro",
            body={"regime_label": "Slowing / Cooling / Neutral / Mixed"},
            as_of=date(2026, 4, 26),
        )
    )
    return state


@pytest.mark.unit
class TestSectorsYaml:
    def test_loads_eleven_sectors(self) -> None:
        sectors = load_sectors()
        assert len(sectors) == 11
        slugs = {s.slug for s in sectors}
        assert "sector-technology" in slugs
        assert "sector-comms" in slugs

    def test_each_sector_has_required_fields(self) -> None:
        for s in load_sectors():
            assert s.slug.startswith("sector-")
            assert s.name
            assert s.etfs, f"{s.slug} must have at least one ETF"
            assert s.top_tickers, f"{s.slug} must have at least one top ticker"
            assert s.key_drivers, f"{s.slug} must have at least one key driver"


@pytest.mark.unit
class TestPhase5Topology:
    def test_equity_then_eleven_sectors_then_scorecard(self) -> None:
        compiled = build_pipeline(
            AtlasResearchState,
            [build_phase5_equity(), build_phase5_sectors(), build_phase5_scorecard()],
        )
        state = _seed_state_through_phase4()
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=_dispatch,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        # Equity slot + 11 sector slots + scorecard = 13 entries.
        assert "equity" in final.phase5_outputs
        sector_slugs = {
            k for k in final.phase5_outputs if k.startswith("sector-") and k != "sector-scorecard"
        }
        assert len(sector_slugs) == 11
        assert "sector-scorecard" in final.phase5_outputs

    def test_scorecard_aggregates_sector_biases(self) -> None:
        compiled = build_pipeline(AtlasResearchState, build_phase5())
        state = _seed_state_through_phase4()
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=_dispatch,
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        scorecard = final.phase5_outputs["sector-scorecard"].payload.body  # type: ignore[union-attr]
        assert len(scorecard["rows"]) == 11
        # All sectors returned "bullish" → scorecard aggregate should be bullish.
        assert scorecard["bias"] == "bullish"
        # Every row carries an ETF and a stance.
        for row in scorecard["rows"]:
            assert row["etf"]
            assert row["stance"] in {"overweight", "underweight", "neutral"}

    def test_sector_nodes_receive_sector_config_in_phase_inputs(self) -> None:
        """Pin the templated-skill contract: each sector call sees its own
        sector_config in phase_inputs."""
        received_slugs: list[str] = []

        def capture(_model: str, messages: list[dict[str, Any]], **_: Any) -> str:
            user_block = messages[1]["content"]
            inputs_part = next(
                (
                    p
                    for p in user_block
                    if isinstance(p, dict) and p.get("text", "").startswith("PHASE_INPUTS")
                ),
                None,
            )
            if inputs_part is not None:
                try:
                    body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
                    slug = body.get("sector_config", {}).get("slug")
                    if slug:
                        received_slugs.append(slug)
                except (ValueError, json.JSONDecodeError):
                    pass
            return _dispatch(_model, messages)

        compiled = build_pipeline(AtlasResearchState, build_phase5())
        state = _seed_state_through_phase4()
        with patch(
            "digigraph.graph.research_agent.completion_text",
            side_effect=capture,
        ):
            compiled.invoke(state)

        assert set(received_slugs) == {s.slug for s in load_sectors()}


@pytest.mark.unit
class TestAggregateBias:
    """Boundary tests for the scorecard → portfolio-level bias reduction."""

    def _row(self, stance: str):
        from digiquant.olympus.atlas.phases.phase5_equities import SectorScorecardEntry

        return SectorScorecardEntry(
            segment="sector-x",
            date=date(2026, 4, 26),
            bias="neutral",
            headline="",
            etf="ETF",
            stance=stance,  # type: ignore[arg-type]
            key_driver="",
            material_findings=[],
            sources=[],
            notes="",
        )

    def test_empty_is_mixed(self) -> None:
        from digiquant.olympus.atlas.phases.phase5_equities import _aggregate_bias

        assert _aggregate_bias([]) == "mixed"

    def test_all_neutral_is_neutral(self) -> None:
        from digiquant.olympus.atlas.phases.phase5_equities import _aggregate_bias

        rows = [self._row("neutral")] * 11
        assert _aggregate_bias(rows) == "neutral"

    def test_strong_overweight_majority_is_bullish(self) -> None:
        from digiquant.olympus.atlas.phases.phase5_equities import _aggregate_bias

        rows = [self._row("overweight")] * 7 + [self._row("underweight")] * 2
        assert _aggregate_bias(rows) == "bullish"

    def test_strong_underweight_majority_is_bearish(self) -> None:
        from digiquant.olympus.atlas.phases.phase5_equities import _aggregate_bias

        rows = [self._row("overweight")] * 2 + [self._row("underweight")] * 7
        assert _aggregate_bias(rows) == "bearish"

    def test_tug_of_war_is_mixed(self) -> None:
        from digiquant.olympus.atlas.phases.phase5_equities import _aggregate_bias

        rows = (
            [self._row("overweight")] * 5 + [self._row("underweight")] * 5 + [self._row("neutral")]
        )
        assert _aggregate_bias(rows) == "mixed"
