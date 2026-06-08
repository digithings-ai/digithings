from __future__ import annotations

import dataclasses
from datetime import date

import pytest

import digiquant.olympus.atlas.phases.phase3_macro as p3
from digiquant.olympus.atlas.phases import _node_factory
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState


def _state() -> AtlasResearchState:
    return AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 6, 8),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
    )


def _run_macro_node_capturing(monkeypatch, *, enabled: bool) -> dict:
    """Build the real macro node with its spec flags forced on, capturing the
    kwargs passed to run_research_agent."""
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1" if enabled else "0")
    _node_factory._atlas_data_client.cache_clear()
    # Avoid a real Supabase connection in the unit test.
    monkeypatch.setattr(_node_factory, "_atlas_data_client", object)

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
def test_node_passes_tools_and_search_when_enabled(monkeypatch):
    cap = _run_macro_node_capturing(monkeypatch, enabled=True)
    assert cap["tools"] is not None
    assert cap["execute_tool"] is not None
    assert cap["search_parameters"] is not None


@pytest.mark.unit
def test_node_passes_nothing_when_disabled(monkeypatch):
    cap = _run_macro_node_capturing(monkeypatch, enabled=False)
    assert cap["tools"] is None
    assert cap["execute_tool"] is None
    assert cap["search_parameters"] is None
