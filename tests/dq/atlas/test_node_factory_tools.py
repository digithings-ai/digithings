from __future__ import annotations

import dataclasses
from datetime import date

import pytest

import digiquant.olympus.atlas.data.web_grounding as wg
import digiquant.olympus.atlas.phases.phase3_macro as p3
from digiquant.olympus.atlas.phases import _node_factory
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState


def _state() -> AtlasResearchState:
    return AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 6, 8),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
    )


def _run_macro_node_capturing(monkeypatch, *, enabled: bool, grounding: dict | None) -> dict:
    """Build the real macro node with its spec flags forced on, capturing the
    kwargs passed to run_research_agent."""
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1" if enabled else "0")
    _node_factory._atlas_data_client.cache_clear()
    # Avoid a real Supabase connection + a real web_search call in the unit test.
    monkeypatch.setattr(_node_factory, "_atlas_data_client", object)
    monkeypatch.setattr(wg, "fetch_web_grounding", lambda **_k: grounding)

    # Force both flags on the spec the node closes over (frozen dataclass → replace).
    forced = dataclasses.replace(p3._SPEC, use_data_tools=True, live_search=True)
    monkeypatch.setattr(p3, "_SPEC", forced)
    node = p3.build_phase3().nodes[0].run

    captured: dict = {}

    def fake_rra(**kwargs):
        captured.update(kwargs)
        return forced.output_model.model_construct()

    # _node_factory imports run_research_agent by name; patch the bound symbol.
    monkeypatch.setattr(_node_factory, "run_research_agent", fake_rra)
    node(_state())
    return captured


@pytest.mark.unit
def test_node_passes_tools_and_injects_grounding_when_enabled(monkeypatch):
    grounding = {"summary": "- CPI hot", "sources": ["https://u"], "as_of": "2026-06-08"}
    cap = _run_macro_node_capturing(monkeypatch, enabled=True, grounding=grounding)
    assert cap["tools"] is not None
    assert cap["execute_tool"] is not None
    # web grounding is injected into phase_inputs, not passed as search_parameters.
    assert "search_parameters" not in cap
    assert cap["phase_inputs"]["web_grounding"] == grounding


@pytest.mark.unit
def test_node_passes_nothing_when_disabled(monkeypatch):
    cap = _run_macro_node_capturing(monkeypatch, enabled=False, grounding=None)
    assert cap["tools"] is None
    assert cap["execute_tool"] is None
    assert "web_grounding" not in cap["phase_inputs"]


@pytest.mark.unit
def test_node_omits_grounding_when_search_returns_none(monkeypatch):
    cap = _run_macro_node_capturing(monkeypatch, enabled=True, grounding=None)
    assert cap["tools"] is not None  # data tools still wired
    assert "web_grounding" not in cap["phase_inputs"]
