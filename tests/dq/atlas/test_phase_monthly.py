"""Isolated tests for the monthly-digest phase model-routing fix.

Regression guard for the bug reported by Copilot on PR #525:
  _monthly_node() was not passing phase_slug="monthly-digest" to
  run_research_agent(), so the monthly-digest config entry in
  model_modes.yaml was never consulted and the call fell through to
  get_model_for_mode() — reproducing the kimi-k2-thinking 403 path.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import patch

import pytest

from digiquant.olympus.atlas.phases.phase_monthly import MonthlyDigest, _monthly_node
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _minimal_state() -> AtlasResearchState:
    return AtlasResearchState(
        run_type="monthly",
        run_date=date(2026, 5, 1),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
    )


def _monthly_payload() -> str:
    return json.dumps(
        {
            "segment": "monthly-digest",
            "date": "2026-05-01",
            "bias": "neutral",
            "headline": "Month-end regime review",
            "material_findings": [],
            "sources": [],
            "notes": "",
            "market_regime_snapshot": "Stable",
            "alt_data_dashboard": "Neutral",
            "institutional_summary": "Flat",
            "asset_classes_summary": "Mixed",
            "us_equities_summary": "Flat",
            "thesis_tracker": "",
            "portfolio_recommendations": "",
            "actionable_summary": [],
            "risk_radar": [],
            "segment_freshness": {},
            "month_over_month_regime_delta": "",
        }
    )


# ─── Config layer ─────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMonthlyDigestModelConfig:
    def test_phase_slug_returns_pinned_model(self) -> None:
        """get_model_for_phase("monthly-digest") must return the pinned reasoning model.

        Pipeline cut over from the rate-limited Gemini/Ollama free tiers to paid
        xAI Grok (issues #569/#570/#572); monthly-digest is now pinned to grok-4.3.
        """
        from digigraph.llm import get_model_for_phase

        model = get_model_for_phase("monthly-digest")
        assert model == "xai/grok-4.3", (
            f"monthly-digest should be pinned to xai/grok-4.3, got {model!r}"
        )

    def test_phase_slug_not_none(self) -> None:
        """The config entry must not be missing (None triggers the 403 fallback)."""
        from digigraph.llm import get_model_for_phase

        assert get_model_for_phase("monthly-digest") is not None


# ─── Call-site routing ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMonthlyNodePassesPhaseSlug:
    def test_run_research_agent_called_with_phase_slug(self) -> None:
        """_monthly_node must pass phase_slug='monthly-digest' so the pinned model is used."""
        state = _minimal_state()

        # run_research_agent is imported lazily inside _monthly_node, so we patch
        # the function at its definition site so the lazy import picks up the mock.
        with patch(
            "digigraph.graph.research_agent.run_research_agent",
        ) as mock_rra:
            mock_rra.return_value = MonthlyDigest(
                segment="monthly-digest",
                date=date(2026, 5, 1),
                bias="neutral",
                headline="ok",
                market_regime_snapshot="",
                alt_data_dashboard="",
                institutional_summary="",
                asset_classes_summary="",
                us_equities_summary="",
            )
            _monthly_node(state)

        assert mock_rra.call_count == 1
        _, kwargs = mock_rra.call_args
        assert kwargs.get("phase_slug") == "monthly-digest", (
            f"Expected phase_slug='monthly-digest', got {kwargs.get('phase_slug')!r}. "
            "Without this the model_modes.yaml entry is never consulted."
        )

    def test_kimi_not_called_in_best_mode(self) -> None:
        """In best mode the pinned model must win; kimi-k2-thinking must NOT be called.

        Simulates the production failure: get_model_for_mode() would return
        kimi-k2-thinking in best mode, but phase_slug routing must intercept first.
        """
        state = _minimal_state()

        called_models: list[str] = []

        def fake_chat(model: str, *args: Any, **kwargs: Any) -> str:
            called_models.append(model)
            return _monthly_payload()

        with (
            # Simulate best mode returning kimi (the 403 path) to prove it's bypassed.
            patch("digigraph.llm._get_llm_mode", return_value="best"),
            patch(
                "digigraph.graph.research_agent.chat_completion",
                side_effect=fake_chat,
            ),
            patch(
                "digiquant.olympus.atlas.skills.load_skill",
                return_value="Monthly synthesis skill text",
            ),
        ):
            _monthly_node(state)

        assert called_models, "LLM must be called"
        for m in called_models:
            assert "kimi" not in m.lower(), (
                f"kimi-k2-thinking must not be selected in best mode; got {m!r}"
            )
        assert all(m == "xai/grok-4.3" for m in called_models), (
            f"Expected the pinned xai/grok-4.3 model via phase_slug; got {called_models}"
        )
