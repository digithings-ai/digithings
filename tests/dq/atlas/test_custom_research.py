"""Custom research trigger tests (#313).

Covers:
- ``AtlasInput`` carries ``custom_prompt``.
- CLI parses ``--custom-prompt`` and threads it into ``AtlasInput``.
- ``AtlasResearchState.custom_prompt`` is populated by ``initial_state``.
- Phase 7 synthesis adds ``custom_prompt`` to ``phase_inputs`` when set,
  and omits it on routine runs.
- Publish phase routes the digest under ``doc_type='Custom Research'``
  + ``document_key='custom-research/<run_id>'`` for custom runs.
- Publish phase skips ``daily_snapshots`` for custom runs.
- Routine runs (custom_prompt=None) keep the standard
  ``Daily Digest`` / ``digest`` keys untouched.
"""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa: F401 — used for fake-payload dict shape
from unittest.mock import patch
from uuid import UUID

import pytest

from digiquant.olympus.atlas.graph import (
    AtlasInput,
    build_cli_parser,
    initial_state,
    resolve_cli_inputs,
)
from digiquant.olympus.atlas.phases.publish_phase import PublishDeps, build_publish_node
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    Carried,  # noqa: F401 — re-export check
    SegmentPayload,
    SegmentSlot,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


# ─── AtlasInput + CLI parser ────────────────────────────────────────────────


@pytest.mark.unit
class TestAtlasInputCustomPrompt:
    def test_default_is_none(self) -> None:
        inp = AtlasInput(run_type="baseline", run_date=date(2026, 4, 26))
        assert inp.custom_prompt is None

    def test_explicit_prompt_propagates(self) -> None:
        inp = AtlasInput(
            run_type="baseline",
            run_date=date(2026, 4, 26),
            custom_prompt="Drill into NVDA earnings risk.",
        )
        assert inp.custom_prompt == "Drill into NVDA earnings risk."


@pytest.mark.unit
class TestCustomPromptCli:
    def test_cli_flag_default_yields_none(self) -> None:
        parser = build_cli_parser()
        args = parser.parse_args(["--run-type", "baseline", "--run-date", "2026-04-26"])
        kwargs = resolve_cli_inputs(args)
        assert kwargs["custom_prompt"] is None

    def test_cli_flag_set_threads_through(self) -> None:
        parser = build_cli_parser()
        args = parser.parse_args(
            [
                "--run-type",
                "baseline",
                "--run-date",
                "2026-04-26",
                "--custom-prompt",
                "Why is XLE underperforming?",
            ]
        )
        kwargs = resolve_cli_inputs(args)
        assert kwargs["custom_prompt"] == "Why is XLE underperforming?"

    def test_empty_prompt_normalized_to_none(self) -> None:
        """``--custom-prompt ""`` and stray whitespace must collapse to ``None``."""
        parser = build_cli_parser()
        args = parser.parse_args(
            [
                "--run-type",
                "baseline",
                "--run-date",
                "2026-04-26",
                "--custom-prompt",
                "   ",
            ]
        )
        kwargs = resolve_cli_inputs(args)
        assert kwargs["custom_prompt"] is None


# ─── initial_state ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestInitialStateCustomPrompt:
    def test_state_carries_custom_prompt(self) -> None:
        inp = AtlasInput(
            run_type="baseline",
            run_date=date(2026, 4, 26),
            custom_prompt="Hot take on small caps?",
        )
        state = initial_state(inp)
        assert state.custom_prompt == "Hot take on small caps?"

    def test_state_default_custom_prompt_is_none(self) -> None:
        inp = AtlasInput(run_type="baseline", run_date=date(2026, 4, 26))
        state = initial_state(inp)
        assert state.custom_prompt is None


# ─── Phase 7 synthesis input threading ──────────────────────────────────────


def _seed_state_minimal(custom_prompt: str | None = None) -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
    )
    if custom_prompt is not None:
        state.custom_prompt = custom_prompt

    def _slot(slug: str) -> SegmentSlot:
        return SegmentSlot(
            payload=SegmentPayload(
                segment=slug,
                body={"segment": slug, "bias": "neutral"},
                as_of=date(2026, 4, 26),
            )
        )

    state.phase1_outputs = {"alt-sentiment-news": _slot("alt-sentiment-news")}
    state.phase3_output = _slot("macro")
    state.phase5_outputs = {"equity": _slot("equity")}
    state.phase6_bias_row = {"date": "2026-04-26"}
    return state


@pytest.mark.unit
class TestPhase7SynthesisCustomPrompt:
    def test_custom_prompt_added_to_phase_inputs_when_set(self) -> None:
        from digiquant.olympus.atlas.phases.phase7_synthesis import _synthesis_node

        captured: dict[str, str] = {}

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            captured["text"] = inputs_part["text"]
            # Return a minimal valid DigestSnapshot.
            import json

            return json.dumps(
                {
                    "segment": "master-digest",
                    "date": "2026-04-26",
                    "bias": "neutral",
                    "headline": "test",
                    "material_findings": [],
                    "sources": [],
                    "notes": "",
                    "market_regime_snapshot": "x",
                    "alt_data_dashboard": "x",
                    "institutional_summary": "x",
                    "asset_classes_summary": "x",
                    "us_equities_summary": "x",
                    "thesis_tracker": "",
                    "portfolio_recommendations": "",
                    "actionable_summary": [],
                    "risk_radar": [],
                    "segment_freshness": {},
                }
            )

        with patch("digigraph.graph.research_agent.chat_completion", side_effect=fake):
            _synthesis_node(_seed_state_minimal("Why is XLE underperforming?"))

        assert "custom_prompt" in captured["text"]
        assert "XLE" in captured["text"]

    def test_custom_prompt_omitted_on_routine_run(self) -> None:
        from digiquant.olympus.atlas.phases.phase7_synthesis import _synthesis_node

        captured: dict[str, str] = {}

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            captured["text"] = inputs_part["text"]
            import json

            return json.dumps(
                {
                    "segment": "master-digest",
                    "date": "2026-04-26",
                    "bias": "neutral",
                    "headline": "test",
                    "material_findings": [],
                    "sources": [],
                    "notes": "",
                    "market_regime_snapshot": "x",
                    "alt_data_dashboard": "x",
                    "institutional_summary": "x",
                    "asset_classes_summary": "x",
                    "us_equities_summary": "x",
                    "thesis_tracker": "",
                    "portfolio_recommendations": "",
                    "actionable_summary": [],
                    "risk_radar": [],
                    "segment_freshness": {},
                }
            )

        with patch("digigraph.graph.research_agent.chat_completion", side_effect=fake):
            _synthesis_node(_seed_state_minimal())

        assert "custom_prompt" not in captured["text"]


# ─── Publish phase routing ──────────────────────────────────────────────────


def _state_with_digest(custom_prompt: str | None = None) -> AtlasResearchState:
    state = _seed_state_minimal(custom_prompt)
    state.run_id = UUID("00000000-0000-0000-0000-000000000abc")
    state.phase7_digest = {"market_regime_snapshot": "x", "us_equities_summary": "y"}
    return state


@pytest.mark.unit
class TestPublishCustomResearch:
    def test_custom_run_uses_custom_research_doc_type(self) -> None:
        client = FakeSupabaseClient()
        state = _state_with_digest("Drill into NVDA earnings.")
        node = build_publish_node(PublishDeps(client=client))

        node(state)

        digest_rows = [r for r in client.store["documents"] if r["doc_type"] == "Custom Research"]
        assert len(digest_rows) == 1
        assert digest_rows[0]["document_key"].startswith("custom-research/")
        assert "00000000" in digest_rows[0]["document_key"]
        assert digest_rows[0]["title"].startswith("Atlas Custom Research")

    def test_custom_run_skips_daily_snapshots(self) -> None:
        """One-off custom runs must not pollute the cadence time series."""
        client = FakeSupabaseClient()
        state = _state_with_digest("anything")
        node = build_publish_node(PublishDeps(client=client))

        node(state)

        assert "daily_snapshots" not in client.store

    def test_routine_run_uses_daily_digest_doc_type(self) -> None:
        """Backward-compat: when ``custom_prompt`` is None, behavior is unchanged."""
        client = FakeSupabaseClient()
        state = _state_with_digest()  # None custom_prompt
        node = build_publish_node(PublishDeps(client=client))

        node(state)

        digest_rows = [r for r in client.store["documents"] if r["doc_type"] == "Daily Digest"]
        assert len(digest_rows) == 1
        assert digest_rows[0]["document_key"] == "digest"
        # Routine baseline run still writes daily_snapshots.
        assert len(client.store["daily_snapshots"]) == 1

    def test_no_custom_research_row_when_digest_missing(self) -> None:
        """Defensive: if Phase 7 was skipped, no Custom Research row gets written."""
        client = FakeSupabaseClient()
        state = _state_with_digest("query")
        state.phase7_digest = None
        node = build_publish_node(PublishDeps(client=client))

        node(state)

        for row in client.store.get("documents", []):
            assert row["doc_type"] != "Custom Research"
        assert "daily_snapshots" not in client.store
